from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.alert_secrets import (
    AlertSecretError,
    decrypt_alert_secret,
    encrypt_alert_secret,
)
from video_intelligence_api.alerting import enqueue_event_alert
from video_intelligence_api.auth import (
    Actor,
    ActorDependency,
    AdminDependency,
    EditorDependency,
)
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.models import (
    ActionExecution,
    ActionExecutionStatus,
    Alert,
    AlertChannel,
    AlertDelivery,
    AlertDeliveryStatus,
    AlertStatus,
    Camera,
    Event,
    Rule,
    RuleAlertChannel,
    Zone,
    new_id,
    utc_now,
)
from video_intelligence_api.schemas import (
    AlertActor,
    AlertChannelCreate,
    AlertChannelRead,
    AlertChannelUpdate,
    AlertDeliveryAssignment,
    AlertDeliveryRead,
    AlertDeliveryResult,
    AlertRead,
    AlertWorkerClaim,
    EventRead,
    RuleAlertRouteCreate,
    RuleAlertRouteRead,
    TestAlertCreate,
)
from video_intelligence_api.security import require_agent_key
from video_intelligence_api.tenancy import tenant_alert, tenant_rule

router = APIRouter(tags=["alerts"])


def channel_response(channel: AlertChannel) -> AlertChannelRead:
    return AlertChannelRead.model_validate(channel)


def route_response(route: RuleAlertChannel, channel: AlertChannel) -> RuleAlertRouteRead:
    return RuleAlertRouteRead(
        id=route.id,
        rule_id=route.rule_id,
        channel_id=route.channel_id,
        channel_name=channel.name,
        cooldown_seconds=route.cooldown_seconds,
        delay_seconds=route.delay_seconds,
        created_at=route.created_at,
    )


async def alert_response(session: SessionDependency, alert: Alert) -> AlertRead:
    event = await session.get(Event, alert.event_id)
    if event is None:
        raise HTTPException(status_code=409, detail="Alert event is unavailable")
    rows = (
        await session.execute(
            select(AlertDelivery, AlertChannel)
            .join(AlertChannel, AlertChannel.id == AlertDelivery.channel_id)
            .where(AlertDelivery.alert_id == alert.id)
            .order_by(AlertDelivery.created_at)
        )
    ).all()
    return AlertRead(
        id=alert.id,
        event_id=alert.event_id,
        status=alert.status,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        resolved_at=alert.resolved_at,
        resolved_by=alert.resolved_by,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
        event=EventRead.model_validate(event),
        deliveries=[
            AlertDeliveryRead(
                id=delivery.id,
                channel_id=channel.id,
                channel_name=channel.name,
                status=delivery.status,
                attempt_count=delivery.attempt_count,
                next_attempt_at=delivery.next_attempt_at,
                last_status_code=delivery.last_status_code,
                last_error=delivery.last_error,
                delivered_at=delivery.delivered_at,
            )
            for delivery, channel in rows
        ],
    )


@router.post(
    "/alert-channels",
    response_model=AlertChannelRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_alert_channel(
    payload: AlertChannelCreate,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: AdminDependency,
) -> AlertChannelRead:
    if settings.environment == "production" and payload.webhook_url.scheme != "https":
        raise HTTPException(status_code=422, detail="Production alert webhooks must use HTTPS")
    try:
        encrypted = encrypt_alert_secret(payload.signing_secret, settings)
    except AlertSecretError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    channel = AlertChannel(
        organization_id=actor.organization_id,
        name=payload.name,
        webhook_url=str(payload.webhook_url),
        signing_secret_encrypted=encrypted,
        enabled=payload.enabled,
        timeout_seconds=payload.timeout_seconds,
        max_attempts=payload.max_attempts,
    )
    session.add(channel)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Alert channel name already exists") from exc
    await session.refresh(channel)
    return channel_response(channel)


@router.get("/alert-channels", response_model=list[AlertChannelRead])
async def list_alert_channels(
    session: SessionDependency, actor: ActorDependency
) -> list[AlertChannelRead]:
    channels = (
        await session.scalars(
            select(AlertChannel)
            .where(AlertChannel.organization_id == actor.organization_id)
            .order_by(AlertChannel.name)
        )
    ).all()
    return [channel_response(channel) for channel in channels]


@router.patch(
    "/alert-channels/{channel_id}",
    response_model=AlertChannelRead,
)
async def update_alert_channel(
    channel_id: str,
    payload: AlertChannelUpdate,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: AdminDependency,
) -> AlertChannelRead:
    channel = await session.scalar(
        select(AlertChannel).where(
            AlertChannel.id == channel_id,
            AlertChannel.organization_id == actor.organization_id,
        )
    )
    if channel is None:
        raise HTTPException(status_code=404, detail="Alert channel not found")
    changes = payload.model_dump(exclude_unset=True)
    secret = changes.pop("signing_secret", None)
    webhook_url = changes.get("webhook_url")
    if (
        settings.environment == "production"
        and webhook_url is not None
        and webhook_url.scheme != "https"
    ):
        raise HTTPException(status_code=422, detail="Production alert webhooks must use HTTPS")
    if secret is not None:
        try:
            channel.signing_secret_encrypted = encrypt_alert_secret(secret, settings)
        except AlertSecretError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    for field, value in changes.items():
        setattr(channel, field, str(value) if field == "webhook_url" else value)
    await session.commit()
    await session.refresh(channel)
    return channel_response(channel)


@router.post(
    "/rules/{rule_id}/alert-routes",
    response_model=RuleAlertRouteRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_alert_route(
    rule_id: str,
    payload: RuleAlertRouteCreate,
    session: SessionDependency,
    actor: EditorDependency,
) -> RuleAlertRouteRead:
    if await tenant_rule(session, actor, rule_id) is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    channel = await session.scalar(
        select(AlertChannel).where(
            AlertChannel.id == payload.channel_id,
            AlertChannel.organization_id == actor.organization_id,
        )
    )
    if channel is None:
        raise HTTPException(status_code=404, detail="Alert channel not found")
    route = RuleAlertChannel(id=new_id(), rule_id=rule_id, **payload.model_dump())
    session.add(route)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="This rule already uses that channel") from exc
    await session.refresh(route)
    return route_response(route, channel)


@router.get(
    "/rules/{rule_id}/alert-routes",
    response_model=list[RuleAlertRouteRead],
)
async def list_alert_routes(
    rule_id: str, session: SessionDependency, actor: ActorDependency
) -> list[RuleAlertRouteRead]:
    if await tenant_rule(session, actor, rule_id) is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    rows = (
        await session.execute(
            select(RuleAlertChannel, AlertChannel)
            .join(AlertChannel, AlertChannel.id == RuleAlertChannel.channel_id)
            .where(RuleAlertChannel.rule_id == rule_id)
            .order_by(RuleAlertChannel.created_at)
        )
    ).all()
    return [route_response(route, channel) for route, channel in rows]


@router.post(
    "/rules/{rule_id}/test-alert",
    response_model=AlertRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_test_alert(
    rule_id: str,
    payload: TestAlertCreate,
    request: Request,
    session: SessionDependency,
    actor: EditorDependency,
) -> AlertRead:
    """Exercise the real incident/UI path without requiring a visual trigger."""
    rule = await tenant_rule(session, actor, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    camera = await session.get(Camera, rule.camera_id)
    zone = await session.get(Zone, rule.zone_id)
    if camera is None:
        raise HTTPException(status_code=409, detail="Rule camera is unavailable")

    now = utc_now()
    source_event_id = new_id()
    details: dict[str, object] = {
        "test": True,
        "summary": "Operator-generated test alert. No visual event or evidence clip was created.",
    }
    event = Event(
        id=new_id(),
        source_event_id=source_event_id,
        schema_version=2,
        event_type=rule.rule_type,
        camera_id=camera.id,
        rule_id=rule.id,
        track_id=None,
        object_class=rule.object_class,
        zone_name=zone.name if zone is not None else "Full camera view",
        entered_at_seconds=0,
        occurred_at_seconds=0,
        dwell_seconds=0,
        confidence=1,
        occurred_at=now,
        clip_uri="",
        raw_payload={
            "schema_version": 2,
            "id": source_event_id,
            "test": True,
            "deliver_outbound": payload.deliver_outbound,
        },
        details=details,
    )
    session.add(event)
    alert = (
        await enqueue_event_alert(session, event)
        if payload.deliver_outbound
        else Alert(id=new_id(), event_id=event.id, created_at=now, updated_at=now)
    )
    if not payload.deliver_outbound:
        session.add(alert)
    await session.commit()
    await session.refresh(event)
    await session.refresh(alert)

    event_payload = EventRead.model_validate(event).model_dump(mode="json")
    await request.app.state.event_connections.broadcast(
        {"type": "event.created", "data": event_payload},
        organization_id=camera.organization_id,
    )
    return await alert_response(session, alert)


@router.delete(
    "/rules/{rule_id}/alert-routes/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_alert_route(
    rule_id: str,
    route_id: str,
    session: SessionDependency,
    actor: EditorDependency,
) -> Response:
    if await tenant_rule(session, actor, rule_id) is None:
        raise HTTPException(status_code=404, detail="Alert route not found")
    route = await session.get(RuleAlertChannel, route_id)
    if route is None or route.rule_id != rule_id:
        raise HTTPException(status_code=404, detail="Alert route not found")
    await session.delete(route)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/alerts", response_model=list[AlertRead])
async def list_alerts(
    session: SessionDependency,
    actor: ActorDependency,
    alert_status: Annotated[AlertStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[AlertRead]:
    statement = (
        select(Alert)
        .join(Event, Event.id == Alert.event_id)
        .join(Camera, Camera.id == Event.camera_id)
        .where(Camera.organization_id == actor.organization_id)
        .order_by(Alert.created_at.desc())
        .limit(limit)
    )
    if alert_status is not None:
        statement = statement.where(Alert.status == alert_status)
    alerts = (await session.scalars(statement)).all()
    return [await alert_response(session, alert) for alert in alerts]


async def transition_alert(
    alert_id: str,
    payload: AlertActor,
    session: SessionDependency,
    actor: Actor,
    target: AlertStatus,
) -> AlertRead:
    alert = await tenant_alert(session, actor, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    now = utc_now()
    if target == AlertStatus.ACKNOWLEDGED:
        if alert.status == AlertStatus.RESOLVED:
            raise HTTPException(status_code=409, detail="Resolved alerts cannot be acknowledged")
        alert.status = target
        alert.acknowledged_at = now
        alert.acknowledged_by = payload.actor
    else:
        alert.status = target
        alert.resolved_at = now
        alert.resolved_by = payload.actor
    pending = (
        await session.scalars(
            select(AlertDelivery).where(
                AlertDelivery.alert_id == alert.id,
                AlertDelivery.status.in_(
                    [AlertDeliveryStatus.QUEUED, AlertDeliveryStatus.RETRYING]
                ),
            )
        )
    ).all()
    for delivery in pending:
        delivery.status = AlertDeliveryStatus.SUPPRESSED
        delivery.last_error = f"Alert {target.value} before delivery"
    pending_actions = (
        await session.scalars(
            select(ActionExecution).where(
                ActionExecution.alert_id == alert.id,
                ActionExecution.status.in_(
                    [
                        ActionExecutionStatus.AWAITING_APPROVAL,
                        ActionExecutionStatus.QUEUED,
                        ActionExecutionStatus.RETRYING,
                    ]
                ),
            )
        )
    ).all()
    for execution in pending_actions:
        execution.status = ActionExecutionStatus.SUPPRESSED
        execution.last_error = f"Alert {target.value} before action execution"
        execution.completed_at = now
    await session.commit()
    await session.refresh(alert)
    return await alert_response(session, alert)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert(
    alert_id: str,
    payload: AlertActor,
    session: SessionDependency,
    actor: EditorDependency,
) -> AlertRead:
    return await transition_alert(alert_id, payload, session, actor, AlertStatus.ACKNOWLEDGED)


@router.post("/alerts/{alert_id}/resolve", response_model=AlertRead)
async def resolve_alert(
    alert_id: str,
    payload: AlertActor,
    session: SessionDependency,
    actor: EditorDependency,
) -> AlertRead:
    return await transition_alert(alert_id, payload, session, actor, AlertStatus.RESOLVED)


@router.post(
    "/agent/alert-deliveries/claim",
    response_model=AlertDeliveryAssignment | None,
    dependencies=[Depends(require_agent_key)],
)
async def claim_alert_delivery(
    payload: AlertWorkerClaim,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AlertDeliveryAssignment | Response:
    now = utc_now()
    statement = (
        select(AlertDelivery, Alert, AlertChannel, Event, Camera, Rule)
        .join(Alert, Alert.id == AlertDelivery.alert_id)
        .join(AlertChannel, AlertChannel.id == AlertDelivery.channel_id)
        .join(Event, Event.id == Alert.event_id)
        .join(Camera, Camera.id == Event.camera_id)
        .join(Rule, Rule.id == Event.rule_id)
        .where(
            Alert.status == AlertStatus.OPEN,
            AlertChannel.enabled.is_(True),
            AlertDelivery.next_attempt_at <= now,
            or_(
                AlertDelivery.status.in_(
                    [AlertDeliveryStatus.QUEUED, AlertDeliveryStatus.RETRYING]
                ),
                (
                    (AlertDelivery.status == AlertDeliveryStatus.DELIVERING)
                    & (AlertDelivery.lease_expires_at < now)
                ),
            ),
        )
        .order_by(AlertDelivery.next_attempt_at, AlertDelivery.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    row = (await session.execute(statement)).first()
    if row is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    delivery, alert, channel, event, camera, rule = row
    if delivery.attempt_count >= channel.max_attempts:
        delivery.status = AlertDeliveryStatus.FAILED
        delivery.worker_id = None
        delivery.lease_expires_at = None
        delivery.last_error = "Maximum delivery attempts reached after expired leases"
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        secret = decrypt_alert_secret(channel.signing_secret_encrypted, settings)
    except AlertSecretError as exc:
        delivery.status = AlertDeliveryStatus.FAILED
        delivery.last_error = str(exc)
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    delivery.status = AlertDeliveryStatus.DELIVERING
    delivery.worker_id = payload.worker_id
    delivery.lease_expires_at = now + timedelta(seconds=settings.alert_lease_seconds)
    delivery.attempt_count += 1
    await session.commit()
    body: dict[str, object] = {
        "schema_version": 1,
        "type": "video.alert.created",
        "alert": {"id": alert.id, "status": alert.status.value},
        "event": EventRead.model_validate(event).model_dump(mode="json"),
        "camera": {"id": camera.id, "name": camera.name},
        "rule": {"id": rule.id, "key": rule.key, "name": rule.name},
        "evidence_url": f"/api/v1/events/{event.id}",
    }
    return AlertDeliveryAssignment(
        delivery_id=delivery.id,
        alert_id=alert.id,
        event_id=event.id,
        webhook_url=channel.webhook_url,
        signing_secret=secret,
        timeout_seconds=channel.timeout_seconds,
        payload=body,
    )


@router.post(
    "/agent/alert-deliveries/{delivery_id}/result",
    response_model=AlertDeliveryRead,
    dependencies=[Depends(require_agent_key)],
)
async def complete_alert_delivery(
    delivery_id: str,
    payload: AlertDeliveryResult,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AlertDeliveryRead:
    row = (
        await session.execute(
            select(AlertDelivery, AlertChannel)
            .join(AlertChannel, AlertChannel.id == AlertDelivery.channel_id)
            .where(AlertDelivery.id == delivery_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Alert delivery not found")
    delivery, channel = row
    if delivery.worker_id != payload.worker_id or delivery.status != AlertDeliveryStatus.DELIVERING:
        raise HTTPException(
            status_code=409, detail="Worker does not hold this alert delivery lease"
        )
    now = utc_now()
    delivery.last_status_code = payload.status_code
    delivery.last_error = payload.error
    delivery.worker_id = None
    delivery.lease_expires_at = None
    if payload.outcome == "delivered":
        delivery.status = AlertDeliveryStatus.DELIVERED
        delivery.delivered_at = now
    elif payload.outcome == "permanent_failure" or delivery.attempt_count >= channel.max_attempts:
        delivery.status = AlertDeliveryStatus.FAILED
        if delivery.attempt_count >= channel.max_attempts and not payload.error:
            delivery.last_error = "Maximum delivery attempts reached"
    else:
        delivery.status = AlertDeliveryStatus.RETRYING
        delay = min(
            settings.alert_retry_base_seconds * 2 ** max(delivery.attempt_count - 1, 0),
            settings.alert_retry_max_seconds,
        )
        delivery.next_attempt_at = now + timedelta(seconds=delay)
    await session.commit()
    await session.refresh(delivery)
    return AlertDeliveryRead(
        id=delivery.id,
        channel_id=channel.id,
        channel_name=channel.name,
        status=delivery.status,
        attempt_count=delivery.attempt_count,
        next_attempt_at=delivery.next_attempt_at,
        last_status_code=delivery.last_status_code,
        last_error=delivery.last_error,
        delivered_at=delivery.delivered_at,
    )
