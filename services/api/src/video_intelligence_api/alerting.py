from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from video_intelligence_api.guarded_actions import build_action_payload
from video_intelligence_api.models import (
    ActionApprovalMode,
    ActionExecution,
    ActionExecutionStatus,
    Alert,
    AlertChannel,
    AlertDelivery,
    AlertDeliveryStatus,
    Event,
    Rule,
    RuleActionBinding,
    RuleAlertChannel,
    new_id,
    utc_now,
)


async def enqueue_event_alert(session: AsyncSession, event: Event) -> Alert:
    """Create the incident and every routed delivery inside the event transaction."""
    now = utc_now()
    alert = Alert(id=new_id(), event_id=event.id, created_at=now, updated_at=now)
    session.add(alert)
    routes = (
        await session.execute(
            select(RuleAlertChannel, AlertChannel)
            .join(AlertChannel, AlertChannel.id == RuleAlertChannel.channel_id)
            .where(
                RuleAlertChannel.rule_id == event.rule_id,
                AlertChannel.enabled.is_(True),
            )
        )
    ).all()
    for route, channel in routes:
        status = AlertDeliveryStatus.QUEUED
        error = None
        if route.cooldown_seconds:
            cutoff = now - timedelta(seconds=route.cooldown_seconds)
            recent = await session.scalar(
                select(AlertDelivery.id)
                .join(Alert, Alert.id == AlertDelivery.alert_id)
                .join(Event, Event.id == Alert.event_id)
                .where(
                    Event.rule_id == event.rule_id,
                    AlertDelivery.channel_id == channel.id,
                    AlertDelivery.created_at >= cutoff,
                    AlertDelivery.status.not_in(
                        [AlertDeliveryStatus.SUPPRESSED, AlertDeliveryStatus.FAILED]
                    ),
                )
                .limit(1)
            )
            if recent is not None:
                status = AlertDeliveryStatus.SUPPRESSED
                error = f"Suppressed by {route.cooldown_seconds}s route cooldown"
        session.add(
            AlertDelivery(
                id=new_id(),
                alert_id=alert.id,
                channel_id=channel.id,
                status=status,
                next_attempt_at=now + timedelta(seconds=route.delay_seconds),
                last_error=error,
                created_at=now,
                updated_at=now,
            )
        )
    if event.rule_id is not None:
        rule = await session.get(Rule, event.rule_id)
        if rule is not None:
            bindings = list(
                (
                    await session.scalars(
                        select(RuleActionBinding).where(
                            RuleActionBinding.rule_id == event.rule_id,
                            RuleActionBinding.enabled.is_(True),
                        )
                    )
                ).all()
            )
            for binding in bindings:
                execution_id = new_id()
                execution_status = (
                    ActionExecutionStatus.QUEUED
                    if binding.approval_mode == ActionApprovalMode.AUTOMATIC
                    else ActionExecutionStatus.AWAITING_APPROVAL
                )
                session.add(
                    ActionExecution(
                        id=execution_id,
                        organization_id=binding.organization_id,
                        alert_id=alert.id,
                        event_id=event.id,
                        binding_id=binding.id,
                        connector_id=binding.connector_id,
                        action_type=binding.action_type,
                        risk_level=binding.risk_level,
                        status=execution_status,
                        idempotency_key=f"action:{execution_id}",
                        payload=build_action_payload(
                            binding.action_type,
                            event,
                            rule,
                            binding.payload_template,
                        ),
                        next_attempt_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
    return alert
