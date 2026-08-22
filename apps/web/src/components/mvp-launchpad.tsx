import { Icon } from "@/components/icon";
import type { AgentTelemetry, Camera, CameraAgent, Rule, VideoEvent } from "@/lib/types";

type BrowserPermission = NotificationPermission | "unsupported";

interface MvpLaunchpadProps {
  camera: Camera | null;
  rules: Rule[];
  agent: CameraAgent | null;
  telemetry: AgentTelemetry | null;
  latestEvent: VideoEvent | null;
  notificationPermission: BrowserPermission;
  busy: boolean;
  onEnableNotifications: () => void;
  onStart: () => void;
  onStop: () => void;
  onTestAlert: (ruleId: string) => void;
}

export function MvpLaunchpad({
  camera,
  rules,
  agent,
  telemetry,
  latestEvent,
  notificationPermission,
  busy,
  onEnableNotifications,
  onStart,
  onStop,
  onTestAlert,
}: MvpLaunchpadProps) {
  const activeRule = rules.find((rule) => rule.status === "active") ?? null;
  const running = agent?.desired_status === "running";
  const notificationsReady = notificationPermission === "granted";
  const ready = Boolean(camera && activeRule && running);
  const steps = [
    { label: "Camera selected", complete: Boolean(camera), target: "#cameras" },
    { label: "Job reviewed and active", complete: Boolean(activeRule), target: "#rules" },
    { label: "Analysis running", complete: running, target: "#agent" },
    { label: "Browser alerts enabled", complete: notificationsReady, target: "#alerts" },
  ];

  return (
    <section className="panel launchpad" aria-labelledby="launchpad-title">
      <div className="launchpadCopy">
        <span className="eyebrow">First dependable workflow</span>
        <h2 id="launchpad-title">Give this camera a job</h2>
        <p>
          Describe an event, review the compiled job, start analysis, and receive a confirmed
          incident with recorded evidence.
        </p>
        <div className="launchSteps">
          {steps.map((step, index) => (
            <a className={step.complete ? "launchStep complete" : "launchStep"} href={step.target} key={step.label}>
              <span>{step.complete ? "✓" : index + 1}</span>
              {step.label}
            </a>
          ))}
        </div>
      </div>

      <div className="launchpadActions">
        {!camera ? (
          <a className="buttonPrimary launchLink" href="#cameras">Add or select a camera</a>
        ) : !activeRule ? (
          <a className="buttonPrimary launchLink" href="#rules">Describe your first job</a>
        ) : !running ? (
          <button className="buttonPrimary" disabled={busy} onClick={onStart} type="button">
            Start analysis
          </button>
        ) : (
          <button className="buttonSecondary" disabled={busy} onClick={onStop} type="button">
            Stop analysis
          </button>
        )}
        {!notificationsReady && notificationPermission !== "unsupported" && (
          <button className="buttonSecondary" onClick={onEnableNotifications} type="button">
            Enable browser alerts
          </button>
        )}
        {activeRule && (
          <button
            className="buttonGhost"
            disabled={busy}
            onClick={() => onTestAlert(activeRule.id)}
            type="button"
          >
            Send safe test alert
          </button>
        )}
        <small>
          Test alerts use no vision request, send no webhook, and create no fake video clip.
        </small>
      </div>

      <div className={`launchSafety ${running ? "running" : "stopped"}`}>
        <div>
          <Icon name="shield" />
          <span>
            <small>Analysis spending state</small>
            <strong>{running ? "Running · provider ceilings enforced" : "Stopped · $0 additional usage"}</strong>
          </span>
        </div>
        {telemetry?.analysis_request_limit_day ? (
          <p>
            This camera session: <strong>{telemetry.analysis_requests_today}</strong> of{" "}
            <strong>{telemetry.analysis_request_limit_day}</strong> visual requests used this worker session,
            capped at <strong>{telemetry.analysis_request_limit_minute}/minute</strong>.
          </p>
        ) : (
          <p>Exact VLM request usage appears here as soon as a semantic job starts reporting.</p>
        )}
        <p className="latestOutcome">
          {latestEvent
            ? `Latest incident: ${latestEvent.object_class} · ${latestEvent.event_type.replaceAll("_", " ")}`
            : ready
              ? "Ready for the first real incident."
              : "Complete the steps to begin monitoring."}
        </p>
      </div>
    </section>
  );
}
