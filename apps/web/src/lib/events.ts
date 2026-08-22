import type { VideoEvent } from "@/lib/types";

export function prependUniqueEvent(events: VideoEvent[], event: VideoEvent): VideoEvent[] {
  if (events.some((candidate) => candidate.id === event.id)) return events;
  return [event, ...events].slice(0, 100);
}

