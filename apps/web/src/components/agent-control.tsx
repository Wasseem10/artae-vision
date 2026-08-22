import { Icon } from "@/components/icon";
import { StatusPill } from "@/components/status-pill";
import type { AgentTelemetry, Camera, CameraAgent, Rule } from "@/lib/types";

interface AgentControlProps {
  camera: Camera | null;
  agent: CameraAgent | null;
  rules: Rule[];
  telemetry: AgentTelemetry | null;
  busy: boolean;
  onStart: () => void;
  onStop: () => void;
}

export function AgentControl({
  camera,
  agent,
  rules,
  telemetry,
  busy,
  onStart,
  onStop,
}: AgentControlProps) {
  const activeRules = rules.filter((rule) => rule.status === "active");
  const running = agent?.desired_status === "running";
  const status = agent?.observed_status ?? "stopped";
  const jobLabel = `${activeRules.length} active job${activeRules.length === 1 ? "" : "s"}`;
  const semanticEnabled = activeRules.some((rule) => rule.spec?.rule_type === "semantic_vision");
  const analysisState = telemetry?.analysis_state?.replaceAll("-", " ") ?? "waiting";

  return (
    <section className="panel agentPanel" id="agent">
      <div className="agentIdentity">
        <span className="agentGlyph"><Icon name="activity" /></span>
        <div>
          <span className="eyebrow">Managed inference</span>
          <h2>{camera ? `${camera.name} vision agent` : "Select a camera"}</h2>
          <p>
            {agent?.last_error ??
              (running
                ? `${jobLabel} share this camera's tracked stream. Stop the agent to change jobs.`
                : activeRules.length
                  ? `${jobLabel} ready to deploy on one camera agent.`
                  : "Activate at least one camera job, then start continuous detection.")}
          </p>
        </div>
      </div>
      <div className="agentMetrics">
        <span><small>Status</small><StatusPill status={status} /></span>
        <span><small>Throughput</small><strong>{agent?.fps?.toFixed(1) ?? "—"} FPS</strong></span>
        <span><small>Inference</small><strong>{agent?.inference_latency_ms?.toFixed(0) ?? "—"} ms</strong></span>
        <span><small>Edge device</small><strong>{agent?.edge_device_id?.slice(0, 8) ?? "local"}</strong></span>
        <span><small>Worker</small><strong>{agent?.worker_id ?? "unclaimed"}</strong></span>
      </div>
      {semanticEnabled && (
        <div className="analysisDecision" aria-live="polite">
          <div className="analysisDecisionHead">
            <span>
              <i className={`analysisDot analysisDot-${telemetry?.analysis_state ?? "waiting"}`} />
              AI verification · {analysisState}
            </span>
            {telemetry?.analysis_triggered !== null && telemetry?.analysis_triggered !== undefined && (
              <strong className={telemetry.analysis_triggered ? "decisionTriggered" : "decisionClear"}>
                {telemetry.analysis_triggered ? "Rule observed" : "No match"}
              </strong>
            )}
          </div>
          <p>
            {telemetry?.analysis_error ??
              telemetry?.analysis_summary ??
              "Collecting a chronological frame window for the first visual decision."}
          </p>
          <div className="analysisDecisionFacts">
            <span>
              Confidence {telemetry?.analysis_confidence === null || telemetry?.analysis_confidence === undefined
                ? "—"
                : `${Math.round(telemetry.analysis_confidence * 100)}%`}
            </span>
            <span>Window {telemetry?.analysis_sequence ?? "—"}</span>
            <span>
              Requests {telemetry?.analysis_requests_today ?? 0}/
              {telemetry?.analysis_request_limit_day || "configured limit"} this worker session
            </span>
            <span>{telemetry?.analysis_request_limit_minute || "—"}/minute ceiling</span>
          </div>
        </div>
      )}
      {running ? (
        <button className="buttonSecondary" disabled={busy} onClick={onStop} type="button">
          Stop agent
        </button>
      ) : (
        <button
          className="buttonPrimary"
          disabled={busy || !camera || activeRules.length === 0}
          onClick={onStart}
          type="button"
        >
          Start agent
        </button>
      )}
    </section>
  );
}
