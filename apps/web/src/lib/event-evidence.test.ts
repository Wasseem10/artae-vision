import { describe, expect, it } from "vitest";
import { clipForEvent, recordingGapSeconds } from "./event-evidence";
import type { BrowserClip } from "./browser-sessions";
const clip = (id: string, start: number, duration: number, url?: string): BrowserClip =>
  ({ id, start, duration, url, width: 640, height: 480 });
describe("event evidence at recorder boundaries", () => {
  it("reports distance on either side of the selected recording without a false boundary gap", () => {
    expect(recordingGapSeconds(clip("before", 0, 9.96), 10)).toBeCloseTo(.04);
    expect(recordingGapSeconds(clip("after", 10.03, 5), 10)).toBeCloseTo(.03);
    expect(recordingGapSeconds(clip("inside", 0, 15), 10)).toBe(0);
    expect(recordingGapSeconds(clip("boundary", .1, .2), .1 + .2)).toBe(0);
  });
  it("keeps an event reviewable across a small recorder restart gap", () => {
    const clips = [clip("first", 0, 9.96, "blob:first"), clip("second", 10.03, 9.9, "blob:second")];
    expect(clipForEvent(clips, 10)?.id).toBe("second");
    expect(clipForEvent(clips, 9.8)?.id).toBe("first");
  });
  it("does not substitute unrelated footage for a missing segment", () => {
    expect(clipForEvent([clip("first", 0, 9, "blob:first"), clip("second", 12, 10, "blob:second")], 10)).toBeUndefined();
  });
  it("waits for a playable local or account copy rather than metadata alone", () => {
    expect(clipForEvent([clip("pending", 0, 10)], 4)).toBeUndefined();
    expect(clipForEvent([clip("saved", 0, 10, "https://storage.example/clip")], 4)?.id).toBe("saved");
  });
});
