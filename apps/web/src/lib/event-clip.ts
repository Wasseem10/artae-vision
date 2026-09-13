import type { BrowserClip } from "./browser-sessions";

export function eventClipWindow(at: number, duration: number) {
  const start = Math.max(0, Math.min(at - 4, duration - 0.1));
  const end = Math.min(duration, start + 12);
  return { start, end };
}

/** Re-encode only the event window, without uploading the original video or audio. */
export async function extractEventClip(url: string, at: number, signal: AbortSignal): Promise<BrowserClip> {
  if (typeof MediaRecorder === "undefined") throw new Error("This browser cannot prepare video clips.");
  const mimeType = ["video/mp4;codecs=avc1.42E01E", "video/webm;codecs=vp8", "video/webm"]
    .find((type) => MediaRecorder.isTypeSupported(type));
  if (!mimeType) throw new Error("Video clip encoding is not supported in this browser.");
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  let animation = 0;
  let stream: MediaStream | undefined;
  let recorder: MediaRecorder | undefined;
  const wait = (name: string, action: () => void) => new Promise<void>((resolve, reject) => {
    const cleanup = () => { clearTimeout(timer); video.removeEventListener(name, done); video.removeEventListener("error", fail); signal.removeEventListener("abort", abort); };
    const done = () => { cleanup(); resolve(); };
    const fail = () => { cleanup(); reject(new Error("Could not decode the event clip.")); };
    const abort = () => { cleanup(); reject(new DOMException("Stopped", "AbortError")); };
    const timer = window.setTimeout(fail, 15000);
    video.addEventListener(name, done, { once: true });
    video.addEventListener("error", fail, { once: true });
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) { abort(); return; }
    action();
  });
  try {
    await wait("loadeddata", () => { video.src = url; video.load(); });
    const { start, end } = eventClipWindow(at, video.duration);
    if (!(end > start) || !Number.isFinite(end)) throw new Error("Invalid event window.");
    if (start > 0) await wait("seeked", () => { video.currentTime = start; });
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 960 / video.videoWidth, 540 / video.videoHeight);
    canvas.width = Math.max(2, Math.floor(video.videoWidth * scale / 2) * 2);
    canvas.height = Math.max(2, Math.floor(video.videoHeight * scale / 2) * 2);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Video canvas unavailable.");
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    stream = canvas.captureStream(20);
    recorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 900000 });
    const chunks: Blob[] = [];
    const activeRecorder = recorder;
    const blob = await new Promise<Blob>((resolve, reject) => {
      const cleanup = () => { clearTimeout(timeout); cancelAnimationFrame(animation); signal.removeEventListener("abort", abort); video.pause(); };
      const fail = (error: Error) => { cleanup(); if (activeRecorder.state !== "inactive") activeRecorder.stop(); reject(error); };
      const abort = () => fail(new DOMException("Stopped", "AbortError"));
      const timeout = window.setTimeout(() => fail(new Error("Clip preparation timed out. Keep this tab visible and retry.")), 25000);
      activeRecorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      activeRecorder.onerror = () => fail(new Error("Video encoding failed."));
      activeRecorder.onstop = () => { cleanup(); resolve(new Blob(chunks, { type: mimeType.split(";")[0] })); };
      const draw = () => {
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        if (video.currentTime >= end - 0.05 || video.ended) { activeRecorder.stop(); return; }
        animation = requestAnimationFrame(draw);
      };
      signal.addEventListener("abort", abort, { once: true });
      if (signal.aborted) { abort(); return; }
      activeRecorder.start(250);
      void video.play().then(draw).catch(() => fail(new Error("Allow video playback to prepare the clip.")));
    });
    if (!blob.size || blob.size > 3_500_000) throw new Error("The clip could not fit within the upload limit.");
    return { id: crypto.randomUUID(), start, duration: end - start, width: canvas.width, height: canvas.height, blob };
  } finally {
    cancelAnimationFrame(animation);
    if (recorder && recorder.state !== "inactive") recorder.stop();
    stream?.getTracks().forEach((track) => track.stop());
    video.pause(); video.removeAttribute("src"); video.load();
  }
}
