import os
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Interviews are short: 3 questions by default, hard cap of 4.
MIN_QUESTIONS = 3
MAX_QUESTIONS = max(MIN_QUESTIONS, min(int(os.getenv("MAX_QUESTIONS", "4")), 4))
DEFAULT_QUESTIONS = 3

Difficulty = Literal["easy", "medium", "hard"]


# Voice route 1: POST /voice/start
class VoiceStartRequest(BaseModel):
    role: str
    level: str
    userid: str
    techstack: str = ""
    type: str = "technical"
    language: str = "english"
    amount: int = DEFAULT_QUESTIONS

    @field_validator("amount")
    @classmethod
    def cap_amount(cls, v: int) -> int:
        return max(MIN_QUESTIONS, min(v, MAX_QUESTIONS))

    @field_validator("role", "level", "userid", "techstack", "type", "language")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()


class VoiceStartResponse(BaseModel):
    interview_id: str
    language: str
    question_number: int
    total_questions: int
    question_text: str
    audio_base64: Optional[str] = None  # WAV from Timbre; None if TTS failed (UI shows text)
    tts_ms: Optional[int] = None


# Voice route 2: POST /voice/answer (multipart: audio file + form fields)
class VoiceAnswerResponse(BaseModel):
    # True when no speech was heard. The turn is NOT consumed; the candidate can retry.
    retry: bool = False
    transcript: str = ""
    interview_complete: bool = False
    question_number: Optional[int] = None  # number of the NEXT question, None when complete
    total_questions: int = 0
    next_question: str = ""
    audio_base64: Optional[str] = None
    stt_ms: Optional[int] = None
    llm_ms: Optional[int] = None
    tts_ms: Optional[int] = None


# Agent internals
class PlannedQuestion(BaseModel):
    question_number: int
    question_text: str
    difficulty: Difficulty


class Evaluation(BaseModel):
    """The agent's reasoning about one answer."""
    verdict: Literal["strong", "adequate", "weak"]
    score: int = Field(ge=0, le=100)  # average of the three metrics below
    technical_knowledge: int = Field(ge=0, le=100)
    problem_solving: int = Field(ge=0, le=100)
    communication_clarity: int = Field(ge=0, le=100)
    evidence_quote: str = ""
    improvement_tip: str = ""
    reasoning: str
    next_difficulty: Difficulty


class InterviewSummary(BaseModel):
    strengths: list[str] = []
    weaknesses: list[str] = []


# Resume (read-only durability proof)
class ResumeInterviewRequest(BaseModel):
    interview_id: str


class TurnOut(BaseModel):
    turn_number: int
    question: str
    answer_transcript: str
    ai_reasoning: Optional[str] = None
    score: Optional[int] = None
    technical_knowledge: Optional[int] = None
    problem_solving: Optional[int] = None
    communication_clarity: Optional[int] = None
    evidence_quote: Optional[str] = None
    improvement_tip: Optional[str] = None
    stt_ms: Optional[int] = None
    llm_ms: Optional[int] = None
    tts_ms: Optional[int] = None
    timestamp: datetime


class ResumeInterviewResponse(BaseModel):
    interview_id: str
    status: str
    current_checkpoint: int
    turn_history: list[TurnOut]
    next_question: Optional[str] = None  # None when nothing is left to ask
    interview_complete: bool


# Trace / results: GET /trace/{interview_id}
class PlanItemOut(BaseModel):
    question_number: int
    question_text: str
    difficulty: Difficulty


class MetricAverages(BaseModel):
    technical_knowledge: Optional[int] = None
    problem_solving: Optional[int] = None
    communication_clarity: Optional[int] = None


class LatencyAverages(BaseModel):
    """Averages of MEASURED per-turn latencies, in milliseconds. None if nothing measured."""
    stt_ms: Optional[int] = None
    llm_ms: Optional[int] = None
    tts_ms: Optional[int] = None


class TraceResponse(BaseModel):
    interview_id: str
    candidate_id: str
    role: str
    level: str
    techstack: str
    language: str = "english"
    status: str
    current_checkpoint: int
    created_at: datetime
    plan: list[PlanItemOut]
    turns: list[TurnOut]
    average_score: Optional[float] = None  # None until the first answer is scored
    overall_score: Optional[int] = None  # set at completion
    summary: Optional[InterviewSummary] = None  # set at completion
    metric_averages: MetricAverages = MetricAverages()
    latency_averages: LatencyAverages = LatencyAverages()