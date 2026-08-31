"""Active-evidence review queue and versioned dataset exports."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select

from video_intelligence_api.active_learning import reconcile_samples, stable_manifest
from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.dependencies import SessionDependency
from video_intelligence_api.field_accuracy import record_case_label, refresh_accuracy_snapshot
from video_intelligence_api.models import (
    AccuracyLabelOutcome,
    Camera,
    DatasetVersionStatus,
    Event,
    EvidenceDatasetSample,
    EvidenceDatasetVersion,
    EvidenceReviewSample,
    EvidenceReviewVote,
    EvidenceSamplingPolicy,
    FieldAccuracyLabel,
    RecordingSegment,
    ReviewSampleStatus,
    Rule,
    VerificationCase,
    VerificationStatus,
    new_id,
    utc_now,
)
from video_intelligence_api.schemas import (
    EvidenceAdjudicationCreate,
    EvidenceDatasetCreate,
    EvidenceDatasetRead,
    EvidenceReviewAssignment,
    EvidenceReviewLabelCreate,
    EvidenceReviewQueueSummary,
    EvidenceReviewSampleRead,
    EvidenceSamplingPolicyRead,
    EvidenceSamplingPolicyUpdate,
    EvidenceSamplingRunRead,
    FieldAccuracyLabelRead,
)
from video_intelligence_api.security import require_agent_key
from video_intelligence_api.tenancy import tenant_rule

router = APIRouter(prefix="/active-learning", tags=["active learning"])


async def sample_response(
    session: SessionDependency, sample: EvidenceReviewSample
) -> EvidenceReviewSampleRead:
    camera = await session.get(Camera, sample.camera_id)
    rule = await session.get(Rule, sample.rule_id)
    label = await session.get(FieldAccuracyLabel, sample.label_id) if sample.label_id else None
    review_count = int(
        await session.scalar(
            select(func.count())
            .select_from(EvidenceReviewVote)
            .where(EvidenceReviewVote.sample_id == sample.id)
        )
        or 0
    )
    policy = await session.scalar(
        select(EvidenceSamplingPolicy).where(EvidenceSamplingPolicy.rule_id == sample.rule_id)
    )
    return EvidenceReviewSampleRead(
        id=sample.id,
        organization_id=sample.organization_id,
        camera_id=sample.camera_id,
        camera_name=camera.name if camera else "Deleted camera",
        rule_id=sample.rule_id,
        rule_name=rule.name if rule else "Deleted job",
        verification_case_id=sample.verification_case_id,
        event_id=sample.event_id,
        recording_id=sample.recording_id,
        kind=sample.kind,
        status=sample.status,
        priority=sample.priority,
        model_context=sample.model_context,
        environment_tags=sample.environment_tags,
        assigned_to=sample.assigned_to,
        assigned_at=sample.assigned_at,
        due_at=sample.due_at,
        label=FieldAccuracyLabelRead.model_validate(label) if label else None,
        review_count=review_count,
        required_reviews=policy.required_reviews if policy else 1,
        consensus_status=sample.consensus_status,
        adjudicated_by=sample.adjudicated_by,
        adjudicated_at=sample.adjudicated_at,
        expires_at=sample.expires_at,
        created_at=sample.created_at,
        updated_at=sample.updated_at,
    )


async def dataset_response(
    session: SessionDependency, dataset: EvidenceDatasetVersion
) -> EvidenceDatasetRead:
    count = int(
        await session.scalar(
            select(func.count())
            .select_from(EvidenceDatasetSample)
            .where(EvidenceDatasetSample.dataset_id == dataset.id)
        )
        or 0
    )
    return EvidenceDatasetRead(
        id=dataset.id,
        organization_id=dataset.organization_id,
        name=dataset.name,
        version=dataset.version,
        status=dataset.status,
        selection=dataset.selection,
        balance=dataset.balance,
        sample_count=count,
        manifest_sha256=dataset.manifest_sha256,
        created_by=dataset.created_by,
        frozen_at=dataset.frozen_at,
        exported_at=dataset.exported_at,
        created_at=dataset.created_at,
    )


@router.post(
    "/agent/reconcile",
    response_model=EvidenceSamplingRunRead,
    dependencies=[Depends(require_agent_key)],
)
async def reconcile_active_learning(session: SessionDependency) -> dict[str, int]:
    return await reconcile_samples(session)


@router.get("/queue", response_model=list[EvidenceReviewSampleRead])
async def list_review_queue(
    session: SessionDependency,
    actor: ActorDependency,
    sample_status: Annotated[ReviewSampleStatus | None, Query(alias="status")] = None,
    rule_id: Annotated[str | None, Query(max_length=36)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[EvidenceReviewSampleRead]:
    statement = select(EvidenceReviewSample).where(
        EvidenceReviewSample.organization_id == actor.organization_id
    )
    if sample_status is not None:
        statement = statement.where(EvidenceReviewSample.status == sample_status)
    if rule_id is not None:
        statement = statement.where(EvidenceReviewSample.rule_id == rule_id)
    samples = (
        await session.scalars(
            statement.order_by(
                EvidenceReviewSample.priority.desc(), EvidenceReviewSample.created_at
            ).limit(limit)
        )
    ).all()
    return [await sample_response(session, sample) for sample in samples]


@router.get("/queue-summary", response_model=EvidenceReviewQueueSummary)
async def review_queue_summary(
    session: SessionDependency, actor: ActorDependency
) -> EvidenceReviewQueueSummary:
    samples = list(
        (
            await session.scalars(
                select(EvidenceReviewSample).where(
                    EvidenceReviewSample.organization_id == actor.organization_id
                )
            )
        ).all()
    )
    now = utc_now()
    counts = Counter(sample.status.value for sample in samples)
    return EvidenceReviewQueueSummary(
        queued=counts["queued"],
        assigned=counts["assigned"],
        reviewing=counts["reviewing"],
        disputed=counts["disputed"],
        labeled=counts["labeled"],
        overdue=sum(
            1
            for sample in samples
            if sample.due_at
            and sample.due_at < now
            and sample.status
            in {
                ReviewSampleStatus.QUEUED,
                ReviewSampleStatus.ASSIGNED,
                ReviewSampleStatus.REVIEWING,
                ReviewSampleStatus.DISPUTED,
            }
        ),
        by_kind=dict(Counter(sample.kind.value for sample in samples)),
    )


@router.post("/queue/{sample_id}/assign", response_model=EvidenceReviewSampleRead)
async def assign_review_sample(
    sample_id: str,
    payload: EvidenceReviewAssignment,
    session: SessionDependency,
    actor: EditorDependency,
) -> EvidenceReviewSampleRead:
    sample = await session.scalar(
        select(EvidenceReviewSample).where(
            EvidenceReviewSample.id == sample_id,
            EvidenceReviewSample.organization_id == actor.organization_id,
        )
    )
    if sample is None:
        raise HTTPException(status_code=404, detail="Review sample not found")
    if sample.status in {ReviewSampleStatus.LABELED, ReviewSampleStatus.SKIPPED}:
        raise HTTPException(status_code=409, detail="Completed review samples cannot be assigned")
    policy = await session.scalar(
        select(EvidenceSamplingPolicy).where(EvidenceSamplingPolicy.rule_id == sample.rule_id)
    )
    now = utc_now()
    sample.assigned_to = payload.assigned_to or actor.subject
    sample.assigned_at = now
    sample.due_at = now + timedelta(hours=policy.review_sla_hours if policy else 24)
    sample.status = ReviewSampleStatus.ASSIGNED
    sample.updated_at = now
    await session.commit()
    return await sample_response(session, sample)


@router.post("/queue/{sample_id}/label", response_model=EvidenceReviewSampleRead)
async def label_review_sample(
    sample_id: str,
    payload: EvidenceReviewLabelCreate,
    session: SessionDependency,
    actor: EditorDependency,
) -> EvidenceReviewSampleRead:
    sample = await session.scalar(
        select(EvidenceReviewSample).where(
            EvidenceReviewSample.id == sample_id,
            EvidenceReviewSample.organization_id == actor.organization_id,
        )
    )
    if sample is None:
        raise HTTPException(status_code=404, detail="Review sample not found")
    if sample.label_id:
        return await sample_response(session, sample)
    if sample.verification_case_id:
        case = await session.get(VerificationCase, sample.verification_case_id)
        if case is None or case.status not in {
            VerificationStatus.CONFIRMED,
            VerificationStatus.REJECTED,
        }:
            raise HTTPException(
                status_code=409,
                detail="Decide this proposal in the verification inbox before auditing it",
            )
    policy = await session.scalar(
        select(EvidenceSamplingPolicy).where(EvidenceSamplingPolicy.rule_id == sample.rule_id)
    )
    required_reviews = policy.required_reviews if policy else 1
    if required_reviews > 1:
        existing_vote = await session.scalar(
            select(EvidenceReviewVote).where(
                EvidenceReviewVote.sample_id == sample.id,
                EvidenceReviewVote.reviewer == actor.subject,
            )
        )
        if existing_vote is not None:
            raise HTTPException(
                status_code=409, detail="Each reviewer can submit only one independent judgment"
            )
        session.add(
            EvidenceReviewVote(
                id=new_id(),
                organization_id=actor.organization_id,
                sample_id=sample.id,
                outcome=payload.actual_outcome,
                reasoning=payload.reasoning,
                environment_tags=list(payload.environment_tags),
                reviewer=actor.subject,
                created_at=utc_now(),
            )
        )
        await session.flush()
        votes = list(
            (
                await session.scalars(
                    select(EvidenceReviewVote)
                    .where(EvidenceReviewVote.sample_id == sample.id)
                    .order_by(EvidenceReviewVote.created_at)
                )
            ).all()
        )
        if len(votes) < required_reviews:
            sample.status = ReviewSampleStatus.REVIEWING
            sample.consensus_status = "awaiting_review"
            sample.updated_at = utc_now()
            await session.commit()
            return await sample_response(session, sample)
        outcomes = {vote.outcome for vote in votes}
        if len(outcomes) > 1 and (policy is None or policy.require_adjudication):
            sample.status = ReviewSampleStatus.DISPUTED
            sample.consensus_status = "disputed"
            sample.updated_at = utc_now()
            await session.commit()
            return await sample_response(session, sample)
        payload = EvidenceReviewLabelCreate(
            actual_outcome=votes[-1].outcome if len(outcomes) > 1 else votes[0].outcome,
            reasoning="Consensus: " + " | ".join(vote.reasoning for vote in votes),
            environment_tags=sorted({tag for vote in votes for tag in vote.environment_tags}),
        )
        sample.consensus_status = "consensus"
    else:
        sample.consensus_status = "single_review"
    await _finalize_sample_label(sample, payload, session, actor.subject)
    await session.commit()
    return await sample_response(session, sample)


async def _finalize_sample_label(
    sample: EvidenceReviewSample,
    payload: EvidenceReviewLabelCreate,
    session: SessionDependency,
    reviewer: str,
) -> None:
    camera, rule = (
        await session.get(Camera, sample.camera_id),
        await session.get(Rule, sample.rule_id),
    )
    if camera is None or rule is None:
        raise HTTPException(status_code=409, detail="The sample camera or job no longer exists")
    now = utc_now()
    if sample.verification_case_id:
        case = await session.get(VerificationCase, sample.verification_case_id)
        event = await session.get(Event, sample.event_id) if sample.event_id else None
        if case is None or event is None:
            raise HTTPException(status_code=409, detail="Verification evidence is unavailable")
        if case.status not in {VerificationStatus.CONFIRMED, VerificationStatus.REJECTED}:
            raise HTTPException(
                status_code=409,
                detail="Decide this proposal in the verification inbox before auditing it",
            )
        label, _ = await record_case_label(
            session,
            case=case,
            event=event,
            camera=camera,
            rule=rule,
            event_occurred=payload.actual_outcome == "event",
            source="active_review",
            notes=payload.reasoning,
            environment_tags=list(payload.environment_tags),
            reviewed_by=reviewer,
        )
    else:
        recording = (
            await session.get(RecordingSegment, sample.recording_id)
            if sample.recording_id
            else None
        )
        if recording is None or recording.organization_id != sample.organization_id:
            raise HTTPException(status_code=409, detail="Recording evidence is unavailable")
        label = FieldAccuracyLabel(
            id=new_id(),
            organization_id=sample.organization_id,
            camera_id=camera.id,
            rule_id=rule.id,
            recording_id=recording.id,
            outcome=AccuracyLabelOutcome.FALSE_NEGATIVE
            if payload.actual_outcome == "event"
            else AccuracyLabelOutcome.TRUE_NEGATIVE,
            source="background_review",
            environment_tags=list(payload.environment_tags),
            notes=payload.reasoning,
            occurred_at=recording.started_at,
            reviewed_by=reviewer,
            created_at=now,
        )
        session.add(label)
        await session.flush()
        await refresh_accuracy_snapshot(
            session,
            organization_id=sample.organization_id,
            camera_id=camera.id,
            rule_id=rule.id,
        )
    sample.label_id = label.id
    sample.environment_tags = list(payload.environment_tags)
    sample.status = ReviewSampleStatus.LABELED
    sample.updated_at = now


@router.post("/queue/{sample_id}/adjudicate", response_model=EvidenceReviewSampleRead)
async def adjudicate_review_sample(
    sample_id: str,
    payload: EvidenceAdjudicationCreate,
    session: SessionDependency,
    actor: EditorDependency,
) -> EvidenceReviewSampleRead:
    sample = await session.scalar(
        select(EvidenceReviewSample).where(
            EvidenceReviewSample.id == sample_id,
            EvidenceReviewSample.organization_id == actor.organization_id,
        )
    )
    if sample is None:
        raise HTTPException(status_code=404, detail="Review sample not found")
    if sample.status != ReviewSampleStatus.DISPUTED:
        raise HTTPException(status_code=409, detail="Only disputed samples need adjudication")
    voters = set(
        (
            await session.scalars(
                select(EvidenceReviewVote.reviewer).where(EvidenceReviewVote.sample_id == sample.id)
            )
        ).all()
    )
    if actor.subject in voters:
        raise HTTPException(
            status_code=409, detail="Adjudication requires a reviewer who did not cast a vote"
        )
    await _finalize_sample_label(sample, payload, session, actor.subject)
    sample.consensus_status = "adjudicated"
    sample.adjudicated_by = actor.subject
    sample.adjudicated_at = utc_now()
    await session.commit()
    return await sample_response(session, sample)


@router.get("/rules/{rule_id}/policy", response_model=EvidenceSamplingPolicyRead)
async def get_sampling_policy(
    rule_id: str, session: SessionDependency, actor: ActorDependency
) -> EvidenceSamplingPolicyRead:
    rule = await tenant_rule(session, actor, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    policy = await session.scalar(
        select(EvidenceSamplingPolicy).where(EvidenceSamplingPolicy.rule_id == rule_id)
    )
    return EvidenceSamplingPolicyRead(
        rule_id=rule.id,
        camera_id=rule.camera_id,
        enabled=policy.enabled if policy else True,
        normal_sample_interval_seconds=policy.normal_sample_interval_seconds if policy else 900,
        daily_limit=policy.daily_limit if policy else 100,
        review_sla_hours=policy.review_sla_hours if policy else 24,
        retention_days=policy.retention_days if policy else 30,
        required_reviews=policy.required_reviews if policy else 1,
        require_adjudication=policy.require_adjudication if policy else True,
    )


@router.put("/rules/{rule_id}/policy", response_model=EvidenceSamplingPolicyRead)
async def update_sampling_policy(
    rule_id: str,
    payload: EvidenceSamplingPolicyUpdate,
    session: SessionDependency,
    actor: EditorDependency,
) -> EvidenceSamplingPolicyRead:
    rule = await tenant_rule(session, actor, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    policy = await session.scalar(
        select(EvidenceSamplingPolicy).where(EvidenceSamplingPolicy.rule_id == rule_id)
    )
    now = utc_now()
    if policy is None:
        policy = EvidenceSamplingPolicy(
            id=new_id(),
            organization_id=actor.organization_id,
            camera_id=rule.camera_id,
            rule_id=rule.id,
            updated_by=actor.subject,
            created_at=now,
            updated_at=now,
            **payload.model_dump(),
        )
        session.add(policy)
    else:
        for field, value in payload.model_dump().items():
            setattr(policy, field, value)
        policy.updated_by, policy.updated_at = actor.subject, now
    await session.commit()
    return EvidenceSamplingPolicyRead.model_validate(policy)


@router.get("/datasets", response_model=list[EvidenceDatasetRead])
async def list_datasets(
    session: SessionDependency, actor: ActorDependency
) -> list[EvidenceDatasetRead]:
    datasets = (
        await session.scalars(
            select(EvidenceDatasetVersion)
            .where(EvidenceDatasetVersion.organization_id == actor.organization_id)
            .order_by(EvidenceDatasetVersion.created_at.desc())
        )
    ).all()
    return [await dataset_response(session, dataset) for dataset in datasets]


@router.post("/datasets", response_model=EvidenceDatasetRead, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    payload: EvidenceDatasetCreate, session: SessionDependency, actor: EditorDependency
) -> EvidenceDatasetRead:
    statement = (
        select(EvidenceReviewSample, FieldAccuracyLabel)
        .join(FieldAccuracyLabel, FieldAccuracyLabel.id == EvidenceReviewSample.label_id)
        .where(
            EvidenceReviewSample.organization_id == actor.organization_id,
            EvidenceReviewSample.status == ReviewSampleStatus.LABELED,
        )
        .order_by(EvidenceReviewSample.created_at.desc())
    )
    if payload.rule_id:
        statement = statement.where(EvidenceReviewSample.rule_id == payload.rule_id)
    if payload.camera_id:
        statement = statement.where(EvidenceReviewSample.camera_id == payload.camera_id)
    groups: dict[str, list[tuple[EvidenceReviewSample, FieldAccuracyLabel]]] = defaultdict(list)
    for sample, label in (await session.execute(statement)).all():
        groups[label.outcome.value].append((sample, label))
    selected: list[tuple[EvidenceReviewSample, FieldAccuracyLabel]] = []
    while len(selected) < payload.max_samples and any(groups.values()):
        for outcome in sorted(groups):
            if groups[outcome] and len(selected) < payload.max_samples:
                selected.append(groups[outcome].pop(0))
    version = (
        int(
            await session.scalar(
                select(func.max(EvidenceDatasetVersion.version)).where(
                    EvidenceDatasetVersion.organization_id == actor.organization_id,
                    EvidenceDatasetVersion.name == payload.name,
                )
            )
            or 0
        )
        + 1
    )
    now = utc_now()
    balance = dict(Counter(label.outcome.value for _, label in selected))
    dataset = EvidenceDatasetVersion(
        id=new_id(),
        organization_id=actor.organization_id,
        name=payload.name,
        version=version,
        status=DatasetVersionStatus.DRAFT,
        selection=payload.model_dump(),
        balance=balance,
        created_by=actor.subject,
        created_at=now,
    )
    session.add(dataset)
    for sample, label in selected:
        session.add(
            EvidenceDatasetSample(
                id=new_id(),
                dataset_id=dataset.id,
                sample_id=sample.id,
                label_snapshot={
                    "outcome": label.outcome.value,
                    "source": label.source,
                    "environment_tags": label.environment_tags,
                    "reviewed_by": label.reviewed_by,
                    "occurred_at": label.occurred_at.isoformat(),
                },
                created_at=now,
            )
        )
    await session.commit()
    return await dataset_response(session, dataset)


async def manifest_rows(
    session: SessionDependency, dataset: EvidenceDatasetVersion
) -> list[dict[str, object]]:
    rows = (
        await session.execute(
            select(EvidenceDatasetSample, EvidenceReviewSample)
            .join(EvidenceReviewSample, EvidenceReviewSample.id == EvidenceDatasetSample.sample_id)
            .where(EvidenceDatasetSample.dataset_id == dataset.id)
            .order_by(EvidenceDatasetSample.id)
        )
    ).all()
    return [
        {
            "dataset": {"name": dataset.name, "version": dataset.version},
            "sample_id": sample.id,
            "camera_id": sample.camera_id,
            "rule_id": sample.rule_id,
            "verification_case_id": sample.verification_case_id,
            "event_id": sample.event_id,
            "recording_id": sample.recording_id,
            "kind": sample.kind.value,
            "model_context": sample.model_context,
            "label": membership.label_snapshot,
        }
        for membership, sample in rows
    ]


@router.post("/datasets/{dataset_id}/freeze", response_model=EvidenceDatasetRead)
async def freeze_dataset(
    dataset_id: str, session: SessionDependency, actor: EditorDependency
) -> EvidenceDatasetRead:
    dataset = await session.scalar(
        select(EvidenceDatasetVersion).where(
            EvidenceDatasetVersion.id == dataset_id,
            EvidenceDatasetVersion.organization_id == actor.organization_id,
        )
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset.status == DatasetVersionStatus.DRAFT:
        _, dataset.manifest_sha256 = stable_manifest(await manifest_rows(session, dataset))
        dataset.status, dataset.frozen_at = DatasetVersionStatus.FROZEN, utc_now()
        await session.commit()
    return await dataset_response(session, dataset)


@router.get("/datasets/{dataset_id}/export")
async def export_dataset(
    dataset_id: str, session: SessionDependency, actor: ActorDependency
) -> Response:
    dataset = await session.scalar(
        select(EvidenceDatasetVersion).where(
            EvidenceDatasetVersion.id == dataset_id,
            EvidenceDatasetVersion.organization_id == actor.organization_id,
        )
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset.status == DatasetVersionStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Freeze the dataset before export")
    body, sha256 = stable_manifest(await manifest_rows(session, dataset))
    if dataset.manifest_sha256 != sha256:
        raise HTTPException(
            status_code=409, detail="Frozen dataset manifest integrity check failed"
        )
    dataset.status, dataset.exported_at = DatasetVersionStatus.EXPORTED, utc_now()
    await session.commit()
    filename = f"{dataset.name.replace(' ', '-')}-v{dataset.version}.jsonl"
    return Response(
        content=body,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Manifest-SHA256": sha256,
        },
    )
