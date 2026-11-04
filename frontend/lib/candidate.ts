const CANDIDATE_KEY = "zyra_candidate";
const SETUP_KEY = "zyra_setup";

export const LANGUAGES: { key: LanguageKey; label: string; native: string }[] = [
  { key: "english", label: "English", native: "English" },
  { key: "hindi", label: "Hindi", native: "हिन्दी" },
  { key: "hinglish", label: "Hinglish", native: "Hinglish" },
  { key: "marathi", label: "Marathi", native: "मराठी" },
];

export function languageLabel(key: string): string {
  return LANGUAGES.find((l) => l.key === key)?.label ?? "English";
}

// Client-side only. There is no login: a name plus a random id stored in the browser.
export function createCandidate(name: string): Candidate {
  const clean = name.trim();
  const slug =
    clean
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "candidate";
  const suffix = Math.random().toString(36).slice(2, 8);

  const candidate: Candidate = { id: `${slug}-${suffix}`, name: clean };
  localStorage.setItem(CANDIDATE_KEY, JSON.stringify(candidate));
  return candidate;
}

export function getCandidate(): Candidate | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(CANDIDATE_KEY);
    return raw ? (JSON.parse(raw) as Candidate) : null;
  } catch {
    return null;
  }
}

export function saveSetup(setup: InterviewSetup) {
  localStorage.setItem(SETUP_KEY, JSON.stringify(setup));
}

export function getSetup(): InterviewSetup | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(SETUP_KEY);
    if (!raw) return null;
    const setup = JSON.parse(raw) as InterviewSetup;
    return { ...setup, language: setup.language ?? "english" };
  } catch {
    return null;
  }
}
