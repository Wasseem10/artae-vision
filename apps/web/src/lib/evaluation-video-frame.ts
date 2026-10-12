/** Evaluation-only decoding contract; /live does not use this helper. */
export const EVALUATION_FRAME_SAMPLING = {
  method: "presented-frame-v1",
  seekOffsetSeconds: 0.001,
  maxFrameLagSeconds: 0.05,
  maxFrameLeadSeconds: 0.002,
} as const;

export type PresentedFrameSample = {
  requestedSeconds: number;
  decodedSeconds: number;
  presentedFrames: number;
};

export function validPresentedTime(requested: number, decoded: number): boolean {
  return Number.isFinite(requested) && requested >= 0 &&
    Number.isFinite(decoded) && decoded >= 0 &&
    requested - decoded <= EVALUATION_FRAME_SAMPLING.maxFrameLagSeconds + 1e-6 &&
    decoded - requested <= EVALUATION_FRAME_SAMPLING.maxFrameLeadSeconds + 1e-6;
}

/** Wait for a decoded frame, not merely a logical seek completion. Reject
 * unsupported browsers, stale/future frames, errors, cancellation, or timeout. */
export function seekPresentedFrame(
  video: HTMLVideoElement,
  seconds: number,
  cancelled: () => boolean = () => false,
  timeoutMs = 15_000,
): Promise<PresentedFrameSample> {
  return new Promise((resolve, reject) => {
    if (!Number.isFinite(seconds) || seconds < 0 ||
        !Number.isFinite(video.duration) || seconds >= video.duration ||
        typeof video.requestVideoFrameCallback !== "function" ||
        typeof video.cancelVideoFrameCallback !== "function") {
      reject(new Error("Presented-frame verification is unavailable or the sample is invalid"));
      return;
    }
    if (cancelled()) { reject(new Error("Evaluation cancelled")); return; }
    let handle: number | undefined;
    const cleanup = () => {
      clearTimeout(timeout);
      clearInterval(cancelTimer);
      video.removeEventListener("error", fail);
      if (handle !== undefined) video.cancelVideoFrameCallback(handle);
    };
    const stop = (message: string) => { cleanup(); reject(new Error(message)); };
    const fail = () => stop("Video decode failed");
    const timeout = setTimeout(() => stop("Presented video frame timed out"), timeoutMs);
    const cancelTimer = setInterval(() => {
      if (cancelled()) stop("Evaluation cancelled");
    }, 100);
    video.addEventListener("error", fail);
    try {
      handle = video.requestVideoFrameCallback((_, metadata) => {
        if (cancelled()) { stop("Evaluation cancelled"); return; }
        if (!validPresentedTime(seconds, metadata.mediaTime) ||
            !Number.isInteger(metadata.presentedFrames) || metadata.presentedFrames <= 0) {
          stop(`Unexpected presented video frame: ${metadata.mediaTime} for ${seconds}`);
          return;
        }
        cleanup();
        resolve({ requestedSeconds: seconds, decodedSeconds: metadata.mediaTime,
          presentedFrames: metadata.presentedFrames });
      });
      video.currentTime = Math.min(seconds + EVALUATION_FRAME_SAMPLING.seekOffsetSeconds,
        video.duration - 0.001);
    } catch (error) {
      cleanup();
      reject(error);
    }
  });
}
