"""Text-only dry run: plan, score, adapt and summarise with typed answers. No Gnani calls."""
from app import db, interview_core
from app.routes.trace import get_trace

ANSWERS = [
    "I am a final year student. I have built REST APIs with FastAPI and PostgreSQL, and I deployed one on Render.",
    "In my last project I used a connection pool and added an index on the candidate id column because queries were slow. I also cached repeated lookups.",
    "I would first check logs and metrics to find the bottleneck, then profile the slow endpoint, add caching and scale horizontally behind a load balancer.",
]

db.open_pool()
db.init_db()

start = interview_core.create_interview(
    role="Backend Engineer",
    level="Junior",
    techstack="FastAPI, PostgreSQL, Docker",
    interview_type="technical",
    amount=3,
    language="english",
    candidate_id="dry-run-test",
)
print("INTERVIEW:", start.interview_id)
print("Q1:", start.question_text)

for i, answer in enumerate(ANSWERS, start=1):
    r = interview_core.submit_answer_core(start.interview_id, i, answer, stt_ms=None)
    print(f"\nanswered {i} | llm_ms={r.llm_ms} | complete={r.complete}")
    if not r.complete:
        print(f"Q{r.next_number}:", r.next_question)

t = get_trace(start.interview_id)
print("\nOVERALL:", t.overall_score, "| AVERAGE:", t.average_score)
print("METRICS:", t.metric_averages)
print("SUMMARY:", t.summary)
for turn in t.turns:
    print(f"\nTurn {turn.turn_number}: {turn.technical_knowledge}/{turn.problem_solving}/{turn.communication_clarity}")
    print("  quote:", turn.evidence_quote)
    print("  tip:  ", turn.improvement_tip)

db.close_pool()