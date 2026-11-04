// One shared <audio> element. Browsers only allow playback after a user gesture, so the
// element is "unlocked" once when the person taps Start, then reused for every question.

const SILENT_WAV =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";

let player: HTMLAudioElement | null = null;

export function unlockAudio() {
  if (!player) player = new Audio();
  player.src = SILENT_WAV;
  player.play().catch(() => {});
}

export function stopAudio() {
  if (player) {
    player.pause();
    player.removeAttribute("src");
  }
}

// Plays a base64 WAV and resolves when it ends (or fails, so the interview never gets stuck)
export function playBase64Wav(base64: string): Promise<void> {
  if (!player) player = new Audio();
  const el = player;

  return new Promise((resolve) => {
    const done = () => {
      el.onended = null;
      el.onerror = null;
      resolve();
    };
    el.onended = done;
    el.onerror = done;
    el.src = `data:audio/wav;base64,${base64}`;
    el.play().catch(done);
  });
}
