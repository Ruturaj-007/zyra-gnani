"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { cn } from "@/lib/utils";
import { vapi } from "@/lib/vapi.sdk";
import { getLatestInterviewId } from "@/lib/api";

enum CallStatus {
  INACTIVE = "INACTIVE",
  CONNECTING = "CONNECTING",
  ACTIVE = "ACTIVE",
  FINISHED = "FINISHED",
}

interface SavedMessage {
  role: "user" | "system" | "assistant";
  content: string;
}

interface VapiMessage {
  type?: string;
  transcriptType?: string;
  role?: SavedMessage["role"];
  transcript?: string;
}

const ASSISTANT_ID = process.env.NEXT_PUBLIC_VAPI_ASSISTANT_ID ?? "";

// Short on purpose: 3 questions keeps the call near 3-4 minutes and controls voice cost
const QUESTION_COUNT = "3";

const Agent = ({ candidate, setup }: AgentProps) => {
  const router = useRouter();
  const [callStatus, setCallStatus] = useState<CallStatus>(CallStatus.INACTIVE);
  const [messages, setMessages] = useState<SavedMessage[]>([]);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [lastMessage, setLastMessage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loadingResults, setLoadingResults] = useState(false);
  const handledEnd = useRef(false);

  useEffect(() => {
    const onCallStart = () => setCallStatus(CallStatus.ACTIVE);
    const onCallEnd = () => setCallStatus(CallStatus.FINISHED);

    const onMessage = (message: VapiMessage) => {
      if (
        message.type === "transcript" &&
        message.transcriptType === "final" &&
        message.role &&
        message.transcript
      ) {
        setMessages((prev) => [
          ...prev,
          { role: message.role!, content: message.transcript! },
        ]);
      }
    };

    const onSpeechStart = () => setIsSpeaking(true);
    const onSpeechEnd = () => setIsSpeaking(false);
    // const onError = (err: unknown) => console.error("Vapi error:", err);
        const onError = (err: unknown) => console.error("Vapi error:", JSON.stringify(err ?? {}, Object.getOwnPropertyNames(err ?? {}), 2));

    vapi.on("call-start", onCallStart);
    vapi.on("call-end", onCallEnd);
    vapi.on("message", onMessage);
    vapi.on("speech-start", onSpeechStart);
    vapi.on("speech-end", onSpeechEnd);
    vapi.on("error", onError);

    return () => {
      vapi.off("call-start", onCallStart);
      vapi.off("call-end", onCallEnd);
      vapi.off("message", onMessage);
      vapi.off("speech-start", onSpeechStart);
      vapi.off("speech-end", onSpeechEnd);
      vapi.off("error", onError);
    };
  }, []);

  useEffect(() => {
    if (messages.length > 0) {
      setLastMessage(messages[messages.length - 1].content);
    }
  }, [messages]);

  // When the call ends, Riley has already created the interview on the backend.
  // The browser never saw its id, so look up this candidate's newest interview.
  useEffect(() => {
    if (callStatus !== CallStatus.FINISHED || handledEnd.current) return;
    handledEnd.current = true;

    (async () => {
      setLoadingResults(true);
      for (let attempt = 0; attempt < 5; attempt++) {
        try {
          const id = await getLatestInterviewId(candidate.id);
          if (id) {
            router.push(`/interview/${id}`);
            return;
          }
        } catch (err) {
          console.error("Could not look up interview:", err);
        }
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
      setLoadingResults(false);
      setError(
        "The call ended before an interview was created. Start the call again and answer at least one question."
      );
    })();
  }, [callStatus, candidate.id, router]);

  const handleCall = async () => {
    setError(null);
    setMessages([]);
    setLastMessage("");
    handledEnd.current = false;
    setCallStatus(CallStatus.CONNECTING);

    try {
      await vapi.start(ASSISTANT_ID, {
        // Riley reads these as {{variables}} and passes them to the generateInterview tool
        variableValues: {
          username: candidate.name,
          userid: candidate.id,
          role: setup.role,
          level: setup.level,
          techstack: setup.techstack,
          type: setup.type,
          amount: QUESTION_COUNT,
        },
      });
    } catch (err) {
      console.error("Could not start call:", err);
      setCallStatus(CallStatus.INACTIVE);
      setError(
        "Could not start the call. Check that microphone access is allowed and the Vapi keys are set in .env.local."
      );
    }
  };

  const handleDisconnect = () => {
    setCallStatus(CallStatus.FINISHED);
    vapi.stop();
  };

  return (
    <>
      <div className="call-view">
        <div className="card-interviewer">
          <div className="avatar">
            <Image
              src="/ai-avatar.png"
              alt="Riley, the AI interviewer"
              width={65}
              height={54}
              className="object-cover"
            />
            {isSpeaking && <span className="animate-speak" />}
          </div>
          <h3>Riley</h3>
        </div>

        <div className="card-border">
          <div className="card-content">
            <Image
              src="/user-avatar.png"
              alt={candidate.name}
              width={539}
              height={539}
              className="rounded-full object-cover size-[120px]"
            />
            <h3>{candidate.name}</h3>
          </div>
        </div>
      </div>

      {messages.length > 0 && (
        <div className="transcript-border">
          <div className="transcript">
            <p key={lastMessage} className="animate-fadeIn">
              {lastMessage}
            </p>
          </div>
        </div>
      )}

      {error && <p className="text-center text-destructive-100">{error}</p>}
      {loadingResults && (
        <p className="text-center">Scoring your interview and building the timeline...</p>
      )}

      <div className="w-full flex justify-center">
        {callStatus !== CallStatus.ACTIVE ? (
          <button
            className="relative btn-call"
            onClick={handleCall}
            disabled={callStatus === CallStatus.CONNECTING || loadingResults}
          >
            <span
              className={cn(
                "absolute animate-ping rounded-full opacity-75",
                callStatus !== CallStatus.CONNECTING && "hidden"
              )}
            />
            <span className="relative">
              {callStatus === CallStatus.INACTIVE || callStatus === CallStatus.FINISHED
                ? "Start interview"
                : ". . ."}
            </span>
          </button>
        ) : (
          <button className="btn-disconnect" onClick={handleDisconnect}>
            End interview
          </button>
        )}
      </div>
    </>
  );
};

export default Agent;
