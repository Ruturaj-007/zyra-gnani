import os
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Interviews are deliberately short (3-4 questions) to control Vapi voice-minute cost.
MIN_QUESTIONS = 3
MAX_QUESTIONS = min(int(os.getenv("MAX_QUESTIONS", "4")), 4)

Difficulty = Literal["easy", "medium", "hard"]


# Tool 1: generateInterview
class GenerateInterviewRequest(BaseModel):
    role: str
    type: str = "technical"
    level: str
    amount: int = MAX_QUESTIONS
    userid: str
    techstack: str = ""

    @field_validator("amount")
    @classmethod
    def cap_amount(cls, v: int) -> int:
        # Whatever the voice agent asks for, force it into the 3-4 range
        return max(MIN_QUESTIONS, min(v, MAX_QUESTIONS))

    @field_validator("role", "type", "level", "userid", "techstack")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()


class GenerateInterviewResponse(BaseModel):
    interview_id: str
    first_question: str


# Tool 2: submitAnswer
class SubmitAnswerRequest(BaseModel):
    interview_id: str
    question_number: int = Field(ge=1)
    answer_transcript: str


class SubmitAnswerResponse(BaseModel):
    # Empty string when the interview is complete
    next_question: str
    interview_complete: bool


# Tool 3: resumeInterview (called manually via Postman/curl in the demo)
class ResumeInterviewRequest(BaseModel):
    interview_id: str


class TurnOut(BaseModel):
    turn_number: int
    question: str
    answer_transcript: str
    ai_reasoning: Optional[str] = None
    score: Optional[int] = None
    timestamp: datetime


class ResumeInterviewResponse(BaseModel):
    interview_id: str
    status: str
    current_checkpoint: int
    turn_history: list[TurnOut]
    next_question: Optional[str] = None  # None when nothing is left to ask
    interview_complete: bool


# Agent internals (used by agent.py, never sent to Vapi)
class PlannedQuestion(BaseModel):
    question_number: int
    question_text: str
    difficulty: Difficulty


class Evaluation(BaseModel):
    """The agent's reasoning about one answer."""
    verdict: Literal["strong", "adequate", "weak"]
    score: int = Field(ge=0, le=100)
    reasoning: str
    next_difficulty: Difficulty


# Trace timeline: GET /trace/{interview_id}
class PlanItemOut(BaseModel):
    question_number: int
    question_text: str
    difficulty: Difficulty


class TraceResponse(BaseModel):
    interview_id: str
    candidate_id: str
    role: str
    level: str
    techstack: str
    status: str
    current_checkpoint: int
    created_at: datetime
    plan: list[PlanItemOut]
    turns: list[TurnOut]
    average_score: Optional[float] = None  # None until the first answer is scored


class LatestInterviewResponse(BaseModel):
    """For the UI to find the interview that was just created during a call."""
    interview_id: Optional[str] = None