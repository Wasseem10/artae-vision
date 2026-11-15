import { describe, expect, it } from "vitest";
import { VideoSourceHealth } from "./video-source-health";

describe("video source liveness", () => {
  it("uses wall time to stop a frozen source at the deadline", () => {
    const source = new VideoSourceHealth(40000);
    expect(source.stalled(2, 4, 40000)).toBe(false);
    expect(source.stalled(2, 4, 54999)).toBe(false);
    expect(source.stalled(2, 4, 55000)).toBe(true);
  });
  it("allows advancing footage and brief buffering to recover", () => {
    const source = new VideoSourceHealth(0);
    source.stalled(0, 4, 0);
    expect(source.stalled(0, 1, 14000)).toBe(false);
    expect(source.stalled(0.1, 4, 14999)).toBe(false);
    expect(source.stalled(0.2, 4, 29000)).toBe(false);
    expect(source.stalled(0.2, 4, 43999)).toBe(false);
    expect(source.stalled(0.2, 4, 44000)).toBe(true);
  });
  it("does not count an advancing clock without decoded frames as recovery", () => {
    const source = new VideoSourceHealth(0);
    source.stalled(0, 4, 0);
    expect(source.stalled(14, 1, 14000)).toBe(false);
    expect(source.stalled(15, 1, 15000)).toBe(true);
  });
  it("does not let invalid or rewound source timestamps renew liveness", () => {
    for (const time of [NaN, Infinity, -1, 1]) {
      const source = new VideoSourceHealth(0);
      source.stalled(2, 4, 0);
      expect(source.stalled(time, 4, 14999)).toBe(false);
      expect(source.stalled(time, 4, 15000)).toBe(true);
    }
  });
  it("starts a fresh deadline for each new session", () => {
    const old = new VideoSourceHealth(0);
    old.stalled(10, 4, 0);
    expect(old.stalled(10, 4, 15000)).toBe(true);
    const fresh = new VideoSourceHealth(60000);
    expect(fresh.stalled(0, 4, 60000)).toBe(false);
    expect(fresh.stalled(0.1, 4, 61000)).toBe(false);
  });
});
