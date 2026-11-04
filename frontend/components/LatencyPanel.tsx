// Shows ONLY numbers the server measured (wall-clock time of each Gnani / Groq call).
// Anything derived is labelled as such. No prices are shown because they are not measured here.

function fmt(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "n/a";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`;
}

function Stat({ label, sub, value }: { label: string; sub: string; value: number | null }) {
  return (
    <div className="dark-gradient rounded-2xl p-4 flex flex-col gap-1">
      <span className="text-sm text-light-400">{label}</span>
      <span className="text-2xl font-bold text-white">{fmt(value)}</span>
      <span className="text-xs text-light-600">{sub}</span>
    </div>
  );
}

export default function LatencyPanel({ trace }: { trace: Trace }) {
  const avg = trace.latency_averages;
  const spokenChars = trace.plan.reduce((sum, q) => sum + q.question_text.length, 0);

  // Derived: the sum of the three measured parts for turns that have all three
  const waits = trace.turns
    .filter((t) => t.stt_ms !== null && t.llm_ms !== null && t.tts_ms !== null)
    .map((t) => (t.stt_ms ?? 0) + (t.llm_ms ?? 0) + (t.tts_ms ?? 0));
  const avgWait = waits.length ? Math.round(waits.reduce((a, b) => a + b, 0) / waits.length) : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Stat label="Speech to text" sub="Gnani Prisma v2.5 · measured" value={avg.stt_ms} />
        <Stat label="Scoring and next question" sub="Groq LLM · measured" value={avg.llm_ms} />
        <Stat label="Text to speech" sub="Gnani Timbre · measured" value={avg.tts_ms} />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-light-400">
              <th className="py-2 pr-4 font-medium">Answer</th>
              <th className="py-2 pr-4 font-medium">Speech to text</th>
              <th className="py-2 pr-4 font-medium">LLM</th>
              <th className="py-2 pr-4 font-medium">Text to speech</th>
            </tr>
          </thead>
          <tbody>
            {trace.turns.map((t) => (
              <tr key={t.turn_number} className="border-t border-light-800">
                <td className="py-2 pr-4 text-white">Q{t.turn_number}</td>
                <td className="py-2 pr-4 text-light-100">{fmt(t.stt_ms)}</td>
                <td className="py-2 pr-4 text-light-100">{fmt(t.llm_ms)}</td>
                <td className="py-2 pr-4 text-light-100">
                  {t.tts_ms === null && t.turn_number === trace.plan.length ? "no next question" : fmt(t.tts_ms)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="!list-none flex flex-col gap-1 text-sm">
        <li>
          Average wait between the end of an answer and the next question starting:{" "}
          <span className="text-white font-semibold">{fmt(avgWait)}</span> (derived: speech to text + LLM + text to
          speech; it leaves out your browser upload and audio playback).
        </li>
        <li>
          Counted usage: {trace.turns.length} answers transcribed, {spokenChars} characters of questions written for
          speech (an upper bound, the last question is only spoken if reached).
        </li>
        <li className="text-light-400">
          Times are wall-clock measurements taken by the server. The last answer&apos;s LLM time includes writing the
          summary. Prices are not shown because they are not measured by this app.
        </li>
      </ul>
    </div>
  );
}
