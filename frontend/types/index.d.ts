type Difficulty = "easy" | "medium" | "hard";

interface Candidate {
  id: string;
  name: string;
}

interface InterviewSetup {
  role: string;
  level: string;
  techstack: string;
  type: string;
}

interface TraceTurn {
  turn_number: number;
  question: string;
  answer_transcript: string;
  ai_reasoning: string | null;
  score: number | null;
  timestamp: string;
}

interface TracePlanItem {
  question_number: number;
  question_text: string;
  difficulty: Difficulty;
}

interface Trace {
  interview_id: string;
  candidate_id: string;
  role: string;
  level: string;
  techstack: string;
  status: "in_progress" | "completed";
  current_checkpoint: number;
  created_at: string;
  plan: TracePlanItem[];
  turns: TraceTurn[];
  average_score: number | null;
}

interface AgentProps {
  candidate: Candidate;
  setup: InterviewSetup;
}
