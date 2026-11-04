import logging

from fastapi import APIRouter

from app import agent, db
from app.schemas import GenerateInterviewRequest, GenerateInterviewResponse

log = logging.getLogger("zyra.generate")

router = APIRouter(prefix="/tools", tags=["vapi-tools"])


@router.post("/generate-interview", response_model=GenerateInterviewResponse)
def generate_interview(body: GenerateInterviewRequest) -> GenerateInterviewResponse:
    """Vapi tool 1: plan a short interview, save it, return the first question.

    This is a plain `def` (not async) on purpose: FastAPI runs it in a worker
    thread, so the blocking Groq and database calls don't freeze the server.
    """
    # PLAN: 3-4 questions with escalating difficulty (amount is already capped by the schema)
    plan = agent.plan_interview(
        role=body.role,
        level=body.level,
        techstack=body.techstack,
        interview_type=body.type,
        amount=body.amount,
    )

    # PERSIST: session + plan are written together, so we never keep a half-created interview
    with db.get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO sessions (candidate_id, role, level, techstack, status, current_checkpoint)
            VALUES (%s, %s, %s, %s, 'in_progress', 1)
            RETURNING interview_id
            """,
            (body.userid, body.role, body.level, body.techstack),
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

    log.info("interview %s created for %s with %d questions", interview_id, body.userid, len(plan))

    return GenerateInterviewResponse(
        interview_id=interview_id,
        first_question=plan[0].question_text,
    )