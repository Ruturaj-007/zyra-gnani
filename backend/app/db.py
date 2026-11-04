import os
from contextlib import contextmanager

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# current_checkpoint = the question_number the candidate should answer NEXT.
# It starts at 1. After question N is answered it becomes N+1.
# When there is no question N+1, status flips to 'completed'.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    interview_id       TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    candidate_id       TEXT NOT NULL,
    role               TEXT NOT NULL,
    level              TEXT NOT NULL,
    techstack          TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'in_progress'
                       CHECK (status IN ('in_progress', 'completed')),
    current_checkpoint INTEGER NOT NULL DEFAULT 1,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS interview_plans (
    interview_id    TEXT NOT NULL REFERENCES sessions(interview_id) ON DELETE CASCADE,
    question_number INTEGER NOT NULL,
    question_text   TEXT NOT NULL,
    difficulty      TEXT NOT NULL
                    CHECK (difficulty IN ('easy', 'medium', 'hard')),
    PRIMARY KEY (interview_id, question_number)
);

CREATE TABLE IF NOT EXISTS turns (
    interview_id      TEXT NOT NULL REFERENCES sessions(interview_id) ON DELETE CASCADE,
    turn_number       INTEGER NOT NULL,
    question          TEXT NOT NULL,
    answer_transcript TEXT NOT NULL,
    ai_reasoning      TEXT,
    score             INTEGER CHECK (score BETWEEN 0 AND 100),
    timestamp         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (interview_id, turn_number)
);

CREATE INDEX IF NOT EXISTS idx_sessions_candidate
    ON sessions (candidate_id, created_at DESC);
"""

pool: ConnectionPool | None = None


def open_pool() -> None:
    """Open the shared connection pool to Neon."""
    global pool
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing. Add it to backend/.env")
    pool = ConnectionPool(
        conninfo=DATABASE_URL,
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row},
        check=ConnectionPool.check_connection,  # revives connections after Neon idles
        open=False,
    )
    pool.open(wait=True, timeout=30)


def close_pool() -> None:
    if pool is not None:
        pool.close()


@contextmanager
def get_conn():
    """Borrow a connection. Commits on success, rolls back on error."""
    if pool is None:
        raise RuntimeError("Database pool is not open")
    with pool.connection() as conn:
        yield conn


def init_db() -> None:
    """Create the three tables if they don't exist yet."""
    with get_conn() as conn:
        conn.execute(SCHEMA_SQL)