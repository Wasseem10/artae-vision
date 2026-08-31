import { describe, expect, it } from "vitest";

import { alertsForCamera, evidenceForEvents, eventsForCamera } from "./incidents";
import type { AlertIncident, EvidenceAsset, VideoEvent } from "./types";

function event(id: string, cameraId: string): VideoEvent {
  return {
    id,
    source_event_id: `source-${id}`,
    schema_version: 2,
    event_type: "zone_entry",
    camera_id: cameraId,
    rule_id: "rule-1",
    track_id: 1,
    object_class: "person",
    zone_name: "Restricted Area",
    entered_at_seconds: 0,
    occurred_at_seconds: 0,
    dwell_seconds: 0,
    confidence: 0.8,
    occurred_at: "2026-08-22T20:37:01Z",
    clip_uri: "clip.mp4",
    details: {},
    verification_status: "not_required",
    verified_at: null,
    verified_by: null,
    created_at: "2026-08-22T20:37:01Z",
  };
}

function alert(videoEvent: VideoEvent): AlertIncident {
  return {
    id: `alert-${videoEvent.id}`,
    event_id: videoEvent.id,
    status: "open",
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
    created_at: videoEvent.created_at,
    updated_at: videoEvent.created_at,
    event: videoEvent,
    deliveries: [],
  };
}

function asset(videoEvent: VideoEvent): EvidenceAsset {
  return {
    id: `asset-${videoEvent.id}`,
    event_id: videoEvent.id,
    status: "ready",
    media_type: "video/mp4",
    size_bytes: 100,
    sha256: "abc",
    duration_seconds: 5,
    provider: "local",
    external_index_id: null,
    external_video_id: null,
    retry_count: 0,
    last_error: null,
    content_url: `/evidence/${videoEvent.id}`,
    created_at: videoEvent.created_at,
    updated_at: videoEvent.created_at,
  };
}

describe("camera incident scope", () => {
  const cameraOneEvent = event("event-1", "camera-1");
  const cameraTwoEvent = event("event-2", "camera-2");

  it("keeps alerts and events from the selected camera only", () => {
    expect(
      alertsForCamera([alert(cameraOneEvent), alert(cameraTwoEvent)], "camera-1").map(
        (item) => item.id,
      ),
    ).toEqual(["alert-event-1"]);
    expect(eventsForCamera([cameraOneEvent, cameraTwoEvent], "camera-1")).toEqual([
      cameraOneEvent,
    ]);
  });

  it("matches evidence to the scoped event list", () => {
    expect(
      evidenceForEvents([asset(cameraOneEvent), asset(cameraTwoEvent)], [cameraOneEvent]).map(
        (item) => item.id,
      ),
    ).toEqual(["asset-event-1"]);
  });

  it("returns an empty scope before a camera is selected", () => {
    expect(alertsForCamera([alert(cameraOneEvent)], null)).toEqual([]);
    expect(eventsForCamera([cameraOneEvent], null)).toEqual([]);
  });
});
