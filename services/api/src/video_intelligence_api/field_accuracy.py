"""Human-grounded live accuracy metrics and automatic-release gate policy."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from video_intelligence_api.models import (
    AccuracyGateStatus,
    AccuracyLabelOutcome,
    Camera,
    Event,
    FieldAccuracyLabel,
    FieldAccuracySnapshot,
    Rule,
    RuleAccuracyPolicy,
    VerificationCase,
    VerificationStatus,
    new_id,
    utc_now,
)

MINIMUM_POSITIVE_LABELS = 5
MINIMUM_NEGATIVE_LABELS = 5
MINIMUM_CHALLENGING_LABELS = 2
MINIMUM_PRECISION = 0.90
MINIMUM_RECALL = 0.90
ROLLING_WINDOW_SIZE = 100
CHALLENGING_TAGS = {"low_light", "partial_occlusion", "far_distance", "camera_motion"}


@dataclass(frozen=True, slots=True)
class AccuracyPolicy:
    minimum_positive_labels: int = MINIMUM_POSITIVE_LABELS
    minimum_negative_labels: int = MINIMUM_NEGATIVE_LABELS
    minimum_challenging_labels: int = MINIMUM_CHALLENGING_LABELS
    minimum_precision: float = MINIMUM_PRECISION
    minimum_recall: float = MINIMUM_RECALL
    rolling_window_size: int = ROLLING_WINDOW_SIZE
    manual_only: bool = False


POLICY = AccuracyPolicy()


async def accuracy_policy(session: AsyncSession, rule_id: str) -> AccuracyPolicy:
    stored = await session.scalar(
        select(RuleAccuracyPolicy).where(RuleAccuracyPolicy.rule_id == rule_id)
    )
    if stored is None:
        return POLICY
    return AccuracyPolicy(
        minimum_positive_labels=stored.minimum_positive_labels,
        minimum_negative_labels=stored.minimum_negative_labels,
        minimum_challenging_labels=stored.minimum_challenging_labels,
        minimum_precision=stored.minimum_precision,
        minimum_recall=stored.minimum_recall,
        rolling_window_size=stored.rolling_window_size,
        manual_only=stored.manual_only,
    )


def label_outcome(*, released: bool, event_occurred: bool) -> AccuracyLabelOutcome:
    if released and event_occurred:
        return AccuracyLabelOutcome.TRUE_POSITIVE
    if released:
        return AccuracyLabelOutcome.FALSE_POSITIVE
    if event_occurred:
        return AccuracyLabelOutcome.FALSE_NEGATIVE
    return AccuracyLabelOutcome.TRUE_NEGATIVE


async def latest_accuracy_snapshot(
    session: AsyncSession,
    rule_id: str,
) -> FieldAccuracySnapshot | None:
    return await session.scalar(
        select(FieldAccuracySnapshot)
        .where(FieldAccuracySnapshot.rule_id == rule_id)
        .order_by(FieldAccuracySnapshot.created_at.desc(), FieldAccuracySnapshot.id.desc())
        .limit(1)
    )


async def automatic_release_allowed(session: AsyncSession, rule_id: str) -> bool:
    snapshot = await latest_accuracy_snapshot(session, rule_id)
    return bool(snapshot and snapshot.automatic_release_allowed)


async def refresh_accuracy_snapshot(
    session: AsyncSession,
    *,
    organization_id: str,
    camera_id: str,
    rule_id: str,
) -> FieldAccuracySnapshot:
    await session.flush()
    policy = await accuracy_policy(session, rule_id)
    previous = await latest_accuracy_snapshot(session, rule_id)
    labels = list(
        (
            await session.scalars(
                select(FieldAccuracyLabel)
                .where(FieldAccuracyLabel.rule_id == rule_id)
                .order_by(FieldAccuracyLabel.created_at.desc())
                .limit(policy.rolling_window_size)
            )
        ).all()
    )
    counts = {outcome: 0 for outcome in AccuracyLabelOutcome}
    for label in labels:
        counts[label.outcome] += 1
    true_positives = counts[AccuracyLabelOutcome.TRUE_POSITIVE]
    false_positives = counts[AccuracyLabelOutcome.FALSE_POSITIVE]
    false_negatives = counts[AccuracyLabelOutcome.FALSE_NEGATIVE]
    true_negatives = counts[AccuracyLabelOutcome.TRUE_NEGATIVE]
    positive_count = true_positives + false_negatives
    negative_count = true_negatives + false_positives
    challenging_count = sum(
        bool(CHALLENGING_TAGS.intersection(label.environment_tags)) for label in labels
    )
    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives
    precision = true_positives / precision_denominator if precision_denominator else None
    recall = true_positives / recall_denominator if recall_denominator else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )

    enough_evidence = (
        positive_count >= policy.minimum_positive_labels
        and negative_count >= policy.minimum_negative_labels
        and challenging_count >= policy.minimum_challenging_labels
    )
    quality_passes = (
        precision is not None
        and recall is not None
        and precision >= policy.minimum_precision
        and recall >= policy.minimum_recall
    )
    if not enough_evidence:
        gate_status = AccuracyGateStatus.COLLECTING
    elif quality_passes:
        gate_status = AccuracyGateStatus.READY
    elif previous is not None and previous.gate_status == AccuracyGateStatus.READY:
        gate_status = AccuracyGateStatus.DRIFTING
    else:
        gate_status = AccuracyGateStatus.FAILING

    recommendations: list[str] = []
    if positive_count < policy.minimum_positive_labels:
        recommendations.append(
            f"Review {policy.minimum_positive_labels - positive_count} more positive "
            "field outcome(s)."
        )
    if negative_count < policy.minimum_negative_labels:
        recommendations.append(
            f"Review {policy.minimum_negative_labels - negative_count} more negative "
            "field outcome(s)."
        )
    if challenging_count < policy.minimum_challenging_labels:
        recommendations.append(
            "Label more low-light, distant, moving-camera, or partly occluded evidence."
        )
    if precision is not None and precision < policy.minimum_precision:
        recommendations.append("False alarms are above policy; inspect rejected live alerts.")
    if recall is not None and recall < policy.minimum_recall:
        recommendations.append(
            "Missed events are above policy; inspect verifier rejections and misses."
        )
    if gate_status == AccuracyGateStatus.READY:
        recommendations.append(
            "Field gate passed; automatic verified release is allowed."
            if not policy.manual_only
            else "Field gate passed, but this job's policy permanently requires manual review."
        )

    snapshot = FieldAccuracySnapshot(
        id=new_id(),
        organization_id=organization_id,
        camera_id=camera_id,
        rule_id=rule_id,
        window_size=policy.rolling_window_size,
        label_count=len(labels),
        positive_count=positive_count,
        negative_count=negative_count,
        challenging_count=challenging_count,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        true_negatives=true_negatives,
        precision=round(precision, 6) if precision is not None else None,
        recall=round(recall, 6) if recall is not None else None,
        f1=round(f1, 6) if f1 is not None else None,
        gate_status=gate_status,
        automatic_release_allowed=(
            gate_status == AccuracyGateStatus.READY and not policy.manual_only
        ),
        recommendations=recommendations,
        created_at=utc_now(),
    )
    session.add(snapshot)
    return snapshot


async def record_case_label(
    session: AsyncSession,
    *,
    case: VerificationCase,
    event: Event,
    camera: Camera,
    rule: Rule,
    event_occurred: bool,
    source: str,
    notes: str,
    environment_tags: list[str],
    reviewed_by: str,
) -> tuple[FieldAccuracyLabel, FieldAccuracySnapshot]:
    existing = await session.scalar(
        select(FieldAccuracyLabel).where(FieldAccuracyLabel.verification_case_id == case.id)
    )
    if existing is not None:
        snapshot = await latest_accuracy_snapshot(session, rule.id)
        if snapshot is None:
            snapshot = await refresh_accuracy_snapshot(
                session,
                organization_id=camera.organization_id,
                camera_id=camera.id,
                rule_id=rule.id,
            )
        return existing, snapshot
    released = event.verification_status == VerificationStatus.CONFIRMED
    label = FieldAccuracyLabel(
        id=new_id(),
        organization_id=camera.organization_id,
        camera_id=camera.id,
        rule_id=rule.id,
        verification_case_id=case.id,
        event_id=event.id,
        outcome=label_outcome(released=released, event_occurred=event_occurred),
        source=source,
        environment_tags=environment_tags,
        notes=notes,
        occurred_at=event.occurred_at,
        reviewed_by=reviewed_by,
        created_at=utc_now(),
    )
    session.add(label)
    snapshot = await refresh_accuracy_snapshot(
        session,
        organization_id=camera.organization_id,
        camera_id=camera.id,
        rule_id=rule.id,
    )
    return label, snapshot
