"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type {
  DatasetReplayBuild,
  DeploymentPromotion,
  EvidenceDatasetVersion,
  ReplaySuite,
  ReplaySuiteRun,
  VisualAgentPlan,
} from "@/lib/types";

interface PromotionControlPanelProps {
  canAdminister: boolean;
  canOperate: boolean;
  onError: (message: string) => void;
}

export function PromotionControlPanel({ canAdminister, canOperate, onError }: PromotionControlPanelProps) {
  const [datasets, setDatasets] = useState<EvidenceDatasetVersion[]>([]);
  const [builds, setBuilds] = useState<DatasetReplayBuild[]>([]);
  const [promotions, setPromotions] = useState<DeploymentPromotion[]>([]);
  const [plans, setPlans] = useState<VisualAgentPlan[]>([]);
  const [runs, setRuns] = useState<ReplaySuiteRun[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [datasetId, setDatasetId] = useState("");
  const [planId, setPlanId] = useState("");
  const [candidateRunId, setCandidateRunId] = useState("");
  const [baselineRunId, setBaselineRunId] = useState("");

  const load = useCallback(async () => {
    try {
      const [nextDatasets, nextBuilds, nextPromotions, nextPlans, suites] = await Promise.all([
        api.listEvidenceDatasets(), api.listDatasetReplayBuilds(), api.listDeploymentPromotions(),
        api.listAgentPlans(), api.listReplaySuites(),
      ]);
      const histories = await Promise.all(suites.map((suite: ReplaySuite) => api.listReplaySuiteRuns(suite.id)));
      setDatasets(nextDatasets);
      setBuilds(nextBuilds);
      setPromotions(nextPromotions);
      setPlans(nextPlans);
      setRuns(histories.flat().filter((run) => run.status === "passed"));
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not load promotion controls.");
    }
  }, [onError]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const selectedBuild = useMemo(() => builds.find((build) => build.dataset_id === datasetId) ?? null, [builds, datasetId]);
  const eligibleRuns = selectedBuild ? runs.filter((run) => run.suite_id === selectedBuild.suite_id) : [];
  const draftPlans = plans.filter((plan) => plan.status === "draft");

  async function perform(key: string, action: () => Promise<unknown>) {
    setBusy(key);
    try { await action(); await load(); }
    catch (failure) { onError(failure instanceof Error ? failure.message : "Promotion action failed."); }
    finally { setBusy(null); }
  }

  async function createPromotion() {
    if (!datasetId || !planId || !candidateRunId) return;
    await perform("create", () => api.createDeploymentPromotion({
      dataset_id: datasetId,
      candidate_plan_id: planId,
      candidate_run_id: candidateRunId,
      baseline_run_id: baselineRunId || null,
    }));
  }

  return (
    <section className="panel promotionPanel" id="deployment-promotions">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Controlled improvement</span>
          <h2>Replay promotion and rollback</h2>
          <p>Turn frozen field evidence into a fair replay gate, compare candidate and baseline runs on the same dataset, and require an administrator decision before production changes.</p>
        </div>
        <button className="buttonSecondary" disabled={Boolean(busy)} onClick={() => void load()} type="button">Refresh</button>
      </div>
      <div className="promotionGrid">
        <div className="promotionColumn">
          <h3>Dataset replay gates</h3>
          {datasets.filter((dataset) => dataset.status !== "draft").map((dataset) => {
            const build = builds.find((item) => item.dataset_id === dataset.id);
            return (
              <article className="promotionCard" key={dataset.id}>
                <div><strong>{dataset.name} v{dataset.version}</strong><span>{dataset.sample_count} samples</span></div>
                {build ? <p>{build.evaluation_ids.length} replay baselines · {build.skipped_samples.length} unavailable</p> : <p>Ready to generate replay baselines from retained media.</p>}
                {canOperate && !build && <button className="buttonPrimary" disabled={Boolean(busy)} onClick={() => void perform(dataset.id, () => api.buildDatasetReplaySuite(dataset.id))} type="button">Build replay suite</button>}
              </article>
            );
          })}
          {!datasets.some((dataset) => dataset.status !== "draft") && <div className="verificationEmpty"><strong>No frozen field dataset</strong><span>Freeze a labeled dataset in the evidence panel first.</span></div>}
        </div>
        <div className="promotionColumn">
          <h3>Candidate comparison</h3>
          <div className="promotionComposer">
            <label>Frozen dataset<select onChange={(event) => { setDatasetId(event.target.value); setCandidateRunId(""); setBaselineRunId(""); }} value={datasetId}><option value="">Select dataset</option>{builds.map((build) => { const dataset = datasets.find((item) => item.id === build.dataset_id); return <option key={build.id} value={build.dataset_id}>{dataset ? `${dataset.name} v${dataset.version}` : build.dataset_id}</option>; })}</select></label>
            <label>Candidate agent plan<select onChange={(event) => setPlanId(event.target.value)} value={planId}><option value="">Select draft plan</option>{draftPlans.map((plan) => <option key={plan.id} value={plan.id}>Revision {plan.revision} · {plan.prompt}</option>)}</select></label>
            <label>Candidate replay run<select onChange={(event) => setCandidateRunId(event.target.value)} value={candidateRunId}><option value="">Select passed run</option>{eligibleRuns.map((run) => <option key={run.id} value={run.id}>{new Date(run.created_at).toLocaleString()} · F1 {String(run.metrics.macro_f1 ?? "—")}</option>)}</select></label>
            <label>Baseline run (optional)<select onChange={(event) => setBaselineRunId(event.target.value)} value={baselineRunId}><option value="">Establish first baseline</option>{eligibleRuns.filter((run) => run.id !== candidateRunId).map((run) => <option key={run.id} value={run.id}>{new Date(run.created_at).toLocaleString()} · F1 {String(run.metrics.macro_f1 ?? "—")}</option>)}</select></label>
            <button className="buttonPrimary" disabled={!canOperate || !datasetId || !planId || !candidateRunId || Boolean(busy)} onClick={() => void createPromotion()} type="button">Create comparison</button>
          </div>
        </div>
      </div>
      <div className="promotionHistory">
        <h3>Promotion decisions</h3>
        {promotions.map((promotion) => (
          <article className="promotionDecision" key={promotion.id}>
            <div><span className={`promotionStatus promotionStatus-${promotion.status}`}>{promotion.status}</span><strong>{promotion.comparison.recommendation.replaceAll("_", " ")}</strong><small>{new Date(promotion.requested_at).toLocaleString()}</small></div>
            <p>Candidate F1 {String(promotion.comparison.candidate.macro_f1 ?? "—")} · recall {String(promotion.comparison.candidate.macro_recall ?? "—")} · false alarms {String(promotion.comparison.candidate.false_positives ?? "—")}</p>
            {promotion.comparison.baseline_available && <p>Delta: F1 {String(promotion.comparison.deltas.macro_f1)} · recall {String(promotion.comparison.deltas.macro_recall)} · false alarms {String(promotion.comparison.deltas.false_positives)}</p>}
            {canAdminister && promotion.status === "ready" && <div className="datasetActions"><button disabled={Boolean(busy)} onClick={() => void perform(promotion.id, () => api.decideDeploymentPromotion(promotion.id, "reject", "Candidate was not approved for production."))} type="button">Reject</button><button className="buttonPrimary" disabled={Boolean(busy) || !promotion.comparison.promotion_gate_passed} onClick={() => void perform(promotion.id, () => api.decideDeploymentPromotion(promotion.id, "approve", "Frozen-dataset replay gates passed; approve the candidate with rollback metadata."))} type="button">Approve promotion</button></div>}
            {canAdminister && promotion.status === "approved" && <button className="buttonSecondary" disabled={Boolean(busy)} onClick={() => void perform(promotion.id, () => api.decideDeploymentPromotion(promotion.id, "rollback", "Restore the previous known-good deployment."))} type="button">Rollback</button>}
          </article>
        ))}
        {promotions.length === 0 && <div className="verificationEmpty"><strong>No promotion decisions</strong><span>Build a replay suite and complete candidate/baseline runs first.</span></div>}
      </div>
    </section>
  );
}
