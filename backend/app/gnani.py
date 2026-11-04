"""Thin client for the two Gnani AI calls Zyra needs.

Speech to text:  Prisma v2.5  POST https://api.vachana.ai/stt/v3  (multipart, WAV in)
Text to speech:  Timbre       POST https://api.vachana.ai/api/v1/tts/inference  (JSON in, WAV out)
Auth header on both: X-API-Key-ID. The key lives only on the backend.
"""
import json
import logging
import os
import threading
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("zyra.gnani")

BASE_URL = "https://api.vachana.ai"
STT_URL = f"{BASE_URL}/stt/v3"
TTS_URL = f"{BASE_URL}/api/v1/tts/inference"

# Optional overrides. Defaults are what the docs describe for Timbre v3.0.
TTS_MODEL = os.getenv("GNANI_TTS_MODEL", "timbre-v3.0")
TTS_VOICE = os.getenv("GNANI_TTS_VOICE", "Shivani")

# Questions are kept short; this is a safety cut-off for one TTS request.
MAX_TTS_CHARS = 300

# UI language -> (label, STT language_code, TTS language).
# Hinglish: the STT docs say en-IN accepts mixed English-Hindi audio and answers in Latin script.
LANGUAGES: dict[str, dict[str, str]] = {
    "english": {"label": "English", "stt": "en-IN", "tts": "en-IN"},
    "hindi": {"label": "Hindi", "stt": "hi-IN", "tts": "hi-IN"},
    "hinglish": {"label": "Hinglish", "stt": "en-IN", "tts": "hi-en"},
    "marathi": {"label": "Marathi", "stt": "mr-IN", "tts": "mr-IN"},
}
DEFAULT_LANGUAGE = "english"

# The account may allow only one active request at a time, so Gnani calls go one by one.
_lock = threading.Lock()


class GnaniError(Exception):
    """Raised when a Gnani call fails. The message is safe to show in logs."""


def _headers() -> dict[str, str]:
    key = os.getenv("GNANI_API_KEY")
    if not key:
        raise GnaniError("GNANI_API_KEY is missing. Add it to backend/.env")
    return {"X-API-Key-ID": key}


def normalize_language(language: str | None) -> str:
    key = (language or DEFAULT_LANGUAGE).strip().lower()
    return key if key in LANGUAGES else DEFAULT_LANGUAGE


def clean_keyterms(skills: str, limit: int = 100) -> list[str]:
    """Turn 'FastAPI, Node.js, PostgreSQL' into words Prisma v2.5 accepts.

    The API wants single words made of letters only. If ONE entry is invalid it
    ignores the whole list, so we clean everything before sending.
    """
    words: list[str] = []
    seen: set[str] = set()
    token = ""
    for ch in (skills or "") + " ":
        if ch.isalpha():
            token += ch
            continue
        if len(token) >= 3 and token.lower() not in seen:
            seen.add(token.lower())
            words.append(token)
        token = ""
    return words[:limit]


def _post_with_retry(send) -> httpx.Response:
    """Run one HTTP call. Retry once after a short wait if Gnani says 429 (rate limited)."""
    with _lock:
        resp = send()
        if resp.status_code == 429:
            log.warning("Gnani returned 429, retrying once")
            time.sleep(1.5)
            resp = send()
        return resp


def transcribe(wav_bytes: bytes, language: str, skills: str = "") -> tuple[str, int]:
    """Speech to text. Returns (transcript, measured_latency_ms)."""
    if not wav_bytes:
        raise GnaniError("No audio received")

    lang = LANGUAGES[normalize_language(language)]
    data: dict[str, str] = {"language_code": lang["stt"], "format": "verbatim"}

    # Word boosting from the candidate's skills (Prisma v2.5: bias_list + bias_score)
    keyterms = clean_keyterms(skills)
    if keyterms:
        data["bias_list"] = json.dumps(keyterms, ensure_ascii=False)
        data["bias_score"] = "1.0"

    def send() -> httpx.Response:
        return httpx.post(
            STT_URL,
            headers=_headers(),
            files={"audio_file": ("answer.wav", wav_bytes, "audio/wav")},
            data=data,
            timeout=30.0,
        )

    started = time.perf_counter()
    try:
        resp = _post_with_retry(send)
    except httpx.HTTPError as exc:
        raise GnaniError(f"STT request failed: {exc}") from exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    if resp.status_code != 200:
        raise GnaniError(f"STT HTTP {resp.status_code}: {resp.text[:300]}")

    body = resp.json()
    if not body.get("success", True):
        raise GnaniError(f"STT error: {str(body.get('error'))[:300]}")

    # An empty transcript is not an error; the caller decides what to do with it.
    return str(body.get("transcript", "")).strip(), latency_ms


def synthesize(text: str, language: str) -> tuple[bytes, int]:
    """Text to speech. Returns (wav_bytes, measured_latency_ms)."""
    text = (text or "").strip()
    if not text:
        raise GnaniError("Nothing to speak")
    if len(text) > MAX_TTS_CHARS:
        text = text[:MAX_TTS_CHARS].rsplit(" ", 1)[0]

    lang = LANGUAGES[normalize_language(language)]
    payload = {
        "text": text,
        "voice": TTS_VOICE,
        "model": TTS_MODEL,
        "language": lang["tts"],
        "speed": 1.0,
        "audio_config": {
            "sample_rate": 24000,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
    }

    def send() -> httpx.Response:
        return httpx.post(
            TTS_URL,
            headers={**_headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=30.0,
        )

    started = time.perf_counter()
    try:
        resp = _post_with_retry(send)
    except httpx.HTTPError as exc:
        raise GnaniError(f"TTS request failed: {exc}") from exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    if resp.status_code != 200:
        raise GnaniError(f"TTS HTTP {resp.status_code}: {resp.text[:300]}")
    if not resp.content:
        raise GnaniError("TTS returned empty audio")

    return resp.content, latency_ms