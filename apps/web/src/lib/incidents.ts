import type { AlertIncident, EvidenceAsset, VideoEvent } from "./types";

export function alertsForCamera(
  alerts: AlertIncident[],
  cameraId: string | null,
): AlertIncident[] {
  if (cameraId === null) return [];
  return alerts.filter((alert) => alert.event.camera_id === cameraId);
}

export function eventsForCamera(events: VideoEvent[], cameraId: string | null): VideoEvent[] {
  if (cameraId === null) return [];
  return events.filter((event) => event.camera_id === cameraId);
}

export function evidenceForEvents(
  evidence: EvidenceAsset[],
  events: VideoEvent[],
): EvidenceAsset[] {
  const eventIds = new Set(events.map((event) => event.id));
  return evidence.filter((asset) => eventIds.has(asset.event_id));
}
