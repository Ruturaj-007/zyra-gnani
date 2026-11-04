import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.routes import resume_interview, trace, voice

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
    title="Zyra on Gnani",
    description="Agentic AI voice interviewer using Gnani Prisma (STT) and Timbre (TTS)",
    version="0.2.0",
    lifespan=lifespan,
)

# Let the Next.js frontend call this API from the browser (local and deployed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Voice loop: POST /voice/start, POST /voice/answer
app.include_router(voice.router)

# Durability proof (read-only) and results data for the UI
app.include_router(resume_interview.router)
app.include_router(trace.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "zyra-on-gnani"}


@app.get("/health/db")
def health_db():
    """Proves the Neon connection works and the tables exist."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        ).fetchall()
    return {"status": "ok", "tables": [r["table_name"] for r in rows]}