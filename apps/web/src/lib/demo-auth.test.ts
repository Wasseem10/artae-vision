import { describe, expect, it } from "vitest";

import { isLocalDemoHost, isLocalDemoLogin } from "./demo-auth";

describe("local demo authentication", () => {
  it("accepts the documented credentials on the native host", () => {
    expect(isLocalDemoLogin("demo@artae.ai", "demo1234", "127.0.0.1")).toBe(true);
  });

  it("normalizes email casing and supports localhost", () => {
    expect(isLocalDemoLogin(" Demo@Artae.AI ", "demo1234", "localhost")).toBe(true);
  });

  it("never enables the demo login on a deployed hostname", () => {
    expect(isLocalDemoHost("app.artae.ai")).toBe(false);
    expect(isLocalDemoLogin("demo@artae.ai", "demo1234", "app.artae.ai")).toBe(false);
  });
});
