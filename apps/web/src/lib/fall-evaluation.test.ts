import { describe, expect, it } from "vitest";
import {
  buildFallEvaluationExport,
  DEFAULT_FALL_EVALUATION_CASES,
  isCompleteFallEvaluation,
  percentile,
  scoreFallEvaluation,
  type FallEvaluationResult,
} from "./fall-evaluation";

const result = (
  id: string,
  expectedEvents: number,
  detections: number[],
  durationSeconds = 10,
): FallEvaluationResult => ({
  id,
  name: id,
  category: expectedEvents ? "fall" : "daily_activity",
  videoUrl: `/${id}.mp4`,
  expectedEvents,
  eventStartSeconds: expectedEvents ? 5 : undefined,
  durationSeconds,
  framesAnalyzed: 100,
  framesWithPose: 90,
  detectedAtSeconds: detections,
  meanInferenceMs: 10,
  p95InferenceMs: 15,
});

describe("fall evaluation scoring", () => {
  it("reports clip-level classification, candidate latency, and false alerts", () => {
    const summary = scoreFallEvaluation([
      result("fall-a", 1, [6]),
      result("fall-b", 1, []),
      result("sitting", 0, []),
      result("bending", 0, [4, 8]),
    ]);

    expect(summary).toMatchObject({
      totalCases: 4,
      passedCases: 2,
      truePositives: 1,
      falsePositives: 1,
      trueNegatives: 1,
      falseNegatives: 1,
      precision: 0.5,
      recall: 0.5,
      accuracy: 0.5,
      totalDetections: 3,
      extraDetections: 2,
      meanDetectionLatencySeconds: 1,
    });
    expect(summary.falseAlertsPerHour).toBe(360);
  });

  it("uses a nearest-rank percentile and handles an empty sample", () => {
    expect(percentile([], 95)).toBe(0);
    expect(percentile([4, 1, 3, 2], 95)).toBe(4);
    expect(percentile([4, 1, 3, 2], 50)).toBe(2);
  });

  it("does not treat partial, failed, or stopped runs as complete exports", () => {
    const complete = DEFAULT_FALL_EVALUATION_CASES.map((definition) => ({
      ...result(
        definition.id,
        definition.expectedEvents,
        definition.expectedEvents ? [8] : [],
      ),
      ...definition,
    }));
    expect(isCompleteFallEvaluation(complete)).toBe(true);
    expect(isCompleteFallEvaluation(complete.slice(0, -1))).toBe(false);
    expect(isCompleteFallEvaluation([...complete.slice(0, -1), complete[0]])).toBe(false);
    expect(isCompleteFallEvaluation([
      ...complete.slice(0, -1),
      { ...complete.at(-1)!, error: "worker failed" },
    ])).toBe(false);

    expect(() => buildFallEvaluationExport("complete", complete.slice(0, -1))).toThrow();
    expect(() => buildFallEvaluationExport("stopped", complete)).toThrow();
    expect(() => buildFallEvaluationExport("failed", complete)).toThrow();

    const exported = buildFallEvaluationExport(
      "complete",
      complete,
      "2026-09-26T00:00:00.000Z",
    );
    expect(exported.status).toBe("complete");
    expect(exported.scoringUnit).toBe("clip");
    expect(exported.summary.totalCases).toBe(5);
    expect(exported.provenance.detector.modelSha256).toMatch(/^[a-f0-9]{64}$/);
    expect(exported.provenance.detector.rule).toBe("BrowserPoseRule/fall-v1");
    expect(exported.provenance).toHaveProperty("codeRevision");
  });
});
