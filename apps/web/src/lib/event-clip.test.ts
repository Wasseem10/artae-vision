import { describe, expect, it } from "vitest";
import { eventClipWindow } from "./event-clip";
describe("event clip window", () => {
  it("includes four seconds before a detected event", () => {
    expect(eventClipWindow(30, 200)).toEqual({ start: 26, end: 38 });
  });
  it("does not seek before the source begins or past its end", () => {
    expect(eventClipWindow(1, 100)).toEqual({ start: 0, end: 12 });
    expect(eventClipWindow(99, 100)).toEqual({ start: 95, end: 100 });
    expect(eventClipWindow(0, 3)).toEqual({ start: 0, end: 3 });
  });
});
