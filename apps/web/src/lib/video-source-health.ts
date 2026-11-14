/** Detect an input that stops advancing between worker requests. This measures
 * decoded-media clock progress, not image content or detector accuracy. */
export class VideoSourceHealth {
  private lastMediaSeconds = -1;
  private lastProgressMs: number;

  constructor(startedMs: number) {
    this.lastProgressMs = startedMs;
  }

  stalled(mediaSeconds: number, readyState: number, wallMs: number): boolean {
    if (readyState >= 2 && Number.isFinite(mediaSeconds) && mediaSeconds >= 0 &&
        mediaSeconds > this.lastMediaSeconds) {
      this.lastMediaSeconds = mediaSeconds;
      this.lastProgressMs = wallMs;
    }
    return wallMs - this.lastProgressMs >= 15000;
  }
}
