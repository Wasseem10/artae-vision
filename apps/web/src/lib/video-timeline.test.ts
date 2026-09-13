import { describe, expect, it } from "vitest";
import { detailedTimes, episodes, mergeObservations, recommendedDetailedInterval, refinementWindows, timelineStatus, type Observation } from "./video-timeline";

describe("detailed video timeline", () => {
  it("includes clip boundaries and refuses silent downsampling", () => {
    expect(detailedTimes(6, 2)).toEqual([0, 2, 4, 5.95]);
    expect(detailedTimes(300, 2)).toHaveLength(151);
    expect(() => detailedTimes(300, 0.5)).toThrow("192");
    expect(detailedTimes(1200, 10)).toHaveLength(121);
    expect(() => detailedTimes(1201, 10)).toThrow("20 minutes");
    expect(() => detailedTimes(Infinity, 2)).toThrow();
  });
  it("recommends a supported cadence that keeps long clips inside the sample budget", () => {
    expect(recommendedDetailedInterval(300, 2)).toBe(2);
    expect(recommendedDetailedInterval(1200, 2)).toBe(10);
  });
  it("computes sample-bounded durations across batches", () => {
    const first: Observation[] = [{ at: 0, state: "inactive" }, { at: 2, state: "active" }];
    const next: Observation[] = [{ at: 2, state: "active" }, { at: 4, state: "active" }, { at: 6, state: "inactive" }];
    expect(episodes(mergeObservations(first, next))).toEqual([
      { first: 2, last: 4, startAfter: 0, endBy: 6, minDuration: 2, maxDuration: 6 },
    ]);
  });
  it("narrows a boundary with additional timestamped observations", () => {
    const points: Observation[] = [{ at: 0, state: "inactive" }, { at: 2, state: "active" }, { at: 4, state: "active" }, { at: 6, state: "inactive" }];
    expect(refinementWindows({ 0: points })).toEqual([[0, 2], [4, 6]]);
    const refined = mergeObservations(points, [{ at: 1.5, state: "inactive" }, { at: 4.5, state: "inactive" }]);
    expect(episodes(refined)[0].maxDuration).toBe(3);
  });
  it("does not invent an arrival before the clip or an end after it", () => {
    expect(episodes([{ at: 0, state: "active" }, { at: 10, state: "active" }])[0]).toMatchObject({
      startAfter: null, endBy: null, minDuration: 10, maxDuration: null,
    });
  });
  it("splits at occlusion instead of treating it as recovery or linking subjects", () => {
    const result = episodes([{ at: 0, state: "active" }, { at: 2, state: "uncertain" }, { at: 4, state: "active" }, { at: 6, state: "inactive" }]);
    expect(result).toHaveLength(2);
    expect(result.every((event) => event.maxDuration === null)).toBe(true);
  });
  it("preserves conflicting overlap judgments as uncertain", () => {
    const merged = mergeObservations([{ at: 2, state: "active" }], [{ at: 2, state: "inactive" }]);
    expect(merged).toEqual([{ at: 2, state: "uncertain" }]);
    expect(timelineStatus(merged)).toBe("uncertain");
    expect(timelineStatus([...merged, { at: 3, state: "active" }])).toBe("match");
    expect(timelineStatus([{ at: 2, state: "inactive" }])).toBe("no_match");
  });
  it("bounds refinement cost and deduplicates shared windows", () => {
    const points: Observation[] = Array.from({ length: 12 }, (_, i) => ({ at: i * 2, state: i % 2 ? "active" : "inactive" }));
    expect(refinementWindows({ 0: points, 1: points })).toHaveLength(4);
    expect(episodes([{ at: 0, state: "inactive" }])).toEqual([]);
  });
});
