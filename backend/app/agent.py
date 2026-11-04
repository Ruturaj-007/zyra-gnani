import json
import logging
import os
import re

from dotenv import load_dotenv
from groq import Groq

from app.schemas import Difficulty, Evaluation, InterviewSummary, PlannedQuestion

load_dotenv()

log = logging.getLogger("zyra.agent")

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
DIFFICULTY_ORDER: list[str] = ["easy", "medium", "hard"]

# Spoken questions must stay short: Timbre input is limited per request.
MAX_QUESTION_CHARS = 250

# How the interviewer should write for each picker language (keys match gnani.LANGUAGES).
LANGUAGE_STYLE = {
    "english": "English",
    "hindi": "Hindi in Devanagari script (common technical terms may stay in English)",
    "hinglish": "Hinglish: Hindi written in Roman (Latin) letters, mixed naturally with English technical terms",
    "marathi": "Marathi in Devanagari script (common technical terms may stay in English)",
}

_client: Groq | None = None


def _style(language: str) -> str:
    return LANGUAGE_STYLE.get((language or "english").lower(), LANGUAGE_STYLE["english"])


# Groq helpers
def _get_client() -> Groq:
    global _client
    if _client is None:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is missing. Add it to backend/.env")
        # Short timeout: the candidate is waiting on a voice turn while we think
        _client = Groq(api_key=key, timeout=12.0, max_retries=1)
    return _client


def _chat_json(system: str, user: str, max_tokens: int = 800, temperature: float = 0.3) -> dict:
    """Call Groq and return parsed JSON.

    gpt-oss is a reasoning model: max_completion_tokens covers its hidden thinking
    AND the answer, so the budget must be generous. reasoning_effort="low" keeps
    latency down, and include_reasoning=False returns only the final JSON.
    """
    resp = _get_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_completion_tokens=max_tokens,
        reasoning_effort="low",
        include_reasoning=False,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    if not content:
        raise ValueError("empty response from model (token budget likely used up by reasoning)")
    return json.loads(content)


def clean_for_voice(text: str) -> str:
    """Remove characters that break or confuse a text-to-speech voice."""
    text = re.sub(r"[*#_`>\[\]{}|~^\\]", " ", text)
    text = text.replace("/", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip('"\u201c\u201d ').strip()


def _focus(role: str, techstack: str) -> str:
    return techstack.strip() or role


def _clamp(value, default: int = 50) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


# STEP 1 - PLAN: build a short interview with escalating difficulty
def difficulty_tags(amount: int) -> list[str]:
    return ["easy", "medium", "hard"] if amount <= 3 else ["easy", "medium", "medium", "hard"]


# Template questions used if the LLM fails. One short set per picker language.
def _fallback_bank(language: str, role: str, focus: str) -> dict[str, str]:
    lang = (language or "english").lower()
    if lang == "hindi":
        return {
            "easy": f"क्या आप अपना परिचय दें और {focus} के साथ अपना अनुभव बताएं?",
            "medium": f"{focus} का इस्तेमाल करके बनाए गए किसी प्रोजेक्ट के बारे में बताइए। उसमें आपकी क्या भूमिका थी?",
            "hard": f"मान लीजिए आपका {role} सिस्टम ज्यादा लोड में फेल होने लगे। आप कारण कैसे ढूंढेंगे और कैसे ठीक करेंगे?",
        }
    if lang == "hinglish":
        return {
            "easy": f"Apna introduction dijiye aur {focus} ke saath apna experience batayiye.",
            "medium": f"Ek project ke baare mein batayiye jahan aapne {focus} use kiya. Aapka role kya tha?",
            "hard": f"Maan lijiye aapka {role} system heavy load mein fail hone lage. Aap problem kaise dhundhenge aur fix karenge?",
        }
    if lang == "marathi":
        return {
            "easy": f"तुमची ओळख करून द्या आणि {focus} मधला तुमचा अनुभव सांगा.",
            "medium": f"{focus} वापरून केलेल्या एका प्रोजेक्टबद्दल सांगा. त्यात तुमची भूमिका काय होती?",
            "hard": f"समजा तुमची {role} सिस्टम जास्त लोडमध्ये बंद पडू लागली. तुम्ही कारण कसे शोधाल आणि कसे सोडवाल?",
        }
    return {
        "easy": f"Can you briefly introduce yourself and tell me about your experience with {focus}?",
        "medium": f"Walk me through a recent project where you used {focus}. What was your role and what decisions did you make?",
        "hard": f"Imagine a {role} system you built starts failing under heavy load. How would you find the cause and fix it?",
    }


def _fallback_questions(role: str, techstack: str, tags: list[str], language: str) -> list[str]:
    bank = _fallback_bank(language, role, _focus(role, techstack))
    return [bank[t] for t in tags]


def _as_text(item) -> str:
    if isinstance(item, dict):
        item = item.get("question") or item.get("question_text") or ""
    return str(item).strip()


def plan_interview(
    role: str,
    level: str,
    techstack: str,
    interview_type: str,
    amount: int,
    language: str = "english",
) -> list[PlannedQuestion]:
    tags = difficulty_tags(amount)
    numbered = "\n".join(f"Question {i + 1}: {t} difficulty" for i, t in enumerate(tags))
    fallback = _fallback_questions(role, techstack, tags, language)

    system = (
        "You are a senior interviewer planning a short spoken interview. "
        'Respond with JSON only, in the form {"questions": ["...", "..."]}.'
    )
    user = (
        f"Role: {role}\nExperience level: {level}\nTech stack: {techstack or 'not specified'}\n"
        f"Focus: {interview_type} questions\nLanguage to write in: {_style(language)}\n\n"
        f"Write exactly {len(tags)} questions in this order:\n{numbered}\n\n"
        "Rules: each question is one sentence, under 25 words and under 200 characters, "
        "easy to understand when spoken aloud, tailored to the role and level. "
        "No lists, no code, no special characters, no numbering."
    )

    try:
        data = _chat_json(system, user, max_tokens=1500, temperature=0.5)
        questions = [clean_for_voice(_as_text(q)) for q in data.get("questions", [])]
        questions = [q for q in questions if q]
        if len(questions) < len(tags):
            raise ValueError(f"expected {len(tags)} questions, got {len(questions)}")
        questions = questions[: len(tags)]
        # A question too long to speak in one TTS request is swapped for the template one
        questions = [q if len(q) <= MAX_QUESTION_CHARS else fallback[i] for i, q in enumerate(questions)]
    except Exception as exc:
        log.warning("plan_interview fell back to template questions: %s", exc)
        questions = fallback

    return [
        PlannedQuestion(question_number=i + 1, question_text=q, difficulty=tags[i])
        for i, q in enumerate(questions)
    ]


# STEP 2 - OBSERVE + REASON: score one answer on three metrics, decide next difficulty
def _verdict_from_score(score: int) -> str:
    if score >= 75:
        return "strong"
    if score >= 45:
        return "adequate"
    return "weak"


def decide_next_difficulty(current: str, verdict: str) -> Difficulty:
    """Strong answer -> step up. Weak answer -> step down. Otherwise stay."""
    idx = DIFFICULTY_ORDER.index(current) if current in DIFFICULTY_ORDER else 1
    if verdict == "strong":
        idx = min(idx + 1, len(DIFFICULTY_ORDER) - 1)
    elif verdict == "weak":
        idx = max(idx - 1, 0)
    return DIFFICULTY_ORDER[idx]  # type: ignore[return-value]


def _first_words(text: str, count: int = 15) -> str:
    return " ".join(text.split()[:count])


def _verified_quote(quote: str, answer: str) -> str:
    """Keep the quote only if it really appears in the candidate's answer; else use their opening words."""
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()  # noqa: E731
    q = (quote or "").strip().strip('"\u201c\u201d')
    if q and norm(q) in norm(answer):
        return q
    return _first_words(answer)


def _build_evaluation(
    tk: int, ps: int, cc: int, quote: str, tip: str, reasoning: str, difficulty: str
) -> Evaluation:
    score = int(round((tk + ps + cc) / 3))
    verdict = _verdict_from_score(score)
    return Evaluation(
        verdict=verdict,
        score=score,
        technical_knowledge=tk,
        problem_solving=ps,
        communication_clarity=cc,
        evidence_quote=quote,
        improvement_tip=tip,
        reasoning=reasoning,
        next_difficulty=decide_next_difficulty(difficulty, verdict),
    )


def evaluate_answer(
    role: str,
    level: str,
    question: str,
    difficulty: str,
    answer: str,
    language: str = "english",
) -> Evaluation:
    answer = (answer or "").strip()

    # Nothing meaningful said: no need to spend an LLM call
    if len(answer.split()) < 4:
        return _build_evaluation(
            10, 10, 20,
            answer,
            "Answer in a few full sentences and include one concrete example.",
            "The answer was too short to show real understanding of the question.",
            difficulty,
        )

    system = (
        "You are a fair but demanding interviewer scoring one spoken answer. "
        "The answer is a speech-to-text transcript, so ignore filler words and small transcription errors. "
        "You only have a transcript: do NOT judge confidence, tone, accent or cultural fit. "
        "Score three things, each an integer 0-100: "
        "technical_knowledge (correctness and depth for the role and level), "
        "problem_solving (reasoning, structure, trade-offs, concrete steps), "
        "communication_clarity (how clearly and logically the ideas are expressed in words). "
        'Respond with JSON only: {"technical_knowledge": <int>, "problem_solving": <int>, '
        '"communication_clarity": <int>, '
        '"evidence_quote": "<an exact short phrase copied from the candidate answer, under 25 words>", '
        '"improvement_tip": "<one specific, actionable tip in English, under 25 words>", '
        '"reasoning": "<at most 2 short sentences in English: what was good and what was missing>"}.'
    )
    user = (
        f"Role: {role}\nLevel: {level}\nQuestion difficulty: {difficulty}\n"
        f"Interview language: {_style(language)}\n"
        f"Question: {question}\n\nCandidate answer: {answer}"
    )

    try:
        data = _chat_json(system, user, max_tokens=1400, temperature=0.2)
        tk = _clamp(data["technical_knowledge"])
        ps = _clamp(data["problem_solving"])
        cc = _clamp(data["communication_clarity"])
        quote = _verified_quote(str(data.get("evidence_quote", "")), answer)
        tip = clean_for_voice(str(data.get("improvement_tip", ""))) or "Add one concrete example from your own work."
        reasoning = clean_for_voice(str(data.get("reasoning", ""))) or "No reasoning returned."
        return _build_evaluation(tk, ps, cc, quote, tip, reasoning, difficulty)
    except Exception as exc:
        log.warning("evaluate_answer fell back to neutral scores: %s", exc)
        return _build_evaluation(
            50, 50, 50,
            _first_words(answer),
            "Add one concrete example from your own work to make the answer stronger.",
            "Automatic scoring was unavailable for this answer, so the difficulty was kept the same.",
            difficulty,
        )


# STEP 3 - REPLAN: rewrite the next question if difficulty needs to change
def adapt_question(
    role: str,
    level: str,
    techstack: str,
    previous_question: str,
    previous_answer: str,
    planned_question: str,
    target_difficulty: str,
    language: str = "english",
) -> str:
    """Rewrite the next planned question to the new difficulty. Falls back to the original."""
    system = (
        "You are a senior interviewer adjusting the next question of a spoken interview. "
        'Respond with JSON only: {"question": "<the new question>"}.'
    )
    user = (
        f"Role: {role}\nLevel: {level}\nTech stack: {techstack or 'not specified'}\n"
        f"Language to write in: {_style(language)}\n"
        f"Previous question: {previous_question}\nCandidate's answer: {previous_answer}\n"
        f"Originally planned next question: {planned_question}\n\n"
        f"Rewrite the next question so it is {target_difficulty} difficulty. Keep the same general topic "
        "as the planned question. One sentence, under 25 words and under 200 characters, easy to say aloud, "
        "no special characters."
    )
    try:
        data = _chat_json(system, user, max_tokens=900, temperature=0.4)
        question = clean_for_voice(str(data.get("question", "")))
        if not question or len(question) > MAX_QUESTION_CHARS:
            raise ValueError("empty or oversized question")
        return question
    except Exception as exc:
        log.warning("adapt_question kept the planned question: %s", exc)
        return planned_question


# STEP 4 - SUMMARISE: overall score + strengths and weaknesses at completion
METRIC_LABELS = {
    "technical_knowledge": "technical knowledge",
    "problem_solving": "problem solving",
    "communication_clarity": "communication clarity",
}


def _fallback_summary(turns: list[dict]) -> InterviewSummary:
    """Deterministic summary from the metric averages, used if the LLM fails."""
    avgs = {}
    for key in METRIC_LABELS:
        vals = [t[key] for t in turns if t.get(key) is not None]
        if vals:
            avgs[key] = sum(vals) / len(vals)
    if not avgs:
        return InterviewSummary()
    best = max(avgs, key=avgs.get)  # type: ignore[arg-type]
    worst = min(avgs, key=avgs.get)  # type: ignore[arg-type]
    return InterviewSummary(
        strengths=[f"Strongest area: {METRIC_LABELS[best]} (about {round(avgs[best])}/100)."],
        weaknesses=[f"Area to improve: {METRIC_LABELS[worst]} (about {round(avgs[worst])}/100)."],
    )


def summarize_interview(role: str, level: str, turns: list[dict]) -> tuple[int, InterviewSummary]:
    """Returns (overall_score, summary). The overall score is plain arithmetic, not an LLM guess."""
    scores = [t["score"] for t in turns if t.get("score") is not None]
    overall = int(round(sum(scores) / len(scores))) if scores else 0
    if not turns:
        return overall, InterviewSummary()

    lines = "\n".join(
        f"Q{t['turn_number']} ({t.get('score', 0)}/100, technical {t.get('technical_knowledge')}, "
        f"problem solving {t.get('problem_solving')}, clarity {t.get('communication_clarity')}): "
        f"{t['question']} | Answer: {_first_words(t['answer_transcript'], 60)}"
        for t in turns
    )
    system = (
        "You are an interviewer writing a short summary for a candidate from a spoken-interview transcript. "
        "Do not comment on confidence, tone or cultural fit. Use plain, kind, specific language in English. "
        'Respond with JSON only: {"strengths": ["...", "..."], "weaknesses": ["...", "..."]} '
        "with 2 to 3 items each, every item under 20 words."
    )
    user = f"Role: {role}\nLevel: {level}\n\n{lines}"

    try:
        data = _chat_json(system, user, max_tokens=1400, temperature=0.3)
        strengths = [clean_for_voice(str(s)) for s in data.get("strengths", []) if str(s).strip()][:3]
        weaknesses = [clean_for_voice(str(s)) for s in data.get("weaknesses", []) if str(s).strip()][:3]
        if not strengths and not weaknesses:
            raise ValueError("empty summary")
        return overall, InterviewSummary(strengths=strengths, weaknesses=weaknesses)
    except Exception as exc:
        log.warning("summarize_interview fell back to metric-based summary: %s", exc)
        return overall, _fallback_summary(turns)