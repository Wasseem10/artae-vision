from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from video_intelligence_api.models import (
    ContextObservation,
    ContextSource,
    CorrelationEvaluation,
    CorrelationEvaluationStatus,
    CorrelationType,
    Event,
    RuleCorrelationPolicy,
    new_id,
    utc_now,
)


def normalized_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def visual_count(event: Event, field: str) -> int:
    candidates: list[object] = [event.details.get(field)]
    raw_details = event.raw_payload.get("details")
    if isinstance(raw_details, dict):
        candidates.append(raw_details.get(field))
    candidates.append(event.raw_payload.get(field))
    for candidate in candidates:
        if isinstance(candidate, bool):
            continue
        if isinstance(candidate, (int, float)) and candidate >= 0:
            return int(candidate)
    return 1


async def enqueue_event_correlations(session: AsyncSession, event: Event) -> bool:
    """Queue correlation work and return whether normal alerting should be deferred."""
    rows = (
        await session.execute(
            select(RuleCorrelationPolicy, ContextSource)
            .join(ContextSource, ContextSource.id == RuleCorrelationPolicy.source_id)
            .where(
                RuleCorrelationPolicy.rule_id == event.rule_id,
                RuleCorrelationPolicy.enabled.is_(True),
                ContextSource.enabled.is_(True),
            )
        )
    ).all()
    if not rows:
        return False

    now = utc_now()
    occurred_at = normalized_utc(event.occurred_at)
    for policy, source in rows:
        window_start = occurred_at - timedelta(seconds=policy.window_before_seconds)
        window_end = occurred_at + timedelta(seconds=policy.window_after_seconds)
        session.add(
            CorrelationEvaluation(
                id=new_id(),
                organization_id=policy.organization_id,
                event_id=event.id,
                policy_id=policy.id,
                source_id=source.id,
                status=CorrelationEvaluationStatus.PENDING,
                visual_count=visual_count(event, policy.visual_count_field),
                window_start=window_start,
                window_end=window_end,
                due_at=max(now, window_end),
                created_at=now,
            )
        )
    return True


async def evaluate_correlation(
    session: AsyncSession,
    evaluation: CorrelationEvaluation,
    policy: RuleCorrelationPolicy,
) -> bool:
    """Finalize a deterministic count-versus-authorizations correlation."""
    observation_count = await session.scalar(
        select(func.count(ContextObservation.id)).where(
            ContextObservation.source_id == evaluation.source_id,
            ContextObservation.observation_type == policy.observation_type,
            ContextObservation.occurred_at >= evaluation.window_start,
            ContextObservation.occurred_at <= evaluation.window_end,
        )
    )
    evaluation.observation_count = int(observation_count or 0)
    evaluation.evaluated_at = utc_now()
    if policy.correlation_type == CorrelationType.COUNT_EXCEEDS_AUTHORIZATIONS:
        matched = evaluation.visual_count > evaluation.observation_count
        evaluation.status = (
            CorrelationEvaluationStatus.MATCHED if matched else CorrelationEvaluationStatus.CLEAR
        )
        comparison = ">" if matched else "<="
        evaluation.explanation = (
            f"Camera count {evaluation.visual_count} {comparison} "
            f"authorized {evaluation.observation_count} within the policy window."
        )
        return matched
    evaluation.status = CorrelationEvaluationStatus.FAILED
    evaluation.explanation = f"Unsupported correlation type: {policy.correlation_type}"
    return False
