const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

// Full story of one interview: plan, turns, AI reasoning, scores
export function getTrace(interviewId: string) {
  return request<Trace>(`/trace/${encodeURIComponent(interviewId)}`);
}

// Riley creates the interview during the call, so the browser looks it up afterwards
export async function getLatestInterviewId(candidateId: string): Promise<string | null> {
  const data = await request<{ interview_id: string | null }>(
    `/trace/latest?candidate_id=${encodeURIComponent(candidateId)}`
  );
  return data.interview_id;
}
