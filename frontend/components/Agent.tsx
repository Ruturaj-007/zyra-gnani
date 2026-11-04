"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { cn } from "@/lib/utils";
import { languageLabel } from "@/lib/candidate";
import { playBase64Wav, stopAudio, unlockAudio } from "@/lib/audio";
import { startRecording, type RecorderHandle } from "@/lib/recorder";
import { sendVoiceAnswer, startVoiceInterview } from "@/lib/api";

type Phase =
  | "idle"
  | "starting"
  | "speaking"
  | "listening"
  | "thinking"
  | "paused"
  | "finishing"
  | "error";

interface Bubble {
  id: number;
  role: "ai" | "user";
  text: string;
}

const PHASE_LABEL: Record<Phase, string> = {
  idle: "Ready",
  starting: "Getting ready",
  speaking: "Speaking",
  listening: "Listening",
  thinking: "Thinking",
  paused: "Waiting for you",
  finishing: "Building your results",
  error: "Something went wrong",
};

const MAX_SILENT_RETRIES = 3;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function ProgressStepper({ total, current, done }: { total: number; current: number; done: boolean }) {
  return (
    <div className="flex flex-col gap-2" aria-label={`Question ${current} of ${total}`}>
      <div className="flex items-center gap-2">
        {Array.from({ length: total }, (_, i) => {
          const n = i + 1;
          const finished = done || n < current;
          const active = !done && n === current;
          return (
            <div key={n} className="flex items-center gap-2 flex-1">
              <span
                className={cn(
                  "size-8 shrink-0 rounded-full flex-center text-sm font-bold transition-colors",
                  finished && "bg-primary-200 text-dark-100",
                  active && "border-2 border-primary-200 text-primary-200",
                  !finished && !active && "bg-dark-200 text-light-400"
                )}
              >
                {finished ? "✓" : n}
              </span>
              {n < total && (
                <span className={cn("h-0.5 flex-1 rounded-full", finished ? "bg-primary-200" : "bg-dark-200")} />
              )}
            </div>
          );
        })}
      </div>
      <p className="text-sm text-light-400">
        {done ? "All questions answered" : `Question ${current} of ${total}`}
      </p>
    </div>
  );
}

const Agent = ({ candidate, setup }: AgentProps) => {
  const router = useRouter();

  const [phase, setPhase] = useState<Phase>("idle");
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [total, setTotal] = useState(3);
  const [current, setCurrent] = useState(1);
  const [level, setLevel] = useState(0);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [canResend, setCanResend] = useState(false);

  const mounted = useRef(true);
  const interviewId = useRef("");
  const questionNumber = useRef(1);
  const recorder = useRef<RecorderHandle | null>(null);
  const lastWav = useRef<Blob | null>(null);
  const silentRetries = useRef(0);
  const bubbleId = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      recorder.current?.cancel();
      stopAudio();
    };
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [bubbles]);

  const addBubble = (role: Bubble["role"], text: string) =>
    setBubbles((prev) => [...prev, { id: (bubbleId.current += 1), role, text }]);

  // Timbre speaks the question; if audio is missing the text still shows and we pause briefly
  async function speak(text: string, audio: string | null) {
    setPhase("speaking");
    if (audio) await playBase64Wav(audio);
    else await sleep(Math.min(6000, 800 + text.length * 45));
  }

  async function listen(): Promise<void> {
    if (!mounted.current) return;
    setError("");
    setPhase("listening");

    let handle: RecorderHandle;
    try {
      handle = await startRecording({ onLevel: setLevel });
    } catch {
      setCanResend(false);
      setError("Microphone access is blocked. Allow the microphone in your browser, then try again.");
      setPhase("error");
      return;
    }
    recorder.current = handle;

    let result;
    try {
      result = await handle.result;
    } catch {
      setCanResend(false);
      setError("Recording failed. Please try again.");
      setPhase("error");
      return;
    }
    recorder.current = null;
    if (!mounted.current) return;

    // Nothing was said: do not spend a speech-to-text call, just ask again
    if (!result.wav) {
      silentRetries.current += 1;
      if (silentRetries.current >= MAX_SILENT_RETRIES) {
        setNotice("I could not hear you. Check your microphone, then tap Answer.");
        setPhase("paused");
        return;
      }
      setNotice("I did not hear anything. Go ahead, I am listening.");
      return listen();
    }

    setNotice("");
    await submit(result.wav);
  }

  async function submit(wav: Blob): Promise<void> {
    lastWav.current = wav;
    setPhase("thinking");

    let reply: VoiceAnswerResponse;
    try {
      reply = await sendVoiceAnswer(interviewId.current, questionNumber.current, wav);
    } catch (err) {
      if (!mounted.current) return;
      setCanResend(true);
      setError(
        err instanceof Error && err.message
          ? `${err.message} Your answer is saved on this screen, you can send it again.`
          : "Could not reach the server. Your answer is saved on this screen, you can send it again."
      );
      setPhase("error");
      return;
    }
    if (!mounted.current) return;
    lastWav.current = null;

    // The speech-to-text heard nothing: the question was NOT used up, so ask for the answer again
    if (reply.retry) {
      silentRetries.current += 1;
      if (silentRetries.current >= MAX_SILENT_RETRIES) {
        setNotice("I could not make out your words. Tap Answer when you are ready.");
        setPhase("paused");
        return;
      }
      setNotice("I could not make out your words. Please say it again.");
      return listen();
    }

    silentRetries.current = 0;
    setNotice("");
    addBubble("user", reply.transcript);

    if (reply.interview_complete) {
      setPhase("finishing");
      router.push(`/interview/${interviewId.current}`);
      return;
    }

    questionNumber.current = reply.question_number ?? questionNumber.current + 1;
    setCurrent(questionNumber.current);
    addBubble("ai", reply.next_question);
    await speak(reply.next_question, reply.audio_base64);
    return listen();
  }

  async function begin() {
    unlockAudio(); // must happen inside the click, so later audio is allowed to play
    setError("");
    setNotice("");
    setBubbles([]);
    setPhase("starting");

    try {
      const first = await startVoiceInterview(candidate, setup);
      if (!mounted.current) return;
      interviewId.current = first.interview_id;
      questionNumber.current = first.question_number;
      silentRetries.current = 0;
      setTotal(first.total_questions);
      setCurrent(first.question_number);
      addBubble("ai", first.question_text);
      await speak(first.question_text, first.audio_base64);
      await listen();
    } catch (err) {
      if (!mounted.current) return;
      setCanResend(false);
      setError(
        err instanceof Error && err.message
          ? `Could not start the interview: ${err.message}`
          : "Could not start the interview. Check your connection and try again."
      );
      setPhase("idle");
    }
  }

  function retryAfterError() {
    setError("");
    if (canResend && lastWav.current) void submit(lastWav.current);
    else if (interviewId.current) void listen();
    else void begin();
  }

  const speaking = phase === "speaking";
  const listening = phase === "listening";
  const started = phase !== "idle" && bubbles.length > 0;

  return (
    <div className="flex flex-col gap-6">
      {started && <ProgressStepper total={total} current={current} done={phase === "finishing"} />}

      <div className="flex flex-col sm:flex-row gap-6">
        {/* Interviewer */}
        <div className="blue-gradient-dark rounded-2xl border border-primary-200/30 flex-1 p-6 flex flex-col items-center gap-3">
          <div className="avatar relative flex-center blue-gradient rounded-full size-24">
            <Image src="/ai-avatar.png" alt="Zyra, the AI interviewer" width={52} height={44} className="object-cover" />
            {speaking && (
              <span className="absolute inline-flex size-5/6 animate-ping rounded-full bg-primary-200 opacity-60" />
            )}
          </div>
          <h3 className="!text-xl !mt-0 text-primary-100">Zyra</h3>
          <p className="text-xs text-light-400">Speaks with Gnani Timbre</p>
        </div>

        {/* Candidate */}
        <div className="border-gradient p-0.5 rounded-2xl flex-1">
          <div className="dark-gradient rounded-2xl h-full p-6 flex flex-col items-center gap-3">
            <div
              className={cn(
                "rounded-full p-1 transition-transform duration-75",
                listening ? "bg-success-100/60" : "bg-transparent"
              )}
              style={{ transform: listening ? `scale(${1 + level * 0.18})` : "scale(1)" }}
            >
              <Image
                src="/user-avatar.png"
                alt={candidate.name}
                width={96}
                height={96}
                className="rounded-full object-cover size-24"
              />
            </div>
            <h3 className="!text-xl text-primary-100">{candidate.name}</h3>
            <p className="text-xs text-light-400">Heard by Gnani Prisma · {languageLabel(setup.language)}</p>
          </div>
        </div>
      </div>

      {/* State pill */}
      <div className="flex flex-col items-center gap-2" aria-live="polite">
        <span
          className={cn(
            "rounded-full px-4 py-1.5 text-sm font-semibold flex items-center gap-2",
            phase === "listening" && "bg-success-100/15 text-success-100",
            phase === "speaking" && "bg-primary-200/15 text-primary-200",
            phase === "thinking" && "bg-light-600/30 text-light-100",
            phase === "error" && "bg-destructive-100/15 text-destructive-100",
            (phase === "idle" || phase === "starting" || phase === "paused" || phase === "finishing") &&
              "bg-dark-200 text-light-100"
          )}
        >
          <span
            className={cn(
              "size-2 rounded-full bg-current",
              (phase === "listening" || phase === "speaking" || phase === "thinking" || phase === "starting") &&
                "animate-pulse"
            )}
          />
          {PHASE_LABEL[phase]}
        </span>
        {phase === "starting" && (
          <p className="text-sm text-light-400 text-center">
            Planning your questions. The first request can take up to a minute if the server was asleep.
          </p>
        )}
        {notice && <p className="text-sm text-primary-200 text-center">{notice}</p>}
      </div>

      {/* Live transcript bubbles */}
      {bubbles.length > 0 && (
        <div
          ref={scrollRef}
          className="dark-gradient rounded-2xl p-4 max-h-80 overflow-y-auto flex flex-col gap-3"
          aria-label="Live transcript"
        >
          {bubbles.map((b) => (
            <div key={b.id} className={cn("flex animate-fadeIn", b.role === "user" ? "justify-end" : "justify-start")}>
              <div
                className={cn(
                  "max-w-[85%] rounded-2xl px-4 py-2.5",
                  b.role === "user"
                    ? "bg-primary-200 text-dark-100 rounded-br-sm"
                    : "bg-dark-200 text-light-100 rounded-bl-sm"
                )}
              >
                <p className={cn("text-xs mb-0.5 font-semibold", b.role === "user" ? "!text-dark-100/70" : "!text-light-400")}>
                  {b.role === "user" ? "You" : "Zyra"}
                </p>
                <p className={cn(b.role === "user" && "!text-dark-100")}>{b.text}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {error && <p className="text-center text-destructive-100">{error}</p>}

      {/* Controls */}
      <div className="w-full flex flex-col items-center gap-2">
        {phase === "idle" && (
          <button className="btn-call" onClick={begin}>
            Start interview
          </button>
        )}

        {listening && (
          <>
            <button className="btn-primary" onClick={() => recorder.current?.stop()}>
              Done answering
            </button>
            <p className="text-sm text-light-400">
              I stop listening after a short pause. Answers can be up to 28 seconds.
            </p>
          </>
        )}

        {phase === "paused" && (
          <button className="btn-call" onClick={() => void listen()}>
            Answer
          </button>
        )}

        {phase === "error" && (
          <button className="btn-primary" onClick={retryAfterError}>
            {canResend ? "Send answer again" : "Try again"}
          </button>
        )}

        {phase === "idle" && (
          <p className="text-sm text-light-400 text-center max-w-md">
            Your browser will ask for microphone access. Use headphones to avoid echo.
          </p>
        )}
      </div>
    </div>
  );
};

export default Agent;
