import { describe, expect, it } from "vitest";

import { parseApiTimestamp } from "./dates";

describe("parseApiTimestamp", () => {
  it("treats timezone-free API timestamps as UTC", () => {
    expect(parseApiTimestamp("2026-08-24T00:13:57.000000").toISOString()).toBe(
      "2026-08-24T00:13:57.000Z",
    );
  });

  it("preserves timestamps that already include an offset", () => {
    expect(parseApiTimestamp("2026-08-23T20:13:57-04:00").toISOString()).toBe(
      "2026-08-24T00:13:57.000Z",
    );
  });
});
