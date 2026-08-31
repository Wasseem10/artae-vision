"use client";

import { useState, type FormEvent } from "react";

import { Icon } from "@/components/icon";
import { StatusPill } from "@/components/status-pill";
import type {
  CameraJobSpec,
  Camera,
  CompileRuleInput,
  Rule,
  RuleCompilation,
  RuleStatus,
  PlatformCapabilities,
  Zone,
} from "@/lib/types";

const jobLabels: Record<CameraJobSpec["rule_type"], string> = {
  object_dwell: "Dwell",
  zone_dwell: "Dwell",
  zone_presence: "Presence",
  zone_entry: "Entry",
  zone_exit: "Exit",
  count_threshold: "Count threshold",
  line_crossing: "Line crossing",
  semantic_vision: "Semantic vision",
};

function jobGeometry(spec: CameraJobSpec): string {
  if (spec.rule_type === "semantic_vision") return "Full camera view";
  return spec.rule_type === "line_crossing" ? spec.line_name : spec.zone_name;
}

function jobCondition(spec: CameraJobSpec): string {
  if (spec.rule_type === "object_dwell" || spec.rule_type === "zone_dwell") {
    return `${spec.duration_seconds}s dwell`;
  }
  if (spec.rule_type === "zone_presence") {
    return spec.confirmation_seconds ? `${spec.confirmation_seconds}s confirmation` : "Immediate";
  }
  if (spec.rule_type === "count_threshold") {
    return `${spec.comparison === "at_least" ? "At least" : "At most"} ${spec.threshold}`;
  }
  if (spec.rule_type === "line_crossing") return `${spec.direction} direction`;
  if (spec.rule_type === "semantic_vision") {
    return `${spec.confirmation_windows} window confirmation · ${spec.cooldown_seconds}s cooldown`;
  }
  return "Tracked transition";
}

interface RulePanelProps {
  camera: Camera | null;
  zones: Zone[];
  rules: Rule[];
  busy: boolean;
  onCompile: (input: CompileRuleInput) => Promise<RuleCompilation>;
  onClarify: (compilationId: string, answer: string) => Promise<RuleCompilation>;
  onAccept: (compilationId: string) => Promise<void>;
  onStatusChange: (ruleId: string, status: RuleStatus) => Promise<void>;
  capabilities: PlatformCapabilities | null;
}

export function RulePanel({
  camera,
  zones,
  rules,
  busy,
  onCompile,
  onClarify,
  onAccept,
  onStatusChange,
  capabilities,
}: RulePanelProps) {
  const [showForm, setShowForm] = useState(false);
  const [prompt, setPrompt] = useState(
    "Alert me when a person is not wearing a hard hat.",
  );
  const [answer, setAnswer] = useState("");
  const [compilation, setCompilation] = useState<RuleCompilation | null>(null);
  const [showOlderRules, setShowOlderRules] = useState(false);

  const activeRules = rules.filter((rule) => rule.status === "active");
  const visibleRules = activeRules.length > 0 ? activeRules : rules.slice(0, 1);
  const visibleRuleIds = new Set(visibleRules.map((rule) => rule.id));
  const olderRules = rules.filter((rule) => !visibleRuleIds.has(rule.id));

  function closeBuilder() {
    setShowForm(false);
    setCompilation(null);
    setAnswer("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!camera) return;
    try {
      if (compilation?.status === "needs_clarification") {
        const revised = await onClarify(compilation.id, answer.trim());
        setCompilation(revised);
        setAnswer("");
      } else {
        const compiled = await onCompile({ camera_id: camera.id, prompt: prompt.trim() });
        setCompilation(compiled);
      }
    } catch {
      // The dashboard displays the API error and preserves the operator's work.
    }
  }

  async function accept() {
    if (!compilation) return;
    try {
      await onAccept(compilation.id);
      closeBuilder();
    } catch {
      // The dashboard displays the API error and keeps the review visible.
    }
  }

  function renderRuleCard(rule: Rule) {
    const geometry = zones.find((candidate) => candidate.id === rule.zone_id);
    const nextStatus: RuleStatus = rule.status === "active" ? "paused" : "active";
    return (
      <article className="ruleCard" key={rule.id}>
        <div className="ruleIcon"><Icon name="rule" /></div>
        <div className="ruleSummary">
          <div className="ruleTitle"><strong>{rule.name}</strong><StatusPill status={rule.status} /></div>
          <p>{rule.original_prompt ?? "Explicit object dwell configuration"}</p>
          <div className="ruleFacts">
            <span><Icon name="map" /> {geometry?.name ?? "Unknown geometry"}</span>
            <span><Icon name="clock" /> {rule.spec ? jobCondition(rule.spec) : `${rule.duration_seconds}s dwell`}</span>
            <span>{rule.spec ? jobLabels[rule.spec.rule_type] : rule.rule_type}</span>
            {rule.execution_plan && <span className="routeBadge">{rule.execution_plan.strategy === "semantic_window" ? "VLM windows" : "YOLO + tracking"}</span>}
            <span>{Math.round(rule.minimum_confidence * 100)}% confidence</span>
            <span>IR v{rule.spec_version}</span>
          </div>
        </div>
        <button className={rule.status === "active" ? "buttonSecondary" : "buttonPrimary"} disabled={busy} onClick={() => onStatusChange(rule.id, nextStatus)} type="button">
          {rule.status === "active" ? "Pause" : "Activate"}
        </button>
      </article>
    );
  }

  return (
    <section className="panel rulePanel" id="rules">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Temporal logic</span>
          <h2>Camera jobs</h2>
        </div>
        <button
          className="buttonPrimary buttonWithIcon"
          disabled={!camera}
          onClick={() => {
            if (showForm) closeBuilder();
            else setShowForm(true);
          }}
          type="button"
        >
          <Icon name="spark" /> Give camera a job
        </button>
      </div>

      {showForm && (
        <form className="ruleBuilder" onSubmit={submit}>
          <div className="builderLead">
            <span className="sparkBadge">
              <Icon name="spark" />
            </span>
            <div>
              <strong>Describe the event in everyday language</strong>
              <p>
                The platform chooses a deterministic tracker or semantic vision job. Nothing
                becomes active until you review the interpretation and its model route.
              </p>
            </div>
          </div>

          <label className="wideField">
            What should this camera watch for?
            <textarea
              maxLength={2000}
              minLength={5}
              onChange={(event) => {
                setPrompt(event.target.value);
                setCompilation(null);
                setAnswer("");
              }}
              required
              rows={3}
              value={prompt}
            />
          </label>

          <div className="compilerContext">
            <span>Available scene geometry</span>
            {zones.length === 0 && <strong>Full camera view · automatic</strong>}
            {zones.map((zone) => (
              <strong key={zone.id}>{zone.name} · {zone.geometry_type}</strong>
            ))}
          </div>
          {capabilities && (
            <div className="compilerContext">
              <span>Deployable engine</span>
              <strong>{capabilities.detector.model}</strong>
              <strong>{capabilities.event_types.length} event types</strong>
              <strong>{capabilities.detector.object_classes.length} object classes</strong>
            </div>
          )}

          {compilation?.status === "needs_clarification" && (
            <div className="compilerClarification" role="status">
              <div>
                <span className="reviewLabel">Clarification needed · revision {compilation.revision}</span>
                <strong>{compilation.clarification_question}</strong>
                <p>{compilation.explanation}</p>
              </div>
              <label>
                Your answer
                <input
                  autoFocus
                  maxLength={1000}
                  onChange={(event) => setAnswer(event.target.value)}
                  placeholder="For example: 30 seconds"
                  required
                  value={answer}
                />
              </label>
            </div>
          )}

          {compilation?.status === "ready_for_review" && compilation.compiled_rule && (
            <div className="compiledReview" aria-live="polite">
              <div className="compiledReviewHead">
                <div>
                  <span className="reviewLabel">
                    Ready for human review · revision {compilation.revision}
                  </span>
                  <strong>{compilation.explanation}</strong>
                </div>
                <span className="compilerProvider">
                  {compilation.provider_model ?? compilation.provider} · {compilation.compiler_version}
                </span>
              </div>
              <div className="compiledFacts">
                <span>
                  <small>Job type</small>
                  <strong>{jobLabels[compilation.compiled_rule.rule_type]}</strong>
                </span>
                <span>
                  <small>Object</small>
                  <strong>{compilation.compiled_rule.object_class}</strong>
                </span>
                <span>
                  <small>Zone or line</small>
                  <strong>{jobGeometry(compilation.compiled_rule)}</strong>
                </span>
                <span>
                  <small>Trigger</small>
                  <strong>{jobCondition(compilation.compiled_rule)}</strong>
                </span>
                <span>
                  <small>Confidence</small>
                  <strong>{Math.round(compilation.compiled_rule.minimum_confidence * 100)}%</strong>
                </span>
              </div>
              {compilation.execution_plan && (
                <div className="modelRoute">
                  <div className="modelRouteHead">
                    <span>
                      <small>Execution strategy</small>
                      <strong>
                        {compilation.execution_plan.strategy === "semantic_window"
                          ? "Temporal visual reasoning"
                          : "Deterministic detection + tracking"}
                      </strong>
                    </span>
                    <span
                      className={
                        compilation.execution_plan.provider_requests
                          ? "routeCost routeCloud"
                          : "routeCost routeLocal"
                      }
                    >
                      {compilation.execution_plan.provider_requests
                        ? "Uses bounded VLM requests"
                        : "Runs locally · no VLM cost"}
                    </span>
                  </div>
                  <p>{compilation.execution_plan.summary}</p>
                  <div
                    className={`supportAssessment support-${compilation.execution_plan.support.tier}`}
                  >
                    <div>
                      <small>Current support level</small>
                      <strong>{compilation.execution_plan.support.label}</strong>
                      <p>{compilation.execution_plan.support.reason}</p>
                    </div>
                    <span>
                      {compilation.execution_plan.support.deployable
                        ? "Replay test required"
                        : "Blocked from deployment"}
                    </span>
                  </div>
                  {compilation.execution_plan.visual_skills.length > 0 && (
                    <div className="routeSkills" aria-label="Selected visual skills">
                      {compilation.execution_plan.visual_skills.map((skill) => (
                        <span key={skill.id} title={skill.benchmark_policy}>
                          {skill.label} · fallback
                        </span>
                      ))}
                    </div>
                  )}
                  <details className="routeLimitations">
                    <summary>Accuracy limits and validation</summary>
                    <ul>
                      {compilation.execution_plan.support.limitations.map((limitation) => (
                        <li key={limitation}>{limitation}</li>
                      ))}
                    </ul>
                  </details>
                  <ol className="modelStages" aria-label="Execution stages">
                    {compilation.execution_plan.stages.map((stage) => (
                      <li key={stage.id} title={stage.purpose}>
                        <small>{stage.locality === "edge" ? "Edge" : "Provider"}</small>
                        <strong>{stage.label}</strong>
                        <span>{stage.executor}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              {compilation.warnings.map((warning) => (
                <p className="compilerWarning" key={warning}>
                  {warning}
                </p>
              ))}
              <div className="reviewNotice">
                <Icon name="shield" />
                <span>
                  Accepting saves this reviewed job as a <strong>draft</strong>. It can only be
                  activated after its capability and replay checks pass.
                </span>
              </div>
            </div>
          )}

          <div className="formActions">
            <button className="buttonSecondary" onClick={closeBuilder} type="button">
              Cancel
            </button>
            {compilation?.status === "ready_for_review" ? (
              <button
                className="buttonPrimary"
                disabled={busy || compilation.execution_plan?.support.deployable === false}
                onClick={accept}
                type="button"
              >
                {busy ? "Saving job…" : "Accept as draft"}
              </button>
            ) : (
              <button
                className="buttonPrimary"
                disabled={
                  busy ||
                  !prompt.trim() ||
                  (compilation?.status === "needs_clarification" && !answer.trim())
                }
                type="submit"
              >
                {busy
                  ? "Compiling…"
                  : compilation?.status === "needs_clarification"
                    ? "Apply clarification"
                    : "Compile for review"}
              </button>
            )}
          </div>
        </form>
      )}

      <div className="ruleList">
        {rules.length === 0 ? (
          <div className="emptyWide">
            <span className="emptyIcon">
              <Icon name="rule" />
            </span>
            <div>
            <strong>No jobs for this camera</strong>
              <p>Describe a visible condition. Zones and lines are optional optimizations.</p>
            </div>
          </div>
        ) : (
          <>
            {visibleRules.map(renderRuleCard)}
            {olderRules.length > 0 && (
              <div className="olderRules">
                <button aria-expanded={showOlderRules} onClick={() => setShowOlderRules((current) => !current)} type="button">
                  <span><strong>{showOlderRules ? "Hide older rules" : `Show ${olderRules.length} older and paused rule${olderRules.length === 1 ? "" : "s"}`}</strong><small>Kept for history; they are not currently running.</small></span>
                  <Icon name="chevron" />
                </button>
                {showOlderRules && <div>{olderRules.map(renderRuleCard)}</div>}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
