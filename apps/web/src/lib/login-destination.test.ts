import { describe, expect, it } from "vitest";
import { loginDestination } from "./login-destination";

describe("login destination", () => {
  it("returns to the browser demo only for the allowed value", () => {
    expect(loginDestination("?next=demo")).toBe("/demo");
    for (const search of [
      "",
      "?next=https://evil.example",
      "?next=//evil.example",
      "?next=/demo",
    ]) {
      expect(loginDestination(search)).toBe("/app");
    }
  });
});
