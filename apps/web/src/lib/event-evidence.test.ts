import { describe, expect, it } from "vitest";
import { clipForEvent } from "./event-evidence";
import type { BrowserClip } from "./browser-sessions";
const clip = (id: string, start: number, duration: number, url?: string): BrowserClip =>
  ({ id, start, duration, url, width: 640, height: 480 });
describe("event evidence at recorder boundaries", () => {
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
