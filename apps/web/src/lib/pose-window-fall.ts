import type { PoseFeatures } from "./browser-pose";

export type PoseWindowModel = {
  schemaVersion: 1;
  name: string;
  sampleIntervalSeconds: number;
  featureNames: string[];
  mean: number[];
  scale: number[];
  weights: number[];
  bias: number;
  threshold: number;
  minConsecutiveSamples: number;
  motionGate: { drop: number; tilt: number; aspectRise: number };
};

const FEATURE_NAMES = [
  "y", "verticality", "aspect", "drop_0.3s", "drop_0.7s",
  "tilt_0.3s", "tilt_0.7s", "aspect_rise_0.3s",
  "aspect_rise_0.7s", "drop_from_recent_min", "pose_coverage_1s",
];

type Sample = { t: number; f: PoseFeatures | null };

/** Research candidate; caller must separately validate before using for real alerts. */
export class PoseWindowFallRule {
  private history: Sample[] = [];
  private previousTime = -Infinity;
  private consecutive = 0;
  private lastAlert = -Infinity;
  private missingSince: number | null = null;

  constructor(readonly model: PoseWindowModel) {
    if (model.schemaVersion !== 1 ||
        JSON.stringify(model.featureNames) !== JSON.stringify(FEATURE_NAMES) ||
        model.mean.length !== FEATURE_NAMES.length ||
        model.scale.length !== FEATURE_NAMES.length ||
        model.weights.length !== FEATURE_NAMES.length ||
        model.scale.some((value) => !Number.isFinite(value) || value <= 0)) {
      throw new Error("Invalid pose window model");
    }
  }

  update(f: PoseFeatures | null, t: number): boolean {
    if (!Number.isFinite(t)) return false;
    if (t <= this.previousTime || t - this.previousTime > 1) {
      this.history = [];
      this.consecutive = 0;
      this.missingSince = null;
    }
    this.previousTime = t;
    if (!f) this.missingSince ??= t;
    else if (this.missingSince !== null) {
      if (t - this.missingSince > 0.3) this.history = [];
      this.missingSince = null;
    }
    this.history = this.history.filter((sample) => t - sample.t <= 1);
    this.history.push({ t, f });
    if (!f) {
      this.consecutive = 0;
      return false;
    }
    const valid = this.history.filter((sample): sample is { t: number; f: PoseFeatures } => !!sample.f);
    const prior = (lag: number) => {
      const earlier = valid.filter((sample) => sample.t <= t - lag + 1e-6);
      return (earlier.at(-1) ?? valid[0]).f;
    };
    const p03 = prior(0.3), p07 = prior(0.7);
    const aspect = Math.min(f.aspect, 3);
    const values = [
      f.y, f.verticality, aspect,
      f.y - p03.y, f.y - p07.y,
      p03.verticality - f.verticality, p07.verticality - f.verticality,
      aspect - Math.min(p03.aspect, 3), aspect - Math.min(p07.aspect, 3),
      f.y - Math.min(...valid.map((sample) => sample.f.y)),
      valid.length / this.history.length,
    ];
    const gate = this.model.motionGate;
    if (Math.max(values[3], values[4]) <= gate.drop &&
        Math.max(values[5], values[6]) <= gate.tilt &&
        Math.max(values[7], values[8]) <= gate.aspectRise) {
      this.consecutive = 0;
      return false;
    }
    const z = values.reduce((total, value, index) =>
      total + ((value - this.model.mean[index]) / this.model.scale[index]) * this.model.weights[index],
    this.model.bias);
    const probability = 1 / (1 + Math.exp(-Math.max(-30, Math.min(30, z))));
    this.consecutive = probability >= this.model.threshold ? this.consecutive + 1 : 0;
    if (this.consecutive >= this.model.minConsecutiveSamples && t - this.lastAlert > 10) {
      this.lastAlert = t;
      this.consecutive = 0;
      return true;
    }
    return false;
  }
}
