"use client";

import { useState, type FormEvent } from "react";

import { Icon } from "@/components/icon";
import { StatusPill } from "@/components/status-pill";
import type { Camera, CreateCameraInput } from "@/lib/types";

interface CameraPanelProps {
  cameras: Camera[];
  selectedCameraId: string | null;
  busy: boolean;
  onSelect: (cameraId: string) => void;
  onCreate: (input: CreateCameraInput) => Promise<void>;
}

export function CameraPanel({
  cameras,
  selectedCameraId,
  busy,
  onSelect,
  onCreate,
}: CameraPanelProps) {
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [source, setSource] = useState("webcam:0");

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await onCreate({ name: name.trim(), source_uri: source.trim() });
      setName("");
      setSource("webcam:0");
      setShowForm(false);
    } catch {
      // The dashboard displays the API error and keeps this form open for correction.
    }
  }

  return (
    <section className="panel cameraPanel" id="cameras">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Sources</span>
          <h2>Cameras</h2>
        </div>
        <button className="iconButton" onClick={() => setShowForm((value) => !value)} type="button">
          <Icon name="plus" />
          <span className="srOnly">Open camera form</span>
        </button>
      </div>

      {showForm && (
        <form className="inlineForm" onSubmit={submit}>
          <label>
            Camera name
            <input
              autoFocus
              maxLength={120}
              onChange={(event) => setName(event.target.value)}
              placeholder="Front entrance"
              required
              value={name}
            />
          </label>
          <label>
            Video source
            <input
              maxLength={2048}
              onChange={(event) => setSource(event.target.value)}
              placeholder="webcam:0 or rtsp://..."
              required
              value={source}
            />
          </label>
          <div className="formActions">
            <button className="buttonSecondary" onClick={() => setShowForm(false)} type="button">
              Cancel
            </button>
            <button className="buttonPrimary" disabled={busy} type="submit">
              {busy ? "Saving…" : "Add camera"}
            </button>
          </div>
        </form>
      )}

      <div className="cameraList">
        {cameras.length === 0 ? (
          <div className="emptyCompact">
            <Icon name="camera" />
            <p>No cameras yet.</p>
            <button className="textButton" onClick={() => setShowForm(true)} type="button">
              Register your first source
            </button>
          </div>
        ) : (
          cameras.map((camera) => (
            <button
              className={`cameraRow ${camera.id === selectedCameraId ? "cameraRowSelected" : ""}`}
              key={camera.id}
              onClick={() => onSelect(camera.id)}
              type="button"
            >
              <span className="cameraGlyph">
                <Icon name="camera" />
              </span>
              <span className="cameraCopy">
                <strong>{camera.name}</strong>
                <small>
                  {camera.source_type.toUpperCase()} · {camera.source_uri}
                </small>
              </span>
              <StatusPill status={camera.status} />
              <Icon className="rowChevron" name="chevron" />
            </button>
          ))
        )}
      </div>
    </section>
  );
}
