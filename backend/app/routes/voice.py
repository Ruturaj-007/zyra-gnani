import base64
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app import gnani, interview_core
from app.schemas import (
    VoiceAnswerResponse,
    VoiceStartRequest,
    VoiceStartResponse,
)

log = logging.getLogger("zyra.voice")

router = APIRouter(prefix="/voice", tags=["voice"])

# 28 s of 16 kHz mono 16-bit WAV is about 0.9 MB, so 3 MB is a generous ceiling
MAX_AUDIO_BYTES = 3 * 1024 * 1024


def _speak(text: str, language: str) -> tuple[Optional[str], Optional[int]]:
    """Text to speech. If Timbre fails the interview goes on: the UI still shows the text."""
    try:
        wav, ms = gnani.synthesize(text, language)
        return base64.b64encode(wav).decode("ascii"), ms
    except gnani.GnaniError as exc:
        log.warning("TTS failed, continuing without audio: %s", exc)
        return None, None


# Plain `def` on purpose: FastAPI runs these in worker threads, so blocking calls don't freeze the server.
@router.post("/start", response_model=VoiceStartResponse)
def voice_start(body: VoiceStartRequest) -> VoiceStartResponse:
    """Plan the interview, save it, and return the first question as text plus Timbre audio."""
    language = gnani.normalize_language(body.language)
    result = interview_core.create_interview(
        role=body.role,
        level=body.level,
        techstack=body.techstack,
        interview_type=body.type,
        amount=body.amount,
        language=language,
        candidate_id=body.userid,
    )
    audio_b64, tts_ms = _speak(result.question_text, language)
    return VoiceStartResponse(
        interview_id=result.interview_id,
        language=language,
        question_number=1,
        total_questions=result.total,
        question_text=result.question_text,
        audio_base64=audio_b64,
        tts_ms=tts_ms,
    )


@router.post("/answer", response_model=VoiceAnswerResponse)
def voice_answer(
    interview_id: str = Form(...),
    question_number: int = Form(1),
    audio: UploadFile = File(...),
) -> VoiceAnswerResponse:
    """One voice turn: Prisma transcribes, the core logic scores and picks the next question, Timbre speaks it."""
    info = interview_core.get_session_info(interview_id)
    total = info["total"]

    if info["status"] == "completed":
        return VoiceAnswerResponse(interview_complete=True, total_questions=total)

    wav = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(wav) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio is too large")

    # SPEECH TO TEXT (Prisma v2.5), with the candidate's skills as word-boost hints
    try:
        transcript, stt_ms = gnani.transcribe(wav, info["language"], info["techstack"])
    except gnani.GnaniError as exc:
        log.error("STT failed for %s: %s", interview_id, exc)
        raise HTTPException(status_code=502, detail="Speech recognition failed. Please try again.")

    # Nothing heard: do NOT use up the question, let the candidate try again
    if not transcript.strip():
        return VoiceAnswerResponse(retry=True, total_questions=total, stt_ms=stt_ms)

    # SCORE + NEXT QUESTION: the same core logic, DB checkpoint is the truth
    checkpoint = info["current_checkpoint"]
    result = interview_core.submit_answer_core(
        interview_id=interview_id,
        question_number=question_number,
        answer_transcript=transcript,
        stt_ms=stt_ms,
    )

    # TEXT TO SPEECH (Timbre) for the next question; its time is saved on the turn just answered
    audio_b64: Optional[str] = None
    tts_ms: Optional[int] = None
    if not result.complete:
        audio_b64, tts_ms = _speak(result.next_question, info["language"])
        if tts_ms is not None and not result.duplicate:
            interview_core.record_tts_ms(interview_id, checkpoint, tts_ms)

    return VoiceAnswerResponse(
        transcript=transcript,
        interview_complete=result.complete,
        question_number=result.next_number,
        total_questions=result.total,
        next_question=result.next_question,
        audio_base64=audio_b64,
        stt_ms=stt_ms,
        llm_ms=result.llm_ms,
        tts_ms=tts_ms,
    )