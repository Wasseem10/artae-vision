import { describe, expect, it } from "vitest";

import { parseIntervalList } from "./evaluation";

describe("parseIntervalList", () => {
  it("parses comma-separated video intervals", () => {
    expect(parseIntervalList("5-10, 24.5 - 30")).toEqual([
      { start_seconds: 5, end_seconds: 10, label: "event" },
      { start_seconds: 24.5, end_seconds: 30, label: "event" },
    ]);
  });

  it("allows an empty list for a negative clip", () => {
    expect(parseIntervalList("  ")).toEqual([]);
  });

  it("rejects reversed or malformed intervals", () => {
    expect(() => parseIntervalList("10-5")).toThrow("must end after");
    expect(() => parseIntervalList("around five seconds")).toThrow("must look like");
  });
});
