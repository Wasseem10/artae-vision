import type { EvaluationInterval } from "./types";

export function parseIntervalList(value: string): EvaluationInterval[] {
  if (!value.trim()) return [];
  return value.split(",").map((part, index) => {
    const match = part.trim().match(/^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$/);
    if (!match) throw new Error(`Interval ${index + 1} must look like 5-10.`);
    const start = Number(match[1]);
    const end = Number(match[2]);
    if (end <= start) throw new Error(`Interval ${index + 1} must end after it starts.`);
    return { start_seconds: start, end_seconds: end, label: "event" };
  });
}
