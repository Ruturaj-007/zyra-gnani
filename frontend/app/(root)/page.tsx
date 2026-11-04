"use client";

import Image from "next/image";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { createCandidate, saveSetup } from "@/lib/candidate";

const LEVELS = ["Junior", "Mid", "Senior"];
const TYPES = ["Technical", "Behavioral", "Mixed"];

const fieldClass = "!bg-dark-200 !rounded-full !min-h-12 !px-5 placeholder:!text-light-100";

function Choice({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          aria-pressed={value === option}
          className={cn(
            "rounded-full px-5 min-h-10 text-sm font-semibold cursor-pointer border transition-colors",
            value === option
              ? "bg-primary-200 text-dark-100 border-primary-200"
              : "bg-dark-200 text-primary-200 border-transparent hover:bg-dark-200/70"
          )}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

export default function Home() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [techstack, setTechstack] = useState("");
  const [level, setLevel] = useState("Junior");
  const [type, setType] = useState("Technical");
  const [error, setError] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !role.trim()) {
      setError("Enter your name and the role you are interviewing for.");
      return;
    }
    createCandidate(name);
    saveSetup({
      role: role.trim(),
      level,
      techstack: techstack.trim(),
      type,
    });
    router.push("/interview");
  };

  return (
    <>
      <section className="card-cta">
        <div className="flex flex-col gap-6 max-w-lg">
          <h2>Practice a real interview. Get questions that adapt to you.</h2>
          <p className="text-lg">
            Riley, an AI interviewer, listens to each answer, scores it, and makes the next question
            harder or easier. A 3 to 4 minute voice call, then a full breakdown of how she reasoned.
          </p>
        </div>

        <Image
          src="/robot.png"
          alt="AI interviewer"
          width={400}
          height={400}
          className="max-sm:hidden"
        />
      </section>

      <section className="flex flex-col gap-6 max-w-2xl w-full mx-auto">
        <h2>Set up your interview</h2>

        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <label htmlFor="name" className="text-light-100">
              Your name
            </label>
            <Input
              id="name"
              className={fieldClass}
              placeholder="Ruturaj Pawar"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor="role" className="text-light-100">
              Role you are interviewing for
            </label>
            <Input
              id="role"
              className={fieldClass}
              placeholder="Backend Engineer"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor="techstack" className="text-light-100">
              Tech stack (optional)
            </label>
            <Input
              id="techstack"
              className={fieldClass}
              placeholder="Python, FastAPI, PostgreSQL"
              value={techstack}
              onChange={(e) => setTechstack(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-light-100">Experience level</span>
            <Choice options={LEVELS} value={level} onChange={setLevel} />
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-light-100">Question focus</span>
            <Choice options={TYPES} value={type} onChange={setType} />
          </div>

          {error && <p className="text-destructive-100">{error}</p>}

          <button type="submit" className="btn-primary max-sm:w-full">
            Continue to the call
          </button>
        </form>
      </section>
    </>
  );
}
