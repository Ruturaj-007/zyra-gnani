from typing import Optional

from fastapi import APIRouter, HTTPException

from app import db
from app.schemas import (
    InterviewSummary,
    LatencyAverages,
    MetricAverages,
    TraceResponse,
)

router = APIRouter(prefix="/trace", tags=["trace"])


def _avg(values: list[Optional[int]]) -> Optional[int]:
    """Average of the values that were actually measured. None if there are none."""
    real = [v for v in values if v is not None]
    return int(round(sum(real) / len(real))) if real else None


def _parse_summary(raw: Optional[str]) -> Optional[InterviewSummary]:
    if not raw:
        return None
    try:
        return InterviewSummary.model_validate_json(raw)
    except Exception:
        return None


@router.get("/{interview_id}", response_model=TraceResponse)
def get_trace(interview_id: str) -> TraceResponse:
    """Everything the results page needs: plan, turns, metrics, summary and measured latency."""
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
            SELECT turn_number, question, answer_transcript, ai_reasoning, score,
                   technical_knowledge, problem_solving, communication_clarity,
                   evidence_quote, improvement_tip, stt_ms, llm_ms, tts_ms, timestamp
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
        language=session["language"],
        status=session["status"],
        current_checkpoint=session["current_checkpoint"],
        created_at=session["created_at"],
        plan=plan,
        turns=turns,
        average_score=average,
        overall_score=session["overall_score"],
        summary=_parse_summary(session["summary"]),
        metric_averages=MetricAverages(
            technical_knowledge=_avg([t["technical_knowledge"] for t in turns]),
            problem_solving=_avg([t["problem_solving"] for t in turns]),
            communication_clarity=_avg([t["communication_clarity"] for t in turns]),
        ),
        latency_averages=LatencyAverages(
            stt_ms=_avg([t["stt_ms"] for t in turns]),
            llm_ms=_avg([t["llm_ms"] for t in turns]),
            tts_ms=_avg([t["tts_ms"] for t in turns]),
        ),
    )