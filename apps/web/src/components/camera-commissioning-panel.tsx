"use client";

import { useMemo, useState } from "react";

import type {
  Camera,
  CameraCommissioningRun,
  CreateCameraCommissioningInput,
  EdgeDevice,
} from "@/lib/types";

interface CameraCommissioningPanelProps {
  camera: Camera | null;
  devices: EdgeDevice[];
  runs: CameraCommissioningRun[];
  busy: boolean;
  canAdminister: boolean;
  onRun: (input: CreateCameraCommissioningInput) => Promise<void>;
  onRefresh: () => Promise<void>;
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function CameraCommissioningPanel({
  camera,
  devices,
  runs,
  busy,
  canAdminister,
  onRun,
  onRefresh,
}: CameraCommissioningPanelProps) {
  const activeDevices = devices.filter((device) => device.status === "active");
  const defaultDeviceId = camera?.edge_device_id ?? activeDevices[0]?.id ?? "";
  const [selectedDeviceId, setSelectedDeviceId] = useState(defaultDeviceId);
  const effectiveDeviceId = camera?.edge_device_id ?? selectedDeviceId ?? defaultDeviceId;
  const latest = runs[0] ?? null;
  const activeRun = runs.some((run) => run.status === "queued" || run.status === "running");
  const metrics = latest?.metrics;
  const selectedDeviceName = useMemo(
    () => activeDevices.find((device) => device.id === effectiveDeviceId)?.name,
    [activeDevices, effectiveDeviceId],
  );

  async function runCheck() {
    if (!camera || !effectiveDeviceId) return;
    await onRun({
      camera_id: camera.id,
      edge_device_id: camera.edge_device_id ? null : effectiveDeviceId,
      duration_seconds: 8,
      maximum_frames: 120,
    });
  }

  return (
    <section className="panel commissioningPanel" id="camera-health">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Camera commissioning</span>
          <h2>Prove the video feed is usable</h2>
          <p>
            Run a brief, model-free stream check for delivery, resolution, frame rate, exposure,
            focus, and frozen frames. This does not start monitoring or use a paid AI model.
          </p>
        </div>
        <button disabled={busy} onClick={() => void onRefresh()} type="button">
          Refresh
        </button>
      </div>

      {!camera ? (
        <p className="mutedText">Select a camera to run its health check.</p>
      ) : (
        <>
          <div className="commissioningActions">
            <div>
              <strong>{camera.name}</strong>
              <small>
                {camera.edge_device_id
                  ? `Pinned to ${selectedDeviceName ?? "its enrolled edge station"}`
                  : "Choose the edge station that can reach this camera"}
              </small>
            </div>
            {!camera.edge_device_id && (
              <label>
                Edge station
                <select
                  disabled={busy || activeRun}
                  onChange={(event) => setSelectedDeviceId(event.target.value)}
                  value={effectiveDeviceId}
                >
                  <option value="">Select a station</option>
                  {activeDevices.map((device) => (
                    <option key={device.id} value={device.id}>{device.name}</option>
                  ))}
                </select>
              </label>
            )}
            {canAdminister && (
              <button
                disabled={busy || activeRun || !effectiveDeviceId}
                onClick={() => void runCheck()}
                type="button"
              >
                {activeRun ? "Health check in progress" : "Run camera health check"}
              </button>
            )}
          </div>

          {!effectiveDeviceId && (
            <p className="mutedText">Enroll an active edge station before commissioning this camera.</p>
          )}

          {latest ? (
            <div className="commissioningResult">
              <div className="commissioningSummary">
                <span className={`commissioningScore commissioningScore-${latest.status}`}>
                  {latest.readiness_score === null ? "—" : latest.readiness_score}
                </span>
                <div>
                  <strong>{latest.status.replaceAll("_", " ")}</strong>
                  <small>
                    Requested {new Date(latest.created_at).toLocaleString()}
                    {latest.completed_at
                      ? ` · completed ${new Date(latest.completed_at).toLocaleString()}`
                      : " · waiting for the edge worker"}
                  </small>
                </div>
              </div>

              {latest.last_error && <p className="commissioningError">{latest.last_error}</p>}

              {metrics && (
                <div className="commissioningMetrics" aria-label="Camera health metrics">
                  <div><small>Resolution</small><strong>{metrics.width}×{metrics.height}</strong></div>
                  <div><small>Observed FPS</small><strong>{metrics.observed_fps.toFixed(1)}</strong></div>
                  <div><small>Brightness</small><strong>{metrics.brightness_mean.toFixed(0)}</strong></div>
                  <div><small>Sharpness</small><strong>{metrics.sharpness_mean.toFixed(0)}</strong></div>
                  <div><small>Frozen frames</small><strong>{percent(metrics.frozen_frame_ratio)}</strong></div>
                  <div><small>Read failures</small><strong>{metrics.read_failures}</strong></div>
                </div>
              )}

              {latest.findings.length > 0 && (
                <div className="commissioningFindings">
                  {latest.findings.map((finding) => (
                    <article className={`commissioningFinding commissioningFinding-${finding.severity}`} key={finding.key}>
                      <strong>{finding.message}</strong>
                      <p>{finding.guidance}</p>
                    </article>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="mutedText">No health check has been run for this camera yet.</p>
          )}
        </>
      )}
    </section>
  );
}
