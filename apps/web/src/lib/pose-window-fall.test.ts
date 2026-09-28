import { describe, expect, it } from "vitest";
import { PoseWindowFallRule, type PoseWindowModel } from "./pose-window-fall";
import type { PoseFeatures } from "./browser-pose";

const model: PoseWindowModel = {
  schemaVersion: 1, name: "test", sampleIntervalSeconds: 0.1,
  featureNames: ["y", "verticality", "aspect", "drop_0.3s", "drop_0.7s",
    "tilt_0.3s", "tilt_0.7s", "aspect_rise_0.3s", "aspect_rise_0.7s",
    "drop_from_recent_min", "pose_coverage_1s"],
  mean: Array(11).fill(0), scale: Array(11).fill(1),
  weights: [0, 0, 0, 20, 0, 0, 0, 0, 0, 0, 0], bias: -1,
  threshold: 0.5, minConsecutiveSamples: 2,
  motionGate: { drop: 0.07, tilt: 0.15, aspectRise: 0.2 },
};
const up: PoseFeatures = { x: 0.5, y: 0.3, verticality: 0.95, aspect: 0.4, visibility: 0.9 };

describe("causal pose window candidate", () => {
  it("ignores still lying posture and alerts on consecutive observed descent", () => {
    const rule = new PoseWindowFallRule(model);
    for (let i = 0; i < 15; i++) expect(rule.update({ ...up, y: 0.8, verticality: 0.2 }, i / 10)).toBe(false);
    const fresh = new PoseWindowFallRule(model);
    for (let i = 0; i < 8; i++) expect(fresh.update(up, i / 10)).toBe(false);
    expect(fresh.update({ ...up, y: 0.42 }, 0.8)).toBe(false);
    expect(fresh.update({ ...up, y: 0.55 }, 0.9)).toBe(true);
    expect(fresh.update({ ...up, y: 0.7 }, 1.0)).toBe(false);
  });

  it("resets confirmation after missing pose and a time gap", () => {
    const rule = new PoseWindowFallRule(model);
    rule.update(up, 0);
    expect(rule.update({ ...up, y: 0.43 }, 0.1)).toBe(false);
    expect(rule.update(null, 0.2)).toBe(false);
    expect(rule.update({ ...up, y: 0.55 }, 0.3)).toBe(false);
    expect(rule.update({ ...up, y: 0.7 }, 2)).toBe(false);
    const lost = new PoseWindowFallRule(model);
    lost.update(up, 0);
    for (let i = 1; i <= 5; i++) expect(lost.update(null, i / 10)).toBe(false);
    expect(lost.update({ ...up, y: 0.75 }, 0.6)).toBe(false);
  });
});
