import logging

from fastapi import APIRouter, HTTPException

from app import agent, db
from app.schemas import SubmitAnswerRequest, SubmitAnswerResponse

log = logging.getLogger("zyra.submit")

router = APIRouter(prefix="/tools", tags=["vapi-tools"])


def _finished() -> SubmitAnswerResponse:
    return SubmitAnswerResponse(next_question="", interview_complete=True)


@router.post("/submit-answer", response_model=SubmitAnswerResponse)
def submit_answer(body: SubmitAnswerRequest) -> SubmitAnswerResponse:
    """Vapi tool 2: the agentic loop.

    OBSERVE the answer -> REASON about its quality -> REPLAN the next question
    -> PERSIST the turn and move the checkpoint -> tell Riley what to say next.

    Plain `def` on purpose: FastAPI runs it in a worker thread, so blocking
    Groq and database calls don't freeze the server.
    """
    with db.get_conn() as conn:
        # Lock the session row so a duplicate or retried tool call can't be processed twice
        session = conn.execute(
            "SELECT * FROM sessions WHERE interview_id = %s FOR UPDATE",
            (body.interview_id,),
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Interview not found")

        plan = conn.execute(
            """
            SELECT question_number, question_text, difficulty
            FROM interview_plans WHERE interview_id = %s ORDER BY question_number
            """,
            (body.interview_id,),
        ).fetchall()
        if not plan:
            raise HTTPException(status_code=409, detail="Interview has no planned questions")

        total = len(plan)
        by_number = {p["question_number"]: p for p in plan}
        checkpoint = session["current_checkpoint"]

        # Already finished: repeat the closing signal instead of failing
        if session["status"] == "completed":
            return _finished()

        # Duplicate call for an answer we already stored: do not re-score, just repeat the result
        already = conn.execute(
            "SELECT 1 FROM turns WHERE interview_id = %s AND turn_number = %s",
            (body.interview_id, body.question_number),
        ).fetchone()
        if already:
            log.info("duplicate submit for %s q%s ignored", body.interview_id, body.question_number)
            nxt = by_number.get(checkpoint)
            if nxt is None:
                return _finished()
            return SubmitAnswerResponse(next_question=nxt["question_text"], interview_complete=False)

        # The database knows which question is really being answered. A voice LLM can send
        # a wrong number, so the checkpoint is the source of truth.
        if body.question_number != checkpoint:
            log.warning(
                "question_number %s != checkpoint %s for %s; trusting checkpoint",
                body.question_number, checkpoint, body.interview_id,
            )
        current = by_number.get(checkpoint)
        if current is None:
            raise HTTPException(status_code=409, detail="No question is waiting for an answer")

        # REASON: how good was the answer, and what difficulty should come next?
        ev = agent.evaluate_answer(
            role=session["role"],
            level=session["level"],
            question=current["question_text"],
            difficulty=current["difficulty"],
            answer=body.answer_transcript,
        )
        reasoning = f"{ev.verdict.upper()}: {ev.reasoning}"

        is_last = checkpoint >= total
        next_question = ""

        if not is_last:
            nxt = by_number[checkpoint + 1]
            next_question = nxt["question_text"]

            # REPLAN: only rewrite the next question if the difficulty needs to change
            if ev.next_difficulty != nxt["difficulty"]:
                next_question = agent.adapt_question(
                    role=session["role"],
                    level=session["level"],
                    techstack=session["techstack"],
                    previous_question=current["question_text"],
                    previous_answer=body.answer_transcript,
                    planned_question=nxt["question_text"],
                    target_difficulty=ev.next_difficulty,
                )
                conn.execute(
                    """
                    UPDATE interview_plans SET question_text = %s, difficulty = %s
                    WHERE interview_id = %s AND question_number = %s
                    """,
                    (next_question, ev.next_difficulty, body.interview_id, checkpoint + 1),
                )
                reasoning += f" Next question changed from {nxt['difficulty']} to {ev.next_difficulty}."
            else:
                reasoning += f" Next difficulty stays {ev.next_difficulty}."

        # PERSIST: the turn, with the agent's reasoning so the trace timeline can show it
        conn.execute(
            """
            INSERT INTO turns (interview_id, turn_number, question, answer_transcript, ai_reasoning, score)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                body.interview_id,
                checkpoint,
                current["question_text"],
                body.answer_transcript,
                reasoning,
                ev.score,
            ),
        )

        # CHECKPOINT: move forward, or close the interview after the last question
        if is_last:
            conn.execute(
                "UPDATE sessions SET status = 'completed', current_checkpoint = %s WHERE interview_id = %s",
                (total + 1, body.interview_id),
            )
            return _finished()

        conn.execute(
            "UPDATE sessions SET current_checkpoint = %s WHERE interview_id = %s",
            (checkpoint + 1, body.interview_id),
        )
        return SubmitAnswerResponse(
            next_question=next_question, interview_complete=False
        )