"use client";

import { useState, type FormEvent, type PointerEvent } from "react";

import { Icon } from "@/components/icon";
import { LiveStreamPlayer } from "@/components/live-stream-player";
import { NativePreview } from "@/components/native-preview";
import { normalizedPoint, svgPoints } from "@/lib/geometry";
import type {
  Camera,
  CameraStream,
  CreateZoneInput,
  GeometryType,
  LiveDetection,
  Zone,
  ZonePoint,
} from "@/lib/types";

interface ZoneEditorProps {
  camera: Camera | null;
  zones: Zone[];
  busy: boolean;
  stream: CameraStream | null;
  streamError: string | null;
  streamLoading: boolean;
  detections: LiveDetection[];
  onCreate: (input: CreateZoneInput) => Promise<void>;
  onRefreshStream: () => void;
}

export function ZoneEditor({
  camera,
  zones,
  busy,
  stream,
  streamError,
  streamLoading,
  detections,
  onCreate,
  onRefreshStream,
}: ZoneEditorProps) {
  const nativeMode = process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "native";
  const [nativePreviewReady, setNativePreviewReady] = useState(false);
  const [name, setName] = useState("loading-zone");
  const [geometryType, setGeometryType] = useState<GeometryType>("polygon");
  const [points, setPoints] = useState<ZonePoint[]>([]);

  function addPoint(event: PointerEvent<HTMLDivElement>) {
    if (!camera || event.button !== 0) return;
    const point = normalizedPoint(
      event.clientX,
      event.clientY,
      event.currentTarget.getBoundingClientRect(),
    );
    setPoints((current) =>
      geometryType === "line" && current.length >= 2 ? current : [...current, point],
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const valid = geometryType === "line" ? points.length === 2 : points.length >= 3;
    if (!camera || !valid) return;
    try {
      await onCreate({ camera_id: camera.id, name: name.trim(), geometry_type: geometryType, points });
      setPoints([]);
      setName(geometryType === "line" ? "entry-line" : "loading-zone");
    } catch {
      // The dashboard displays the API error and preserves the polygon for correction.
    }
  }

  return (
    <section className="panel zonePanel" id="zones">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Spatial logic</span>
          <h2>Scene geometry</h2>
        </div>
        <span className="panelMeta">Normalized coordinates</span>
      </div>

      <div className={`zoneCanvas ${camera ? "" : "zoneCanvasDisabled"}`}>
        {stream?.configured ? (
          <LiveStreamPlayer
            key={stream.camera_id}
            name={camera?.name ?? "Camera"}
            whepUrl={stream.whep_url}
          />
        ) : (
          <div className="scenePlaceholder">
            <div className="sceneWall sceneWallLeft" />
            <div className="sceneWall sceneWallRight" />
            <div className="sceneFloor" />
            <div className="sceneDoor">
              <span />
              <span />
            </div>
            <div className="scenePallets" />
          </div>
        )}
        {!stream?.configured && nativeMode && camera && (
          <NativePreview
            cameraId={camera.id}
            name={camera.name}
            onAvailabilityChange={setNativePreviewReady}
          />
        )}
        {camera && <div className="zoneInteractionLayer" onPointerDown={addPoint} />}
        <div className="cameraOverlay">
          <span
            className={`liveTag ${stream?.ready || nativePreviewReady ? "" : "liveTagWaiting"}`}
          >
            <i /> {stream?.ready || nativePreviewReady
              ? "Live"
              : streamLoading
                ? "Connecting"
                : "Waiting"}
          </span>
          <span className="cameraOverlayName">{camera?.name ?? "Select a camera to draw"}</span>
          {camera && (
            <button className="streamRetry" onClick={onRefreshStream} type="button">
              Retry stream
            </button>
          )}
        </div>
        <svg aria-hidden="true" className="zoneSvg" preserveAspectRatio="none" viewBox="0 0 100 100">
          {detections.map((detection, index) => (
            <g key={`${detection.track_id ?? "d"}-${index}`}>
              <rect
                className="detectionBox"
                height={(detection.y2 - detection.y1) * 100}
                width={(detection.x2 - detection.x1) * 100}
                x={detection.x1 * 100}
                y={detection.y1 * 100}
              />
              <text className="detectionLabel" x={detection.x1 * 100} y={Math.max(3, detection.y1 * 100 - 1)}>
                {detection.label} {Math.round(detection.confidence * 100)}%
                {detection.track_id === null ? "" : ` #${detection.track_id}`}
              </text>
            </g>
          ))}
          {points.length > 1 && geometryType === "polygon" && (
            <polygon className="zonePolygon" points={svgPoints(points)} />
          )}
          {points.length === 2 && geometryType === "line" && (
            <line
              className="zonePolygon"
              x1={points[0].x * 100}
              x2={points[1].x * 100}
              y1={points[0].y * 100}
              y2={points[1].y * 100}
            />
          )}
          {points.map((point, index) => (
            <circle className="zoneHandle" cx={point.x * 100} cy={point.y * 100} key={index} r="1.3" />
          ))}
        </svg>
        {camera && points.length === 0 && !stream?.ready && !nativePreviewReady && (
          <div className="drawHint">
            <Icon name={streamError ? "activity" : "camera"} />
            <strong>
              {streamError
                ? "Media gateway unavailable"
                : nativeMode
                  ? "Native analysis mode"
                  : "Waiting for video"}
            </strong>
            <span>
              {streamError ?? (nativeMode
                ? "The worker can analyze this camera. Browser video arrives when MediaMTX is enabled."
                : stream?.mode === "publisher"
                  ? "Start the MP4 or webcam publisher for this camera"
                  : "The RTSP source will connect when the player opens")}
            </span>
          </div>
        )}
      </div>

      <form className="zoneControls" onSubmit={submit}>
        <label>
          Geometry name
          <input
            disabled={!camera}
            maxLength={120}
            onChange={(event) => setName(event.target.value)}
            required
            value={name}
          />
        </label>
        <label>
          Type
          <select
            disabled={!camera}
            onChange={(event) => {
              const next = event.target.value as GeometryType;
              setGeometryType(next);
              setPoints([]);
              setName(next === "line" ? "entry-line" : "loading-zone");
            }}
            value={geometryType}
          >
            <option value="polygon">Polygon zone</option>
            <option value="line">Crossing line</option>
          </select>
        </label>
        <div className="pointCounter">
          <strong>{points.length}</strong>
          <span>points</span>
        </div>
        <button
          className="buttonSecondary"
          disabled={points.length === 0}
          onClick={() => setPoints((current) => current.slice(0, -1))}
          type="button"
        >
          Undo
        </button>
        <button
          className="buttonSecondary"
          disabled={points.length === 0}
          onClick={() => setPoints([])}
          type="button"
        >
          Clear
        </button>
        <button
          className="buttonPrimary"
          disabled={
            !camera || busy || (geometryType === "line" ? points.length !== 2 : points.length < 3)
          }
          type="submit"
        >
          {busy ? "Saving…" : `Save ${geometryType}`}
        </button>
      </form>

      {zones.length > 0 && (
        <div className="savedZones">
          <span>Saved for this camera</span>
          {zones.map((zone) => (
            <button
              key={zone.id}
              onClick={() => {
                setPoints(zone.points);
                setGeometryType(zone.geometry_type);
                setName(`${zone.name}-copy`);
              }}
              type="button"
            >
              <Icon name="map" /> {zone.name} <small>{zone.geometry_type} · {zone.points.length} pts</small>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
