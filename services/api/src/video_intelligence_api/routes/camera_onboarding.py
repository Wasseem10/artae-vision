"""Credentialed ONVIF media-profile resolution and verified camera creation."""

from __future__ import annotations

import base64
import binascii
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.auth import ActorDependency, AdminDependency
from video_intelligence_api.camera_secrets import (
    CameraSecretError,
    decrypt_camera_credentials,
    encrypt_camera_credentials,
)
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.models import (
    AgentDesiredStatus,
    AgentObservedStatus,
    Camera,
    CameraAgent,
    CameraDiscoveryRun,
    CameraDiscoveryStatus,
    CameraOnboardingRun,
    CameraOnboardingStatus,
    CameraStatus,
    EdgeDevice,
    EdgeDeviceStatus,
    SourceType,
    new_id,
    utc_now,
)
from video_intelligence_api.schemas import (
    CameraOnboardingAssignment,
    CameraOnboardingCreate,
    CameraOnboardingRead,
    CameraOnboardingResult,
    OnvifMediaProfile,
    WorkerClaimRequest,
)
from video_intelligence_api.security import EdgePrincipal, require_edge_device
from video_intelligence_api.source_utils import split_source_credentials

router = APIRouter(tags=["camera onboarding"])


def _actual_device(principal: EdgePrincipal) -> tuple[str, str]:
    if principal.device_id is None or principal.organization_id is None:
        raise HTTPException(
            status_code=409,
            detail="Camera onboarding requires an enrolled edge-device token",
        )
    return principal.device_id, principal.organization_id


def _validated_service_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or parsed.hostname is None:
        raise HTTPException(status_code=422, detail="ONVIF endpoint must be HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise HTTPException(status_code=422, detail="ONVIF endpoint cannot contain credentials")
    return value.strip()


def _clean_profiles(profiles: list[OnvifMediaProfile]) -> list[dict[str, object]]:
    cleaned: list[dict[str, object]] = []
    for profile in profiles:
        source_uri, _, _ = split_source_credentials(profile.stream_uri)
        if urlsplit(source_uri).scheme.lower() not in {"rtsp", "rtsps"}:
            raise ValueError("ONVIF media profile returned a non-RTSP stream")
        body = profile.model_dump(mode="json")
        body["stream_uri"] = source_uri
        cleaned.append(body)
    return cleaned


@router.get("/camera-onboarding-runs", response_model=list[CameraOnboardingRead])
async def list_camera_onboarding_runs(
    session: SessionDependency,
    actor: ActorDependency,
) -> list[CameraOnboardingRun]:
    return list(
        (
            await session.scalars(
                select(CameraOnboardingRun)
                .where(CameraOnboardingRun.organization_id == actor.organization_id)
                .order_by(CameraOnboardingRun.created_at.desc())
                .limit(100)
            )
        ).all()
    )


@router.post(
    "/camera-onboarding-runs",
    response_model=CameraOnboardingRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_camera_onboarding_run(
    payload: CameraOnboardingCreate,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: AdminDependency,
) -> CameraOnboardingRun:
    endpoint_url = _validated_service_url(payload.endpoint_url)
    discovery = await session.scalar(
        select(CameraDiscoveryRun).where(
            CameraDiscoveryRun.id == payload.discovery_run_id,
            CameraDiscoveryRun.organization_id == actor.organization_id,
            CameraDiscoveryRun.status == CameraDiscoveryStatus.COMPLETED,
        )
    )
    if discovery is None:
        raise HTTPException(status_code=404, detail="Completed discovery run not found")
    discovered_urls = {
        str(xaddr)
        for device in discovery.devices
        for xaddr in device.get("xaddrs", [])
        if isinstance(xaddr, str)
    }
    if endpoint_url not in discovered_urls:
        raise HTTPException(
            status_code=409, detail="Endpoint was not returned by this discovery run"
        )
    existing_name = await session.scalar(
        select(Camera.id).where(
            Camera.organization_id == actor.organization_id,
            Camera.name == payload.camera_name.strip(),
        )
    )
    if existing_name is not None:
        raise HTTPException(status_code=409, detail="Camera name already exists")
    device = await session.scalar(
        select(EdgeDevice).where(
            EdgeDevice.id == discovery.edge_device_id,
            EdgeDevice.organization_id == actor.organization_id,
            EdgeDevice.status == EdgeDeviceStatus.ACTIVE,
        )
    )
    if device is None:
        raise HTTPException(status_code=409, detail="Discovery edge device is no longer active")
    try:
        encrypted = encrypt_camera_credentials(payload.username, payload.password, settings)
    except CameraSecretError as exc:
        raise HTTPException(
            status_code=503, detail="Camera credential encryption is unavailable"
        ) from exc
    run = CameraOnboardingRun(
        id=new_id(),
        organization_id=actor.organization_id,
        edge_device_id=device.id,
        discovery_run_id=discovery.id,
        camera_name=payload.camera_name.strip(),
        endpoint_url=endpoint_url,
        credential_encrypted=encrypted,
        verify_tls=payload.verify_tls,
        requested_by=actor.subject,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


@router.post(
    "/agent/camera-onboarding-runs/claim",
    response_model=CameraOnboardingAssignment | None,
)
async def claim_camera_onboarding_run(
    payload: WorkerClaimRequest,
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> CameraOnboardingAssignment | Response:
    device_id, organization_id = _actual_device(principal)
    now = utc_now()
    run = await session.scalar(
        select(CameraOnboardingRun)
        .where(
            CameraOnboardingRun.organization_id == organization_id,
            CameraOnboardingRun.edge_device_id == device_id,
            or_(
                CameraOnboardingRun.status == CameraOnboardingStatus.QUEUED,
                (
                    (CameraOnboardingRun.status == CameraOnboardingStatus.RUNNING)
                    & (CameraOnboardingRun.lease_expires_at < now)
                ),
            ),
        )
        .order_by(CameraOnboardingRun.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if run is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if run.credential_encrypted is None:
        run.status = CameraOnboardingStatus.FAILED
        run.last_error = "Camera credentials are unavailable"
        run.completed_at = now
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        username, password = decrypt_camera_credentials(run.credential_encrypted, settings)
    except CameraSecretError as exc:
        raise HTTPException(status_code=503, detail="Camera credentials are unavailable") from exc
    run.status = CameraOnboardingStatus.RUNNING
    run.worker_id = payload.worker_id
    run.lease_expires_at = now + timedelta(seconds=settings.camera_onboarding_lease_seconds)
    run.last_error = None
    await session.commit()
    return CameraOnboardingAssignment(
        worker_id=payload.worker_id,
        onboarding_id=run.id,
        endpoint_url=run.endpoint_url,
        username=username,
        password=password,
        verify_tls=run.verify_tls,
    )


@router.post(
    "/agent/camera-onboarding-runs/{onboarding_id}/result",
    response_model=CameraOnboardingRead,
)
async def report_camera_onboarding_result(
    onboarding_id: str,
    payload: CameraOnboardingResult,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> CameraOnboardingRun:
    device_id, organization_id = _actual_device(principal)
    run = await session.scalar(
        select(CameraOnboardingRun).where(
            CameraOnboardingRun.id == onboarding_id,
            CameraOnboardingRun.organization_id == organization_id,
            CameraOnboardingRun.edge_device_id == device_id,
        )
    )
    if (
        run is None
        or run.status != CameraOnboardingStatus.RUNNING
        or run.worker_id != payload.worker_id
    ):
        raise HTTPException(status_code=409, detail="Worker does not hold this onboarding lease")

    failure = payload.error
    preview: bytes | None = None
    clean_stream_uri: str | None = None
    clean_profiles: list[dict[str, object]] = []
    if failure is None:
        try:
            clean_profiles = _clean_profiles(payload.profiles)
            if not payload.selected_profile_token or not payload.stream_uri:
                raise ValueError("ONVIF onboarding did not select a media profile")
            if payload.selected_profile_token not in {
                str(profile["token"]) for profile in clean_profiles
            }:
                raise ValueError("Selected ONVIF profile was not returned by the camera")
            clean_stream_uri, _, _ = split_source_credentials(payload.stream_uri)
            if urlsplit(clean_stream_uri).scheme.lower() not in {"rtsp", "rtsps"}:
                raise ValueError("Selected ONVIF stream is not RTSP")
            if payload.preview_jpeg_base64 is None:
                raise ValueError("Camera stream could not be preview-verified")
            preview = base64.b64decode(payload.preview_jpeg_base64, validate=True)
            if (
                not preview.startswith(b"\xff\xd8")
                or not preview.endswith(b"\xff\xd9")
                or len(preview) > settings.preview_max_bytes
            ):
                raise ValueError("Camera preview is not a valid bounded JPEG")
        except (ValueError, binascii.Error) as exc:
            failure = str(exc)

    if failure is not None:
        run.status = CameraOnboardingStatus.FAILED
        run.last_error = failure[:1000]
        run.completed_at = utc_now()
        run.worker_id = None
        run.lease_expires_at = None
        await session.commit()
        await session.refresh(run)
        return run

    assert clean_stream_uri is not None and preview is not None
    camera = Camera(
        id=new_id(),
        organization_id=run.organization_id,
        edge_device_id=run.edge_device_id,
        name=run.camera_name,
        source_uri=clean_stream_uri,
        source_type=SourceType.RTSP,
        status=CameraStatus.ONLINE,
        credential_encrypted=run.credential_encrypted,
    )
    agent = CameraAgent(
        camera_id=camera.id,
        edge_device_id=run.edge_device_id,
        desired_status=AgentDesiredStatus.STOPPED,
        observed_status=AgentObservedStatus.STOPPED,
    )
    session.add_all([camera, agent])
    run.profiles = clean_profiles
    run.selected_profile_token = payload.selected_profile_token
    run.camera_id = camera.id
    run.status = CameraOnboardingStatus.COMPLETED
    run.last_error = None
    run.completed_at = utc_now()
    run.worker_id = None
    run.lease_expires_at = None
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        run = await session.get(CameraOnboardingRun, onboarding_id)
        assert run is not None
        run.status = CameraOnboardingStatus.FAILED
        run.last_error = "Camera name already exists"
        run.completed_at = utc_now()
        run.worker_id = None
        run.lease_expires_at = None
        await session.commit()
        await session.refresh(run)
        return run
    await request.app.state.preview_store.put(camera.id, camera.organization_id, preview)
    await session.refresh(run)
    return run
