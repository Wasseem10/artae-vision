import type { BrowserClip } from "./browser-sessions";

/** Distance from an event to the selected segment's recorded interval. */
export function recordingGapSeconds(clip: Pick<BrowserClip, "start" | "duration">, at: number): number {
  return Math.max(clip.start - at, at - (clip.start + clip.duration), 0);
}
/** Recorder restarts can leave tiny timestamp gaps between playable segments.
 * Prefer containing footage, then the nearest segment within 250 ms. */
export function clipForEvent(clips: BrowserClip[], at: number): BrowserClip | undefined {
  const playable = clips.filter((clip) => clip.blob || clip.url);
  const containing = playable.find((clip) => clip.start <= at && clip.start + clip.duration >= at);
  if (containing) return containing;
  let nearest: BrowserClip | undefined;
  let distance = 0.25;
  for (const clip of playable) {
    const gap = Math.min(Math.abs(at - clip.start), Math.abs(at - clip.start - clip.duration));
    if (gap <= distance) { nearest = clip; distance = gap; }
  }
  return nearest;
}
