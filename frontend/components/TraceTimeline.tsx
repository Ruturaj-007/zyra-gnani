import { cn } from "@/lib/utils";

const DIFFICULTY_STYLE: Record<Difficulty, string> = {
  easy: "bg-success-100/15 text-success-100",
  medium: "bg-primary-200/15 text-primary-200",
  hard: "bg-destructive-100/15 text-destructive-100",
};

function scoreColor(score: number) {
  if (score >= 75) return "bg-success-100";
  if (score >= 45) return "bg-primary-200";
  return "bg-destructive-100";
}

function MetricBar({ label, score }: { label: string; score: number | null }) {
  if (score === null) return null;
  return (
    <div className="flex items-center gap-3" role="img" aria-label={`${label} ${score} out of 100`}>
      <span className="text-sm text-light-400 w-44 shrink-0">{label}</span>
      <div className="h-2 flex-1 rounded-full bg-dark-200 overflow-hidden">
        <div className={cn("h-full rounded-full", scoreColor(score))} style={{ width: `${Math.max(2, Math.min(100, score))}%` }} />
      </div>
      <span className="text-sm font-bold text-white w-14 text-right">{score}/100</span>
    </div>
  );
}

// One entry per planned question: what was asked, what was said, the three metrics, evidence and a tip
export default function TraceTimeline({ trace }: { trace: Trace }) {
  const turnByNumber = new Map(trace.turns.map((t) => [t.turn_number, t]));

  return (
    <ol className="flex flex-col list-none">
      {trace.plan.map((item, index) => {
        const turn = turnByNumber.get(item.question_number);
        const isLast = index === trace.plan.length - 1;

        return (
          <li key={item.question_number} className="flex gap-4">
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  "size-9 shrink-0 rounded-full flex-center text-sm font-bold",
                  turn ? "bg-primary-200 text-dark-100" : "bg-dark-200 text-light-400"
                )}
              >
                {item.question_number}
              </span>
              {!isLast && <span className="w-px flex-1 bg-light-600/60 my-1" />}
            </div>

            <div className={cn("flex flex-col gap-3 flex-1 min-w-0", !isLast && "pb-8")}>
              <div className="flex flex-wrap items-center gap-3">
                <span className={cn("rounded-full px-3 py-1 text-xs font-semibold capitalize", DIFFICULTY_STYLE[item.difficulty])}>
                  {item.difficulty}
                </span>
                {!turn && <span className="text-sm text-light-400">Not answered yet</span>}
              </div>

              <p className="text-white text-lg">{item.question_text}</p>

              {turn && (
                <div className="dark-gradient rounded-2xl p-5 flex flex-col gap-4">
                  <div className="flex flex-col gap-1">
                    <span className="text-sm text-light-400">What Gnani Prisma heard</span>
                    <p className="text-light-100">{turn.answer_transcript}</p>
                  </div>

                  <div className="flex flex-col gap-2 border-t border-light-800 pt-4">
                    <MetricBar label="Technical knowledge" score={turn.technical_knowledge} />
                    <MetricBar label="Problem solving" score={turn.problem_solving} />
                    <MetricBar label="Communication clarity" score={turn.communication_clarity} />
                  </div>

                  {turn.evidence_quote && (
                    <blockquote className="border-l-2 border-primary-200 pl-4 flex flex-col gap-1">
                      <span className="text-sm text-light-400">Evidence from your own words</span>
                      <p className="text-white italic">&ldquo;{turn.evidence_quote}&rdquo;</p>
                    </blockquote>
                  )}

                  {turn.improvement_tip && (
                    <div className="rounded-xl bg-primary-200/10 px-4 py-3 flex flex-col gap-1">
                      <span className="text-sm text-primary-200 font-semibold">How to improve</span>
                      <p className="text-light-100">{turn.improvement_tip}</p>
                    </div>
                  )}

                  {turn.ai_reasoning && (
                    <div className="flex flex-col gap-1 border-t border-light-800 pt-4">
                      <span className="text-sm text-light-400">How Zyra reasoned</span>
                      <p className="text-light-100">{turn.ai_reasoning}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
