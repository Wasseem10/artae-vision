// Timestamps come from the video, never from model-generated duration guesses.
export type FrameState = "active" | "inactive" | "uncertain";
export type Observation = { at: number; state: FrameState };
export type Timeline = Record<number, Observation[]>;
export type Episode = {
  first: number; last: number; startAfter: number | null; endBy: number | null;
  minDuration: number; maxDuration: number | null;
};

export const DETAILED_INTERVALS = [0.5, 1, 2, 5, 10, 15, 30] as const;

export function recommendedDetailedInterval(duration: number, requested: number): number {
  if (!Number.isFinite(duration) || duration <= 0 || duration > 1200) {
    throw new Error("Detailed timing supports clips up to 20 minutes.");
  }
  if (!DETAILED_INTERVALS.includes(requested as (typeof DETAILED_INTERVALS)[number])) {
    throw new Error("Choose a supported sampling interval.");
  }
  const end = Math.max(0, duration - 0.05);
  const minimum = end / 190;
  return DETAILED_INTERVALS.find((interval) => interval >= requested && interval >= minimum) ?? 30;
}

export function timelineStatus(points: Observation[]): "match" | "no_match" | "uncertain" {
  if (points.some((point) => point.state === "active")) return "match";
  if (!points.length || points.some((point) => point.state === "uncertain")) return "uncertain";
  return "no_match";
}

export function detailedTimes(duration: number, interval: number): number[] {
  if (!Number.isFinite(duration) || duration <= 0 || duration > 1200) throw new Error("Detailed timing supports clips up to 20 minutes.");
  if (!DETAILED_INTERVALS.includes(interval as (typeof DETAILED_INTERVALS)[number])) throw new Error("Choose a supported sampling interval.");
  const end = Math.max(0, duration - 0.05);
  const times = Array.from({ length: Math.floor(end / interval) + 1 }, (_, i) => i * interval);
  if (end > times[times.length - 1]) times.push(end);
  if (times.length > 192) throw new Error("This interval needs more than 192 samples. Choose a longer interval or trim the video; coverage will not be silently reduced.");
  return times;
}

export function mergeObservations(previous: Observation[], next: Observation[]): Observation[] {
  const byTime = new Map(previous.map((item) => [item.at.toFixed(3), item]));
  for (const item of next) {
    const key = item.at.toFixed(3), old = byTime.get(key);
    // Conflicting judgments of the same frame cannot establish an exact boundary.
    byTime.set(key, old && old.state !== item.state ? { ...item, state: "uncertain" } : item);
  }
  return [...byTime.values()].sort((a, b) => a.at - b.at);
}

export function episodes(observations: Observation[]): Episode[] {
  const result: Episode[] = [];
  for (let i = 0; i < observations.length; i++) {
    if (observations[i].state !== "active") continue;
    const firstIndex = i;
    while (i + 1 < observations.length && observations[i + 1].state === "active") i++;
    const first = observations[firstIndex].at, last = observations[i].at;
    const before = observations[firstIndex - 1], after = observations[i + 1];
    const startAfter = before?.state === "inactive" ? before.at : null;
    const endBy = after?.state === "inactive" ? after.at : null;
    result.push({ first, last, startAfter, endBy, minDuration: last - first,
      maxDuration: startAfter !== null && endBy !== null ? endBy - startAfter : null });
  }
  return result;
}

export function refinementWindows(timeline: Timeline): [number, number][] {
  const windows = new Map<string, [number, number]>();
  for (const observations of Object.values(timeline)) {
    for (let i = 1; i < observations.length; i++) {
      const a = observations[i - 1], b = observations[i];
      if (a.state !== b.state && a.state !== "uncertain" && b.state !== "uncertain" && b.at - a.at > 0.5)
        windows.set(`${a.at}:${b.at}`, [a.at, b.at]);
    }
  }
  return [...windows.values()].sort((a, b) => (b[1] - b[0]) - (a[1] - a[0])).slice(0, 4);
}

export function timeLabel(seconds: number): string {
  const rounded = Math.round(seconds * 10) / 10;
  return `${Math.floor(rounded / 60)}:${(rounded % 60).toFixed(1).padStart(4, "0")}`;
}
