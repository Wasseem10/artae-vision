import { describe, expect, it } from "vitest";
import { loginDestination } from "./login-destination";

describe("login destination", () => {
  it("returns to the fall monitor by default and only allows the separate experiment explicitly", () => {
    expect(loginDestination("?next=demo")).toBe("/demo");
    for (const search of [
      "",
      "?next=live",
      "?next=https://evil.example",
      "?next=//evil.example",
      "?next=/demo",
    ]) {
      expect(loginDestination(search)).toBe("/live");
    }
  });
});
