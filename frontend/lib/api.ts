const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fail(res: Response): Promise<never> {
  let detail = "";
  try {
    const body = await res.json();
    detail = typeof body?.detail === "string" ? body.detail : "";
  } catch {
    // body was not JSON
  }
  throw new Error(detail || `API ${res.status}`);
}

// Full story of one interview: plan, turns, metrics, summary, measured latency
export async function getTrace(interviewId: string): Promise<Trace> {
  const res = await fetch(`${API_URL}/trace/${encodeURIComponent(interviewId)}`, {
    cache: "no-store",
  });
  if (!res.ok) return fail(res);
  return res.json();
}

// Plans the interview and returns the first question (text + Timbre audio)
export async function startVoiceInterview(
  candidate: Candidate,
  setup: InterviewSetup
): Promise<VoiceStartResponse> {
  const res = await fetch(`${API_URL}/voice/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      role: setup.role,
      level: setup.level,
      techstack: setup.techstack,
      type: setup.type.toLowerCase(),
      language: setup.language,
      userid: candidate.id,
      amount: 3,
    }),
  });
  if (!res.ok) return fail(res);
  return res.json();
}

// One voice turn: sends the recorded WAV, gets the transcript and the next question
export async function sendVoiceAnswer(
  interviewId: string,
  questionNumber: number,
  wav: Blob
): Promise<VoiceAnswerResponse> {
  const form = new FormData();
  form.append("interview_id", interviewId);
  form.append("question_number", String(questionNumber));
  form.append("audio", wav, "answer.wav");

  const res = await fetch(`${API_URL}/voice/answer`, { method: "POST", body: form });
  if (!res.ok) return fail(res);
  return res.json();
}

// The backend is on a free tier that sleeps; this wakes it up while the user fills the form
export function pingBackend() {
  fetch(`${API_URL}/health`, { cache: "no-store" }).catch(() => {});
}
