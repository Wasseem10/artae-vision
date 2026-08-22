"use client";

import { useState, type FormEvent } from "react";

import type { EdgeDevice, EdgeDeviceCredential, EdgeFleetDevice } from "@/lib/types";

interface EdgeDevicesPanelProps {
  devices: EdgeDevice[];
  fleet: EdgeFleetDevice[];
  busy: boolean;
  canAdminister: boolean;
  onCreate: (name: string, capacity: number) => Promise<EdgeDeviceCredential>;
  onDemoProfile: (deviceId: string) => Promise<void>;
  onRotate: (deviceId: string) => Promise<EdgeDeviceCredential>;
  onRevoke: (deviceId: string) => Promise<void>;
}

export function EdgeDevicesPanel({
  devices,
  fleet,
  busy,
  canAdminister,
  onCreate,
  onDemoProfile,
  onRotate,
  onRevoke,
}: EdgeDevicesPanelProps) {
  const [name, setName] = useState("");
  const [capacity, setCapacity] = useState(1);
  const [credential, setCredential] = useState<EdgeDeviceCredential | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const created = await onCreate(name, capacity);
    setCredential(created);
    setName("");
  }

  return (
    <section className="panel edgeDevicesPanel" id="edge-devices">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Managed execution</span>
          <h2>Edge devices</h2>
          <p>Enroll inference hosts and limit how many camera streams each may run.</p>
        </div>
        <span className="statusBadge">
          {devices.filter((device) => device.status === "active").length} active
        </span>
      </div>

      {credential && (
        <div className="credentialNotice" role="status">
          <strong>Save this device token now</strong>
          <p>It is shown once and stored by the API only as a hash.</p>
          <code>{credential.token}</code>
          <button onClick={() => void navigator.clipboard.writeText(credential.token)} type="button">
            Copy token
          </button>
          <button className="secondaryButton" onClick={() => setCredential(null)} type="button">
            I saved it
          </button>
        </div>
      )}

      {canAdminister && (
        <form className="edgeEnrollment" onSubmit={submit}>
          <label>
            Device name
            <input
              maxLength={120}
              onChange={(event) => setName(event.target.value)}
              placeholder="Loading dock GPU host"
              required
              value={name}
            />
          </label>
          <label>
            Concurrent cameras
            <input
              max={32}
              min={1}
              onChange={(event) => setCapacity(Number(event.target.value))}
              type="number"
              value={capacity}
            />
          </label>
          <button disabled={busy} type="submit">
            Enroll device
          </button>
        </form>
      )}

      <div className="deviceList">
        {devices.length === 0 ? (
          <p className="mutedText">No edge devices enrolled yet.</p>
        ) : (
          devices.map((device) => {
            const fleetDevice = fleet.find((item) => item.device.id === device.id);
            const profile = fleetDevice?.profile;
            return (
            <article className="deviceRow" key={device.id}>
              <div>
                <strong>{device.name}</strong>
                <p>
                  Capacity {device.max_concurrent_streams} · credential {device.credential_fingerprint}
                </p>
                <small>
                  {device.last_seen_at
                    ? `Last seen ${new Date(device.last_seen_at).toLocaleString()}`
                    : "Never connected"}
                  {device.last_worker_id ? ` · ${device.last_worker_id}` : ""}
                </small>
                {profile ? (
                  <div className="fleetHealth">
                    <span className={`fleetHealthState fleetHealth-${profile.health_status}`}>{profile.health_status}</span>
                    <span>{profile.os_name} · {profile.architecture} · {profile.cpu_count} CPU</span>
                    <span>{profile.accelerator ?? "CPU inference"}</span>
                    <span>Worker {profile.worker_version} · offline queue {profile.offline_queue_depth}</span>
                    {fleetDevice?.config && <span>Signed config revision {fleetDevice.config.revision}</span>}
                    {fleetDevice?.update && <span>Latest update: {fleetDevice.update.status.replaceAll("_", " ")}</span>}
                  </div>
                ) : canAdminister ? (
                  <button className="fleetPreviewButton" disabled={busy} onClick={() => void onDemoProfile(device.id)} type="button">Preview fleet health</button>
                ) : null}
              </div>
              <span className={`deviceState deviceState-${device.status}`}>{device.status}</span>
              {canAdminister && device.status === "active" && (
                <div className="deviceActions">
                  <button
                    className="secondaryButton"
                    disabled={busy}
                    onClick={() => void onRotate(device.id).then(setCredential)}
                    type="button"
                  >
                    Rotate token
                  </button>
                  <button disabled={busy} onClick={() => void onRevoke(device.id)} type="button">
                    Revoke
                  </button>
                </div>
              )}
            </article>
            );
          })
        )}
      </div>
    </section>
  );
}
