"""Durable camera-agent control plus leased edge-worker telemetry."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from sqlalchemy import func, or_, select

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.camera_secrets import (
    CameraSecretError,
    resolved_camera_source,
)
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
    CameraStatus,
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


def camera_capture_source(camera: Camera, settings: SettingsDependency) -> str:
    source = camera.source_uri
    if camera.credential_encrypted is None:
        return source
    try:
        return resolved_camera_source(camera, settings)
    except CameraSecretError as exc:
        raise HTTPException(status_code=503, detail="Camera credentials are unavailable") from exc


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
            last_frame_at=None,
            health_status="offline",
            heartbeat_age_seconds=None,
            fps=None,
            inference_latency_ms=None,
            frame_width=None,
            frame_height=None,
            frames_processed=0,
            reconnect_count=0,
            recording_state="disabled",
            recording_segments_completed=0,
            recording_dropped_frames=0,
            recording_error=None,
            failure_count=0,
            next_retry_at=None,
            last_error=None,
            updated_at=None,
        )
    observed = agent.observed_status
    now = utc_now()
    lease = agent.lease_expires_at
    if lease is not None and lease.tzinfo is None:
        lease = lease.replace(tzinfo=utc_now().tzinfo)
    if (
        agent.desired_status == AgentDesiredStatus.RUNNING
        and observed in {AgentObservedStatus.STARTING, AgentObservedStatus.RUNNING}
        and lease is not None
        and lease < now
    ):
        observed = AgentObservedStatus.WAITING
    heartbeat = agent.last_heartbeat_at
    if heartbeat is not None and heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=now.tzinfo)
    heartbeat_age = max(0.0, (now - heartbeat).total_seconds()) if heartbeat else None
    if agent.desired_status == AgentDesiredStatus.STOPPED:
        health_status = "offline"
    elif agent.observed_status == AgentObservedStatus.ERROR:
        health_status = "error"
    elif lease is not None and lease < now:
        health_status = "stale"
    elif agent.observed_status == AgentObservedStatus.RUNNING:
        health_status = "healthy"
    else:
        health_status = "recovering"
    return CameraAgentRead(
        camera_id=camera_id,
        desired_status=agent.desired_status,
        observed_status=observed,
        worker_id=agent.worker_id,
        edge_device_id=agent.edge_device_id,
        lease_expires_at=agent.lease_expires_at,
        last_heartbeat_at=agent.last_heartbeat_at,
        last_frame_at=agent.last_frame_at,
        health_status=health_status,
        heartbeat_age_seconds=heartbeat_age,
        fps=agent.fps,
        inference_latency_ms=agent.inference_latency_ms,
        frame_width=agent.frame_width,
        frame_height=agent.frame_height,
        frames_processed=agent.frames_processed,
        reconnect_count=agent.reconnect_count,
        recording_state=agent.recording_state,
        recording_segments_completed=agent.recording_segments_completed,
        recording_dropped_frames=agent.recording_dropped_frames,
        recording_error=agent.recording_error,
        failure_count=agent.failure_count,
        next_retry_at=agent.next_retry_at,
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
        source = (
            camera_capture_source(camera, request.app.state.settings)
            if camera.source_type.value == "rtsp" and camera.edge_device_id is None
            else "publisher"
        )
        try:
            await gateway.provision(camera_path(camera_id), source)
        except MediaGatewayError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        agent.desired_status = AgentDesiredStatus.RUNNING
        agent.observed_status = AgentObservedStatus.WAITING
        agent.last_error = None
        agent.failure_count = 0
        agent.next_retry_at = None
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
            or_(CameraAgent.next_retry_at.is_(None), CameraAgent.next_retry_at <= now),
        )
        .order_by(CameraAgent.updated_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if principal.organization_id is not None:
        statement = statement.where(Camera.organization_id == principal.organization_id)
    if principal.device_id is not None:
        statement = statement.where(
            or_(Camera.edge_device_id.is_(None), Camera.edge_device_id == principal.device_id)
        )
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
    direct_capture = (
        camera_capture_source(camera, settings)
        if camera.source_type.value in {"webcam", "file"} or camera.edge_device_id is not None
        else None
    )
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
    if payload.frames_processed is not None:
        agent.frames_processed = payload.frames_processed
    if payload.reconnect_count is not None:
        agent.reconnect_count = payload.reconnect_count
    if payload.recording_state is not None:
        agent.recording_state = payload.recording_state
        agent.recording_error = payload.recording_error
    if payload.recording_segments_completed is not None:
        agent.recording_segments_completed = payload.recording_segments_completed
    if payload.recording_dropped_frames is not None:
        agent.recording_dropped_frames = payload.recording_dropped_frames
    elif payload.recording_error is not None:
        agent.recording_error = payload.recording_error
    agent.last_error = payload.error
    if observed == AgentObservedStatus.RUNNING:
        agent.last_frame_at = now
        agent.failure_count = 0
        agent.next_retry_at = None
        camera.status = CameraStatus.ONLINE
    elif observed == AgentObservedStatus.ERROR:
        agent.failure_count += 1
        exponent = min(agent.failure_count - 1, 16)
        retry_seconds = min(
            settings.agent_restart_backoff_base_seconds * 2**exponent,
            settings.agent_restart_backoff_max_seconds,
        )
        agent.next_retry_at = now + timedelta(seconds=retry_seconds)
        camera.status = CameraStatus.ERROR
    elif observed == AgentObservedStatus.STOPPED:
        camera.status = CameraStatus.OFFLINE
        if agent.desired_status == AgentDesiredStatus.STOPPED:
            agent.failure_count = 0
            agent.next_retry_at = None
    if observed in {AgentObservedStatus.STOPPED, AgentObservedStatus.ERROR}:
        agent.worker_id = None
        agent.edge_device_id = None
        agent.lease_expires_at = None
    await session.commit()
    await session.refresh(agent)

    body = agent_response(payload.camera_id, agent)
    data = payload.model_dump(mode="json")
    data.update(body.model_dump(mode="json"))
    await request.app.state.event_connections.broadcast(
        {"type": "agent.telemetry", "data": data},
        organization_id=camera.organization_id,
    )
    return body
