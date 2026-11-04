"""Real-audio test against the running server. Uses Timbre to 'speak' answers, Prisma to hear them."""
import io
import wave

import httpx

from app import gnani

API = "http://localhost:8000"
LANG = "english"  # try "hindi" or "hinglish" on later runs

ANSWER_TEXT = {
    "english": "I would start by explaining the basic idea, then give an example from my own project with FastAPI and PostgreSQL, and mention the trade offs I considered.",
    "hindi": "मैं पहले बुनियादी बात समझाऊंगा, फिर अपने फास्ट एपीआई और पोस्टग्रेस प्रोजेक्ट का एक उदाहरण दूंगा।",
    "hinglish": "Main pehle basic idea samjhaunga, phir apne FastAPI aur PostgreSQL project ka ek example dunga.",
}[LANG]


def silent_wav(seconds: float = 1.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


def post_answer(client: httpx.Client, interview_id: str, number: int, wav: bytes) -> dict:
    r = client.post(
        f"{API}/voice/answer",
        data={"interview_id": interview_id, "question_number": str(number)},
        files={"audio": ("answer.wav", wav, "audio/wav")},
        timeout=90,
    )
    r.raise_for_status()
    return r.json()


with httpx.Client() as client:
    start = client.post(
        f"{API}/voice/start",
        json={
            "role": "Backend Engineer",
            "level": "Junior",
            "userid": "audio-test",
            "techstack": "FastAPI, PostgreSQL, Docker",
            "language": LANG,
        },
        timeout=90,
    )
    start.raise_for_status()
    s = start.json()
    iid = s["interview_id"]
    print("INTERVIEW:", iid)
    print("Q1:", s["question_text"])
    print("Q1 audio returned:", bool(s["audio_base64"]), "| tts_ms:", s["tts_ms"])

    # Silence must NOT use up a question
    r = post_answer(client, iid, 1, silent_wav())
    print("\nsilence ->", "retry" if r["retry"] else "UNEXPECTED", "| transcript:", repr(r["transcript"]))

    answer_wav, _ = gnani.synthesize(ANSWER_TEXT, LANG)
    number = 1
    while True:
        r = post_answer(client, iid, number, answer_wav)
        print(f"\nanswer {number} heard as: {r['transcript']}")
        print(f"  stt_ms={r['stt_ms']} llm_ms={r['llm_ms']} tts_ms={r['tts_ms']}")
        if r["interview_complete"]:
            print("COMPLETE")
            break
        print(f"  next Q{r['question_number']}: {r['next_question']}")
        print("  next audio returned:", bool(r["audio_base64"]))
        number = r["question_number"]

    t = client.get(f"{API}/trace/{iid}").json()
    print("\nOVERALL:", t["overall_score"])
    print("METRICS:", t["metric_averages"])
    print("LATENCY (measured averages, ms):", t["latency_averages"])
    print("RESULT LINK ID:", iid)