"use client";

import { useState } from "react";

import type {
  CameraDiscoveryRun,
  CameraOnboardingRun,
  CreateCameraOnboardingInput,
  DiscoveredOnvifDevice,
  EdgeDevice,
} from "@/lib/types";

interface CameraDiscoveryPanelProps {
  devices: EdgeDevice[];
  runs: CameraDiscoveryRun[];
  onboardingRuns: CameraOnboardingRun[];
  busy: boolean;
  canAdminister: boolean;
  onScan: (deviceId: string) => Promise<void>;
  onConnect: (input: CreateCameraOnboardingInput) => Promise<void>;
  onRefresh: () => Promise<void>;
}

interface CredentialForm {
  cameraName: string;
  username: string;
  password: string;
  verifyTls: boolean;
}

function discoveredName(device: DiscoveredOnvifDevice): string {
  const nameScope = device.scopes.find((scope) => scope.includes("/name/"));
  if (nameScope) {
    const value = nameScope.split("/name/").at(-1);
    if (value) {
      try {
        return decodeURIComponent(value).replaceAll("_", " ");
      } catch {
        return value.replaceAll("_", " ");
      }
    }
  }
  return `Camera ${device.remote_address}`;
}

export function CameraDiscoveryPanel({
  devices,
  runs,
  onboardingRuns,
  busy,
  canAdminister,
  onScan,
  onConnect,
  onRefresh,
}: CameraDiscoveryPanelProps) {
  const activeDevices = devices.filter((device) => device.status === "active");
  const [forms, setForms] = useState<Record<string, CredentialForm>>({});

  function formFor(key: string, device: DiscoveredOnvifDevice): CredentialForm {
    return forms[key] ?? {
      cameraName: discoveredName(device),
      username: "admin",
      password: "",
      verifyTls: true,
    };
  }

  function updateForm(
    key: string,
    device: DiscoveredOnvifDevice,
    changes: Partial<CredentialForm>,
  ) {
    setForms((current) => ({
      ...current,
      [key]: { ...formFor(key, device), ...changes },
    }));
  }

  async function connect(
    run: CameraDiscoveryRun,
    device: DiscoveredOnvifDevice,
    key: string,
  ) {
    const endpoint = device.xaddrs[0];
    const form = formFor(key, device);
    if (!endpoint || !form.cameraName.trim() || !form.username.trim()) return;
    await onConnect({
      discovery_run_id: run.id,
      endpoint_url: endpoint,
      camera_name: form.cameraName.trim(),
      username: form.username.trim(),
      password: form.password,
      verify_tls: form.verifyTls,
    });
    updateForm(key, device, { password: "" });
  }

  return (
    <section className="panel discoveryPanel" id="camera-discovery">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Camera onboarding</span>
          <h2>Discover and connect ONVIF cameras</h2>
          <p>
            The selected edge station scans its camera LAN, resolves authenticated media profiles,
            and saves a camera only after reading a real RTSP preview frame.
          </p>
        </div>
        <button disabled={busy} onClick={() => void onRefresh()} type="button">Refresh</button>
      </div>
      {canAdminister && (
        <div className="discoveryActions">
          {activeDevices.map((device) => (
            <button disabled={busy} key={device.id} onClick={() => void onScan(device.id)} type="button">
              Scan from {device.name}
            </button>
          ))}
          {activeDevices.length === 0 && <span className="mutedText">Enroll an active edge device before scanning.</span>}
        </div>
      )}
      <div className="discoveryRuns">
        {runs.length === 0 ? <p className="mutedText">No discovery scans requested.</p> : runs.map((run) => (
          <article key={run.id}>
            <div><strong>{run.status}</strong><small>{new Date(run.created_at).toLocaleString()} · {run.devices.length} device(s)</small></div>
            {run.last_error && <p>{run.last_error}</p>}
            {run.devices.map((device) => {
              const key = `${run.id}-${device.endpoint_reference}`;
              const endpoint = device.xaddrs[0];
              const form = formFor(key, device);
              return (
                <div className="discoveredCamera" key={key}>
                  <strong>{discoveredName(device)}</strong>
                  <span>{endpoint ?? device.endpoint_reference}</span>
                  {canAdminister && endpoint && (
                    <div className="onboardingCredentialForm">
                      <label>
                        Camera name
                        <input
                          maxLength={120}
                          onChange={(event) => updateForm(key, device, { cameraName: event.target.value })}
                          value={form.cameraName}
                        />
                      </label>
                      <label>
                        Username
                        <input
                          autoComplete="username"
                          maxLength={255}
                          onChange={(event) => updateForm(key, device, { username: event.target.value })}
                          value={form.username}
                        />
                      </label>
                      <label>
                        Password
                        <input
                          autoComplete="current-password"
                          maxLength={1000}
                          onChange={(event) => updateForm(key, device, { password: event.target.value })}
                          type="password"
                          value={form.password}
                        />
                      </label>
                      {endpoint.startsWith("https://") && (
                        <label className="checkboxLabel">
                          <input
                            checked={form.verifyTls}
                            onChange={(event) => updateForm(key, device, { verifyTls: event.target.checked })}
                            type="checkbox"
                          />
                          Verify camera TLS certificate
                        </label>
                      )}
                      <button
                        disabled={busy || !form.cameraName.trim() || !form.username.trim()}
                        onClick={() => void connect(run, device, key)}
                        type="button"
                      >
                        Authenticate and verify preview
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </article>
        ))}
      </div>
      <div className="onboardingRuns">
        <h3>Connection verification</h3>
        {onboardingRuns.length === 0 ? (
          <p className="mutedText">No credentialed camera connections requested.</p>
        ) : onboardingRuns.map((run) => {
          const selected = run.profiles.find((profile) => profile.token === run.selected_profile_token);
          return (
            <article key={run.id}>
              <div>
                <strong>{run.camera_name}</strong>
                <small>{run.status} · {new Date(run.created_at).toLocaleString()}</small>
              </div>
              {run.last_error && <p>{run.last_error}</p>}
              {selected && (
                <p>
                  Preview verified · {selected.encoding ?? "video"} · {selected.width ?? "?"}×{selected.height ?? "?"}
                  {selected.frame_rate ? ` · ${selected.frame_rate} FPS` : ""}
                </p>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
