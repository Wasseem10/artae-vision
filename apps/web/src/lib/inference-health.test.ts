import { describe, expect, it } from "vitest";
import { InferenceHealth } from "./inference-health";

describe("inference health measurements", () => {
  it("does not invent measurements before results arrive", () => {
    expect(new InferenceHealth().summary()).toEqual({
      samples: 0, medianMs: null, p95Ms: null, processedFps: null,
    });
  });
  it("measures throughput from completion intervals, independently of inference latency", () => {
    const health = new InferenceHealth();
    expect(health.add(1000, 20).processedFps).toBeNull();
    health.add(1100, 40);
    expect(health.add(1200, 100)).toEqual({ samples: 3, medianMs: 40, p95Ms: 94, processedFps: 10 });
  });
  it("discards invalid and non-increasing samples", () => {
    const health = new InferenceHealth();
    const expected = health.add(1000, 20);
    for (const [time, latency] of [[1000, 3], [999, 4], [NaN, 5], [1100, -1], [1100, Infinity]])
      expect(health.add(time, latency)).toEqual(expected);
  });
  it("bounds the window and stops old slow samples affecting current metrics", () => {
    const health = new InferenceHealth();
    health.add(0, 1000);
    for (let i = 1; i <= 30; i++) health.add(i * 200, 10);
    expect(health.summary()).toEqual({ samples: 30, medianMs: 10, p95Ms: 10, processedFps: 5 });
  });
});
