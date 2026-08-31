"""Frozen-dataset replay builds and explicit deployment promotions."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from video_intelligence_api.auth import ActorDependency, AdminDependency, EditorDependency
from video_intelligence_api.dependencies import SessionDependency
from video_intelligence_api.execution_plans import plan_job
from video_intelligence_api.job_specs import validate_job_spec
from video_intelligence_api.models import (
    DatasetReplayBuild,
    DatasetVersionStatus,
    DeploymentPromotion,
    EvidenceAsset,
    EvidenceDatasetSample,
    EvidenceDatasetVersion,
    EvidenceReviewSample,
    PromotionStatus,
    RecordingSegment,
    RecordingSegmentStatus,
    ReplayEvaluation,
    ReplaySuite,
    ReplaySuiteRun,
    ReplaySuiteRunStatus,
    Rule,
    RuleCompilation,
    RuleStatus,
    VisualAgentPlan,
    VisualAgentPlanStatus,
    VisualAgentSimulation,
    new_id,
    utc_now,
)
from video_intelligence_api.routes.agent_plans import _approve
from video_intelligence_api.schemas import (
    DatasetReplayBuildRead,
    DeploymentPromotionCreate,
    DeploymentPromotionDecision,
    DeploymentPromotionRead,
)

router = APIRouter(prefix="/promotions", tags=["deployment promotions"])


def _fingerprint(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _metric(run: ReplaySuiteRun | None, key: str) -> float | int | None:
    if run is None:
        return None
    value = run.metrics.get(key)
    return value if isinstance(value, (int, float)) else None


def _comparison(candidate: ReplaySuiteRun, baseline: ReplaySuiteRun | None) -> dict[str, object]:
    candidate_f1 = float(_metric(candidate, "macro_f1") or 0)
    candidate_recall = float(_metric(candidate, "macro_recall") or 0)
    candidate_fp = int(_metric(candidate, "false_positives") or 0)
    if baseline is None:
        return {
            "baseline_available": False,
            "candidate": {
                "macro_f1": candidate_f1,
                "macro_recall": candidate_recall,
                "false_positives": candidate_fp,
            },
            "deltas": {},
            "promotion_gate_passed": candidate.status == ReplaySuiteRunStatus.PASSED,
            "recommendation": "establish_baseline",
        }
    baseline_f1 = float(_metric(baseline, "macro_f1") or 0)
    baseline_recall = float(_metric(baseline, "macro_recall") or 0)
    baseline_fp = int(_metric(baseline, "false_positives") or 0)
    deltas = {
        "macro_f1": round(candidate_f1 - baseline_f1, 6),
        "macro_recall": round(candidate_recall - baseline_recall, 6),
        "false_positives": candidate_fp - baseline_fp,
    }
    passed = (
        candidate.status == ReplaySuiteRunStatus.PASSED
        and deltas["macro_f1"] >= -0.01
        and deltas["macro_recall"] >= -0.01
        and deltas["false_positives"] <= 0
    )
    return {
        "baseline_available": True,
        "baseline": {
            "macro_f1": baseline_f1,
            "macro_recall": baseline_recall,
            "false_positives": baseline_fp,
        },
        "candidate": {
            "macro_f1": candidate_f1,
            "macro_recall": candidate_recall,
            "false_positives": candidate_fp,
        },
        "deltas": deltas,
        "promotion_gate_passed": passed,
        "recommendation": "approve" if passed else "reject_regression",
    }


@router.post(
    "/datasets/{dataset_id}/replay-suite",
    response_model=DatasetReplayBuildRead,
    status_code=status.HTTP_201_CREATED,
)
async def build_dataset_replay_suite(
    dataset_id: str,
    session: SessionDependency,
    actor: EditorDependency,
) -> DatasetReplayBuild:
    existing = await session.scalar(
        select(DatasetReplayBuild).where(
            DatasetReplayBuild.dataset_id == dataset_id,
            DatasetReplayBuild.organization_id == actor.organization_id,
        )
    )
    if existing is not None:
        return existing
    dataset = await session.scalar(
        select(EvidenceDatasetVersion).where(
            EvidenceDatasetVersion.id == dataset_id,
            EvidenceDatasetVersion.organization_id == actor.organization_id,
        )
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset.status == DatasetVersionStatus.DRAFT or not dataset.manifest_sha256:
        raise HTTPException(status_code=409, detail="Freeze the dataset before building replays")
    rows = (
        await session.execute(
            select(EvidenceDatasetSample, EvidenceReviewSample)
            .join(EvidenceReviewSample, EvidenceReviewSample.id == EvidenceDatasetSample.sample_id)
            .where(EvidenceDatasetSample.dataset_id == dataset.id)
            .order_by(EvidenceDatasetSample.id)
        )
    ).all()
    evaluation_ids: list[str] = []
    skipped: list[dict[str, object]] = []
    now = utc_now()
    for membership, sample in rows:
        rule = await session.get(Rule, sample.rule_id)
        if rule is None or rule.spec is None:
            skipped.append({"sample_id": sample.id, "reason": "job specification unavailable"})
            continue
        compilation = await session.scalar(
            select(RuleCompilation)
            .where(RuleCompilation.accepted_rule_id == rule.id)
            .order_by(RuleCompilation.created_at.desc())
            .limit(1)
        )
        if compilation is None:
            skipped.append({"sample_id": sample.id, "reason": "accepted compilation unavailable"})
            continue
        source_uri: str | None = None
        duration = 0.0
        if sample.recording_id:
            recording = await session.get(RecordingSegment, sample.recording_id)
            if recording and recording.status == RecordingSegmentStatus.READY:
                source_uri, duration = recording.storage_uri, recording.duration_seconds
        elif sample.event_id:
            evidence = await session.scalar(
                select(EvidenceAsset).where(EvidenceAsset.event_id == sample.event_id)
            )
            if evidence:
                source_uri = evidence.storage_uri
                duration = float(evidence.duration_seconds or 10.0)
        if not source_uri or duration <= 0:
            skipped.append({"sample_id": sample.id, "reason": "replayable media unavailable"})
            continue
        job = validate_job_spec(rule.spec)
        prompt = rule.original_prompt or rule.name
        execution = plan_job(job, prompt)
        outcome = str(membership.label_snapshot["outcome"])
        contains_event = outcome in {"true_positive", "false_negative"}
        evaluation = ReplayEvaluation(
            id=new_id(),
            organization_id=actor.organization_id,
            camera_id=sample.camera_id,
            compilation_id=compilation.id,
            name=f"{dataset.name} v{dataset.version} · {sample.id[:8]}",
            source_uri=source_uri,
            prompt=prompt,
            scenario_key=None,
            scenario_variant="positive" if contains_event else "negative",
            source_kind="field",
            environment_tags=list(membership.label_snapshot.get("environment_tags") or []),
            duration_seconds=duration,
            execution_strategy=execution.strategy,
            compiled_rule=job.model_dump(mode="json"),
            execution_plan=execution.model_dump(mode="json"),
            expected_intervals=(
                [{"start_seconds": 0.0, "end_seconds": duration, "label": "event"}]
                if contains_event
                else []
            ),
            created_at=now,
            updated_at=now,
        )
        session.add(evaluation)
        evaluation_ids.append(evaluation.id)
    if not evaluation_ids:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "No dataset samples have replayable retained media",
                "skipped": skipped,
            },
        )
    suite = ReplaySuite(
        id=new_id(),
        organization_id=actor.organization_id,
        name=f"{dataset.name} v{dataset.version} field gate",
        evaluation_ids=evaluation_ids,
        minimum_macro_f1=0.8,
        minimum_macro_recall=0.8,
        maximum_false_positives=0,
        maximum_estimated_cost_usd=max(1.0, len(evaluation_ids) * 0.1),
        require_pricing=True,
        created_at=now,
        updated_at=now,
    )
    session.add(suite)
    build = DatasetReplayBuild(
        id=new_id(),
        organization_id=actor.organization_id,
        dataset_id=dataset.id,
        suite_id=suite.id,
        evaluation_ids=evaluation_ids,
        skipped_samples=skipped,
        created_by=actor.subject,
        created_at=now,
    )
    session.add(build)
    await session.commit()
    await session.refresh(build)
    return build


@router.get("", response_model=list[DeploymentPromotionRead])
async def list_promotions(
    session: SessionDependency, actor: ActorDependency
) -> list[DeploymentPromotion]:
    return list(
        (
            await session.scalars(
                select(DeploymentPromotion)
                .where(DeploymentPromotion.organization_id == actor.organization_id)
                .order_by(DeploymentPromotion.created_at.desc())
            )
        ).all()
    )


@router.get("/dataset-replay-builds", response_model=list[DatasetReplayBuildRead])
async def list_dataset_replay_builds(
    session: SessionDependency, actor: ActorDependency
) -> list[DatasetReplayBuild]:
    return list(
        (
            await session.scalars(
                select(DatasetReplayBuild)
                .where(DatasetReplayBuild.organization_id == actor.organization_id)
                .order_by(DatasetReplayBuild.created_at.desc())
            )
        ).all()
    )


@router.post("", response_model=DeploymentPromotionRead, status_code=status.HTTP_201_CREATED)
async def create_promotion(
    payload: DeploymentPromotionCreate,
    session: SessionDependency,
    actor: EditorDependency,
) -> DeploymentPromotion:
    build = await session.scalar(
        select(DatasetReplayBuild).where(
            DatasetReplayBuild.dataset_id == payload.dataset_id,
            DatasetReplayBuild.organization_id == actor.organization_id,
        )
    )
    plan = await session.scalar(
        select(VisualAgentPlan).where(
            VisualAgentPlan.id == payload.candidate_plan_id,
            VisualAgentPlan.organization_id == actor.organization_id,
        )
    )
    candidate = await session.scalar(
        select(ReplaySuiteRun).where(
            ReplaySuiteRun.id == payload.candidate_run_id,
            ReplaySuiteRun.organization_id == actor.organization_id,
        )
    )
    if build is None or plan is None or candidate is None:
        raise HTTPException(status_code=404, detail="Dataset build, plan, or replay run not found")
    if plan.status != VisualAgentPlanStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Only a draft agent plan can be promoted")
    if plan.unsupported_capabilities:
        raise HTTPException(status_code=409, detail="Candidate plan has unsupported capabilities")
    simulation_count = int(
        await session.scalar(
            select(func.count())
            .select_from(VisualAgentSimulation)
            .where(VisualAgentSimulation.plan_id == plan.id)
        )
        or 0
    )
    if not simulation_count:
        raise HTTPException(status_code=409, detail="Run the safe plan simulation first")
    matching_evaluations = int(
        await session.scalar(
            select(func.count())
            .select_from(ReplayEvaluation)
            .join(RuleCompilation, RuleCompilation.id == ReplayEvaluation.compilation_id)
            .where(
                ReplayEvaluation.id.in_(build.evaluation_ids),
                RuleCompilation.accepted_rule_id == plan.rule_id,
            )
        )
        or 0
    )
    if matching_evaluations != len(build.evaluation_ids):
        raise HTTPException(
            status_code=409, detail="Promotion dataset must contain only the candidate job"
        )
    if candidate.suite_id != build.suite_id or candidate.status != ReplaySuiteRunStatus.PASSED:
        raise HTTPException(
            status_code=409, detail="Candidate must pass this dataset's replay suite"
        )
    baseline = None
    if payload.baseline_run_id:
        baseline = await session.scalar(
            select(ReplaySuiteRun).where(
                ReplaySuiteRun.id == payload.baseline_run_id,
                ReplaySuiteRun.organization_id == actor.organization_id,
            )
        )
        if (
            baseline is None
            or baseline.suite_id != build.suite_id
            or baseline.status != ReplaySuiteRunStatus.PASSED
        ):
            raise HTTPException(status_code=409, detail="Baseline must use the same frozen dataset")
    baseline_plan = await session.scalar(
        select(VisualAgentPlan)
        .where(
            VisualAgentPlan.camera_id == plan.camera_id,
            VisualAgentPlan.status == VisualAgentPlanStatus.APPROVED,
            VisualAgentPlan.id != plan.id,
        )
        .order_by(VisualAgentPlan.revision.desc())
        .limit(1)
    )
    comparison = _comparison(candidate, baseline)
    comparison["candidate_plan_sha256"] = _fingerprint(plan.plan)
    comparison["baseline_plan_sha256"] = _fingerprint(baseline_plan.plan) if baseline_plan else None
    now = utc_now()
    promotion = DeploymentPromotion(
        id=new_id(),
        organization_id=actor.organization_id,
        dataset_id=payload.dataset_id,
        camera_id=plan.camera_id,
        rule_id=plan.rule_id,
        candidate_plan_id=plan.id,
        baseline_plan_id=baseline_plan.id if baseline_plan else None,
        candidate_run_id=candidate.id,
        baseline_run_id=baseline.id if baseline else None,
        status=PromotionStatus.READY,
        comparison=comparison,
        rollback_metadata={
            "baseline_plan_id": baseline_plan.id if baseline_plan else None,
            "baseline_regression_run_id": baseline_plan.regression_run_id
            if baseline_plan
            else None,
            "candidate_plan_id": plan.id,
            "camera_id": plan.camera_id,
            "rule_id": plan.rule_id,
        },
        requested_by=actor.subject,
        requested_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(promotion)
    await session.commit()
    await session.refresh(promotion)
    return promotion


@router.post("/{promotion_id}/approve", response_model=DeploymentPromotionRead)
async def approve_promotion(
    promotion_id: str,
    payload: DeploymentPromotionDecision,
    session: SessionDependency,
    actor: AdminDependency,
) -> DeploymentPromotion:
    promotion = await session.scalar(
        select(DeploymentPromotion).where(
            DeploymentPromotion.id == promotion_id,
            DeploymentPromotion.organization_id == actor.organization_id,
        )
    )
    if promotion is None:
        raise HTTPException(status_code=404, detail="Promotion not found")
    if promotion.status != PromotionStatus.READY:
        raise HTTPException(status_code=409, detail="Only ready promotions can be approved")
    if not bool(promotion.comparison.get("promotion_gate_passed")):
        raise HTTPException(status_code=409, detail="Candidate regressed against the baseline")
    plan = await session.get(VisualAgentPlan, promotion.candidate_plan_id)
    run = await session.get(ReplaySuiteRun, promotion.candidate_run_id)
    if plan is None or run is None:
        raise HTTPException(status_code=409, detail="Promotion artifacts are unavailable")
    await _approve(plan, run, session, actor.subject)
    promotion.status = PromotionStatus.APPROVED
    promotion.decided_by = actor.subject
    promotion.decided_at = utc_now()
    promotion.decision_reason = payload.reasoning
    promotion.updated_at = utc_now()
    await session.commit()
    await session.refresh(promotion)
    return promotion


@router.post("/{promotion_id}/reject", response_model=DeploymentPromotionRead)
async def reject_promotion(
    promotion_id: str,
    payload: DeploymentPromotionDecision,
    session: SessionDependency,
    actor: AdminDependency,
) -> DeploymentPromotion:
    promotion = await session.scalar(
        select(DeploymentPromotion).where(
            DeploymentPromotion.id == promotion_id,
            DeploymentPromotion.organization_id == actor.organization_id,
        )
    )
    if promotion is None:
        raise HTTPException(status_code=404, detail="Promotion not found")
    if promotion.status != PromotionStatus.READY:
        raise HTTPException(status_code=409, detail="Only ready promotions can be rejected")
    promotion.status = PromotionStatus.REJECTED
    promotion.decided_by = actor.subject
    promotion.decided_at = utc_now()
    promotion.decision_reason = payload.reasoning
    promotion.updated_at = utc_now()
    await session.commit()
    return promotion


@router.post("/{promotion_id}/rollback", response_model=DeploymentPromotionRead)
async def rollback_promotion(
    promotion_id: str,
    payload: DeploymentPromotionDecision,
    session: SessionDependency,
    actor: AdminDependency,
) -> DeploymentPromotion:
    promotion = await session.scalar(
        select(DeploymentPromotion).where(
            DeploymentPromotion.id == promotion_id,
            DeploymentPromotion.organization_id == actor.organization_id,
        )
    )
    if promotion is None:
        raise HTTPException(status_code=404, detail="Promotion not found")
    if promotion.status != PromotionStatus.APPROVED:
        raise HTTPException(status_code=409, detail="Only approved promotions can be rolled back")
    now = utc_now()
    if promotion.baseline_plan_id:
        baseline_plan = await session.get(VisualAgentPlan, promotion.baseline_plan_id)
        baseline_run = (
            await session.get(ReplaySuiteRun, baseline_plan.regression_run_id)
            if baseline_plan and baseline_plan.regression_run_id
            else None
        )
        if baseline_plan is None or baseline_run is None:
            raise HTTPException(status_code=409, detail="Rollback baseline is unavailable")
        await _approve(baseline_plan, baseline_run, session, actor.subject)
    else:
        candidate_plan = await session.get(VisualAgentPlan, promotion.candidate_plan_id)
        rule = await session.get(Rule, promotion.rule_id)
        if candidate_plan:
            candidate_plan.status = VisualAgentPlanStatus.SUPERSEDED
        if rule:
            rule.status = RuleStatus.PAUSED
    promotion.status = PromotionStatus.ROLLED_BACK
    promotion.rolled_back_by = actor.subject
    promotion.rolled_back_at = now
    promotion.rollback_reason = payload.reasoning
    promotion.updated_at = now
    await session.commit()
    await session.refresh(promotion)
    return promotion
