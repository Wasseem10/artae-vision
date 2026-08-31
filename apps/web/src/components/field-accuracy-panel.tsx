"use client";

import { useMemo, useState } from "react";

import type { AccuracyEnvironmentTag, FieldAccuracyReport } from "@/lib/types";

interface FieldAccuracyPanelProps {
  reports: FieldAccuracyReport[];
  busy: boolean;
  canOperate: boolean;
  onMiss: (
    ruleId: string,
    occurredAt: string,
    reasoning: string,
    environmentTags: AccuracyEnvironmentTag[],
  ) => Promise<void>;
  onManualOnly: (report: FieldAccuracyReport, enabled: boolean) => Promise<void>;
  onRefresh: () => Promise<void>;
}

const conditions: Array<{ value: AccuracyEnvironmentTag; label: string }> = [
  { value: "low_light", label: "Low light" },
  { value: "partial_occlusion", label: "Occlusion" },
  { value: "far_distance", label: "Far distance" },
  { value: "camera_motion", label: "Camera motion" },
];

function metric(value: number | null | undefined) {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

export function FieldAccuracyPanel({
  reports,
  busy,
  canOperate,
  onMiss,
  onManualOnly,
  onRefresh,
}: FieldAccuracyPanelProps) {
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  const [showMissForm, setShowMissForm] = useState(false);
  const [missReason, setMissReason] = useState("");
  const [occurredAt, setOccurredAt] = useState(() => new Date().toISOString().slice(0, 16));
  const [environmentTags, setEnvironmentTags] = useState<AccuracyEnvironmentTag[]>([]);
  const selected = useMemo(
    () => reports.find((report) => report.rule_id === selectedRuleId) ?? reports[0] ?? null,
    [reports, selectedRuleId],
  );
  const snapshot = selected?.latest_snapshot ?? null;

  function toggleTag(tag: AccuracyEnvironmentTag) {
    setEnvironmentTags((current) =>
      current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag],
    );
  }

  async function submitMiss() {
    if (!selected || missReason.trim().length < 3) return;
    await onMiss(
      selected.rule_id,
      new Date(occurredAt).toISOString(),
      missReason.trim(),
      environmentTags,
    );
    setMissReason("");
    setEnvironmentTags([]);
    setShowMissForm(false);
  }

  return (
    <section className="panel fieldAccuracyPanel" id="field-accuracy">
      <div className="panelHeader fieldAccuracyHeader">
        <div>
          <span className="eyebrow">Closed-loop learning</span>
          <h2>Field accuracy and release gates</h2>
          <p>
            Human-reviewed live outcomes measure each camera and job separately. Automatic
            semantic release unlocks only after the field gate passes and locks again on drift.
          </p>
        </div>
        <div className="fieldAccuracyHeaderActions">
          <button className="buttonSecondary" disabled={busy} onClick={() => void onRefresh()} type="button">Refresh</button>
          {selected && canOperate && (
            <button className="buttonSecondary" disabled={busy} onClick={() => setShowMissForm((current) => !current)} type="button">Report missed event</button>
          )}
        </div>
      </div>
      {reports.length === 0 ? (
        <div className="verificationEmpty">
          <strong>No semantic jobs to score</strong>
          <span>Create a plain-language semantic camera job to start field calibration.</span>
        </div>
      ) : (
        <div className="fieldAccuracyWorkspace">
          <aside className="fieldAccuracyRuleList">
            {reports.map((report) => (
              <button
                className={report.rule_id === selected?.rule_id ? "fieldAccuracyRuleActive" : ""}
                key={report.rule_id}
                onClick={() => setSelectedRuleId(report.rule_id)}
                type="button"
              >
                <span>{report.camera_name}</span>
                <strong>{report.rule_name}</strong>
                <small>{report.unlabeled_case_count} outcome{report.unlabeled_case_count === 1 ? "" : "s"} awaiting audit</small>
              </button>
            ))}
          </aside>
          {selected && (
            <div className="fieldAccuracyDetail">
              <div className="fieldAccuracyGateHeader">
                <div>
                  <span>{selected.camera_name}</span>
                  <h3>{selected.rule_name}</h3>
                </div>
                <span className={`accuracyGate accuracyGate-${snapshot?.gate_status ?? "collecting"}`}>
                  {snapshot?.gate_status ?? "collecting"}
                </span>
              </div>
              {canOperate && (
                <label className="manualOnlyControl">
                  <input
                    checked={selected.policy.manual_only}
                    disabled={busy}
                    onChange={(event) => void onManualOnly(selected, event.target.checked)}
                    type="checkbox"
                  />
                  Always require operator review for this job
                </label>
              )}
              <div className="accuracyMetrics">
                <article><span>Precision</span><strong>{metric(snapshot?.precision)}</strong><small>Target {metric(selected.policy.minimum_precision)}</small></article>
                <article><span>Recall</span><strong>{metric(snapshot?.recall)}</strong><small>Target {metric(selected.policy.minimum_recall)}</small></article>
                <article><span>F1 score</span><strong>{metric(snapshot?.f1)}</strong><small>{snapshot?.label_count ?? 0} labels</small></article>
                <article><span>Automatic release</span><strong>{snapshot?.automatic_release_allowed ? "Unlocked" : "Locked"}</strong><small>Verified semantic events</small></article>
              </div>
              <div className="accuracyEvidenceProgress">
                <div><span>Positive outcomes</span><strong>{snapshot?.positive_count ?? 0} / {selected.policy.minimum_positive_labels}</strong></div>
                <div><span>Negative outcomes</span><strong>{snapshot?.negative_count ?? 0} / {selected.policy.minimum_negative_labels}</strong></div>
                <div><span>Challenging conditions</span><strong>{snapshot?.challenging_count ?? 0} / {selected.policy.minimum_challenging_labels}</strong></div>
              </div>
              <div className="accuracyConfusionGrid">
                <span>True alerts <strong>{snapshot?.true_positives ?? 0}</strong></span>
                <span>False alerts <strong>{snapshot?.false_positives ?? 0}</strong></span>
                <span>Missed events <strong>{snapshot?.false_negatives ?? 0}</strong></span>
                <span>Correct suppressions <strong>{snapshot?.true_negatives ?? 0}</strong></span>
              </div>
              <div className="accuracyRecommendations">
                <strong>Next evidence needed</strong>
                {(snapshot?.recommendations.length ? snapshot.recommendations : [
                  "Review live proposals in the verification inbox to build the field dataset.",
                ]).map((recommendation) => <p key={recommendation}>{recommendation}</p>)}
              </div>
              {showMissForm && (
                <div className="missedEventForm">
                  <h4>Record a visible event the system missed</h4>
                  <label htmlFor="miss-occurred-at">When it happened</label>
                  <input id="miss-occurred-at" onChange={(event) => setOccurredAt(event.target.value)} type="datetime-local" value={occurredAt} />
                  <label htmlFor="miss-reason">Evidence and reason</label>
                  <textarea id="miss-reason" onChange={(event) => setMissReason(event.target.value)} rows={3} value={missReason} />
                  <div className="environmentTags">
                    {conditions.map((condition) => (
                      <button className={environmentTags.includes(condition.value) ? "environmentTagActive" : ""} key={condition.value} onClick={() => toggleTag(condition.value)} type="button">{condition.label}</button>
                    ))}
                  </div>
                  <div className="verificationActions">
                    <button onClick={() => setShowMissForm(false)} type="button">Cancel</button>
                    <button className="buttonPrimary" disabled={busy || missReason.trim().length < 3} onClick={() => void submitMiss()} type="button">Save missed event</button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
