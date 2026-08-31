"use client";

import { useMemo, useState } from "react";

import { API_URL } from "@/lib/api";
import type {
  AccuracyEnvironmentTag,
  VerificationCase,
  VerificationStatus,
} from "@/lib/types";

interface VerificationInboxProps {
  cases: VerificationCase[];
  busy: boolean;
  canOperate: boolean;
  onDecision: (
    caseId: string,
    status: "confirmed" | "rejected",
    reasoning: string,
    environmentTags: AccuracyEnvironmentTag[],
  ) => Promise<void>;
  onAudit: (
    caseId: string,
    actualOutcome: "event" | "no_event",
    reasoning: string,
    environmentTags: AccuracyEnvironmentTag[],
  ) => Promise<void>;
  onRefresh: () => Promise<void>;
}

const tabs: Array<{ label: string; statuses: VerificationStatus[] }> = [
  { label: "Needs review", statuses: ["pending", "uncertain"] },
  { label: "Confirmed", statuses: ["confirmed"] },
  { label: "Rejected", statuses: ["rejected"] },
];
const environmentOptions: Array<{ value: AccuracyEnvironmentTag; label: string }> = [
  { value: "low_light", label: "Low light" },
  { value: "partial_occlusion", label: "Occlusion" },
  { value: "far_distance", label: "Far distance" },
  { value: "camera_motion", label: "Camera motion" },
];

function percent(value: number | null) {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export function VerificationInbox({
  cases,
  busy,
  canOperate,
  onDecision,
  onAudit,
  onRefresh,
}: VerificationInboxProps) {
  const [tabIndex, setTabIndex] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reasoning, setReasoning] = useState("");
  const [environmentTags, setEnvironmentTags] = useState<AccuracyEnvironmentTag[]>([]);
  const visible = useMemo(
    () => cases.filter((item) => tabs[tabIndex].statuses.includes(item.status)),
    [cases, tabIndex],
  );
  const selected = visible.find((item) => item.id === selectedId) ?? visible[0] ?? null;

  const videoUrl = selected?.evidence_content_url
    ? selected.evidence_content_url.startsWith("http")
      ? selected.evidence_content_url
      : `${API_URL}${selected.evidence_content_url}`
    : null;
  const needsReview = selected?.status === "pending" || selected?.status === "uncertain";
  const needsAudit = Boolean(selected && !needsReview && !selected.accuracy_label);

  async function decide(status: "confirmed" | "rejected") {
    if (!selected) return;
    const explanation = reasoning.trim();
    if (explanation.length < 3) return;
    await onDecision(selected.id, status, explanation, environmentTags);
  }

  async function audit(correct: boolean) {
    if (!selected) return;
    const explanation = reasoning.trim();
    if (explanation.length < 3) return;
    const predictedEvent = selected.status === "confirmed";
    const actualEvent = correct ? predictedEvent : !predictedEvent;
    await onAudit(
      selected.id,
      actualEvent ? "event" : "no_event",
      explanation,
      environmentTags,
    );
  }

  function toggleEnvironmentTag(tag: AccuracyEnvironmentTag) {
    setEnvironmentTags((current) =>
      current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag],
    );
  }

  return (
    <section className="panel verificationInbox" id="verification-inbox">
      <div className="panelHeader verificationHeader">
        <div>
          <span className="eyebrow">Live accuracy gate</span>
          <h2>Visual verification inbox</h2>
          <p>
            Semantic detections stay quarantined until a distinct model or an operator confirms
            the visible evidence. Rejected and uncertain proposals cannot trigger alerts.
          </p>
        </div>
        <button className="buttonSecondary" disabled={busy} onClick={() => void onRefresh()} type="button">Refresh</button>
      </div>
      <div className="verificationTabs" role="tablist" aria-label="Verification status">
        {tabs.map((tab, index) => {
          const count = cases.filter((item) => tab.statuses.includes(item.status)).length;
          return (
            <button
              aria-selected={tabIndex === index}
              className={tabIndex === index ? "verificationTabActive" : ""}
              key={tab.label}
              onClick={() => { setTabIndex(index); setSelectedId(null); setReasoning(""); setEnvironmentTags([]); }}
              role="tab"
              type="button"
            >
              {tab.label} <span>{count}</span>
            </button>
          );
        })}
      </div>
      {selected ? (
        <div className="verificationWorkspace">
          <aside className="verificationCaseList" aria-label="Verification cases">
            {visible.map((item) => (
              <button
                className={item.id === selected.id ? "verificationCaseActive" : ""}
                key={item.id}
                onClick={() => { setSelectedId(item.id); setReasoning(""); setEnvironmentTags([]); }}
                type="button"
              >
                <span>{item.camera_name}</span>
                <strong>{item.rule_name}</strong>
                <small>{new Date(item.event.occurred_at).toLocaleString()}</small>
                <i>{item.status}</i>
              </button>
            ))}
          </aside>
          <div className="verificationEvidence">
            <div className="verificationEvidenceTitle">
              <div>
                <span>{selected.camera_name}</span>
                <strong>{selected.proposal_summary}</strong>
              </div>
              <span className={`verificationStatus verificationStatus-${selected.status}`}>
                {selected.status.replace("_", " ")}
              </span>
            </div>
            {videoUrl ? (
              <video controls preload="metadata" src={videoUrl} />
            ) : (
              <div className="verificationNoVideo">
                <strong>Clip is still arriving</strong>
                <span>Evidence status: {selected.evidence_status ?? "not available"}</span>
              </div>
            )}
            <div className="verificationTimeline" aria-label="Evidence time range">
              <span style={{ left: "12%", width: "76%" }} />
              <i style={{ left: "68%" }} />
            </div>
            <div className="verificationMetrics">
              <span>Proposer <strong>{percent(selected.proposer_confidence)}</strong></span>
              <span>Verifier <strong>{percent(selected.verifier_confidence)}</strong></span>
              <span>Visible window <strong>{selected.event.dwell_seconds.toFixed(1)}s</strong></span>
            </div>
          </div>
          <aside className="verificationReasoning">
            <span className="eyebrow">Decision record</span>
            <h3>Why this case is here</h3>
            <p>{selected.reasoning}</p>
            <dl>
              <div><dt>Proposer</dt><dd>{selected.proposer_model ?? "unidentified"}</dd></div>
              <div><dt>Verifier</dt><dd>{selected.verifier_model ?? "operator required"}</dd></div>
              <div><dt>Verifier finding</dt><dd>{selected.verifier_summary ?? "No independent result"}</dd></div>
            </dl>
            {(needsReview || needsAudit) && canOperate ? (
              <>
                <label htmlFor={`verification-reason-${selected.id}`}>Operator reasoning</label>
                <textarea
                  id={`verification-reason-${selected.id}`}
                  onChange={(event) => setReasoning(event.target.value)}
                  rows={4}
                  value={reasoning}
                />
                <span className="environmentLabel">Evidence conditions</span>
                <div className="environmentTags">
                  {environmentOptions.map((option) => (
                    <button
                      className={environmentTags.includes(option.value) ? "environmentTagActive" : ""}
                      key={option.value}
                      onClick={() => toggleEnvironmentTag(option.value)}
                      type="button"
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                {needsReview ? (
                  <div className="verificationActions">
                    <button disabled={busy || reasoning.trim().length < 3} onClick={() => void decide("rejected")} type="button">Reject</button>
                    <button className="buttonPrimary" disabled={busy || reasoning.trim().length < 3} onClick={() => void decide("confirmed")} type="button">Confirm event</button>
                  </div>
                ) : (
                  <div className="verificationActions">
                    <button disabled={busy || reasoning.trim().length < 3} onClick={() => void audit(false)} type="button">Outcome was wrong</button>
                    <button className="buttonPrimary" disabled={busy || reasoning.trim().length < 3} onClick={() => void audit(true)} type="button">Outcome was correct</button>
                  </div>
                )}
              </>
            ) : (
              <small className="verificationReviewed">
                {selected.accuracy_label
                  ? `Field label: ${selected.accuracy_label.outcome.replaceAll("_", " ")}`
                  : selected.reviewed_by
                    ? `Reviewed by ${selected.reviewed_by}`
                    : "Automatically decided"}
              </small>
            )}
          </aside>
        </div>
      ) : (
        <div className="verificationEmpty">
          <strong>No {tabs[tabIndex].label.toLowerCase()} cases</strong>
          <span>New semantic proposals will appear here with their clip and decision record.</span>
        </div>
      )}
    </section>
  );
}
