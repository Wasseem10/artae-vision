"use client";

import { useEffect, useState, type FormEvent } from "react";

import { api } from "@/lib/api";
import type { AlertChannel, Camera, HealthAlertRoute, OperationalHealthIncident, OperationalHealthWatchdogStatus } from "@/lib/types";

interface OperationalHealthPanelProps {
  incidents: OperationalHealthIncident[];
  watchdog: OperationalHealthWatchdogStatus | null;
  watchdogError: boolean;
  camera: Camera | null;
  channels: AlertChannel[];
  busy: boolean;
  canAdminister: boolean;
  canOperate: boolean;
  onAcknowledge: (incidentId: string) => Promise<void>;
  onRefresh: () => Promise<void>;
}

export function OperationalHealthPanel({
  incidents,
  watchdog,
  watchdogError,
  camera,
  channels,
  busy,
  canAdminister,
  canOperate,
  onAcknowledge,
  onRefresh,
}: OperationalHealthPanelProps) {
  const [routes, setRoutes] = useState<HealthAlertRoute[]>([]);
  const [channelId, setChannelId] = useState("");
  const [outageAfterSeconds, setOutageAfterSeconds] = useState(120);
  const [routeBusy, setRouteBusy] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);
  const active = incidents.filter((incident) => incident.status !== "resolved");
  const recentlyResolved = incidents.filter((incident) => incident.status === "resolved").slice(0, 5);
  const lastWatchdogCheck = watchdog?.last_successful_evaluation_at
    ? new Date(watchdog.last_successful_evaluation_at).toLocaleString()
    : "unknown";

  useEffect(() => {
    let cancelled = false;
    if (!camera) return;
    api.listHealthAlertRoutes(camera.id).then(
      (nextRoutes) => {
        if (!cancelled) {
          setRoutes(nextRoutes);
          setRouteError(null);
        }
      },
      (failure: unknown) => {
        if (!cancelled) setRouteError(failure instanceof Error ? failure.message : "Could not load outage routes.");
      },
    );
    return () => { cancelled = true; };
  }, [camera]);

  async function createRoute(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!camera || !channelId) return;
    setRouteBusy(true);
    try {
      const route = await api.createHealthAlertRoute(camera.id, channelId, outageAfterSeconds);
      setRoutes((current) => [...current, route]);
      setChannelId("");
      setRouteError(null);
    } catch (failure) {
      setRouteError(failure instanceof Error ? failure.message : "Could not enable outage notification.");
    } finally {
      setRouteBusy(false);
    }
  }

  async function deleteRoute(routeId: string) {
    if (!camera) return;
    setRouteBusy(true);
    try {
      await api.deleteHealthAlertRoute(camera.id, routeId);
      setRoutes((current) => current.filter((route) => route.id !== routeId));
      setRouteError(null);
    } catch (failure) {
      setRouteError(failure instanceof Error ? failure.message : "Could not remove outage notification.");
    } finally {
      setRouteBusy(false);
    }
  }

  return (
    <section className="panel operationalHealthPanel" id="fleet-health-incidents">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Reliability checks</span>
          <h2>Camera and edge health incidents</h2>
          <p>
            While the operations worker is running, it checks heartbeats, live frames, recording,
            and attached edge stations. Problems open incidents automatically and resolve only
            after telemetry recovers. No active incident does not confirm that a camera is staffed.
          </p>
        </div>
        <div className="operationalHealthHeaderActions">
          <span className={`statusBadge ${active.length ? "healthBadgeAttention" : ""}`}>
            {active.length ? `${active.length} active` : "No active incidents"}
          </span>
          <button disabled={busy} onClick={() => void onRefresh()} type="button">Refresh</button>
        </div>
      </div>

      <p role={watchdogError || (watchdog && watchdog.status !== "fresh") ? "alert" : undefined}>
        {watchdogError ? "Watchdog status unavailable. Health checks may not be running." :
          !watchdog ? "Checking watchdog status…" :
          watchdog.status === "never_run" ? "Watchdog has never completed a health check. Incident silence is unverified." :
          watchdog.status === "stale" ? `Watchdog is stale. Last successful check: ${lastWatchdogCheck}. Incident silence is unverified.` :
          `Watchdog checked recently. Last successful check: ${lastWatchdogCheck}. This does not confirm camera coverage.`}
      </p>

      {canAdminister && (
        <div className="healthRouteConfig">
          <div>
            <strong>Outbound camera outage notification</strong>
            <p>Configure a destination for a sustained outage on the selected camera. A webhook response confirms provider acceptance; a signed-in reviewer must separately acknowledge the incident.</p>
          </div>
          {!camera ? (
            <p className="mutedText">Select a camera to manage its outage route.</p>
          ) : (
            <>
              <form className="compactForm" onSubmit={(event) => void createRoute(event)}>
                <strong>{camera.name}</strong>
                <label>
                  Destination
                  <select required value={channelId} onChange={(event) => setChannelId(event.target.value)}>
                    <option value="">Choose a destination</option>
                    {channels.filter((channel) => channel.enabled && !routes.some((route) => route.channel_id === channel.id)).map((channel) => (
                      <option key={channel.id} value={channel.id}>{channel.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Notify after outage persists (seconds)
                  <input required type="number" min={60} max={3600} value={outageAfterSeconds} onChange={(event) => setOutageAfterSeconds(Number(event.target.value))} />
                </label>
                <button disabled={busy || routeBusy || !channelId} type="submit">Enable outage route</button>
                {!channels.some((channel) => channel.enabled) && <small>Add or enable an HTTPS destination in Alerts first.</small>}
              </form>
              {routes.length > 0 && (
                <div className="healthRouteList">
                  {routes.map((route) => (
                    <div key={route.id}>
                      <span>{route.channel_name} · after {route.outage_after_seconds} seconds</span>
                      <button className="secondaryButton" disabled={busy || routeBusy} onClick={() => void deleteRoute(route.id)} type="button">Remove</button>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
          {routeError && <p className="commissioningError" role="alert">{routeError}</p>}
        </div>
      )}

      {active.length === 0 ? (
        <div className="healthEmptyState">
          <strong>No active reliability incidents</strong>
          <span>Intentionally stopped cameras are excluded, so planned downtime does not create noise.</span>
        </div>
      ) : (
        <div className="operationalIncidentList">
          {active.map((incident) => (
            <article className={`operationalIncident operationalIncident-${incident.severity}`} key={incident.id}>
              <div className="operationalIncidentMain">
                <span>{incident.resource_type === "camera" ? "Camera" : "Edge station"} · {incident.resource_name}</span>
                <strong>{incident.title}</strong>
                <p>{incident.detail}</p>
                <small>
                  First detected {new Date(incident.first_detected_at).toLocaleString()} · last confirmed {new Date(incident.last_detected_at).toLocaleString()}
                </small>
                {incident.deliveries?.length ? (
                  <small>
                    Outage notification: {incident.deliveries.map((delivery) =>
                      `${delivery.channel_name}: ${delivery.status === "delivered" ? "webhook accepted" : delivery.status}`,
                    ).join(" · ")}
                  </small>
                ) : incident.resource_type === "camera" && incident.severity === "critical" ? (
                  <small>No outbound outage notification recorded yet</small>
                ) : null}
                {incident.acknowledged_by && incident.acknowledged_at && (
                  <small>
                    Acknowledged by {incident.acknowledged_by} at {new Date(incident.acknowledged_at).toLocaleString()}
                  </small>
                )}
              </div>
              <div className="operationalIncidentActions">
                <span className={`healthSeverity healthSeverity-${incident.severity}`}>{incident.severity}</span>
                {incident.status === "open" && canOperate && (
                  <button disabled={busy} onClick={() => void onAcknowledge(incident.id)} type="button">
                    Acknowledge
                  </button>
                )}
                {incident.status === "acknowledged" && <span className="healthAcknowledged">Acknowledged</span>}
              </div>
            </article>
          ))}
        </div>
      )}

      {recentlyResolved.length > 0 && (
        <details className="resolvedHealthIncidents">
          <summary>Recently recovered systems ({recentlyResolved.length})</summary>
          {recentlyResolved.map((incident) => (
            <div key={incident.id}>
              <strong>{incident.resource_name}</strong>
              <span>{incident.title} · recovered {incident.resolved_at ? new Date(incident.resolved_at).toLocaleString() : "automatically"}</span>
            </div>
          ))}
        </details>
      )}
    </section>
  );
}
