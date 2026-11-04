import json
import logging
import os
import re

from dotenv import load_dotenv
from groq import Groq

from app.schemas import Difficulty, Evaluation, PlannedQuestion

load_dotenv()

log = logging.getLogger("zyra.agent")

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
DIFFICULTY_ORDER: list[str] = ["easy", "medium", "hard"]

_client: Groq | None = None


# Groq helpers
def _get_client() -> Groq:
    global _client
    if _client is None:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is missing. Add it to backend/.env")
        # Short timeout: Vapi is waiting on a live voice call while we think
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


# STEP 1 - PLAN: build a short interview with escalating difficulty
def difficulty_tags(amount: int) -> list[str]:
    return ["easy", "medium", "hard"] if amount <= 3 else ["easy", "medium", "medium", "hard"]


def _fallback_questions(role: str, techstack: str, tags: list[str]) -> list[str]:
    focus = _focus(role, techstack)
    bank = {
        "easy": f"Can you briefly introduce yourself and tell me about your experience with {focus}?",
        "medium": f"Walk me through a recent project where you used {focus}. What was your role and what decisions did you make?",
        "hard": f"Imagine a {role} system you built starts failing under heavy load. How would you find the cause and fix it?",
    }
    return [bank[t] for t in tags]


def _as_text(item) -> str:
    if isinstance(item, dict):
        item = item.get("question") or item.get("question_text") or ""
    return str(item).strip()


def plan_interview(
    role: str, level: str, techstack: str, interview_type: str, amount: int
) -> list[PlannedQuestion]:
    tags = difficulty_tags(amount)
    numbered = "\n".join(f"Question {i + 1}: {t} difficulty" for i, t in enumerate(tags))

    system = (
        "You are a senior interviewer planning a short spoken interview. "
        'Respond with JSON only, in the form {"questions": ["...", "..."]}.'
    )
    user = (
        f"Role: {role}\nExperience level: {level}\nTech stack: {techstack or 'not specified'}\n"
        f"Focus: {interview_type} questions\n\n"
        f"Write exactly {len(tags)} questions in this order:\n{numbered}\n\n"
        "Rules: each question is one sentence, under 30 words, easy to understand when spoken aloud, "
        "tailored to the role and level. No lists, no code, no special characters, no numbering."
    )

    try:
        data = _chat_json(system, user, max_tokens=1200, temperature=0.5)
        questions = [clean_for_voice(_as_text(q)) for q in data.get("questions", [])]
        questions = [q for q in questions if q]
        if len(questions) < len(tags):
            raise ValueError(f"expected {len(tags)} questions, got {len(questions)}")
        questions = questions[: len(tags)]
    except Exception as exc:
        log.warning("plan_interview fell back to template questions: %s", exc)
        questions = _fallback_questions(role, techstack, tags)

    return [
        PlannedQuestion(question_number=i + 1, question_text=q, difficulty=tags[i])
        for i, q in enumerate(questions)
    ]


# STEP 2 - OBSERVE + REASON: evaluate one answer, decide next difficulty
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


def evaluate_answer(
    role: str, level: str, question: str, difficulty: str, answer: str
) -> Evaluation:
    answer = (answer or "").strip()

    # Nothing meaningful said: no need to spend an LLM call
    if len(answer.split()) < 4:
        verdict = "weak"
        return Evaluation(
            verdict=verdict,
            score=15,
            reasoning="The answer was too short to show real understanding of the question.",
            next_difficulty=decide_next_difficulty(difficulty, verdict),
        )

    system = (
        "You are a fair but demanding interviewer scoring one spoken answer. "
        "The answer is a speech transcript, so ignore filler words and small transcription errors. "
        'Respond with JSON only: {"score": <integer 0-100>, "reasoning": "<at most 2 short sentences: '
        'what was good and what was missing>"}.'
    )
    user = (
        f"Role: {role}\nLevel: {level}\nQuestion difficulty: {difficulty}\n"
        f"Question: {question}\n\nCandidate answer: {answer}"
    )

    try:
        data = _chat_json(system, user, max_tokens=900, temperature=0.2)
        score = max(0, min(100, int(round(float(data["score"])))))
        reasoning = clean_for_voice(str(data.get("reasoning", ""))) or "No reasoning returned."
        verdict = _verdict_from_score(score)
        return Evaluation(
            verdict=verdict,
            score=score,
            reasoning=reasoning,
            next_difficulty=decide_next_difficulty(difficulty, verdict),
        )
    except Exception as exc:
        log.warning("evaluate_answer fell back to neutral score: %s", exc)
        return Evaluation(
            verdict="adequate",
            score=50,
            reasoning="Automatic scoring was unavailable for this answer, so the difficulty was kept the same.",
            next_difficulty=decide_next_difficulty(difficulty, "adequate"),
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
) -> str:
    """Rewrite the next planned question to the new difficulty. Falls back to the original."""
    system = (
        "You are a senior interviewer adjusting the next question of a spoken interview. "
        'Respond with JSON only: {"question": "<the new question>"}.'
    )
    user = (
        f"Role: {role}\nLevel: {level}\nTech stack: {techstack or 'not specified'}\n"
        f"Previous question: {previous_question}\nCandidate's answer: {previous_answer}\n"
        f"Originally planned next question: {planned_question}\n\n"
        f"Rewrite the next question so it is {target_difficulty} difficulty. Keep the same general topic "
        "as the planned question. One sentence, under 30 words, easy to say aloud, "
        "no special characters."
    )
    try:
        data = _chat_json(system, user, max_tokens=700, temperature=0.4)
        question = clean_for_voice(str(data.get("question", "")))
        if not question or len(question) > 300:
            raise ValueError("empty or oversized question")
        return question
    except Exception as exc:
        log.warning("adapt_question kept the planned question: %s", exc)
        return planned_question