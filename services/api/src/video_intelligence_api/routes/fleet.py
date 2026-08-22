from __future__ import annotations

import hashlib
import hmac
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select

from video_intelligence_api.auth import ActorDependency, AdminDependency
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.models import (
    EdgeConfigBundle,
    EdgeDevice,
    EdgeHealthStatus,
    EdgeStationProfile,
    EdgeUpdateDeployment,
    EdgeUpdateStatus,
    new_id,
    utc_now,
)
from video_intelligence_api.schemas import (
    EdgeConfigBundleCreate,
    EdgeConfigBundleRead,
    EdgeFleetDeviceRead,
    EdgeStationProfileRead,
    EdgeStationProfileReport,
    EdgeUpdateCreate,
    EdgeUpdateRead,
    EdgeUpdateReport,
)
from video_intelligence_api.security import EdgePrincipal, require_edge_device

router = APIRouter(tags=["edge fleet"])


async def _tenant_device(
    session: SessionDependency, organization_id: str, device_id: str
) -> EdgeDevice:
    device = await session.scalar(
        select(EdgeDevice).where(
            EdgeDevice.id == device_id,
            EdgeDevice.organization_id == organization_id,
        )
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Edge device not found")
    return device


def _actual_device(principal: EdgePrincipal) -> tuple[str, str]:
    if principal.device_id is None or principal.organization_id is None:
        raise HTTPException(
            status_code=409,
            detail="This fleet endpoint requires an enrolled edge-device token",
        )
    return principal.device_id, principal.organization_id


def _signed_configuration(
    settings: SettingsDependency, configuration: dict[str, object]
) -> tuple[str, str]:
    if settings.media_signing_key is None:
        raise HTTPException(
            status_code=409,
            detail="Configuration signing is unavailable until a media signing key is set",
        )
    canonical = json.dumps(configuration, separators=(",", ":"), sort_keys=True).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    signature = hmac.new(
        settings.media_signing_key.get_secret_value().encode(),
        canonical,
        hashlib.sha256,
    ).hexdigest()
    return digest, signature


async def _upsert_profile(
    session: SessionDependency,
    device: EdgeDevice,
    payload: EdgeStationProfileReport,
) -> EdgeStationProfile:
    profile = await session.get(EdgeStationProfile, device.id)
    if profile is None:
        profile = EdgeStationProfile(
            device_id=device.id,
            organization_id=device.organization_id,
        )
        session.add(profile)
    for field, value in payload.model_dump().items():
        setattr(profile, field, value)
    device.last_seen_at = utc_now()
    device.last_worker_id = payload.hostname
    await session.commit()
    await session.refresh(profile)
    return profile


@router.post("/agent/fleet/profile", response_model=EdgeStationProfileRead)
async def report_station_profile(
    payload: EdgeStationProfileReport,
    session: SessionDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> EdgeStationProfile:
    device_id, organization_id = _actual_device(principal)
    device = await _tenant_device(session, organization_id, device_id)
    return await _upsert_profile(session, device, payload)


@router.get("/edge-devices/fleet", response_model=list[EdgeFleetDeviceRead])
async def list_fleet(
    session: SessionDependency,
    actor: ActorDependency,
) -> list[EdgeFleetDeviceRead]:
    devices = list(
        (
            await session.scalars(
                select(EdgeDevice)
                .where(EdgeDevice.organization_id == actor.organization_id)
                .order_by(EdgeDevice.created_at.desc())
            )
        ).all()
    )
    fleet: list[EdgeFleetDeviceRead] = []
    for device in devices:
        profile = await session.get(EdgeStationProfile, device.id)
        config = await session.scalar(
            select(EdgeConfigBundle)
            .where(EdgeConfigBundle.device_id == device.id)
            .order_by(EdgeConfigBundle.revision.desc())
            .limit(1)
        )
        update = await session.scalar(
            select(EdgeUpdateDeployment)
            .where(EdgeUpdateDeployment.device_id == device.id)
            .order_by(EdgeUpdateDeployment.created_at.desc())
            .limit(1)
        )
        fleet.append(
            EdgeFleetDeviceRead(
                device=device,
                profile=profile,
                config=config,
                update=update,
            )
        )
    return fleet


@router.post(
    "/edge-devices/{device_id}/config-revisions",
    response_model=EdgeConfigBundleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_config_revision(
    device_id: str,
    payload: EdgeConfigBundleCreate,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: AdminDependency,
) -> EdgeConfigBundle:
    await _tenant_device(session, actor.organization_id, device_id)
    current_revision = await session.scalar(
        select(func.max(EdgeConfigBundle.revision)).where(EdgeConfigBundle.device_id == device_id)
    )
    digest, signature = _signed_configuration(settings, payload.configuration)
    bundle = EdgeConfigBundle(
        id=new_id(),
        organization_id=actor.organization_id,
        device_id=device_id,
        revision=(current_revision or 0) + 1,
        configuration=payload.configuration,
        content_sha256=digest,
        signature=signature,
        created_by=actor.subject,
    )
    session.add(bundle)
    await session.commit()
    await session.refresh(bundle)
    return bundle


@router.get("/agent/fleet/config", response_model=EdgeConfigBundleRead)
async def get_station_config(
    response: Response,
    session: SessionDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> EdgeConfigBundle:
    device_id, organization_id = _actual_device(principal)
    bundle = await session.scalar(
        select(EdgeConfigBundle)
        .where(
            EdgeConfigBundle.device_id == device_id,
            EdgeConfigBundle.organization_id == organization_id,
        )
        .order_by(EdgeConfigBundle.revision.desc())
        .limit(1)
    )
    if bundle is None:
        raise HTTPException(status_code=404, detail="No configuration revision is assigned")
    response.headers["ETag"] = f'"{bundle.content_sha256}"'
    response.headers["X-Config-Signature"] = bundle.signature
    return bundle


@router.post(
    "/edge-devices/{device_id}/updates",
    response_model=EdgeUpdateRead,
    status_code=status.HTTP_201_CREATED,
)
async def request_update(
    device_id: str,
    payload: EdgeUpdateCreate,
    session: SessionDependency,
    actor: AdminDependency,
) -> EdgeUpdateDeployment:
    await _tenant_device(session, actor.organization_id, device_id)
    profile = await session.get(EdgeStationProfile, device_id)
    from_version = profile.worker_version if profile else "unknown"
    update = EdgeUpdateDeployment(
        id=new_id(),
        organization_id=actor.organization_id,
        device_id=device_id,
        from_version=from_version,
        target_version=payload.target_version,
        rollback_version=from_version,
        status=EdgeUpdateStatus.PENDING,
        requested_by=actor.subject,
    )
    session.add(update)
    await session.commit()
    await session.refresh(update)
    return update


@router.post("/agent/fleet/updates/{update_id}", response_model=EdgeUpdateRead)
async def report_update(
    update_id: str,
    payload: EdgeUpdateReport,
    session: SessionDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> EdgeUpdateDeployment:
    device_id, organization_id = _actual_device(principal)
    update = await session.scalar(
        select(EdgeUpdateDeployment).where(
            EdgeUpdateDeployment.id == update_id,
            EdgeUpdateDeployment.device_id == device_id,
            EdgeUpdateDeployment.organization_id == organization_id,
        )
    )
    if update is None:
        raise HTTPException(status_code=404, detail="Update deployment not found")
    allowed = {
        EdgeUpdateStatus.PENDING: {EdgeUpdateStatus.DOWNLOADING, EdgeUpdateStatus.FAILED},
        EdgeUpdateStatus.DOWNLOADING: {EdgeUpdateStatus.APPLYING, EdgeUpdateStatus.FAILED},
        EdgeUpdateStatus.APPLYING: {
            EdgeUpdateStatus.SUCCEEDED,
            EdgeUpdateStatus.FAILED,
            EdgeUpdateStatus.ROLLED_BACK,
        },
        EdgeUpdateStatus.FAILED: {EdgeUpdateStatus.ROLLED_BACK},
    }
    if payload.status not in allowed.get(update.status, set()):
        raise HTTPException(status_code=409, detail="Invalid update state transition")
    update.status = payload.status
    update.error = payload.error
    if payload.status in {
        EdgeUpdateStatus.SUCCEEDED,
        EdgeUpdateStatus.FAILED,
        EdgeUpdateStatus.ROLLED_BACK,
    }:
        update.completed_at = utc_now()
    await session.commit()
    await session.refresh(update)
    return update


@router.post(
    "/edge-devices/{device_id}/fleet/demo-profile",
    response_model=EdgeStationProfileRead,
)
async def create_demo_profile(
    device_id: str,
    session: SessionDependency,
    actor: AdminDependency,
) -> EdgeStationProfile:
    device = await _tenant_device(session, actor.organization_id, device_id)
    return await _upsert_profile(
        session,
        device,
        EdgeStationProfileReport(
            hostname="local-edge-preview",
            os_name="Windows",
            architecture="x86_64",
            cpu_count=8,
            memory_mb=16384,
            accelerator=None,
            storage_available_mb=65536,
            worker_version="0.1.0",
            health_status=EdgeHealthStatus.HEALTHY,
            offline_queue_depth=0,
            last_sync_at=utc_now(),
            details={"simulated": True},
        ),
    )
