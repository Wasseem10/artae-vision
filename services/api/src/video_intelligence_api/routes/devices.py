"""Organization-owned edge-device enrollment and credential lifecycle."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.auth import ActorDependency, AdminDependency
from video_intelligence_api.dependencies import SessionDependency
from video_intelligence_api.device_credentials import generate_device_credential
from video_intelligence_api.models import (
    AgentDesiredStatus,
    AgentObservedStatus,
    CameraAgent,
    EdgeDevice,
    EdgeDeviceStatus,
    new_id,
    utc_now,
)
from video_intelligence_api.schemas import (
    EdgeDeviceCreate,
    EdgeDeviceCredential,
    EdgeDeviceRead,
    EdgeDeviceUpdate,
)

router = APIRouter(prefix="/edge-devices", tags=["edge devices"])


async def _tenant_device(
    session: SessionDependency, organization_id: str, device_id: str
) -> EdgeDevice | None:
    return await session.scalar(
        select(EdgeDevice).where(
            EdgeDevice.id == device_id,
            EdgeDevice.organization_id == organization_id,
        )
    )


async def _release_device_leases(session: SessionDependency, device_id: str) -> None:
    agents = list(
        (
            await session.scalars(
                select(CameraAgent).where(CameraAgent.edge_device_id == device_id)
            )
        ).all()
    )
    for agent in agents:
        agent.worker_id = None
        agent.edge_device_id = None
        agent.lease_expires_at = None
        agent.observed_status = (
            AgentObservedStatus.WAITING
            if agent.desired_status == AgentDesiredStatus.RUNNING
            else AgentObservedStatus.STOPPED
        )


@router.get("", response_model=list[EdgeDeviceRead])
async def list_edge_devices(
    session: SessionDependency,
    actor: ActorDependency,
) -> list[EdgeDevice]:
    return list(
        (
            await session.scalars(
                select(EdgeDevice)
                .where(EdgeDevice.organization_id == actor.organization_id)
                .order_by(EdgeDevice.created_at.desc())
            )
        ).all()
    )


@router.post("", response_model=EdgeDeviceCredential, status_code=status.HTTP_201_CREATED)
async def create_edge_device(
    payload: EdgeDeviceCreate,
    session: SessionDependency,
    actor: AdminDependency,
) -> EdgeDeviceCredential:
    device_id = new_id()
    credential = generate_device_credential(device_id)
    device = EdgeDevice(
        id=device_id,
        organization_id=actor.organization_id,
        name=payload.name,
        max_concurrent_streams=payload.max_concurrent_streams,
        credential_hash=credential.token_hash,
        credential_fingerprint=credential.fingerprint,
    )
    session.add(device)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="An edge device with this name already exists",
        ) from exc
    await session.refresh(device)
    return EdgeDeviceCredential(
        device=EdgeDeviceRead.model_validate(device), token=credential.token
    )


@router.patch("/{device_id}", response_model=EdgeDeviceRead)
async def update_edge_device(
    device_id: Annotated[str, Path(min_length=36, max_length=36)],
    payload: EdgeDeviceUpdate,
    session: SessionDependency,
    actor: AdminDependency,
) -> EdgeDevice:
    device = await _tenant_device(session, actor.organization_id, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Edge device not found")
    if payload.name is not None:
        device.name = payload.name
    if payload.max_concurrent_streams is not None:
        device.max_concurrent_streams = payload.max_concurrent_streams
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Edge-device name is already in use") from exc
    await session.refresh(device)
    return device


@router.post("/{device_id}/rotate-credential", response_model=EdgeDeviceCredential)
async def rotate_edge_device_credential(
    device_id: Annotated[str, Path(min_length=36, max_length=36)],
    session: SessionDependency,
    actor: AdminDependency,
) -> EdgeDeviceCredential:
    device = await _tenant_device(session, actor.organization_id, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Edge device not found")
    if device.status == EdgeDeviceStatus.REVOKED:
        raise HTTPException(status_code=409, detail="A revoked edge device cannot be rotated")
    credential = generate_device_credential(device.id)
    device.credential_hash = credential.token_hash
    device.credential_fingerprint = credential.fingerprint
    await _release_device_leases(session, device.id)
    await session.commit()
    await session.refresh(device)
    return EdgeDeviceCredential(
        device=EdgeDeviceRead.model_validate(device), token=credential.token
    )


@router.post("/{device_id}/revoke", response_model=EdgeDeviceRead)
async def revoke_edge_device(
    device_id: Annotated[str, Path(min_length=36, max_length=36)],
    session: SessionDependency,
    actor: AdminDependency,
) -> EdgeDevice:
    device = await _tenant_device(session, actor.organization_id, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Edge device not found")
    if device.status != EdgeDeviceStatus.REVOKED:
        device.status = EdgeDeviceStatus.REVOKED
        device.revoked_at = utc_now()
        await _release_device_leases(session, device.id)
        await session.commit()
        await session.refresh(device)
    return device
