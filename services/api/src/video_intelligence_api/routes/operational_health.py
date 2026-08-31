"""Automatic camera and edge-station reliability incidents."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.models import (
    AlertStatus,
    Camera,
    CameraAgent,
    EdgeDevice,
    OperationalHealthIncident,
    new_id,
    utc_now,
)
from video_intelligence_api.operational_health import camera_conditions, edge_condition
from video_intelligence_api.schemas import (
    OperationalHealthEvaluationRead,
    OperationalHealthIncidentRead,
)
from video_intelligence_api.security import require_agent_key

router = APIRouter(tags=["operational health"])


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
    )


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
        select(OperationalHealthIncident).where(
            OperationalHealthIncident.id == incident_id,
            OperationalHealthIncident.organization_id == actor.organization_id,
        )
    )
    if incident is None:
        raise HTTPException(status_code=404, detail="Operational health incident not found")
    if incident.status == AlertStatus.RESOLVED:
        raise HTTPException(status_code=409, detail="Resolved incidents cannot be acknowledged")
    if incident.status == AlertStatus.OPEN:
        incident.status = AlertStatus.ACKNOWLEDGED
        incident.acknowledged_at = utc_now()
        incident.acknowledged_by = actor.subject
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
            resolved += 1
    await session.commit()
    active_count = len(observed_keys)
    return OperationalHealthEvaluationRead(
        evaluated_resources=len(camera_rows) + len(devices),
        active_incidents=active_count,
        opened_incidents=opened,
        resolved_incidents=resolved,
    )
