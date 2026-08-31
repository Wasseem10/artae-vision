"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { EvidenceDatasetVersion, EvidenceReviewQueueSummary, EvidenceReviewSample } from "@/lib/types";

interface ActiveLearningPanelProps {
  canOperate: boolean;
  onError: (message: string) => void;
}

const emptySummary: EvidenceReviewQueueSummary = { queued: 0, assigned: 0, reviewing: 0, disputed: 0, overdue: 0, labeled: 0, by_kind: {} };

export function ActiveLearningPanel({ canOperate, onError }: ActiveLearningPanelProps) {
  const [samples, setSamples] = useState<EvidenceReviewSample[]>([]);
  const [datasets, setDatasets] = useState<EvidenceDatasetVersion[]>([]);
  const [summary, setSummary] = useState(emptySummary);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [datasetName, setDatasetName] = useState("field-evidence");
  const [reason, setReason] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const [nextSamples, nextSummary, nextDatasets] = await Promise.all([
        api.listEvidenceReviewQueue(), api.getEvidenceReviewSummary(), api.listEvidenceDatasets(),
      ]);
      setSamples(nextSamples);
      setSummary(nextSummary);
      setDatasets(nextDatasets);
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not load the evidence learning queue.");
    }
  }, [onError]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function run(id: string, action: () => Promise<unknown>) {
    setBusyId(id);
    try { await action(); await load(); }
    catch (failure) { onError(failure instanceof Error ? failure.message : "The evidence action failed."); }
    finally { setBusyId(null); }
  }

  async function label(sample: EvidenceReviewSample, actualOutcome: "event" | "no_event") {
    const note = reason[sample.id]?.trim() || (actualOutcome === "event" ? "Target behavior is visible in the reviewed footage." : "Target behavior is not visible in the reviewed footage.");
    await run(sample.id, () => sample.status === "disputed"
      ? api.adjudicateEvidenceReview(sample.id, actualOutcome, note)
      : api.labelEvidenceReview(sample.id, actualOutcome, note));
  }

  async function toggleHighRiskReview(sample: EvidenceReviewSample) {
    await run(sample.id, async () => {
      const policy = await api.getEvidenceSamplingPolicy(sample.rule_id);
      await api.updateEvidenceSamplingPolicy(sample.rule_id, {
        enabled: policy.enabled,
        normal_sample_interval_seconds: policy.normal_sample_interval_seconds,
        daily_limit: policy.daily_limit,
        review_sla_hours: policy.review_sla_hours,
        retention_days: policy.retention_days,
        required_reviews: policy.required_reviews === 2 ? 1 : 2,
        require_adjudication: true,
      });
    });
  }

  return (
    <section className="panel activeLearningPanel" id="active-learning">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Active evidence loop</span>
          <h2>Review queue and dataset versions</h2>
          <p>Routine footage, uncertain proposals, and difficult conditions are sampled automatically, deduplicated, assigned, and frozen into reproducible evaluation datasets.</p>
        </div>
        <button className="buttonSecondary" disabled={Boolean(busyId)} onClick={() => void load()} type="button">Refresh</button>
      </div>
      <div className="activeLearningStats">
        <article><span>Waiting</span><strong>{summary.queued}</strong></article>
        <article><span>Assigned</span><strong>{summary.assigned}</strong></article>
        <article><span>In consensus</span><strong>{summary.reviewing}</strong></article>
        <article><span>Disputed</span><strong>{summary.disputed}</strong></article>
        <article className={summary.overdue ? "activeLearningOverdue" : ""}><span>Overdue</span><strong>{summary.overdue}</strong></article>
        <article><span>Labeled</span><strong>{summary.labeled}</strong></article>
      </div>
      <div className="activeLearningGrid">
        <div className="reviewQueueList">
          <div className="activeLearningSectionTitle"><h3>Priority review queue</h3><span>{samples.length} samples</span></div>
          {samples.filter((sample) => ["queued", "assigned", "reviewing", "disputed"].includes(sample.status)).slice(0, 12).map((sample) => (
            <article className="reviewSampleCard" key={sample.id}>
              <div className="reviewSampleHeader">
                <span className={`reviewKind reviewKind-${sample.kind}`}>{sample.kind}</span>
                <strong>{sample.rule_name}</strong>
                <small>{Math.round(sample.priority * 100)} priority</small>
              </div>
              <p>{sample.camera_name} · {sample.recording_id ? "Archived camera segment" : "Semantic proposal"}</p>
              <div className="reviewSampleMeta">
                <span>{sample.assigned_to ? `Assigned to ${sample.assigned_to}` : "Unassigned"}</span>
                <span>{sample.review_count}/{sample.required_reviews} reviews · {sample.consensus_status.replaceAll("_", " ")}</span>
                {sample.due_at && <span>Due {new Date(sample.due_at).toLocaleString()}</span>}
              </div>
              {canOperate && !sample.assigned_to && <button className="buttonSecondary" disabled={busyId === sample.id} onClick={() => void run(sample.id, () => api.assignEvidenceReview(sample.id))} type="button">Assign to me</button>}
              {canOperate && <button className="buttonSecondary" disabled={busyId === sample.id || sample.review_count > 0} onClick={() => void toggleHighRiskReview(sample)} type="button">{sample.required_reviews === 2 ? "Use standard single review" : "Mark job high risk · require 2 reviews"}</button>}
              {canOperate && sample.recording_id && (
                <div className="reviewLabelControls">
                  <input aria-label="Review notes" onChange={(event) => setReason((current) => ({ ...current, [sample.id]: event.target.value }))} placeholder="Optional evidence note" value={reason[sample.id] ?? ""} />
                  <button disabled={busyId === sample.id} onClick={() => void label(sample, "no_event")} type="button">{sample.status === "disputed" ? "Adjudicate: no event" : "No event"}</button>
                  <button className="buttonPrimary" disabled={busyId === sample.id} onClick={() => void label(sample, "event")} type="button">{sample.status === "disputed" ? "Adjudicate: event" : "Event visible"}</button>
                </div>
              )}
              {sample.verification_case_id && <a className="inlineLink" href="#verification-inbox">Review proposal in verification inbox</a>}
            </article>
          ))}
          {!samples.some((sample) => ["queued", "assigned", "reviewing", "disputed"].includes(sample.status)) && <div className="verificationEmpty"><strong>Queue is clear</strong><span>New samples appear automatically as footage is archived and proposals arrive.</span></div>}
        </div>
        <div className="datasetVersions">
          <div className="activeLearningSectionTitle"><h3>Versioned datasets</h3><span>Balanced labels</span></div>
          {canOperate && <div className="datasetCreate"><input aria-label="Dataset name" onChange={(event) => setDatasetName(event.target.value)} value={datasetName} /><button className="buttonPrimary" disabled={!datasetName.trim() || Boolean(busyId)} onClick={() => void run("create-dataset", () => api.createEvidenceDataset(datasetName.trim()))} type="button">Build version</button></div>}
          {datasets.map((dataset) => (
            <article className="datasetCard" key={dataset.id}>
              <div><strong>{dataset.name} v{dataset.version}</strong><span className={`datasetStatus datasetStatus-${dataset.status}`}>{dataset.status}</span></div>
              <p>{dataset.sample_count} reviewed samples · {Object.entries(dataset.balance).map(([key, value]) => `${key.replaceAll("_", " ")} ${value}`).join(" · ") || "No labeled samples yet"}</p>
              {dataset.manifest_sha256 && <small title={dataset.manifest_sha256}>Integrity {dataset.manifest_sha256.slice(0, 12)}…</small>}
              <div className="datasetActions">
                {canOperate && dataset.status === "draft" && <button disabled={busyId === dataset.id} onClick={() => void run(dataset.id, () => api.freezeEvidenceDataset(dataset.id))} type="button">Freeze version</button>}
                {dataset.status !== "draft" && <button disabled={busyId === dataset.id} onClick={() => void run(dataset.id, () => api.downloadEvidenceDataset(dataset))} type="button">Export JSONL</button>}
              </div>
            </article>
          ))}
          {datasets.length === 0 && <div className="verificationEmpty"><strong>No dataset versions yet</strong><span>Label review samples, then build the first balanced field dataset.</span></div>}
        </div>
      </div>
    </section>
  );
}
