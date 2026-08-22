"""Durable camera-agent control plus leased edge-worker telemetry."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from sqlalchemy import func, or_, select

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.dependencies import (
    MediaGatewayDependency,
    SessionDependency,
    SettingsDependency,
)
from video_intelligence_api.job_specs import legacy_job_spec
from video_intelligence_api.media_gateway import MediaGatewayError, camera_path
from video_intelligence_api.models import (
    AgentDesiredStatus,
    AgentObservedStatus,
    Camera,
    CameraAgent,
    EdgeDevice,
    Rule,
    RuleStatus,
    Zone,
    utc_now,
)
from video_intelligence_api.schemas import (
    AgentControlUpdate,
    AgentRuleConfig,
    AgentZoneConfig,
    CameraAgentRead,
    WorkerAssignment,
    WorkerClaimRequest,
    WorkerTelemetry,
)
from video_intelligence_api.security import (
    EdgePrincipal,
    ensure_edge_organization,
    require_edge_device,
)
from video_intelligence_api.tenancy import tenant_camera

router = APIRouter(tags=["managed agents"])


def agent_response(camera_id: str, agent: CameraAgent | None) -> CameraAgentRead:
    if agent is None:
        return CameraAgentRead(
            camera_id=camera_id,
            desired_status=AgentDesiredStatus.STOPPED,
            observed_status=AgentObservedStatus.STOPPED,
            worker_id=None,
            edge_device_id=None,
            lease_expires_at=None,
            last_heartbeat_at=None,
            fps=None,
            inference_latency_ms=None,
            frame_width=None,
            frame_height=None,
            last_error=None,
            updated_at=None,
        )
    observed = agent.observed_status
    lease = agent.lease_expires_at
    if lease is not None and lease.tzinfo is None:
        lease = lease.replace(tzinfo=utc_now().tzinfo)
    if (
        agent.desired_status == AgentDesiredStatus.RUNNING
        and observed in {AgentObservedStatus.STARTING, AgentObservedStatus.RUNNING}
        and lease is not None
        and lease < utc_now()
    ):
        observed = AgentObservedStatus.WAITING
    return CameraAgentRead(
        camera_id=camera_id,
        desired_status=agent.desired_status,
        observed_status=observed,
        worker_id=agent.worker_id,
        edge_device_id=agent.edge_device_id,
        lease_expires_at=agent.lease_expires_at,
        last_heartbeat_at=agent.last_heartbeat_at,
        fps=agent.fps,
        inference_latency_ms=agent.inference_latency_ms,
        frame_width=agent.frame_width,
        frame_height=agent.frame_height,
        last_error=agent.last_error,
        updated_at=agent.updated_at,
    )


async def active_rule_rows(camera_id: str, session: SessionDependency) -> list[tuple[Rule, Zone]]:
    rows = (
        await session.execute(
            select(Rule, Zone)
            .join(Zone, Rule.zone_id == Zone.id)
            .where(Rule.camera_id == camera_id, Rule.status == RuleStatus.ACTIVE)
            .order_by(Rule.created_at)
        )
    ).all()
    return list(rows)


def assignment_rule(rule: Rule, zone: Zone) -> AgentRuleConfig:
    spec = rule.spec or legacy_job_spec(
        object_class=rule.object_class,
        zone_id=zone.id,
        zone_name=zone.name,
        duration_seconds=rule.duration_seconds,
        minimum_confidence=rule.minimum_confidence,
        absence_grace_seconds=rule.absence_grace_seconds,
    ).model_dump(mode="json")
    return AgentRuleConfig(
        id=rule.id,
        key=rule.key,
        rule_type=rule.rule_type,
        object_class=rule.object_class,
        duration_seconds=rule.duration_seconds,
        minimum_confidence=rule.minimum_confidence,
        absence_grace_seconds=rule.absence_grace_seconds,
        zone=AgentZoneConfig(
            id=zone.id,
            name=zone.name,
            geometry_type=zone.geometry_type,
            points=zone.points,
        ),
        spec=spec,
    )


@router.get("/cameras/{camera_id}/agent", response_model=CameraAgentRead)
async def get_camera_agent(
    camera_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: ActorDependency,
) -> CameraAgentRead:
    if await tenant_camera(session, actor, camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return agent_response(camera_id, await session.get(CameraAgent, camera_id))


@router.put("/cameras/{camera_id}/agent", response_model=CameraAgentRead)
async def control_camera_agent(
    camera_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: AgentControlUpdate,
    request: Request,
    session: SessionDependency,
    gateway: MediaGatewayDependency,
    actor: EditorDependency,
) -> CameraAgentRead:
    camera = await tenant_camera(session, actor, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    agent = await session.get(CameraAgent, camera_id)
    if agent is None:
        agent = CameraAgent(camera_id=camera_id)
        session.add(agent)

    if payload.desired_status == AgentDesiredStatus.RUNNING:
        rules = await active_rule_rows(camera_id, session)
        if not rules:
            raise HTTPException(
                status_code=409,
                detail="Activate at least one rule before starting this camera agent",
            )
        source = camera.source_uri if camera.source_type.value == "rtsp" else "publisher"
        try:
            await gateway.provision(camera_path(camera_id), source)
        except MediaGatewayError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        agent.desired_status = AgentDesiredStatus.RUNNING
        agent.observed_status = AgentObservedStatus.WAITING
        agent.last_error = None
    else:
        agent.desired_status = AgentDesiredStatus.STOPPED
        agent.observed_status = (
            AgentObservedStatus.STOPPING if agent.worker_id else AgentObservedStatus.STOPPED
        )
    await session.commit()
    await session.refresh(agent)
    body = agent_response(camera_id, agent)
    await request.app.state.event_connections.broadcast(
        {"type": "agent.status", "data": body.model_dump(mode="json")},
        organization_id=camera.organization_id,
    )
    return body


@router.post(
    "/agent/assignments/claim",
    response_model=WorkerAssignment | None,
)
async def claim_assignment(
    payload: WorkerClaimRequest,
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> WorkerAssignment | Response:
    now = utc_now()
    device = None
    if principal.device_id is not None:
        device = await session.scalar(
            select(EdgeDevice).where(EdgeDevice.id == principal.device_id).with_for_update()
        )
        if device is None:
            raise HTTPException(status_code=401, detail="Edge device is unavailable")
        active_count = await session.scalar(
            select(func.count())
            .select_from(CameraAgent)
            .where(
                CameraAgent.edge_device_id == device.id,
                CameraAgent.worker_id.is_not(None),
                CameraAgent.lease_expires_at >= now,
            )
        )
        if (active_count or 0) >= device.max_concurrent_streams:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
    statement = (
        select(CameraAgent, Camera)
        .join(Camera, Camera.id == CameraAgent.camera_id)
        .where(
            CameraAgent.desired_status == AgentDesiredStatus.RUNNING,
            or_(
                CameraAgent.worker_id.is_(None),
                CameraAgent.lease_expires_at.is_(None),
                CameraAgent.lease_expires_at < now,
            ),
        )
        .order_by(CameraAgent.updated_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if principal.organization_id is not None:
        statement = statement.where(Camera.organization_id == principal.organization_id)
    row = (await session.execute(statement)).first()
    if row is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    agent, camera = row
    rules = await active_rule_rows(camera.id, session)
    if not rules:
        agent.observed_status = AgentObservedStatus.ERROR
        agent.last_error = "Camera no longer has any active rules"
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    agent.worker_id = payload.worker_id
    agent.edge_device_id = principal.device_id
    agent.observed_status = AgentObservedStatus.STARTING
    agent.last_heartbeat_at = now
    agent.lease_expires_at = now + timedelta(seconds=settings.agent_lease_seconds)
    agent.last_error = None
    if device is not None:
        device.last_worker_id = payload.worker_id
        device.last_seen_at = now
    await session.commit()
    analysis_source = f"{settings.media_gateway_rtsp_url.rstrip('/')}/{camera_path(camera.id)}"
    direct_capture = camera.source_uri if camera.source_type.value in {"webcam", "file"} else None
    publish_url = (
        analysis_source
        if direct_capture is not None and settings.media_gateway_mode == "mediamtx"
        else None
    )
    return WorkerAssignment(
        worker_id=payload.worker_id,
        camera_id=camera.id,
        camera_name=camera.name,
        analysis_source_uri=analysis_source,
        capture_source_uri=direct_capture,
        publish_url=publish_url,
        rules=[assignment_rule(rule, zone) for rule, zone in rules],
    )


@router.post(
    "/agent/telemetry",
    response_model=CameraAgentRead,
)
async def ingest_worker_telemetry(
    payload: WorkerTelemetry,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> CameraAgentRead:
    agent = await session.get(CameraAgent, payload.camera_id)
    if (
        agent is None
        or agent.worker_id != payload.worker_id
        or (principal.device_id is not None and agent.edge_device_id != principal.device_id)
    ):
        raise HTTPException(status_code=409, detail="Worker does not hold this camera lease")

    camera = await session.get(Camera, payload.camera_id)
    if camera is None:
        raise HTTPException(status_code=409, detail="Camera is unavailable")
    ensure_edge_organization(principal, camera.organization_id)

    now = utc_now()
    observed = payload.observed_status
    if agent.desired_status == AgentDesiredStatus.STOPPED:
        observed = (
            AgentObservedStatus.STOPPED
            if payload.observed_status == AgentObservedStatus.STOPPED
            else AgentObservedStatus.STOPPING
        )
    agent.observed_status = observed
    agent.last_heartbeat_at = now
    agent.lease_expires_at = now + timedelta(seconds=settings.agent_lease_seconds)
    agent.fps = payload.fps
    agent.inference_latency_ms = payload.inference_latency_ms
    agent.frame_width = payload.frame_width
    agent.frame_height = payload.frame_height
    agent.last_error = payload.error
    if observed in {AgentObservedStatus.STOPPED, AgentObservedStatus.ERROR}:
        agent.worker_id = None
        agent.edge_device_id = None
        agent.lease_expires_at = None
    await session.commit()
    await session.refresh(agent)

    data = payload.model_dump(mode="json")
    data["desired_status"] = agent.desired_status.value
    await request.app.state.event_connections.broadcast(
        {"type": "agent.telemetry", "data": data},
        organization_id=camera.organization_id,
    )
    return agent_response(payload.camera_id, agent)
