import { describe, expect, it } from "vitest";
import {
  BrowserPoseRule,
  type PoseFeatures,
  poseFeatures,
} from "./browser-pose";
const up: PoseFeatures = {
  x: 0.5,
  y: 0.35,
  verticality: 0.95,
  aspect: 0.45,
  visibility: 0.9,
};
const down: PoseFeatures = { ...up, y: 0.75, verticality: 0.2, aspect: 1.7 };
describe("real browser pose rules", () => {
  it("requires sustained observed presence, never just elapsed playback", () => {
    const r = new BrowserPoseRule("presence");
    for (let t = 0; t < 10; t += 0.1) expect(r.update(null, t)).toBe(false);
    expect(r.update(up, 10)).toBe(false);
    for (let t = 10.2; t < 11; t += 0.2) r.update(up, t);
    expect(r.update(up, 11.1)).toBe(true);
    expect(r.update(up, 11.2)).toBe(false);
  });
  it("does not flag an already lying person or normal sitting", () => {
    for (const posture of [down, { ...up, y: 0.7 }]) {
      const r = new BrowserPoseRule("fall");
      for (let i = 0; i < 30; i++)
        expect(r.update(posture, i / 10)).toBe(false);
    }
  });
  it("requires upright -> descent -> continuously horizontal", () => {
    const r = new BrowserPoseRule("fall");
    for (let i = 0; i <= 10; i++) expect(r.update(up, i / 10)).toBe(false);
    expect(r.update({ ...up, y: 0.55 }, 1.1)).toBe(false);
    expect(r.update(down, 1.2)).toBe(false);
    expect(r.update(down, 1.7)).toBe(false);
    expect(r.update(down, 2.1)).toBe(true);
    expect(r.update(down, 2.2)).toBe(false);
  });
  it("does not bridge a tracking gap or backward seek into a fall", () => {
    const r = new BrowserPoseRule("fall");
    for (let i = 0; i <= 10; i++) r.update(up, i / 10);
    for (let i = 0; i < 15; i++)
      expect(r.update(down, 10 + i / 10)).toBe(false);
    expect(r.update(down, 0)).toBe(false);
  });
  it("requires visible core landmarks", () =>
    expect(poseFeatures([], 640, 480)).toBeNull());
});
