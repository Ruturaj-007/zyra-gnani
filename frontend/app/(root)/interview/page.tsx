"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import Agent from "@/components/Agent";
import { getCandidate, getSetup } from "@/lib/candidate";

export default function Interview() {
  const router = useRouter();
  const [state, setState] = useState<{ candidate: Candidate; setup: InterviewSetup } | null>(null);

  useEffect(() => {
    const candidate = getCandidate();
    const setup = getSetup();
    if (!candidate || !setup) {
      router.replace("/");
      return;
    }
    setState({ candidate, setup });
  }, [router]);

  if (!state) return <p>Loading...</p>;

  const { candidate, setup } = state;

  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto w-full">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold capitalize">{setup.role} interview</h1>
        <p className="text-sm text-gray-400">
          {setup.type} · {setup.level}
          {setup.techstack ? ` · ${setup.techstack}` : ""}
        </p>
      </div>

      <Agent candidate={candidate} setup={setup} />
    </div>
  );
}
