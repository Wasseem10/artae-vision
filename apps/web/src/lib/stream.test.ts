import { describe, expect, it } from "vitest";

import { readerScriptUrl } from "../components/live-stream-player";

describe("readerScriptUrl", () => {
  it("loads the reader from the same gateway origin as WHEP", () => {
    expect(readerScriptUrl("http://127.0.0.1:8889/camera-123/whep")).toBe(
      "http://127.0.0.1:8889/reader.js",
    );
  });
});
