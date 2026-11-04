"use client";

import dayjs from "dayjs";
import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import LatencyPanel from "@/components/LatencyPanel";
import RadarChart from "@/components/RadarChart";
import TraceTimeline from "@/components/TraceTimeline";
import { getTrace } from "@/lib/api";
import { languageLabel } from "@/lib/candidate";

const MAX_POLLS = 8;

function CopyLinkButton() {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      // Clipboard API blocked: fall back to a temporary input
      const input = document.createElement("input");
      input.value = url;
      document.body.appendChild(input);
      input.select();
      document.execCommand("copy");
      input.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button type="button" onClick={copy} className="btn-secondary">
      {copied ? "Link copied" : "Copy result link"}
    </button>
  );
}

export default function InterviewResults() {
  const { id } = useParams<{ id: string }>();
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let polls = 0;
    let timer: ReturnType<typeof setTimeout>;

    // The last answer may still be saving when we arrive, so refresh a few times
    const load = async () => {
      try {
        const data = await getTrace(id);
        if (cancelled) return;
        setTrace(data);
        setError("");
        polls += 1;
        if (data.status !== "completed" && polls < MAX_POLLS) {
          timer = setTimeout(load, 4000);
        }
      } catch {
        if (!cancelled) setError("Could not load this interview. The server may be waking up, try again in a moment.");
      }
    };

    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id]);

  if (error) return <p className="text-center text-destructive-100">{error}</p>;
  if (!trace) return <p className="text-center">Loading your results...</p>;

  const answered = trace.turns.length;
  const overall = trace.overall_score ?? (trace.average_score !== null ? Math.round(trace.average_score) : null);
  const m = trace.metric_averages;

  return (
    <section className="section-feedback">
      <div className="flex flex-col items-center gap-2">
        <h1 className="text-4xl font-semibold text-center">
          Results for your <span className="capitalize">{trace.role}</span> interview
        </h1>
        <p className="text-sm text-light-400">
          {languageLabel(trace.language)} · {trace.level}
          {trace.techstack ? ` · ${trace.techstack}` : ""}
        </p>
      </div>

      <div className="flex flex-row flex-wrap justify-center gap-6">
        <div className="flex flex-row gap-2 items-center">
          <Image src="/star.svg" width={22} height={22} alt="" />
          <p>
            Overall score:{" "}
            <span className="text-primary-200 font-bold">{overall !== null ? overall : "N/A"}</span>/100
          </p>
        </div>

        <div className="flex flex-row gap-2">
          <Image src="/calendar.svg" width={22} height={22} alt="" />
          <p>{dayjs(trace.created_at).format("MMM D, YYYY h:mm A")}</p>
        </div>

        <p>
          {answered} of {trace.plan.length} questions answered
          {trace.status !== "completed" ? " (interview not finished)" : ""}
        </p>
      </div>

      <div className="flex flex-wrap justify-center gap-3">
        <CopyLinkButton />
      </div>

      <hr />

      {/* Radar + summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
        <RadarChart
          technical={m.technical_knowledge}
          problem={m.problem_solving}
          clarity={m.communication_clarity}
        />

        <div className="flex flex-col gap-5">
          <h2>Summary</h2>
          {trace.summary ? (
            <>
              <div className="flex flex-col gap-2">
                <h3 className="!text-xl text-success-100">Strengths</h3>
                <ul>
                  {trace.summary.strengths.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
              <div className="flex flex-col gap-2">
                <h3 className="!text-xl text-destructive-100">To work on</h3>
                <ul>
                  {trace.summary.weaknesses.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
            </>
          ) : (
            <p>The summary appears once the interview is finished.</p>
          )}
          <p className="text-sm text-light-400">
            Scored from the transcript only, on technical knowledge, problem solving and communication clarity. Tone,
            confidence and cultural fit are not judged, because a transcript cannot show them.
          </p>
        </div>
      </div>

      <hr />

      <div className="flex flex-col gap-6">
        <h2>Answer by answer</h2>
        <p>
          Each question was planned with a difficulty. After every answer, the next question was made harder or easier
          to match.
        </p>
        <TraceTimeline trace={trace} />
      </div>

      <hr />

      <div className="flex flex-col gap-6">
        <h2>Speed behind the voice loop</h2>
        <LatencyPanel trace={trace} />
      </div>

      <hr />

      <p className="text-sm text-light-400">
        Voice is powered by Gnani AI: Prisma v2.5 for speech to text and Timbre for text to speech. Planning, scoring
        and summaries run on a Groq-hosted LLM. Zyra on Gnani evolved from my earlier Zyra.ai project; the Gnani voice
        loop, languages, multi-metric scoring and this results page are new.
      </p>

      <div className="buttons">
        <Link href="/" className="btn-primary flex-1 flex-center">
          Practice again
        </Link>
      </div>
    </section>
  );
}
