"use client";

import { useState, type FormEvent } from "react";

import { parseApiTimestamp } from "@/lib/dates";
import type {
  AlertChannel,
  AlertIncident,
  CreateAlertChannelInput,
  CreateAlertRouteInput,
  Rule,
} from "@/lib/types";

interface AlertPanelProps {
  alerts: AlertIncident[];
  cameraName: string | null;
  channels: AlertChannel[];
  rules: Rule[];
  busy: boolean;
  onCreateChannel: (input: CreateAlertChannelInput) => Promise<void>;
  onCreateRoute: (ruleId: string, input: CreateAlertRouteInput) => Promise<void>;
  onTransition: (alertId: string, action: "acknowledge" | "resolve") => Promise<void>;
}

export function AlertPanel({
  alerts,
  cameraName,
  channels,
  rules,
  busy,
  onCreateChannel,
  onCreateRoute,
  onTransition,
}: AlertPanelProps) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [ruleId, setRuleId] = useState("");
  const [channelId, setChannelId] = useState("");
  const [cooldown, setCooldown] = useState(60);
  const [delay, setDelay] = useState(0);

  function formatIncidentTime(value: string): string {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(parseApiTimestamp(value));
  }

  async function submitChannel(event: FormEvent) {
    event.preventDefault();
    await onCreateChannel({ name, webhook_url: url, signing_secret: secret });
    setName("");
    setUrl("");
    setSecret("");
  }

  async function submitRoute(event: FormEvent) {
    event.preventDefault();
    await onCreateRoute(ruleId, {
      channel_id: channelId,
      cooldown_seconds: cooldown,
      delay_seconds: delay,
    });
  }

  return (
    <section className="panel alertPanel" id="alerts">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Durable response</span>
          <h2>Alerting</h2>
          <p>
            Review incidents for {cameraName ?? "the selected camera"}, then acknowledge or
            resolve them with a durable audit trail.
          </p>
        </div>
        <span className="statusBadge">
          {alerts.filter((alert) => alert.status === "open").length} open
          {cameraName ? ` · ${cameraName}` : ""}
        </span>
      </div>

      <div className="alertConfigGrid">
        <form className="compactForm" onSubmit={submitChannel}>
          <strong>1. Add webhook destination</strong>
          <label>
            Name
            <input required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} placeholder="Security operations" />
          </label>
          <label>
            HTTPS endpoint
            <input required type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com/video-alerts" />
          </label>
          <label>
            Signing secret
            <input required minLength={16} type="password" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder="At least 16 characters" />
          </label>
          <button disabled={busy} type="submit">Save destination</button>
          <small>The secret is encrypted and is never shown again.</small>
        </form>

        <form className="compactForm" onSubmit={submitRoute}>
          <strong>2. Connect destination to a job</strong>
          <label>
            Job
            <select required value={ruleId} onChange={(event) => setRuleId(event.target.value)}>
              <option value="">Choose a job</option>
              {rules.map((rule) => <option key={rule.id} value={rule.id}>{rule.name}</option>)}
            </select>
          </label>
          <label>
            Destination
            <select required value={channelId} onChange={(event) => setChannelId(event.target.value)}>
              <option value="">Choose a destination</option>
              {channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
            </select>
          </label>
          <div className="splitFields">
            <label>Cooldown (seconds)<input min={0} max={604800} type="number" value={cooldown} onChange={(event) => setCooldown(Number(event.target.value))} /></label>
            <label>Delay (seconds)<input min={0} max={604800} type="number" value={delay} onChange={(event) => setDelay(Number(event.target.value))} /></label>
          </div>
          <button disabled={busy || rules.length === 0 || channels.length === 0} type="submit">Enable alert route</button>
          <small>Delay creates an escalation that is cancelled if someone acknowledges first.</small>
        </form>
      </div>

      <div className="alertList">
        {alerts.length === 0 ? <p className="mutedText">No incidents yet. Events will appear here even before a destination is configured.</p> : alerts.map((alert) => (
          <article className="alertRow" key={alert.id}>
            <div>
              <strong>{alert.event.object_class} · {alert.event.event_type.replaceAll("_", " ")}</strong>
              <p>{alert.event.zone_name} · {Math.round(alert.event.confidence * 100)}% confidence</p>
              <small>{alert.deliveries.length ? alert.deliveries.map((item) => `${item.channel_name}: ${item.status}`).join(" · ") : "Dashboard only · no outbound route"}</small>
              <time dateTime={alert.event.occurred_at}>
                {formatIncidentTime(alert.event.occurred_at)}
              </time>
            </div>
            <div className="alertActions">
              <span className={`alertState alertState-${alert.status}`}>{alert.status}</span>
              {alert.status === "open" && <button aria-label={`Acknowledge ${alert.event.object_class} incident from ${alert.event.zone_name}`} disabled={busy} onClick={() => void onTransition(alert.id, "acknowledge")} type="button">Acknowledge</button>}
              {alert.status !== "resolved" && <button aria-label={`Resolve ${alert.event.object_class} incident from ${alert.event.zone_name}`} className="secondaryButton" disabled={busy} onClick={() => void onTransition(alert.id, "resolve")} type="button">Resolve</button>}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
