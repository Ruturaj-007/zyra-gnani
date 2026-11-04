from typing import Optional

from fastapi import APIRouter, HTTPException

from app import db
from app.schemas import LatestInterviewResponse, TraceResponse

router = APIRouter(prefix="/trace", tags=["trace"])


# NOTE: /latest must be declared BEFORE /{interview_id}, otherwise FastAPI
# would treat the word "latest" as an interview id.
@router.get("/latest", response_model=LatestInterviewResponse)
def latest_interview(candidate_id: str) -> LatestInterviewResponse:
    """Find the newest interview for a candidate.

    The voice agent creates the interview server-side during the call, so the
    browser doesn't know its id. After the call ends, the UI asks for it here.
    """
    with db.get_conn() as conn:
        row = conn.execute(
            """
            SELECT interview_id FROM sessions
            WHERE candidate_id = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (candidate_id,),
        ).fetchone()
    return LatestInterviewResponse(interview_id=row["interview_id"] if row else None)


@router.get("/{interview_id}", response_model=TraceResponse)
def get_trace(interview_id: str) -> TraceResponse:
    """Everything the timeline UI needs: the plan, each turn, the AI's reasoning and the scores."""
    with db.get_conn() as conn:
        session = conn.execute(
            "SELECT * FROM sessions WHERE interview_id = %s", (interview_id,)
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

        turns = conn.execute(
            """
            SELECT turn_number, question, answer_transcript, ai_reasoning, score, timestamp
            FROM turns WHERE interview_id = %s ORDER BY turn_number
            """,
            (interview_id,),
        ).fetchall()

    scores = [t["score"] for t in turns if t["score"] is not None]
    average: Optional[float] = round(sum(scores) / len(scores), 1) if scores else None

    return TraceResponse(
        interview_id=session["interview_id"],
        candidate_id=session["candidate_id"],
        role=session["role"],
        level=session["level"],
        techstack=session["techstack"],
        status=session["status"],
        current_checkpoint=session["current_checkpoint"],
        created_at=session["created_at"],
        plan=plan,
        turns=turns,
        average_score=average,
    )