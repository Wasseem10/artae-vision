"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/components/icon";
import { evidenceContentUrl } from "@/lib/api";
import type { Camera, EvidenceAsset, StreamStatus, VideoEvent } from "@/lib/types";

interface EventFeedProps {
  events: VideoEvent[];
  cameras: Camera[];
  evidence: EvidenceAsset[];
  streamStatus: StreamStatus;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function eventLabel(eventType: string): string {
  return eventType.replaceAll("_", " ");
}

export function EventFeed({ events, cameras, evidence, streamStatus }: EventFeedProps) {
  const [selectedAsset, setSelectedAsset] = useState<EvidenceAsset | null>(null);

  useEffect(() => {
    if (!selectedAsset) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setSelectedAsset(null);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selectedAsset]);

  return (
    <>
      <section className="panel eventPanel" id="events">
        <div className="panelHeader">
          <div>
            <span className="eyebrow">Committed evidence</span>
            <h2>Event timeline</h2>
          </div>
          <span className={`streamState stream-${streamStatus}`}>
            <i /> {streamStatus === "live" ? "Live updates" : streamStatus}
          </span>
        </div>

        {events.length === 0 ? (
          <div className="emptyEvents">
            <span className="eventRadar">
              <i />
            </span>
            <strong>Listening for the first event</strong>
            <p>Deploy at least one camera job. Committed events appear here instantly.</p>
          </div>
        ) : (
          <div className="eventList">
            {events.map((event) => {
              const camera = cameras.find((candidate) => candidate.id === event.camera_id);
              const asset = evidence.find((candidate) => candidate.event_id === event.id);
              const isTest = event.details.test === true;
              const clipLabel =
                isTest
                  ? "Test alert · no clip"
                  : asset?.status === "ready"
                  ? "Search ready"
                  : asset?.status === "indexing"
                    ? "Indexing"
                    : asset?.content_url
                      ? "Clip playable"
                      : "Finishing clip";
              return (
                <article className="eventRow" key={event.id}>
                  <div className="eventThumb">
                    <span>{event.object_class.slice(0, 1).toUpperCase()}</span>
                    <small>
                      {event.track_id === null ? "aggregate" : `track ${event.track_id}`}
                    </small>
                  </div>
                  <div className="eventBody">
                    <div className="eventTitle">
                      <strong>
                        {event.object_class} · {eventLabel(event.event_type)}
                      </strong>
                      <time dateTime={event.occurred_at}>{formatTime(event.occurred_at)}</time>
                    </div>
                    <p>
                      {camera?.name ?? "Camera"} · {event.zone_name}
                    </p>
                    <div className="eventFacts">
                      {event.dwell_seconds > 0 && (
                        <span>
                          <Icon name="clock" /> {event.dwell_seconds.toFixed(1)}s
                        </span>
                      )}
                      {typeof event.details.count === "number" && (
                        <span>Count {event.details.count}</span>
                      )}
                      {typeof event.details.direction === "string" && (
                        <span>{event.details.direction} direction</span>
                      )}
                      <span>{Math.round(event.confidence * 100)}% confidence</span>
                      {isTest && <span className="testEventBadge">Test</span>}
                      <span className={`clipState clip-${asset?.status ?? "pending"}`}>
                        {clipLabel}
                      </span>
                      {asset?.content_url && (
                        <button
                          className="playClipButton"
                          onClick={() => setSelectedAsset(asset)}
                          type="button"
                        >
                          Play clip
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {selectedAsset?.content_url && (
        <div
          aria-labelledby="event-clip-title"
          aria-modal="true"
          className="clipModalBackdrop"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) setSelectedAsset(null);
          }}
          role="dialog"
        >
          <div className="clipModal">
            <div className="clipModalHeader">
              <div>
                <span className="eyebrow">Recorded evidence</span>
                <h2 id="event-clip-title">Alert clip</h2>
              </div>
              <button
                aria-label="Close alert clip"
                className="clipModalClose"
                onClick={() => setSelectedAsset(null)}
                type="button"
              >
                ×
              </button>
            </div>
            <video
              autoPlay
              controls
              key={selectedAsset.id}
              preload="metadata"
              src={evidenceContentUrl(selectedAsset.content_url)}
            />
            <p>
              {selectedAsset.duration_seconds === null
                ? "Evidence captured around the alert."
                : `${selectedAsset.duration_seconds.toFixed(1)} seconds captured around the alert.`}
            </p>
          </div>
        </div>
      )}
    </>
  );
}
