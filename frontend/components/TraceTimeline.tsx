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

function ScoreBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-3" role="img" aria-label={`Score ${score} out of 100`}>
      <div className="h-2 flex-1 rounded-full bg-dark-200 overflow-hidden">
        <div
          className={cn("h-full rounded-full", scoreColor(score))}
          style={{ width: `${Math.max(2, Math.min(100, score))}%` }}
        />
      </div>
      <span className="text-sm font-bold text-white w-14 text-right">{score}/100</span>
    </div>
  );
}

// One entry per planned question: what was asked, what was said, how the agent reasoned
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

            <div className={cn("flex flex-col gap-3 flex-1", !isLast && "pb-8")}>
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={cn(
                    "rounded-full px-3 py-1 text-xs font-semibold capitalize",
                    DIFFICULTY_STYLE[item.difficulty]
                  )}
                >
                  {item.difficulty}
                </span>
                {!turn && <span className="text-sm text-light-400">Not answered yet</span>}
              </div>

              <p className="text-white text-lg">{item.question_text}</p>

              {turn && (
                <div className="dark-gradient rounded-2xl p-5 flex flex-col gap-4">
                  <div className="flex flex-col gap-1">
                    <span className="text-sm text-light-400">Your answer</span>
                    <p className="text-light-100">{turn.answer_transcript}</p>
                  </div>

                  {turn.score !== null && <ScoreBar score={turn.score} />}

                  {turn.ai_reasoning && (
                    <div className="flex flex-col gap-1 border-t border-light-800 pt-4">
                      <span className="text-sm text-light-400">How Riley reasoned</span>
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
