"use client";

import dayjs from "dayjs";
import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import TraceTimeline from "@/components/TraceTimeline";
import { getTrace } from "@/lib/api";

const MAX_POLLS = 8;

export default function InterviewResults() {
  const { id } = useParams<{ id: string }>();
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let polls = 0;
    let timer: ReturnType<typeof setTimeout>;

    // The last answer may still be scoring when the call ends, so refresh a few times
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
        if (!cancelled) setError("Could not load this interview. Check that the backend is running.");
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

  return (
    <section className="section-feedback">
      <div className="flex flex-row justify-center">
        <h1 className="text-4xl font-semibold text-center">
          Results for your <span className="capitalize">{trace.role}</span> interview
        </h1>
      </div>

      <div className="flex flex-row flex-wrap justify-center gap-6">
        <div className="flex flex-row gap-2 items-center">
          <Image src="/star.svg" width={22} height={22} alt="" />
          <p>
            Average score:{" "}
            <span className="text-primary-200 font-bold">
              {trace.average_score !== null ? Math.round(trace.average_score) : "N/A"}
            </span>
            /100
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

      <hr />

      <div className="flex flex-col gap-6">
        <h2>How the interview unfolded</h2>
        <p>
          Each question was planned with a difficulty. After every answer, Riley scored it and
          changed the next question to match.
        </p>
        <TraceTimeline trace={trace} />
      </div>

      <div className="buttons">
        <Link href="/" className="btn-primary flex-1 flex-center">
          Practice again
        </Link>
      </div>
    </section>
  );
}
