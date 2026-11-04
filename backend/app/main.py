import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.routes import generate_interview, resume_interview, submit_answer, trace

load_dotenv()


def _allowed_origins() -> list[str]:
    """FRONTEND_ORIGIN can hold several origins separated by commas."""
    raw = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    # Trim spaces and any trailing slash, because browsers send origins without one
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.open_pool()
    db.init_db()
    yield
    db.close_pool()


app = FastAPI(
    title="Zyra.ai",
    description="Agentic AI voice interview platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Let the Next.js frontend call this API from the browser (local and deployed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Vapi tool routes
app.include_router(generate_interview.router)
app.include_router(submit_answer.router)
app.include_router(resume_interview.router)

# Trace routes for the timeline UI
app.include_router(trace.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "zyra.ai"}


@app.get("/health/db")
def health_db():
    """Proves the Neon connection works and the tables exist."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        ).fetchall()
    return {"status": "ok", "tables": [r["table_name"] for r in rows]}