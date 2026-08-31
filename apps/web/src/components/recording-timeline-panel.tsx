"use client";

import { useState } from "react";

import { API_URL } from "@/lib/api";
import type { Camera, RecordingSegment } from "@/lib/types";

interface RecordingTimelinePanelProps {
  camera: Camera | null;
  recordings: RecordingSegment[];
  busy: boolean;
  canAdminister: boolean;
  onLegalHold: (recordingId: string, enabled: boolean) => Promise<void>;
  onRefresh: () => Promise<void>;
  onRunRetention: () => Promise<void>;
}

function bytes(value: number | null): string {
  if (value === null) return "edge only";
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function RecordingTimelinePanel({
  camera,
  recordings,
  busy,
  canAdminister,
  onLegalHold,
  onRefresh,
  onRunRetention,
}: RecordingTimelinePanelProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = recordings.find((item) => item.id === selectedId) ??
    recordings.find((item) => item.status === "ready") ?? null;

  return (
    <section className="panel recordingPanel" id="recordings">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Historical video</span>
          <h2>{camera ? `${camera.name} recordings` : "Select a camera"}</h2>
          <p>Archived edge segments use signed playback links and explicit retention controls.</p>
        </div>
        <div className="recordingHeaderActions">
          <button disabled={busy || !camera} onClick={() => void onRefresh()} type="button">Refresh</button>
          {canAdminister && (
            <button className="secondaryButton" disabled={busy} onClick={() => void onRunRetention()} type="button">
              Run retention
            </button>
          )}
        </div>
      </div>
      <div className="recordingWorkspace">
        <div className="recordingList">
          {recordings.length === 0 ? (
            <p className="mutedText">No historical segments have been cataloged for this camera.</p>
          ) : recordings.map((recording) => (
            <button
              className={`recordingRow ${selected?.id === recording.id ? "recordingRowActive" : ""}`}
              key={recording.id}
              onClick={() => setSelectedId(recording.id)}
              type="button"
            >
              <span><strong>{new Date(recording.started_at).toLocaleString()}</strong><small>{recording.duration_seconds.toFixed(1)} sec · {bytes(recording.size_bytes)}</small></span>
              <i className={`recordingState recordingState-${recording.status}`}>{recording.status.replace("_", " ")}</i>
            </button>
          ))}
        </div>
        <div className="recordingPlayer">
          {selected?.content_url ? (
            <video controls key={selected.id} preload="metadata" src={`${API_URL}${selected.content_url}`} />
          ) : (
            <div className="recordingPlaceholder">{selected ? "Segment remains on its edge device." : "Select an archived segment to play it."}</div>
          )}
          {selected && (
            <div className="recordingDetails">
              <span>{selected.width}×{selected.height} · {selected.fps.toFixed(1)} FPS</span>
              <span>Expires {new Date(selected.expires_at).toLocaleString()}</span>
              {canAdminister && selected.status !== "expired" && (
                <button disabled={busy} onClick={() => void onLegalHold(selected.id, !selected.legal_hold)} type="button">
                  {selected.legal_hold ? "Release legal hold" : "Place legal hold"}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
