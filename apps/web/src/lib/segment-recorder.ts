export type RecordingState = "recording" | "finalizing" | "stopped" | "failed";
type RecordedSegment = { blob: Blob; start: number; duration: number };
type Options = {
  stream: MediaStream;
  mimeType: string;
  now: () => number;
  onSegment: (segment: RecordedSegment) => void;
  onState: (state: RecordingState) => void;
  onFailure: () => void;
  createRecorder?: (stream: MediaStream, options: MediaRecorderOptions) => MediaRecorder;
};

/** Owns one canvas stream. A recorder failure ends recording, not detection.
 * Final dataavailable/stop events may arrive after stop() returns. */
export function startSegmentedRecording(options: Options): { stop: () => void } {
  let stopped = false, failed = false, released = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let finalizeTimer: ReturnType<typeof setTimeout> | undefined;
  let current: { recorder: MediaRecorder; end: number | null } | undefined;
  const release = () => {
    if (released) return;
    released = true;
    options.stream.getTracks().forEach((track) => {
      try { track.stop(); } catch { /* Release remaining tracks even if one fails. */ }
    });
  };
  const stopRecorder = () => {
    if (!current) return;
    current.end ??= options.now();
    finalizeTimer ??= setTimeout(fail, 5000);
    if (current.recorder.state !== "inactive") current.recorder.stop();
  };
  const fail = () => {
    if (failed) return;
    failed = true;
    clearTimeout(timer);
    clearTimeout(finalizeTimer);
    options.onState("failed");
    options.onFailure();
    // A failed recorder may still emit a final usable segment. Its onstop
    // callback can retain those bytes but must never start a retry loop.
    // Cleanup must not schedule another finalization watchdog.
    try {
      if (current && current.recorder.state !== "inactive") {
        current.end ??= options.now();
        current.recorder.stop();
      }
    } catch { /* Cleanup still releases capture tracks. */ }
    release();
  };
  const next = () => {
    if (stopped || failed) return;
    const start = options.now(), chunks: Blob[] = [];
    try {
      const recorder = options.createRecorder
        ? options.createRecorder(options.stream, { mimeType: options.mimeType, videoBitsPerSecond: 600000 })
        : new MediaRecorder(options.stream, { mimeType: options.mimeType, videoBitsPerSecond: 600000 });
      const segment = { recorder, end: null as number | null };
      current = segment;
      let completed = false;
      recorder.ondataavailable = (event) => { if (!completed && event.data.size) chunks.push(event.data); };
      recorder.onerror = () => { if (!completed) { segment.end ??= options.now(); fail(); } };
      recorder.onstop = () => {
        if (completed) return;
        completed = true;
        clearTimeout(timer);
        clearTimeout(finalizeTimer);
        finalizeTimer = undefined;
        // Freeze the end when stop was requested, before the video can be
        // unloaded or another session changes the source clock.
        const duration = (segment.end ?? options.now()) - start;
        const blob = new Blob(chunks, { type: options.mimeType });
        current = undefined;
        if (!Number.isFinite(start) || start < 0 || !Number.isFinite(duration) || duration < 0) fail();
        else if (duration >= 0.2) {
          if (!blob.size) fail();
          else {
            try { options.onSegment({ blob, start, duration }); } catch { fail(); }
          }
        }
        if (stopped && !failed) options.onState("stopped");
        else next();
      };
      recorder.start();
      if (!failed) {
        options.onState("recording");
        timer = setTimeout(() => { try { stopRecorder(); } catch { fail(); } }, 10000);
      }
    } catch { fail(); }
  };
  next();
  return { stop() {
    if (stopped) return;
    stopped = true;
    clearTimeout(timer);
    if (!failed) options.onState(current ? "finalizing" : "stopped");
    try { if (!failed) stopRecorder(); } catch { fail(); }
    release();
  } };
}
