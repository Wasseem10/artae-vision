"""Operator-requested ONVIF discovery executed on an enrolled edge network."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import or_, select

from video_intelligence_api.auth import ActorDependency, AdminDependency
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.models import (
    CameraDiscoveryRun,
    CameraDiscoveryStatus,
    EdgeDevice,
    EdgeDeviceStatus,
    new_id,
    utc_now,
)
from video_intelligence_api.schemas import (
    CameraDiscoveryAssignment,
    CameraDiscoveryCreate,
    CameraDiscoveryRead,
    CameraDiscoveryResult,
    WorkerClaimRequest,
)
from video_intelligence_api.security import EdgePrincipal, require_edge_device

router = APIRouter(tags=["camera discovery"])


def _actual_device(principal: EdgePrincipal) -> tuple[str, str]:
    if principal.device_id is None or principal.organization_id is None:
        raise HTTPException(
            status_code=409,
            detail="Camera discovery requires an enrolled edge-device token",
        )
    return principal.device_id, principal.organization_id


@router.get("/camera-discovery-runs", response_model=list[CameraDiscoveryRead])
async def list_camera_discovery_runs(
    session: SessionDependency,
    actor: ActorDependency,
) -> list[CameraDiscoveryRun]:
    return list(
        (
            await session.scalars(
                select(CameraDiscoveryRun)
                .where(CameraDiscoveryRun.organization_id == actor.organization_id)
                .order_by(CameraDiscoveryRun.created_at.desc())
                .limit(50)
            )
        ).all()
    )


@router.post(
    "/camera-discovery-runs",
    response_model=CameraDiscoveryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_camera_discovery_run(
    payload: CameraDiscoveryCreate,
    session: SessionDependency,
    actor: AdminDependency,
) -> CameraDiscoveryRun:
    device = await session.scalar(
        select(EdgeDevice).where(
            EdgeDevice.id == payload.edge_device_id,
            EdgeDevice.organization_id == actor.organization_id,
            EdgeDevice.status == EdgeDeviceStatus.ACTIVE,
        )
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Active edge device not found")
    run = CameraDiscoveryRun(
        id=new_id(),
        organization_id=actor.organization_id,
        edge_device_id=device.id,
        timeout_seconds=payload.timeout_seconds,
        requested_by=actor.subject,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


@router.post(
    "/agent/camera-discovery-runs/claim",
    response_model=CameraDiscoveryAssignment | None,
)
async def claim_camera_discovery_run(
    payload: WorkerClaimRequest,
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> CameraDiscoveryAssignment | Response:
    device_id, organization_id = _actual_device(principal)
    now = utc_now()
    run = await session.scalar(
        select(CameraDiscoveryRun)
        .where(
            CameraDiscoveryRun.organization_id == organization_id,
            CameraDiscoveryRun.edge_device_id == device_id,
            or_(
                CameraDiscoveryRun.status == CameraDiscoveryStatus.QUEUED,
                (
                    (CameraDiscoveryRun.status == CameraDiscoveryStatus.RUNNING)
                    & (CameraDiscoveryRun.lease_expires_at < now)
                ),
            ),
        )
        .order_by(CameraDiscoveryRun.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if run is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    run.status = CameraDiscoveryStatus.RUNNING
    run.worker_id = payload.worker_id
    run.lease_expires_at = now + timedelta(seconds=settings.camera_discovery_lease_seconds)
    run.last_error = None
    await session.commit()
    return CameraDiscoveryAssignment(
        worker_id=payload.worker_id,
        discovery_id=run.id,
        timeout_seconds=run.timeout_seconds,
    )


@router.post(
    "/agent/camera-discovery-runs/{discovery_id}/result",
    response_model=CameraDiscoveryRead,
)
async def report_camera_discovery_result(
    discovery_id: str,
    payload: CameraDiscoveryResult,
    session: SessionDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> CameraDiscoveryRun:
    device_id, organization_id = _actual_device(principal)
    run = await session.scalar(
        select(CameraDiscoveryRun).where(
            CameraDiscoveryRun.id == discovery_id,
            CameraDiscoveryRun.organization_id == organization_id,
            CameraDiscoveryRun.edge_device_id == device_id,
        )
    )
    if (
        run is None
        or run.status != CameraDiscoveryStatus.RUNNING
        or run.worker_id != payload.worker_id
    ):
        raise HTTPException(status_code=409, detail="Worker does not hold this discovery lease")
    run.devices = [device.model_dump(mode="json") for device in payload.devices]
    run.last_error = payload.error
    run.status = CameraDiscoveryStatus.FAILED if payload.error else CameraDiscoveryStatus.COMPLETED
    run.completed_at = utc_now()
    run.worker_id = None
    run.lease_expires_at = None
    await session.commit()
    await session.refresh(run)
    return run
