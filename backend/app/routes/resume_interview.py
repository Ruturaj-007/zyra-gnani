from fastapi import APIRouter, HTTPException

from app import db
from app.schemas import ResumeInterviewRequest, ResumeInterviewResponse

router = APIRouter(prefix="/tools", tags=["vapi-tools"])


@router.post("/resume-interview", response_model=ResumeInterviewResponse)
def resume_interview(body: ResumeInterviewRequest) -> ResumeInterviewResponse:
    """Vapi tool 3: prove durability.

    Everything lives in Postgres, not in server memory, so an interview can be
    picked up after a dropped call or a server restart. This route only reads;
    it is called manually (Postman/curl) in the demo, not live by Riley.
    """
    with db.get_conn() as conn:
        session = conn.execute(
            "SELECT interview_id, status, current_checkpoint FROM sessions WHERE interview_id = %s",
            (body.interview_id,),
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Interview not found")

        turns = conn.execute(
            """
            SELECT turn_number, question, answer_transcript, ai_reasoning, score, timestamp
            FROM turns WHERE interview_id = %s ORDER BY turn_number
            """,
            (body.interview_id,),
        ).fetchall()

        completed = session["status"] == "completed"
        next_question = None

        if not completed:
            row = conn.execute(
                """
                SELECT question_text FROM interview_plans
                WHERE interview_id = %s AND question_number = %s
                """,
                (body.interview_id, session["current_checkpoint"]),
            ).fetchone()
            next_question = row["question_text"] if row else None

    return ResumeInterviewResponse(
        interview_id=session["interview_id"],
        status=session["status"],
        current_checkpoint=session["current_checkpoint"],
        turn_history=turns,
        next_question=next_question,
        interview_complete=completed,
    )