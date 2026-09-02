"use client";

import { useMemo, useState } from "react";

import { Icon } from "@/components/icon";
import { BrowserWebcamPreview } from "@/components/browser-webcam-preview";
import { LiveStreamPlayer } from "@/components/live-stream-player";
import { NativePreview } from "@/components/native-preview";
import { API_URL } from "@/lib/api";
import type { AlertIncident, Camera, CameraAgent, CameraStream, LiveDetection, RecordingSegment, VideoEvent } from "@/lib/types";

interface Props {
  agent: CameraAgent | null;
  alerts: AlertIncident[];
  analysisLabel: string;
  busy: boolean;
  camera: Camera;
  detections: LiveDetection[];
  events: VideoEvent[];
  nativePreviewEnabled: boolean;
  onPreviewAvailabilityChange: (available: boolean) => void;
  onStop: () => Promise<void> | void;
  operating: boolean;
  previewReady: boolean;
  recordings: RecordingSegment[];
  stream: CameraStream | null;
}

function shortTime(value: string) {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(new Date(value));
}

function eventLabel(event: VideoEvent) {
  if (event.details.test === true) return "Safe test completed";
  if (event.details.uploaded_video === true) return "Uploaded video matched";
  const summary = typeof event.details.summary === "string" ? event.details.summary.trim() : "";
  return summary || `Detected ${event.object_class || "the requested condition"}`;
}

function verificationLabel(event: VideoEvent, hasAlert: boolean) {
  if (event.verification_status === "pending" || event.verification_status === "uncertain") return "Needs review";
  if (event.verification_status === "rejected") return "Rejected";
  if (hasAlert) return "Alert created";
  return "Detected";
}

export function MonitoringFeed({ agent, alerts, analysisLabel, busy, camera, detections, events, nativePreviewEnabled, onPreviewAvailabilityChange, onStop, operating, previewReady, recordings, stream }: Props) {
  const [selectedRecordingId, setSelectedRecordingId] = useState<string | null>(null);
  const playableRecordings = useMemo(
    () => [...recordings]
      .filter((recording) => recording.status === "ready" && recording.content_url)
      .sort((left, right) => new Date(left.started_at).getTime() - new Date(right.started_at).getTime()),
    [recordings],
  );
  const selectedRecording = playableRecordings.find((recording) => recording.id === selectedRecordingId) ?? null;
  const streamReady = Boolean(stream?.ready && stream.whep_url);
  const browserPreviewEnabled = camera.source_type === "webcam" && !nativePreviewEnabled && !streamReady;
  const eventLog = useMemo(
    () => [...events].sort((left, right) => new Date(right.occurred_at).getTime() - new Date(left.occurred_at).getTime()),
    [events],
  );
  const alertEventIds = useMemo(() => new Set(alerts.map((alert) => alert.event_id)), [alerts]);
  const timelineValue = selectedRecording ? playableRecordings.findIndex((recording) => recording.id === selectedRecording.id) : playableRecordings.length;
  const recording = operating && agent?.recording_state === "recording";
  const runtimeError = agent?.observed_status === "error" || agent?.health_status === "error";
  const liveStatus = runtimeError
    ? "AI needs attention"
    : operating
      ? recording ? "AI watching · recording" : "AI watching · video live"
      : "Starting camera AI";
  const historyLabel = playableRecordings.length === 0
    ? recording ? "Saving the first playback segment…" : "Playback starts when recording begins"
    : `${playableRecordings.length} saved segment${playableRecordings.length === 1 ? "" : "s"}`;
  const visiblePeople = detections.filter((detection) => detection.label.toLowerCase() === "person").length;
  const emptyLogTitle = browserPreviewEnabled
    ? "Preview only"
    : runtimeError
      ? "AI could not start"
      : operating
        ? visiblePeople > 0
          ? `Watching — ${visiblePeople} ${visiblePeople === 1 ? "person" : "people"} visible`
          : "Watching — no person visible"
        : "Connecting to camera AI";

  function recordingForEvent(event: VideoEvent) {
    const occurredAt = new Date(event.occurred_at).getTime();
    return playableRecordings.find((recording) => occurredAt >= new Date(recording.started_at).getTime() - 2_000 && occurredAt <= new Date(recording.ended_at).getTime() + 2_000) ?? null;
  }

  return (
    <section className="visionMonitorWorkspace">
      <div className="visionRealPreview">
        <header>
          <span><i className={operating && !selectedRecording ? "isOnline" : ""} /><strong>{camera.name}</strong></span>
          <div className="visionFeedMode">{selectedRecording ? <button onClick={() => setSelectedRecordingId(null)} type="button"><i /> Go live</button> : <><em className={runtimeError ? "hasError" : ""}>{liveStatus}</em><button className="visionStopAgent" disabled={busy} onClick={() => void onStop()} title="Stop live analysis and video recording" type="button">Stop camera</button></>}</div>
        </header>
        <div className="visionVideoStage">
          {selectedRecording?.content_url ? <video autoPlay controls key={selectedRecording.id} preload="metadata" src={`${API_URL}${selectedRecording.content_url}`} /> : <>
            {streamReady && stream?.whep_url && <LiveStreamPlayer key={stream.camera_id} name={camera.name} whepUrl={stream.whep_url} />}
            {nativePreviewEnabled && <NativePreview cameraId={camera.id} name={camera.name} onAvailabilityChange={onPreviewAvailabilityChange} />}
            {browserPreviewEnabled && <BrowserWebcamPreview name={camera.name} onAvailabilityChange={onPreviewAvailabilityChange} />}
            {!streamReady && !previewReady && <div className="visionWaitingFeed"><Icon name="camera" /><strong>Waiting for the real camera feed</strong><small>No placeholder image is shown.</small></div>}
            {(streamReady || previewReady) && detections.map((detection, index) => <span className="visionDetection" key={`${detection.track_id ?? index}-${detection.label}`} style={{ height: `${Math.max(0.02, detection.y2 - detection.y1) * 100}%`, left: `${detection.x1 * 100}%`, top: `${detection.y1 * 100}%`, width: `${Math.max(0.02, detection.x2 - detection.x1) * 100}%` }}><b>{detection.label} {Math.round(detection.confidence * 100)}%</b></span>)}
          </>}
          {selectedRecording && <span className="visionPlaybackBadge"><Icon name="clock" /> REPLAY · {shortTime(selectedRecording.started_at)}</span>}
          {!selectedRecording && browserPreviewEnabled && previewReady && <span className="visionPlaybackBadge"><Icon name="camera" /> LOCAL PREVIEW · CAMERA SERVICE NOT CONNECTED</span>}
        </div>
        <div className="visionRuntimeStrip" aria-label="Camera agent status">
          <span><small>AI</small><strong>{runtimeError ? "Problem" : operating ? "Watching" : "Starting"}</strong></span>
          <span><small>DETECTOR</small><strong>{analysisLabel}</strong></span>
          <span><small>VIDEO</small><strong>{recording ? "Recording" : agent?.recording_state === "error" ? "Error" : "Starting"}</strong></span>
          <span><small>PROCESSED</small><strong>{agent?.frames_processed?.toLocaleString() ?? "0"} frames</strong></span>
        </div>
        <div className="visionRewindPanel">
          <div><span><Icon name="clock" /> {historyLabel}</span><strong>{selectedRecording ? shortTime(selectedRecording.started_at) : "LIVE"}</strong></div>
          <input aria-label="Rewind live feed" disabled={playableRecordings.length === 0} max={playableRecordings.length} min={0} onChange={(event) => { const nextIndex = Number(event.target.value); setSelectedRecordingId(nextIndex === playableRecordings.length ? null : playableRecordings[nextIndex]?.id ?? null); }} step={1} type="range" value={timelineValue} />
          <div className="visionRewindLabels"><span>{playableRecordings[0] ? shortTime(playableRecordings[0].started_at) : "Keep this page open; saved video will appear automatically"}</span><span>Now</span></div>
        </div>
      </div>

      <aside aria-label="Detection log" className="visionDetectionLog">
        <header><div><small>DETECTION LOG</small><strong>What the agent saw</strong></div><span>{eventLog.length}</span></header>
        {eventLog.length === 0 ? <div className="visionDetectionEmpty"><Icon name="activity" /><strong>{emptyLogTitle}</strong><p>{browserPreviewEnabled ? "This is only a browser preview. Start the Artae camera service to enable detection, recording, and alerts." : runtimeError ? agent?.last_error ?? "Stop the agent, check the camera service, and try again." : operating ? `${analysisLabel} is analyzing the live video. The requested condition has not been confirmed yet.` : "The camera can appear before the AI is ready. Model loading normally takes several seconds."}</p></div> : <div className="visionDetectionRows">{eventLog.map((event) => {
          const hasAlert = alertEventIds.has(event.id);
          const matchingRecording = recordingForEvent(event);
          return <button disabled={!matchingRecording} key={event.id} onClick={() => matchingRecording && setSelectedRecordingId(matchingRecording.id)} type="button"><i className={event.verification_status === "rejected" ? "isRejected" : ""} /><span><strong>{eventLabel(event)}</strong><small>{shortTime(event.occurred_at)} · {Math.round(event.confidence * 100)}% confidence</small><em>{verificationLabel(event, hasAlert)}{matchingRecording ? " · View moment" : " · Clip processing"}</em></span><Icon name="chevron" /></button>;
        })}</div>}
      </aside>
    </section>
  );
}
