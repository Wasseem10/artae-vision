import { describe, expect, it } from "vitest";

import { prependUniqueEvent } from "./events";
import type { VideoEvent } from "./types";

function event(id: string): VideoEvent {
  return {
    id,
    source_event_id: id,
    schema_version: 1,
    event_type: "object_dwell",
    camera_id: "camera-1",
    rule_id: "rule-1",
    track_id: 7,
    object_class: "person",
    zone_name: "loading-zone",
    entered_at_seconds: 1,
    occurred_at_seconds: 11,
    dwell_seconds: 10,
    confidence: 0.9,
    occurred_at: "2026-08-17T12:00:00Z",
    clip_uri: "clip.mp4",
    details: {},
    created_at: "2026-08-17T12:00:00Z",
  };
}

describe("event ordering", () => {
  it("prepends a new live event", () => {
    expect(prependUniqueEvent([event("old")], event("new")).map((item) => item.id)).toEqual([
      "new",
      "old",
    ]);
  });

  it("does not duplicate a retried event", () => {
    const existing = [event("same")];
    expect(prependUniqueEvent(existing, event("same"))).toBe(existing);
  });
});
