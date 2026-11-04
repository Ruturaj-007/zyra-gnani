// Browser-side recorder: silence detection to auto-stop, then encode 16 kHz mono 16-bit WAV
// (the format Gnani Prisma accepts), so the backend needs no ffmpeg.

const TARGET_RATE = 16000;

export type StopReason = "silence" | "max" | "no-speech" | "manual";

export interface RecordingResult {
  wav: Blob | null; // null when there was nothing worth sending
  reason: StopReason;
  heardSpeech: boolean;
  durationMs: number;
}

export interface RecorderOptions {
  maxMs?: number; // hard cap per answer; Gnani REST accepts at most 30 s
  silenceMs?: number; // stop after this much quiet once the person has spoken
  noSpeechMs?: number; // give up if nothing is said for this long
  onLevel?: (level: number) => void; // 0..1, for the live meter
}

export interface RecorderHandle {
  stop: () => void; // the manual "Done answering" button
  cancel: () => void; // abort without producing audio
  result: Promise<RecordingResult>;
}

function pickMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  for (const m of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"]) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return undefined;
}

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const write = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };

  write(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  write(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

// Decode whatever the browser recorded (webm/mp4/ogg), downmix to mono and resample to 16 kHz
async function toWav16k(blob: Blob): Promise<Blob> {
  const arrayBuffer = await blob.arrayBuffer();
  const decodeCtx = new AudioContext();
  let decoded: AudioBuffer;
  try {
    decoded = await decodeCtx.decodeAudioData(arrayBuffer);
  } finally {
    decodeCtx.close().catch(() => {});
  }

  const frames = Math.max(1, Math.ceil(decoded.duration * TARGET_RATE));
  const offline = new OfflineAudioContext(1, frames, TARGET_RATE);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();
  return encodeWav(rendered.getChannelData(0), TARGET_RATE);
}

export async function startRecording(options: RecorderOptions = {}): Promise<RecorderHandle> {
  const { maxMs = 28000, silenceMs = 1800, noSpeechMs = 10000, onLevel } = options;

  // Throws if the microphone is blocked; the caller shows a friendly message
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });

  const audioCtx = new AudioContext();
  const analyser = audioCtx.createAnalyser();
  analyser.fftSize = 1024;
  audioCtx.createMediaStreamSource(stream).connect(analyser);
  const samples = new Float32Array(analyser.fftSize);

  const mime = pickMime();
  const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  const chunks: BlobPart[] = [];
  recorder.ondataavailable = (e) => {
    if (e.data.size > 0) chunks.push(e.data);
  };

  const startedAt = performance.now();
  let reason: StopReason = "manual";
  let heardSpeech = false;
  let cancelled = false;
  let lastVoiceAt = startedAt;
  let floor = 0;
  let floorCount = 0;
  let finished = false;

  const finish = (why: StopReason) => {
    if (finished) return;
    finished = true;
    reason = why;
    clearInterval(timer);
    if (recorder.state !== "inactive") recorder.stop();
  };

  // Check the microphone level every 50 ms
  const timer = setInterval(() => {
    analyser.getFloatTimeDomainData(samples);
    let sum = 0;
    for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
    const rms = Math.sqrt(sum / samples.length);
    onLevel?.(Math.min(1, rms * 8));

    const now = performance.now();
    const elapsed = now - startedAt;

    // Learn the room's background noise during the first 400 ms
    if (elapsed < 400) {
      floor = (floor * floorCount + rms) / (floorCount + 1);
      floorCount += 1;
      return;
    }

    const threshold = Math.max(0.015, floor * 3);
    if (rms > threshold) {
      heardSpeech = true;
      lastVoiceAt = now;
    }

    if (elapsed >= maxMs) finish("max");
    else if (heardSpeech && now - lastVoiceAt >= silenceMs) finish("silence");
    else if (!heardSpeech && elapsed >= noSpeechMs) finish("no-speech");
  }, 50);

  const result = new Promise<RecordingResult>((resolve, reject) => {
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      audioCtx.close().catch(() => {});
      onLevel?.(0);
      const durationMs = Math.round(performance.now() - startedAt);

      if (cancelled || (reason === "no-speech" && !heardSpeech)) {
        resolve({ wav: null, reason, heardSpeech, durationMs });
        return;
      }
      try {
        const wav = await toWav16k(new Blob(chunks, { type: recorder.mimeType || mime }));
        resolve({ wav, reason, heardSpeech, durationMs });
      } catch (err) {
        reject(err);
      }
    };
    recorder.onerror = () => reject(new Error("Recording failed"));
  });

  recorder.start();

  return {
    stop: () => finish("manual"),
    cancel: () => {
      cancelled = true;
      finish("manual");
    },
    result,
  };
}
