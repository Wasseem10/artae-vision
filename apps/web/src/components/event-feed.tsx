"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/components/icon";
import { api, evidenceContentUrl } from "@/lib/api";
import type { Camera, EvidenceAsset, StreamStatus, VideoEvent } from "@/lib/types";

interface EventFeedProps {
  events: VideoEvent[];
  cameras: Camera[];
  evidence: EvidenceAsset[];
  streamStatus: StreamStatus;
  canOperate: boolean;
  canAdminister: boolean;
  onRefreshEvidence: () => Promise<void>;
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

export function EventFeed({ events, cameras, evidence, streamStatus, canOperate, canAdminister, onRefreshEvidence }: EventFeedProps) {
  const [selectedAsset, setSelectedAsset] = useState<EvidenceAsset | null>(null);
  const [clipOpened, setClipOpened] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const listedAsset = selectedAsset && evidence.find((candidate) => candidate.id === selectedAsset.id);
  const modalAsset = selectedAsset && listedAsset
    ? listedAsset.status === "expired" || Date.parse(listedAsset.updated_at) > Date.parse(selectedAsset.updated_at)
      ? listedAsset
      : selectedAsset
    : null;

  useEffect(() => {
    if (!selectedAsset) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setSelectedAsset(null);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selectedAsset]);

  function openClip(asset: EvidenceAsset) {
    setSelectedAsset(asset);
    setClipOpened(false);
    setActionError(null);
  }

  async function markReviewed() {
    if (!modalAsset || !clipOpened || modalAsset.reviewed_at || !canOperate || actionBusy) return;
    setActionBusy(true);
    setActionError(null);
    try {
      setSelectedAsset(await api.markEvidenceReviewed(modalAsset.id));
      await onRefreshEvidence();
    } catch (failure) {
      setActionError(failure instanceof Error ? failure.message : "Could not mark this clip reviewed.");
    } finally {
      setActionBusy(false);
    }
  }

  async function toggleLegalHold() {
    if (!modalAsset || !canAdminister || actionBusy) return;
    setActionBusy(true);
    setActionError(null);
    try {
      setSelectedAsset(await api.setEvidenceLegalHold(modalAsset.id, !modalAsset.legal_hold));
      await onRefreshEvidence();
    } catch (failure) {
      setActionError(failure instanceof Error ? failure.message : "Could not change the legal hold.");
    } finally {
      setActionBusy(false);
    }
  }

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
                  : asset?.status === "expired"
                    ? "Expired · clip removed"
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
                      {asset?.content_url && asset.status !== "expired" && (
                        <button
                          className="playClipButton"
                          onClick={() => openClip(asset)}
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

      {modalAsset?.content_url && modalAsset.status !== "expired" && (
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
              key={modalAsset.id}
              onLoadedData={() => {
                setClipOpened(true);
                setActionError(null);
              }}
              onError={() => {
                setClipOpened(false);
                setActionError("The clip could not be loaded. Review remains unavailable.");
              }}
              preload="metadata"
              src={evidenceContentUrl(modalAsset.content_url)}
            />
            <p>
              {modalAsset.duration_seconds === null
                ? "Evidence captured around the alert."
                : `${modalAsset.duration_seconds.toFixed(1)} seconds captured around the alert.`}
            </p>
            <div className="clipModalReview">
              <span>Clip status: {modalAsset.status.replaceAll("_", " ")}</span>
              <span>{modalAsset.expires_at ? `Retention end: ${formatTime(modalAsset.expires_at)}` : "Retention end not set"}</span>
              <span>{modalAsset.legal_hold ? "Legal hold active" : "No legal hold"}</span>
              <span>{modalAsset.reviewed_at ? `Reviewed ${formatTime(modalAsset.reviewed_at)}${modalAsset.reviewed_by ? ` by ${modalAsset.reviewed_by}` : ""}` : "Awaiting operator review"}</span>
            </div>
            {(canOperate || canAdminister) && (
              <div className="clipModalReviewActions">
                {canOperate && !modalAsset.reviewed_at && (
                  <button disabled={!clipOpened || actionBusy} onClick={() => void markReviewed()} type="button">
                    Mark reviewed
                  </button>
                )}
                {canAdminister && (
                  <button disabled={actionBusy} onClick={() => void toggleLegalHold()} type="button">
                    {modalAsset.legal_hold ? "Release legal hold" : "Place legal hold"}
                  </button>
                )}
              </div>
            )}
            {actionError && <p className="clipModalReviewError" role="alert">{actionError}</p>}
          </div>
        </div>
      )}
    </>
  );
}
