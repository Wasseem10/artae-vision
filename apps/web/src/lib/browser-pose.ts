export type Landmark = { x: number; y: number; visibility?: number };
export type BrowserJob = "presence" | "fall";
export type PoseFeatures = {
  y: number;
  verticality: number;
  aspect: number;
  visibility: number;
  x: number;
};
export const POSE_CONNECTIONS = [
  [11, 12],
  [11, 13],
  [13, 15],
  [12, 14],
  [14, 16],
  [11, 23],
  [12, 24],
  [23, 24],
  [23, 25],
  [25, 27],
  [24, 26],
  [26, 28],
];

export function poseFeatures(
  points: Landmark[],
  width: number,
  height: number,
): PoseFeatures | null {
  const core = [11, 12, 23, 24].map((i) => points[i]);
  if (
    width <= 0 ||
    height <= 0 ||
    core.some(
      (p) =>
        !p ||
        (p.visibility ?? 0) < 0.6 ||
        !Number.isFinite(p.x) ||
        !Number.isFinite(p.y),
    )
  )
    return null;
  const [ls, rs, lh, rh] = core;
  const sx = (ls.x + rs.x) / 2,
    sy = (ls.y + rs.y) / 2;
  const hx = (lh.x + rh.x) / 2,
    hy = (lh.y + rh.y) / 2;
  const dx = (hx - sx) * width,
    dy = (hy - sy) * height;
  const length = Math.hypot(dx, dy);
  if (length < 8) return null;
  const visible = points.filter(
    (p) =>
      (p.visibility ?? 0) >= 0.6 &&
      Number.isFinite(p.x) &&
      Number.isFinite(p.y),
  );
  const bw =
    (Math.max(...visible.map((p) => p.x)) -
      Math.min(...visible.map((p) => p.x))) *
    width;
  const bh =
    (Math.max(...visible.map((p) => p.y)) -
      Math.min(...visible.map((p) => p.y))) *
    height;
  return {
    y: (sy + hy) / 2,
    x: (sx + hx) / 2,
    verticality: Math.abs(dy) / length,
    aspect: bw / Math.max(bh, 1),
    visibility: Math.min(...core.map((p) => p.visibility ?? 0)),
  };
}

/** Conservative one-person temporal heuristic, NOT a medically validated fall classifier.
 * No event on a timer, already-lying posture, tracking loss, or unsupported prompts. */
export class BrowserPoseRule {
  private last: { f: PoseFeatures; t: number } | null = null;
  private phase: "unarmed" | "upright" | "descending" | "alerted" = "unarmed";
  private visibleSince: number | null = null;
  private missingSince: number | null = null;
  private downSince: number | null = null;
  private candidate = 0;
  private uprightSince: number | null = null;
  private lastAlert = -Infinity;
  constructor(readonly job: BrowserJob) {}
  get status() {
    return this.phase;
  }
  update(f: PoseFeatures | null, t: number): boolean {
    if (!Number.isFinite(t)) return false;
    if (!f) {
      this.missingSince ??= t;
      if (t - this.missingSince > 0.8) this.reset();
      return false;
    }
    this.missingSince = null;
    const previous = this.last;
    // A seek, suspended tab, long gap or a different person must not become a fall.
    if (
      previous &&
      (t <= previous.t ||
        t - previous.t > 1 ||
        Math.abs(f.x - previous.f.x) > 0.25)
    )
      this.reset();
    this.visibleSince ??= t;
    const dt = this.last ? t - this.last.t : 0;
    const speed = this.last && dt > 0 ? (f.y - this.last.f.y) / dt : 0;
    this.last = { f, t };
    const upright = f.verticality > 0.75 && f.aspect < 1.05;
    if (this.job === "presence") {
      if (
        this.phase !== "alerted" &&
        t - this.visibleSince >= 1 &&
        t - this.lastAlert > 10
      ) {
        this.phase = "alerted";
        this.lastAlert = t;
        return true;
      }
      return false;
    }
    if (upright) this.uprightSince ??= t;
    else this.uprightSince = null;
    if (
      this.phase === "unarmed" &&
      this.uprightSince !== null &&
      t - this.uprightSince > 0.5
    )
      this.phase = "upright";
    else if (this.phase === "upright" && speed > 0.3) {
      this.phase = "descending";
      this.candidate = t;
    } else if (this.phase === "descending") {
      if (t - this.candidate > 3) {
        this.reset();
        return false;
      }
      if (f.verticality < 0.48 && f.aspect > 0.9) {
        this.downSince ??= t;
        if (t - this.downSince >= 0.8 && t - this.lastAlert > 10) {
          this.phase = "alerted";
          this.lastAlert = t;
          return true;
        }
      } else this.downSince = null;
    } else if (
      this.phase === "alerted" &&
      this.uprightSince !== null &&
      t - this.uprightSince > 1
    )
      this.reset();
    return false;
  }
  private reset() {
    this.last = null;
    this.phase = "unarmed";
    this.visibleSince = null;
    this.downSince = null;
    this.uprightSince = null;
  }
}
