"""Core interview logic, shared by the voice routes.

The database checkpoint is the source of truth. Every call is idempotent:
the session row is locked, and an answer that is already stored is never scored twice.
"""
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException

from app import agent, db
from app.schemas import PlannedQuestion

log = logging.getLogger("zyra.core")


@dataclass
class StartResult:
    interview_id: str
    question_text: str
    total: int


@dataclass
class AnswerResult:
    next_question: str  # "" when the interview is complete
    next_number: Optional[int]  # None when complete
    complete: bool
    total: int
    llm_ms: Optional[int] = None  # measured time of scoring + replanning (+ summary at the end)
    duplicate: bool = False


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


# START: plan 3-4 questions, save session + plan together
def create_interview(
    role: str,
    level: str,
    techstack: str,
    interview_type: str,
    amount: int,
    language: str,
    candidate_id: str,
) -> StartResult:
    plan: list[PlannedQuestion] = agent.plan_interview(
        role=role,
        level=level,
        techstack=techstack,
        interview_type=interview_type,
        amount=amount,
        language=language,
    )

    with db.get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO sessions (candidate_id, role, level, techstack, language, status, current_checkpoint)
            VALUES (%s, %s, %s, %s, %s, 'in_progress', 1)
            RETURNING interview_id
            """,
            (candidate_id, role, level, techstack, language),
        ).fetchone()
        interview_id = row["interview_id"]

        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO interview_plans (interview_id, question_number, question_text, difficulty)
                VALUES (%s, %s, %s, %s)
                """,
                [(interview_id, q.question_number, q.question_text, q.difficulty) for q in plan],
            )

    log.info("interview %s created for %s (%s, %d questions)", interview_id, candidate_id, language, len(plan))
    return StartResult(interview_id=interview_id, question_text=plan[0].question_text, total=len(plan))


# LOOKUP: what the voice route needs before it can transcribe (language, skills, checkpoint)
def get_session_info(interview_id: str) -> dict:
    with db.get_conn() as conn:
        session = conn.execute(
            "SELECT interview_id, language, techstack, status, current_checkpoint "
            "FROM sessions WHERE interview_id = %s",
            (interview_id,),
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Interview not found")
        total = conn.execute(
            "SELECT count(*) AS n FROM interview_plans WHERE interview_id = %s", (interview_id,)
        ).fetchone()["n"]
    return {**session, "total": total}


def get_question(interview_id: str, question_number: int) -> Optional[str]:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT question_text FROM interview_plans WHERE interview_id = %s AND question_number = %s",
            (interview_id, question_number),
        ).fetchone()
    return row["question_text"] if row else None


# ANSWER: observe -> reason -> replan -> persist -> checkpoint
def submit_answer_core(
    interview_id: str,
    question_number: int,
    answer_transcript: str,
    stt_ms: Optional[int] = None,
) -> AnswerResult:
    with db.get_conn() as conn:
        # Lock the session row so a duplicate or retried call can't be processed twice
        session = conn.execute(
            "SELECT * FROM sessions WHERE interview_id = %s FOR UPDATE", (interview_id,)
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Interview not found")

        plan = conn.execute(
            """
            SELECT question_number, question_text, difficulty
            FROM interview_plans WHERE interview_id = %s ORDER BY question_number
            """,
            (interview_id,),
        ).fetchall()
        if not plan:
            raise HTTPException(status_code=409, detail="Interview has no planned questions")

        total = len(plan)
        by_number = {p["question_number"]: p for p in plan}
        checkpoint = session["current_checkpoint"]
        language = session["language"]

        # Already finished: repeat the closing signal instead of failing
        if session["status"] == "completed":
            return AnswerResult("", None, True, total, duplicate=True)

        # Duplicate call for an answer we already stored: do not re-score, just repeat the result
        already = conn.execute(
            "SELECT 1 FROM turns WHERE interview_id = %s AND turn_number = %s",
            (interview_id, question_number),
        ).fetchone()
        if already:
            log.info("duplicate submit for %s q%s ignored", interview_id, question_number)
            nxt = by_number.get(checkpoint)
            if nxt is None:
                return AnswerResult("", None, True, total, duplicate=True)
            return AnswerResult(nxt["question_text"], checkpoint, False, total, duplicate=True)

        # The database knows which question is really being answered, so the checkpoint wins
        if question_number != checkpoint:
            log.warning(
                "question_number %s != checkpoint %s for %s; trusting checkpoint",
                question_number, checkpoint, interview_id,
            )
        current = by_number.get(checkpoint)
        if current is None:
            raise HTTPException(status_code=409, detail="No question is waiting for an answer")

        llm_started = time.perf_counter()

        # REASON: three metrics, evidence, tip, and what difficulty comes next
        ev = agent.evaluate_answer(
            role=session["role"],
            level=session["level"],
            question=current["question_text"],
            difficulty=current["difficulty"],
            answer=answer_transcript,
            language=language,
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
                    previous_answer=answer_transcript,
                    planned_question=nxt["question_text"],
                    target_difficulty=ev.next_difficulty,
                    language=language,
                )
                conn.execute(
                    """
                    UPDATE interview_plans SET question_text = %s, difficulty = %s
                    WHERE interview_id = %s AND question_number = %s
                    """,
                    (next_question, ev.next_difficulty, interview_id, checkpoint + 1),
                )
                reasoning += f" Next question changed from {nxt['difficulty']} to {ev.next_difficulty}."
            else:
                reasoning += f" Next difficulty stays {ev.next_difficulty}."

        # PERSIST: the turn (llm_ms is patched below once the summary is done, if needed)
        conn.execute(
            """
            INSERT INTO turns (
                interview_id, turn_number, question, answer_transcript, ai_reasoning, score,
                technical_knowledge, problem_solving, communication_clarity,
                evidence_quote, improvement_tip, stt_ms, llm_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                interview_id,
                checkpoint,
                current["question_text"],
                answer_transcript,
                reasoning,
                ev.score,
                ev.technical_knowledge,
                ev.problem_solving,
                ev.communication_clarity,
                ev.evidence_quote,
                ev.improvement_tip,
                stt_ms,
                _ms(llm_started),
            ),
        )

        # CHECKPOINT: move forward, or close the interview after the last question
        if is_last:
            turns = conn.execute(
                """
                SELECT turn_number, question, answer_transcript, score,
                       technical_knowledge, problem_solving, communication_clarity
                FROM turns WHERE interview_id = %s ORDER BY turn_number
                """,
                (interview_id,),
            ).fetchall()
            overall, summary = agent.summarize_interview(session["role"], session["level"], turns)
            llm_total = _ms(llm_started)  # scoring + summary, all measured
            conn.execute(
                "UPDATE turns SET llm_ms = %s WHERE interview_id = %s AND turn_number = %s",
                (llm_total, interview_id, checkpoint),
            )
            conn.execute(
                """
                UPDATE sessions
                SET status = 'completed', current_checkpoint = %s, overall_score = %s, summary = %s
                WHERE interview_id = %s
                """,
                (total + 1, overall, summary.model_dump_json(), interview_id),
            )
            return AnswerResult("", None, True, total, llm_ms=llm_total)

        conn.execute(
            "UPDATE sessions SET current_checkpoint = %s WHERE interview_id = %s",
            (checkpoint + 1, interview_id),
        )
        return AnswerResult(next_question, checkpoint + 1, False, total, llm_ms=_ms(llm_started))


# LATENCY: the text-to-speech time is only known after the turn is saved, so it is patched in
def record_tts_ms(interview_id: str, turn_number: int, tts_ms: int) -> None:
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE turns SET tts_ms = %s WHERE interview_id = %s AND turn_number = %s",
            (tts_ms, interview_id, turn_number),
        )