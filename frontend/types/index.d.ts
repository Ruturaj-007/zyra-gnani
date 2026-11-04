type Difficulty = "easy" | "medium" | "hard";

type LanguageKey = "english" | "hindi" | "hinglish" | "marathi";

interface Candidate {
  id: string;
  name: string;
}

interface InterviewSetup {
  role: string;
  level: string;
  techstack: string;
  type: string;
  language: LanguageKey;
}

interface TraceTurn {
  turn_number: number;
  question: string;
  answer_transcript: string;
  ai_reasoning: string | null;
  score: number | null;
  technical_knowledge: number | null;
  problem_solving: number | null;
  communication_clarity: number | null;
  evidence_quote: string | null;
  improvement_tip: string | null;
  stt_ms: number | null;
  llm_ms: number | null;
  tts_ms: number | null;
  timestamp: string;
}

interface TracePlanItem {
  question_number: number;
  question_text: string;
  difficulty: Difficulty;
}

interface MetricAverages {
  technical_knowledge: number | null;
  problem_solving: number | null;
  communication_clarity: number | null;
}

interface LatencyAverages {
  stt_ms: number | null;
  llm_ms: number | null;
  tts_ms: number | null;
}

interface InterviewSummary {
  strengths: string[];
  weaknesses: string[];
}

interface Trace {
  interview_id: string;
  candidate_id: string;
  role: string;
  level: string;
  techstack: string;
  language: LanguageKey;
  status: "in_progress" | "completed";
  current_checkpoint: number;
  created_at: string;
  plan: TracePlanItem[];
  turns: TraceTurn[];
  average_score: number | null;
  overall_score: number | null;
  summary: InterviewSummary | null;
  metric_averages: MetricAverages;
  latency_averages: LatencyAverages;
}

interface VoiceStartResponse {
  interview_id: string;
  language: LanguageKey;
  question_number: number;
  total_questions: number;
  question_text: string;
  audio_base64: string | null;
  tts_ms: number | null;
}

interface VoiceAnswerResponse {
  retry: boolean;
  transcript: string;
  interview_complete: boolean;
  question_number: number | null;
  total_questions: number;
  next_question: string;
  audio_base64: string | null;
  stt_ms: number | null;
  llm_ms: number | null;
  tts_ms: number | null;
}

interface AgentProps {
  candidate: Candidate;
  setup: InterviewSetup;
}
