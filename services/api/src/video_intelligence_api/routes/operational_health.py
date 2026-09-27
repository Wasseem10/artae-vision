"""Automatic reliability incidents and opt-in camera outage delivery."""

from datetime import UTC, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, case, or_, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.alert_secrets import AlertSecretError, decrypt_alert_secret
from video_intelligence_api.auth import ActorDependency, AdminDependency, EditorDependency
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.models import (
    AlertChannel,
    AlertDeliveryStatus,
    AlertStatus,
    Camera,
    CameraAgent,
    EdgeDevice,
    OperationalHealthDelivery,
    OperationalHealthIncident,
    OperationalHealthRoute,
    OperationalHealthSeverity,
    OperationalHealthWatchdog,
    new_id,
    utc_now,
)
from video_intelligence_api.operational_health import camera_conditions, edge_condition
from video_intelligence_api.schemas import (
    AlertDeliveryResult,
    AlertWorkerClaim,
    HealthResponse,
    OperationalHealthDeliveryAssignment,
    OperationalHealthDeliveryRead,
    OperationalHealthEvaluationRead,
    OperationalHealthIncidentRead,
    OperationalHealthRouteCreate,
    OperationalHealthRouteRead,
    OperationalHealthWatchdogRead,
)
from video_intelligence_api.security import require_agent_key, require_health_monitor_key

router = APIRouter(tags=["operational health"])


async def _watchdog_status(
    session: SessionDependency, settings: SettingsDependency
) -> OperationalHealthWatchdogRead:
    now = utc_now()
    watchdog = await session.get(OperationalHealthWatchdog, 1)
    last_success = watchdog.last_successful_evaluation_at if watchdog else None
    if last_success is None:
        state = "never_run"
    else:
        if last_success.tzinfo is None:
            last_success = last_success.replace(tzinfo=UTC)
        age_seconds = (now - last_success).total_seconds()
        state = (
            "fresh"
            if 0 <= age_seconds <= settings.operational_health_watchdog_stale_seconds
            else "stale"
        )
    return OperationalHealthWatchdogRead(
        status=state,
        last_successful_evaluation_at=last_success,
        stale_after_seconds=settings.operational_health_watchdog_stale_seconds,
        server_time=now,
    )


@router.get(
    "/operational-health/watchdog",
    response_model=OperationalHealthWatchdogRead,
)
async def read_operational_health_watchdog(
    session: SessionDependency,
    settings: SettingsDependency,
    _actor: ActorDependency,
    response: Response,
) -> OperationalHealthWatchdogRead:
    """Show global evaluator liveness without exposing another tenant's resources."""
    response.headers["Cache-Control"] = "no-store"
    return await _watchdog_status(session, settings)


@router.get(
    "/health/watchdog",
    response_model=HealthResponse,
    dependencies=[Depends(require_health_monitor_key)],
)
async def operational_health_watchdog_ready(
    session: SessionDependency,
    settings: SettingsDependency,
    response: Response,
) -> HealthResponse:
    """Low-detail probe for a separately authenticated external uptime monitor."""
    response.headers["Cache-Control"] = "no-store"
    watchdog = await _watchdog_status(session, settings)
    if watchdog.status != "fresh":
        raise HTTPException(
            status_code=503,
            detail="Operational health watchdog is not current",
            headers={"Cache-Control": "no-store"},
        )
    return HealthResponse()


def _delivery_response(
    delivery: OperationalHealthDelivery, channel: AlertChannel
) -> OperationalHealthDeliveryRead:
    return OperationalHealthDeliveryRead(
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


def _route_response(
    route: OperationalHealthRoute, channel: AlertChannel
) -> OperationalHealthRouteRead:
    return OperationalHealthRouteRead(
        id=route.id,
        camera_id=route.camera_id,
        channel_id=channel.id,
        channel_name=channel.name,
        outage_after_seconds=route.outage_after_seconds,
        created_at=route.created_at,
    )


def _suppress_delivery(delivery: OperationalHealthDelivery, reason: str) -> None:
    in_flight = delivery.status == AlertDeliveryStatus.DELIVERING
    delivery.status = AlertDeliveryStatus.SUPPRESSED
    delivery.worker_id = None
    delivery.lease_expires_at = None
    delivery.last_error = (
        f"{reason}; in-flight webhook may still arrive (outcome unknown)" if in_flight else reason
    )


async def _incident_response(
    session: SessionDependency,
    incident: OperationalHealthIncident,
) -> OperationalHealthIncidentRead:
    resource_name = "Unknown resource"
    if incident.camera_id:
        camera = await session.get(Camera, incident.camera_id)
        resource_name = camera.name if camera else "Deleted camera"
    elif incident.edge_device_id:
        device = await session.get(EdgeDevice, incident.edge_device_id)
        resource_name = device.name if device else "Deleted edge station"
    deliveries = (
        await session.execute(
            select(OperationalHealthDelivery, AlertChannel)
            .join(AlertChannel, AlertChannel.id == OperationalHealthDelivery.channel_id)
            .where(OperationalHealthDelivery.incident_id == incident.id)
            .order_by(OperationalHealthDelivery.created_at)
        )
    ).all()
    return OperationalHealthIncidentRead(
        id=incident.id,
        organization_id=incident.organization_id,
        camera_id=incident.camera_id,
        edge_device_id=incident.edge_device_id,
        resource_type=incident.resource_type,
        resource_name=resource_name,
        condition=incident.condition,
        severity=incident.severity,
        status=incident.status,
        title=incident.title,
        detail=incident.detail,
        diagnostics=incident.diagnostics,
        occurrence_count=incident.occurrence_count,
        first_detected_at=incident.first_detected_at,
        last_detected_at=incident.last_detected_at,
        acknowledged_at=incident.acknowledged_at,
        acknowledged_by=incident.acknowledged_by,
        resolved_at=incident.resolved_at,
        resolved_by=incident.resolved_by,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        deliveries=[_delivery_response(delivery, channel) for delivery, channel in deliveries],
    )


@router.post(
    "/cameras/{camera_id}/health-alert-routes",
    response_model=OperationalHealthRouteRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_camera_health_route(
    camera_id: str,
    payload: OperationalHealthRouteCreate,
    session: SessionDependency,
    actor: AdminDependency,
) -> OperationalHealthRouteRead:
    camera = await session.get(Camera, camera_id)
    if camera is None or camera.organization_id != actor.organization_id:
        raise HTTPException(status_code=404, detail="Camera not found")
    channel = await session.get(AlertChannel, payload.channel_id)
    if channel is None or channel.organization_id != actor.organization_id:
        raise HTTPException(status_code=404, detail="Alert channel not found")
    if not channel.enabled:
        raise HTTPException(status_code=409, detail="Alert channel is disabled")
    route = OperationalHealthRoute(
        id=new_id(),
        camera_id=camera.id,
        channel_id=channel.id,
        outage_after_seconds=payload.outage_after_seconds,
    )
    session.add(route)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Camera already uses this channel") from exc
    await session.refresh(route)
    return _route_response(route, channel)


@router.get(
    "/cameras/{camera_id}/health-alert-routes",
    response_model=list[OperationalHealthRouteRead],
)
async def list_camera_health_routes(
    camera_id: str, session: SessionDependency, actor: ActorDependency
) -> list[OperationalHealthRouteRead]:
    camera = await session.get(Camera, camera_id)
    if camera is None or camera.organization_id != actor.organization_id:
        raise HTTPException(status_code=404, detail="Camera not found")
    rows = (
        await session.execute(
            select(OperationalHealthRoute, AlertChannel)
            .join(AlertChannel, AlertChannel.id == OperationalHealthRoute.channel_id)
            .where(OperationalHealthRoute.camera_id == camera_id)
            .order_by(OperationalHealthRoute.created_at)
        )
    ).all()
    return [_route_response(route, channel) for route, channel in rows]


@router.delete(
    "/cameras/{camera_id}/health-alert-routes/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_camera_health_route(
    camera_id: str,
    route_id: str,
    session: SessionDependency,
    actor: AdminDependency,
) -> Response:
    camera = await session.get(Camera, camera_id)
    if camera is None or camera.organization_id != actor.organization_id:
        raise HTTPException(status_code=404, detail="Camera not found")
    route = await session.get(OperationalHealthRoute, route_id)
    if route is None or route.camera_id != camera_id:
        raise HTTPException(status_code=404, detail="Health alert route not found")
    pending = (
        await session.scalars(
            select(OperationalHealthDelivery)
            .join(
                OperationalHealthIncident,
                OperationalHealthIncident.id == OperationalHealthDelivery.incident_id,
            )
            .where(
                OperationalHealthIncident.camera_id == camera_id,
                OperationalHealthDelivery.channel_id == route.channel_id,
                OperationalHealthDelivery.status.in_(
                    [
                        AlertDeliveryStatus.QUEUED,
                        AlertDeliveryStatus.RETRYING,
                        AlertDeliveryStatus.DELIVERING,
                    ]
                ),
            )
            .with_for_update(of=OperationalHealthDelivery)
        )
    ).all()
    for delivery in pending:
        _suppress_delivery(delivery, "Camera health route removed")
    await session.delete(route)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/operational-health/incidents",
    response_model=list[OperationalHealthIncidentRead],
)
async def list_operational_health_incidents(
    session: SessionDependency,
    actor: ActorDependency,
    incident_status: Annotated[AlertStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[OperationalHealthIncidentRead]:
    statement = select(OperationalHealthIncident).where(
        OperationalHealthIncident.organization_id == actor.organization_id
    )
    if incident_status is not None:
        statement = statement.where(OperationalHealthIncident.status == incident_status)
    incidents = (
        await session.scalars(
            statement.order_by(OperationalHealthIncident.last_detected_at.desc()).limit(limit)
        )
    ).all()
    return [await _incident_response(session, incident) for incident in incidents]


@router.post(
    "/operational-health/incidents/{incident_id}/acknowledge",
    response_model=OperationalHealthIncidentRead,
)
async def acknowledge_operational_health_incident(
    incident_id: str,
    session: SessionDependency,
    actor: EditorDependency,
) -> OperationalHealthIncidentRead:
    incident = await session.scalar(
        select(OperationalHealthIncident)
        .where(
            OperationalHealthIncident.id == incident_id,
            OperationalHealthIncident.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if incident is None:
        raise HTTPException(status_code=404, detail="Operational health incident not found")
    if incident.status == AlertStatus.RESOLVED:
        raise HTTPException(status_code=409, detail="Resolved incidents cannot be acknowledged")
    if incident.status == AlertStatus.OPEN:
        incident.status = AlertStatus.ACKNOWLEDGED
        incident.acknowledged_at = utc_now()
        incident.acknowledged_by = actor.subject
        pending = (
            await session.scalars(
                select(OperationalHealthDelivery)
                .where(
                    OperationalHealthDelivery.incident_id == incident.id,
                    OperationalHealthDelivery.status.in_(
                        [
                            AlertDeliveryStatus.QUEUED,
                            AlertDeliveryStatus.RETRYING,
                            AlertDeliveryStatus.DELIVERING,
                        ]
                    ),
                )
                .with_for_update(of=OperationalHealthDelivery)
            )
        ).all()
        for delivery in pending:
            _suppress_delivery(delivery, "Operational health incident acknowledged")
        await session.commit()
        await session.refresh(incident)
    return await _incident_response(session, incident)


@router.post(
    "/agent/operational-health/evaluate",
    response_model=OperationalHealthEvaluationRead,
    dependencies=[Depends(require_agent_key)],
)
async def evaluate_operational_health(
    session: SessionDependency,
    settings: SettingsDependency,
) -> OperationalHealthEvaluationRead:
    now = utc_now()
    camera_rows = (
        await session.execute(
            select(Camera, CameraAgent).outerjoin(CameraAgent, CameraAgent.camera_id == Camera.id)
        )
    ).all()
    camera_organizations = {camera.id: camera.organization_id for camera, _ in camera_rows}
    conditions = []
    monitored_edge_ids: set[str] = set()
    for camera, agent in camera_rows:
        conditions.extend(camera_conditions(camera, agent, settings, now))
        if camera.edge_device_id:
            monitored_edge_ids.add(camera.edge_device_id)
        if agent is not None and agent.edge_device_id:
            monitored_edge_ids.add(agent.edge_device_id)

    devices: list[EdgeDevice] = []
    if monitored_edge_ids:
        devices = list(
            (
                await session.scalars(
                    select(EdgeDevice).where(EdgeDevice.id.in_(monitored_edge_ids))
                )
            ).all()
        )
    for device in devices:
        condition = edge_condition(device, settings, now)
        if condition:
            conditions.append(condition)

    active_incidents = (
        await session.scalars(
            select(OperationalHealthIncident)
            .where(OperationalHealthIncident.active_key.is_not(None))
            .with_for_update()
        )
    ).all()
    active_by_key = {incident.active_key: incident for incident in active_incidents}
    observed_keys = {condition.active_key for condition in conditions}
    opened = 0
    for condition in conditions:
        incident = active_by_key.get(condition.active_key)
        if incident is None:
            incident = OperationalHealthIncident(
                id=new_id(),
                organization_id=condition.organization_id,
                camera_id=condition.camera_id,
                edge_device_id=condition.edge_device_id,
                resource_type=condition.resource_type,
                condition=condition.condition,
                severity=condition.severity,
                status=AlertStatus.OPEN,
                active_key=condition.active_key,
                title=condition.title,
                detail=condition.detail,
                diagnostics=condition.diagnostics,
                occurrence_count=1,
                first_detected_at=now,
                last_detected_at=now,
            )
            session.add(incident)
            active_by_key[condition.active_key] = incident
            opened += 1
        else:
            incident.condition = condition.condition
            incident.severity = condition.severity
            incident.title = condition.title
            incident.detail = condition.detail
            incident.diagnostics = condition.diagnostics
            incident.occurrence_count += 1
            incident.last_detected_at = now

    resolved = 0
    for incident in active_incidents:
        if incident.active_key not in observed_keys:
            incident.status = AlertStatus.RESOLVED
            incident.active_key = None
            incident.resolved_at = now
            incident.resolved_by = "system:operational-health-watchdog"
            pending = (
                await session.scalars(
                    select(OperationalHealthDelivery)
                    .where(
                        OperationalHealthDelivery.incident_id == incident.id,
                        OperationalHealthDelivery.status.in_(
                            [
                                AlertDeliveryStatus.QUEUED,
                                AlertDeliveryStatus.RETRYING,
                                AlertDeliveryStatus.DELIVERING,
                            ]
                        ),
                    )
                    .with_for_update(of=OperationalHealthDelivery)
                )
            ).all()
            for delivery in pending:
                _suppress_delivery(delivery, "Monitoring recovered")
            resolved += 1

    camera_incidents = [
        incident
        for key, incident in active_by_key.items()
        if key in observed_keys
        and incident.camera_id is not None
        and incident.severity == OperationalHealthSeverity.CRITICAL
        and incident.status == AlertStatus.OPEN
    ]
    if camera_incidents:
        await session.flush()
        routes = (
            await session.execute(
                select(OperationalHealthRoute, AlertChannel)
                .join(AlertChannel, AlertChannel.id == OperationalHealthRoute.channel_id)
                .where(
                    OperationalHealthRoute.camera_id.in_(
                        [incident.camera_id for incident in camera_incidents]
                    ),
                    AlertChannel.enabled.is_(True),
                )
            )
        ).all()
        incidents_by_camera = {incident.camera_id: incident for incident in camera_incidents}
        for route, channel in routes:
            incident = incidents_by_camera[route.camera_id]
            if (
                channel.organization_id != incident.organization_id
                or camera_organizations.get(route.camera_id) != incident.organization_id
            ):
                continue
            first_seen = incident.first_detected_at
            if first_seen.tzinfo is None:
                first_seen = first_seen.replace(tzinfo=UTC)
            if now - first_seen < timedelta(seconds=route.outage_after_seconds):
                continue
            values = {
                "id": new_id(),
                "incident_id": incident.id,
                "channel_id": channel.id,
                "status": AlertDeliveryStatus.QUEUED,
                "attempt_count": 0,
                "next_attempt_at": now,
                "created_at": now,
                "updated_at": now,
            }
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                statement = postgres_insert(OperationalHealthDelivery).values(**values)
            else:
                statement = sqlite_insert(OperationalHealthDelivery).values(**values)
            await session.execute(
                statement.on_conflict_do_nothing(
                    index_elements=[
                        OperationalHealthDelivery.incident_id,
                        OperationalHealthDelivery.channel_id,
                    ]
                )
            )
    completed_at = utc_now()
    values = {"id": 1, "last_successful_evaluation_at": completed_at}
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        watchdog_insert = postgres_insert(OperationalHealthWatchdog).values(**values)
    else:
        watchdog_insert = sqlite_insert(OperationalHealthWatchdog).values(**values)
    await session.execute(
        watchdog_insert.on_conflict_do_update(
            index_elements=[OperationalHealthWatchdog.id],
            set_={
                "last_successful_evaluation_at": case(
                    (
                        OperationalHealthWatchdog.last_successful_evaluation_at < completed_at,
                        completed_at,
                    ),
                    else_=OperationalHealthWatchdog.last_successful_evaluation_at,
                )
            },
        )
    )
    await session.commit()
    active_count = len(observed_keys)
    return OperationalHealthEvaluationRead(
        evaluated_resources=len(camera_rows) + len(devices),
        active_incidents=active_count,
        opened_incidents=opened,
        resolved_incidents=resolved,
    )


@router.post(
    "/agent/operational-health/deliveries/claim",
    response_model=OperationalHealthDeliveryAssignment | None,
    dependencies=[Depends(require_agent_key)],
)
async def claim_operational_health_delivery(
    payload: AlertWorkerClaim,
    session: SessionDependency,
    settings: SettingsDependency,
) -> OperationalHealthDeliveryAssignment | Response:
    now = utc_now()
    row = (
        await session.execute(
            select(OperationalHealthDelivery, OperationalHealthIncident, AlertChannel, Camera)
            .join(
                OperationalHealthIncident,
                OperationalHealthIncident.id == OperationalHealthDelivery.incident_id,
            )
            .join(AlertChannel, AlertChannel.id == OperationalHealthDelivery.channel_id)
            .join(Camera, Camera.id == OperationalHealthIncident.camera_id)
            .join(
                OperationalHealthRoute,
                and_(
                    OperationalHealthRoute.camera_id == OperationalHealthIncident.camera_id,
                    OperationalHealthRoute.channel_id == OperationalHealthDelivery.channel_id,
                ),
            )
            .where(
                OperationalHealthIncident.status == AlertStatus.OPEN,
                OperationalHealthIncident.active_key.is_not(None),
                OperationalHealthIncident.organization_id == Camera.organization_id,
                AlertChannel.organization_id == Camera.organization_id,
                AlertChannel.enabled.is_(True),
                OperationalHealthDelivery.next_attempt_at <= now,
                or_(
                    OperationalHealthDelivery.status.in_(
                        [AlertDeliveryStatus.QUEUED, AlertDeliveryStatus.RETRYING]
                    ),
                    (
                        (OperationalHealthDelivery.status == AlertDeliveryStatus.DELIVERING)
                        & (OperationalHealthDelivery.lease_expires_at < now)
                    ),
                ),
            )
            .order_by(
                OperationalHealthDelivery.next_attempt_at,
                OperationalHealthDelivery.created_at,
            )
            .with_for_update(skip_locked=True, of=OperationalHealthDelivery)
            .limit(1)
        )
    ).first()
    if row is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    delivery, incident, channel, camera = row
    if delivery.attempt_count >= channel.max_attempts:
        delivery.status = AlertDeliveryStatus.FAILED
        delivery.worker_id = None
        delivery.lease_expires_at = None
        delivery.last_error = "Maximum health delivery attempts reached after expired leases"
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
    # A second worker must not reclaim this delivery while the webhook request
    # is still within its configured timeout. Leave time to report the result.
    lease_seconds = max(settings.alert_lease_seconds, channel.timeout_seconds + 30)
    delivery.lease_expires_at = now + timedelta(seconds=lease_seconds)
    delivery.attempt_count += 1
    await session.commit()
    return OperationalHealthDeliveryAssignment(
        delivery_id=delivery.id,
        incident_id=incident.id,
        webhook_url=channel.webhook_url,
        signing_secret=secret,
        timeout_seconds=channel.timeout_seconds,
        payload={
            "schema_version": 1,
            "type": "video.monitoring.unavailable",
            "incident": {
                "id": incident.id,
                "condition": incident.condition,
                "severity": incident.severity.value,
                "first_detected_at": incident.first_detected_at.isoformat(),
            },
            "camera": {"id": camera.id, "name": camera.name},
            "message": (
                "Camera monitoring has stopped. Check the person using the household's "
                "usual response process; do not assume that no falls occurred."
            ),
            "review_path": "/api/v1/operational-health/incidents",
        },
    )


@router.post(
    "/agent/operational-health/deliveries/{delivery_id}/result",
    response_model=OperationalHealthDeliveryRead,
    dependencies=[Depends(require_agent_key)],
)
async def complete_operational_health_delivery(
    delivery_id: str,
    payload: AlertDeliveryResult,
    session: SessionDependency,
    settings: SettingsDependency,
) -> OperationalHealthDeliveryRead:
    row = (
        await session.execute(
            select(OperationalHealthDelivery, AlertChannel, OperationalHealthIncident)
            .join(AlertChannel, AlertChannel.id == OperationalHealthDelivery.channel_id)
            .join(
                OperationalHealthIncident,
                OperationalHealthIncident.id == OperationalHealthDelivery.incident_id,
            )
            .where(OperationalHealthDelivery.id == delivery_id)
            .with_for_update(of=OperationalHealthDelivery)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Health delivery not found")
    delivery, channel, incident = row
    if delivery.worker_id != payload.worker_id or delivery.status != AlertDeliveryStatus.DELIVERING:
        raise HTTPException(
            status_code=409, detail="Worker does not hold this health delivery lease"
        )
    now = utc_now()
    delivery.last_status_code = payload.status_code
    delivery.last_error = payload.error
    delivery.worker_id = None
    delivery.lease_expires_at = None
    if payload.outcome == "delivered":
        delivery.status = AlertDeliveryStatus.DELIVERED
        delivery.delivered_at = now
    elif (
        incident.status != AlertStatus.OPEN
        or incident.active_key is None
        or await session.scalar(
            select(OperationalHealthRoute.id).where(
                OperationalHealthRoute.camera_id == incident.camera_id,
                OperationalHealthRoute.channel_id == delivery.channel_id,
            )
        )
        is None
    ):
        delivery.status = AlertDeliveryStatus.SUPPRESSED
        delivery.last_error = (
            "Outage route removed or incident closed during in-flight delivery; "
            "request outcome may be unknown"
        )
    elif payload.outcome == "permanent_failure" or delivery.attempt_count >= channel.max_attempts:
        delivery.status = AlertDeliveryStatus.FAILED
        if delivery.attempt_count >= channel.max_attempts and not payload.error:
            delivery.last_error = "Maximum health delivery attempts reached"
    else:
        delivery.status = AlertDeliveryStatus.RETRYING
        delay = min(
            settings.alert_retry_base_seconds * 2 ** max(delivery.attempt_count - 1, 0),
            settings.alert_retry_max_seconds,
        )
        delivery.next_attempt_at = now + timedelta(seconds=delay)
    await session.commit()
    await session.refresh(delivery)
    return _delivery_response(delivery, channel)
