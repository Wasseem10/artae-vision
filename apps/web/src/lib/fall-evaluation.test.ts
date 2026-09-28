import { describe, expect, it } from "vitest";
import {
  buildFallEvaluationExport,
  DEFAULT_FALL_EVALUATION_CASES,
  isCompleteFallEvaluation,
  percentile,
  parseFallEvaluationDataset,
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

  it("compares both rules on identical clip labels and rejects changed media paths", () => {
    const clips = [
      { ...result("fall-01", 1, [4]), postureBaselineDetectedAtSeconds: [3], windowModelDetectedAtSeconds: [4.1] },
      { ...result("adl-01", 0, []), postureBaselineDetectedAtSeconds: [2], windowModelDetectedAtSeconds: [] },
    ];
    expect(scoreFallEvaluation(clips)).toMatchObject({ recall: 1, falsePositives: 0 });
    expect(scoreFallEvaluation(clips, "posture")).toMatchObject({
      recall: 1, falsePositives: 1, falseAlertsPerHour: 360,
    });
    expect(scoreFallEvaluation(clips, "window")).toMatchObject({ recall: 1, falsePositives: 0 });
    const digest = "a".repeat(64);
    const manifest = {
      schemaVersion: 1, datasetId: "urfall-rgb-cam0-v1", source: "source",
      citation: "citation", license: "CC BY-NC-SA 4.0", split: "split",
      labelNote: "approximate", cases: [{
        id: "fall-01", name: "UR Fall fall-01", category: "fall",
        partition: "development", videoUrl: "/vision/urfall/fall-01-cam0-rgb.mp4",
        expectedEvents: 1, eventStartSeconds: 1, frameCount: 30,
        sourceZipSha256: digest, videoSha256: digest,
      }],
    };
    expect(parseFallEvaluationDataset(manifest).cases).toHaveLength(1);
    expect(() => parseFallEvaluationDataset({
      ...manifest, cases: [{ ...manifest.cases[0], videoUrl: "https://other.example/video" }],
    })).toThrow();
  });

  it("keeps the second research set split by subject and rejects a swapped clip", () => {
    const digest = "b".repeat(64);
    const manifest = {
      schemaVersion: 1, datasetId: "gmdcsa24-v2.1", source: "source",
      citation: "citation", license: "source license", split: "subject split",
      labelNote: "author labels", sourceRevision: "5abac7693229900cf80f722e878fbb119211fc1c",
      cases: [
        { id: "gmd-s1-fall-01", name: "dev", category: "fall", partition: "development",
          subjectId: "subject-1", videoUrl: "/vision/gmdcsa24/Subject%201/Fall/01.mp4",
          expectedEvents: 1, eventStartSeconds: 2, videoSha256: digest,
          sourceGitBlobSha1: "a".repeat(40) },
        { id: "gmd-s4-adl-01", name: "reserved", category: "daily_activity", partition: "holdout",
          subjectId: "subject-4", videoUrl: "/vision/gmdcsa24/Subject%204/ADL/01.mp4",
          expectedEvents: 0, videoSha256: digest, sourceGitBlobSha1: "a".repeat(40) },
      ],
    };
    expect(parseFallEvaluationDataset(manifest).cases).toHaveLength(2);
    expect(() => parseFallEvaluationDataset({ ...manifest, cases: [
      manifest.cases[0], { ...manifest.cases[1], partition: "development" },
    ] })).toThrow();
    expect(() => parseFallEvaluationDataset({ ...manifest, cases: [
      manifest.cases[0], { ...manifest.cases[1], videoUrl: "/vision/gmdcsa24/Subject%201/ADL/01.mp4" },
    ] })).toThrow();
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
    expect(exported.schemaVersion).toBe(3);
    expect(exported.scoringUnit).toBe("clip");
    expect(exported.summary.totalCases).toBe(5);
    expect(exported.provenance.detector.modelSha256).toMatch(/^[a-f0-9]{64}$/);
    expect(exported.provenance.detector.rule).toBe("BrowserPoseRule/fall-v2");
    expect(exported.provenance.candidate.name).toBe("PoseWindowLogistic/v1");
    expect(exported.provenance).toHaveProperty("codeRevision");
  });
});
