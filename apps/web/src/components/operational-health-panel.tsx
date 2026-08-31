"use client";

import type { OperationalHealthIncident } from "@/lib/types";

interface OperationalHealthPanelProps {
  incidents: OperationalHealthIncident[];
  busy: boolean;
  canOperate: boolean;
  onAcknowledge: (incidentId: string) => Promise<void>;
  onRefresh: () => Promise<void>;
}

export function OperationalHealthPanel({
  incidents,
  busy,
  canOperate,
  onAcknowledge,
  onRefresh,
}: OperationalHealthPanelProps) {
  const active = incidents.filter((incident) => incident.status !== "resolved");
  const recentlyResolved = incidents.filter((incident) => incident.status === "resolved").slice(0, 5);

  return (
    <section className="panel operationalHealthPanel" id="fleet-health-incidents">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Always-on reliability</span>
          <h2>Camera and edge health incidents</h2>
          <p>
            The operations worker continuously watches heartbeats, live frames, recording, and
            attached edge stations. Problems open incidents automatically and resolve themselves
            only after telemetry recovers.
          </p>
        </div>
        <div className="operationalHealthHeaderActions">
          <span className={`statusBadge ${active.length ? "healthBadgeAttention" : ""}`}>
            {active.length ? `${active.length} active` : "All monitored systems healthy"}
          </span>
          <button disabled={busy} onClick={() => void onRefresh()} type="button">Refresh</button>
        </div>
      </div>

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
