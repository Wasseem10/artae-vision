import type { ConditionResult } from "./browser-sessions";

export function readConditions(prompt: string): string[] {
  return prompt.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

// A later negative must never erase a detection from an earlier part of the video.
// Any uncertain batch keeps the final absence answer uncertain.
export function mergeConditions(previous: ConditionResult[], next: ConditionResult[]): ConditionResult[] {
  const priority = { match: 4, uncertain: 3, unsupported: 2, no_match: 1 };
  const results = new Map(previous.map((item) => [item.condition_index, item]));
  for (const item of next) {
    const old = results.get(item.condition_index);
    if (!old || priority[item.status] > priority[old.status]) results.set(item.condition_index, item);
  }
  return [...results.values()].sort((a, b) => a.condition_index - b.condition_index);
}
