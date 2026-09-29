import { describe, expect, it } from "vitest";
import model from "./fall-window-model.json";
import { MultiPersonFallTracker } from "./multi-person-fall";
import type { PoseFeatures } from "./browser-pose";
import type { PoseWindowModel } from "./pose-window-fall";

const pose = (x: number, y = .3, verticality = .9, aspect = .5): PoseFeatures =>
  ({ x, y, verticality, aspect, visibility: .95 });

describe("multi-person fall tracking", () => {
  it("keeps two people's motion separate when pose result order changes", () => {
    const tracker = new MultiPersonFallTracker(model as PoseWindowModel);
    const alerts: number[] = [];
    for (let frame = 0; frame <= 17; frame++) {
      const t = frame / 10;
      const falling = frame <= 6 ? pose(.25) : frame === 7 ? pose(.25, .35)
        : pose(.25, .7, .3, 1.2);
      const standing = pose(.75);
      const people = frame % 2 ? [standing, falling] : [falling, standing];
      const result = tracker.update(people, t);
      expect(result).toHaveLength(2);
      expect(result.find((item) => item.features.x === .25)?.id).toBe(1);
      expect(result.find((item) => item.features.x === .75)?.id).toBe(2);
      alerts.push(...result.filter((item) => item.temporalHit).map((item) => item.id));
    }
    expect(alerts).toEqual([1]);
  });

  it("drops identity history when two tracks become ambiguous", () => {
    const tracker = new MultiPersonFallTracker(model as PoseWindowModel);
    expect(tracker.update([pose(.4), pose(.6)], 0).map((item) => item.id)).toEqual([1, 2]);
    expect(tracker.update([pose(.5)], .1)).toEqual([]);
    const resumed = tracker.update([pose(.5)], .2);
    expect(resumed.map((item) => item.id)).toEqual([3]);
    expect(resumed[0].temporalHit).toBe(false);
  });

  it("starts a new history after tracking disappears", () => {
    const tracker = new MultiPersonFallTracker(model as PoseWindowModel);
    expect(tracker.update([pose(.25)], 0)[0].id).toBe(1);
    tracker.update([], .2);
    expect(tracker.update([pose(.25)], 1.1)[0].id).toBe(2);
  });

  it("makes room for a new visible person when all track slots were occupied", () => {
    const tracker = new MultiPersonFallTracker(model as PoseWindowModel, 2);
    tracker.update([pose(.1), pose(.4)], 0);
    const visible = tracker.update([pose(.4), pose(.9)], .1);
    expect(visible.map((person) => person.id)).toEqual([2, 3]);
  });
});
