"""Edge-executed camera stream commissioning without starting visual inference."""

import base64
import binascii
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import or_, select

from video_intelligence_api.auth import ActorDependency, AdminDependency
from video_intelligence_api.camera_commissioning import assess_camera
from video_intelligence_api.camera_secrets import CameraSecretError, resolved_camera_source
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.models import (
    Camera,
    CameraCommissioningRun,
    CameraCommissioningStatus,
    CameraStatus,
    EdgeDevice,
    EdgeDeviceStatus,
    new_id,
    utc_now,
)
from video_intelligence_api.schemas import (
    CameraCommissioningAssignment,
    CameraCommissioningCreate,
    CameraCommissioningMetrics,
    CameraCommissioningRead,
    CameraCommissioningResult,
    WorkerClaimRequest,
)
from video_intelligence_api.security import EdgePrincipal, require_edge_device
from video_intelligence_api.tenancy import tenant_camera

router = APIRouter(tags=["camera commissioning"])


def _actual_device(principal: EdgePrincipal) -> tuple[str, str]:
    if principal.device_id is None or principal.organization_id is None:
        raise HTTPException(
            status_code=409, detail="Commissioning requires an enrolled edge-device token"
        )
    return principal.device_id, principal.organization_id


def commissioning_response(run: CameraCommissioningRun) -> CameraCommissioningRead:
    return CameraCommissioningRead(
        id=run.id,
        organization_id=run.organization_id,
        camera_id=run.camera_id,
        edge_device_id=run.edge_device_id,
        status=run.status,
        duration_seconds=run.duration_seconds,
        maximum_frames=run.maximum_frames,
        metrics=CameraCommissioningMetrics.model_validate(run.metrics) if run.metrics else None,
        findings=run.findings,
        readiness_score=run.readiness_score,
        worker_id=run.worker_id,
        lease_expires_at=run.lease_expires_at,
        last_error=run.last_error,
        requested_by=run.requested_by,
        completed_at=run.completed_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.get("/camera-commissioning-runs", response_model=list[CameraCommissioningRead])
async def list_camera_commissioning_runs(
    session: SessionDependency,
    actor: ActorDependency,
    camera_id: Annotated[str | None, Query(max_length=36)] = None,
) -> list[CameraCommissioningRead]:
    statement = select(CameraCommissioningRun).where(
        CameraCommissioningRun.organization_id == actor.organization_id
    )
    if camera_id:
        statement = statement.where(CameraCommissioningRun.camera_id == camera_id)
    runs = (
        await session.scalars(
            statement.order_by(CameraCommissioningRun.created_at.desc()).limit(100)
        )
    ).all()
    return [commissioning_response(run) for run in runs]


@router.post("/camera-commissioning-runs", response_model=CameraCommissioningRead, status_code=201)
async def create_camera_commissioning_run(
    payload: CameraCommissioningCreate,
    session: SessionDependency,
    actor: AdminDependency,
) -> CameraCommissioningRead:
    camera = await tenant_camera(session, actor, payload.camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    device_id = camera.edge_device_id or payload.edge_device_id
    if device_id is None:
        raise HTTPException(status_code=422, detail="Select an edge device for this camera")
    if camera.edge_device_id is not None and payload.edge_device_id not in {
        None,
        camera.edge_device_id,
    }:
        raise HTTPException(status_code=409, detail="Camera is pinned to another edge device")
    device = await session.scalar(
        select(EdgeDevice).where(
            EdgeDevice.id == device_id,
            EdgeDevice.organization_id == actor.organization_id,
            EdgeDevice.status == EdgeDeviceStatus.ACTIVE,
        )
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Active edge device not found")
    active = await session.scalar(
        select(CameraCommissioningRun.id).where(
            CameraCommissioningRun.camera_id == camera.id,
            CameraCommissioningRun.status.in_(
                [
                    CameraCommissioningStatus.QUEUED,
                    CameraCommissioningStatus.RUNNING,
                ]
            ),
        )
    )
    if active is not None:
        raise HTTPException(
            status_code=409, detail="Camera already has an active commissioning run"
        )
    run = CameraCommissioningRun(
        id=new_id(),
        organization_id=actor.organization_id,
        camera_id=camera.id,
        edge_device_id=device.id,
        duration_seconds=payload.duration_seconds,
        maximum_frames=payload.maximum_frames,
        requested_by=actor.subject,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return commissioning_response(run)


@router.post(
    "/agent/camera-commissioning-runs/claim", response_model=CameraCommissioningAssignment | None
)
async def claim_camera_commissioning_run(
    payload: WorkerClaimRequest,
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> CameraCommissioningAssignment | Response:
    device_id, organization_id = _actual_device(principal)
    now = utc_now()
    row = (
        await session.execute(
            select(CameraCommissioningRun, Camera)
            .join(Camera, Camera.id == CameraCommissioningRun.camera_id)
            .where(
                CameraCommissioningRun.organization_id == organization_id,
                CameraCommissioningRun.edge_device_id == device_id,
                or_(
                    CameraCommissioningRun.status == CameraCommissioningStatus.QUEUED,
                    (
                        (CameraCommissioningRun.status == CameraCommissioningStatus.RUNNING)
                        & (CameraCommissioningRun.lease_expires_at < now)
                    ),
                ),
            )
            .order_by(CameraCommissioningRun.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
    ).first()
    if row is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    run, camera = row
    try:
        source_uri = resolved_camera_source(camera, settings)
    except CameraSecretError as exc:
        raise HTTPException(status_code=503, detail="Camera credentials are unavailable") from exc
    run.status = CameraCommissioningStatus.RUNNING
    run.worker_id = payload.worker_id
    run.lease_expires_at = now + timedelta(seconds=settings.camera_commissioning_lease_seconds)
    run.last_error = None
    await session.commit()
    return CameraCommissioningAssignment(
        worker_id=payload.worker_id,
        commissioning_id=run.id,
        camera_id=camera.id,
        source_uri=source_uri,
        duration_seconds=run.duration_seconds,
        maximum_frames=run.maximum_frames,
    )


@router.post(
    "/agent/camera-commissioning-runs/{commissioning_id}/result",
    response_model=CameraCommissioningRead,
)
async def report_camera_commissioning_result(
    commissioning_id: str,
    payload: CameraCommissioningResult,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> CameraCommissioningRead:
    device_id, organization_id = _actual_device(principal)
    run = await session.scalar(
        select(CameraCommissioningRun).where(
            CameraCommissioningRun.id == commissioning_id,
            CameraCommissioningRun.organization_id == organization_id,
            CameraCommissioningRun.edge_device_id == device_id,
        )
    )
    if (
        run is None
        or run.status != CameraCommissioningStatus.RUNNING
        or run.worker_id != payload.worker_id
    ):
        raise HTTPException(status_code=409, detail="Worker does not hold this commissioning lease")
    if payload.error or payload.metrics is None:
        run.status = CameraCommissioningStatus.FAILED
        run.last_error = (payload.error or "Commissioning returned no metrics")[:1000]
    else:
        assessment = assess_camera(payload.metrics)
        run.metrics = payload.metrics.model_dump(mode="json")
        run.findings = [item.model_dump(mode="json") for item in assessment.findings]
        run.readiness_score = assessment.score
        run.status = (
            CameraCommissioningStatus.PASSED
            if assessment.ready
            else CameraCommissioningStatus.NEEDS_ATTENTION
        )
        run.last_error = None
        if payload.preview_jpeg_base64:
            try:
                preview = base64.b64decode(payload.preview_jpeg_base64, validate=True)
                if (
                    not preview.startswith(b"\xff\xd8")
                    or not preview.endswith(b"\xff\xd9")
                    or len(preview) > settings.preview_max_bytes
                ):
                    raise ValueError
                await request.app.state.preview_store.put(
                    run.camera_id, run.organization_id, preview
                )
            except (ValueError, binascii.Error):
                run.status = CameraCommissioningStatus.FAILED
                run.last_error = "Commissioning preview was invalid"
        camera = await session.get(Camera, run.camera_id)
        if camera is not None and run.status == CameraCommissioningStatus.PASSED:
            camera.status = CameraStatus.ONLINE
    run.completed_at = utc_now()
    run.worker_id = None
    run.lease_expires_at = None
    await session.commit()
    await session.refresh(run)
    return commissioning_response(run)
