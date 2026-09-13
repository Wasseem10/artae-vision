import { describe, expect, it } from "vitest";
import { mergeConditions, readConditions } from "./condition-results";
import type { ConditionResult } from "./browser-sessions";

const answer = (index: number, status: ConditionResult["status"], at?: number): ConditionResult => ({
  condition_index: index, condition: `Condition ${index}`, status, summary: status,
  matched_frame_index: status === "match" ? 0 : null, at_seconds: at,
});

describe("independent conditions over a full video", () => {
  it("retains an early match while a different condition matches later", () => {
    const first = [answer(0, "match", 4), answer(1, "no_match")];
    const final = mergeConditions(first, [answer(0, "no_match"), answer(1, "match", 51)]);
    expect(final.map((item) => item.status)).toEqual(["match", "match"]);
    expect(final.map((item) => item.at_seconds)).toEqual([4, 51]);
  });
  it("does not turn an incomplete observation into a definitive negative", () => {
    expect(mergeConditions([answer(0, "uncertain")], [answer(0, "no_match")])[0].status).toBe("uncertain");
    expect(mergeConditions([answer(0, "uncertain")], [answer(0, "match")])[0].status).toBe("match");
  });
  it("preserves conjunctions within each user-defined condition", () => {
    expect(readConditions("A blue shirt and orange background\n\nA dog on a couch")).toEqual([
      "A blue shirt and orange background", "A dog on a couch",
    ]);
  });
});
