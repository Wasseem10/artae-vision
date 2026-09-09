"""Tenant-scoped historical recording catalog, archive upload, and retention."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select

from video_intelligence_api.auth import ActorDependency, AdminDependency
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.media_access import (
    recording_signature_is_valid,
    signed_recording_url,
)
from video_intelligence_api.models import (
    Camera,
    RecordingSegment,
    RecordingSegmentStatus,
    utc_now,
)
from video_intelligence_api.recording_storage import (
    RecordingStorageError,
    recording_storage,
)
from video_intelligence_api.schemas import (
    RecordingLegalHoldUpdate,
    RecordingRetentionResult,
    RecordingSegmentRead,
    RecordingSegmentReport,
)
from video_intelligence_api.security import (
    EdgePrincipal,
    ensure_edge_organization,
    require_edge_device,
)
from video_intelligence_api.tenancy import tenant_camera

router = APIRouter(tags=["historical recordings"])


def recording_response(
    segment: RecordingSegment,
    settings: SettingsDependency,
) -> RecordingSegmentRead:
    body = RecordingSegmentRead.model_validate(segment)
    if segment.status == RecordingSegmentStatus.READY and segment.storage_uri:
        body.content_url = signed_recording_url(segment.id, segment.organization_id, settings)
    return body


@router.get("/cameras/{camera_id}/recordings", response_model=list[RecordingSegmentRead])
async def list_camera_recordings(
    camera_id: str,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: ActorDependency,
    started_after: Annotated[datetime | None, Query()] = None,
    ended_before: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 250,
) -> list[RecordingSegmentRead]:
    if await tenant_camera(session, actor, camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    statement = select(RecordingSegment).where(
        RecordingSegment.organization_id == actor.organization_id,
        RecordingSegment.camera_id == camera_id,
    )
    if started_after is not None:
        statement = statement.where(RecordingSegment.ended_at >= started_after)
    if ended_before is not None:
        statement = statement.where(RecordingSegment.started_at <= ended_before)
    segments = (
        await session.scalars(statement.order_by(RecordingSegment.started_at.desc()).limit(limit))
    ).all()
    return [recording_response(segment, settings) for segment in segments]


async def enforce_camera_history_limit(
    *,
    session: SessionDependency,
    settings: SettingsDependency,
    organization_id: str,
    camera_id: str,
) -> RecordingRetentionResult:
    """Keep at most the configured amount of playable video per camera.

    Legal-hold recordings are deliberately excluded from the rolling limit. They
    remain available until an administrator releases the hold.
    """
    segments = list(
        (
            await session.scalars(
                select(RecordingSegment)
                .where(
                    RecordingSegment.organization_id == organization_id,
                    RecordingSegment.camera_id == camera_id,
                    RecordingSegment.status == RecordingSegmentStatus.READY,
                    RecordingSegment.legal_hold.is_(False),
                )
                .order_by(RecordingSegment.started_at.asc())
                .with_for_update()
            )
        ).all()
    )
    maximum_seconds = float(settings.recording_retention_hours * 3600)
    retained_seconds = sum(max(0.0, segment.duration_seconds) for segment in segments)
    if retained_seconds <= maximum_seconds or len(segments) <= 1:
        return RecordingRetentionResult(expired_segments=0, deleted_bytes=0)

    storage = recording_storage(settings)
    deleted_bytes = 0
    expired_segments = 0
    # Never delete the newest segment solely because its reported duration is
    # unusually large. The next completed segment will give the archive another
    # safe opportunity to rotate history.
    for segment in segments[:-1]:
        if retained_seconds <= maximum_seconds:
            break
        if segment.storage_uri:
            try:
                deleted = await anyio.to_thread.run_sync(
                    lambda uri=segment.storage_uri: storage.delete(uri)
                )
            except RecordingStorageError as exc:
                segment.last_error = str(exc)[:1000]
                # Preserve the newer timeline when the oldest object cannot be
                # removed. A later upload will retry this same boundary.
                break
            if deleted:
                deleted_bytes += segment.size_bytes or 0
        retained_seconds -= max(0.0, segment.duration_seconds)
        segment.storage_uri = None
        segment.status = RecordingSegmentStatus.EXPIRED
        segment.last_error = None
        expired_segments += 1
    await session.commit()
    return RecordingRetentionResult(
        expired_segments=expired_segments,
        deleted_bytes=deleted_bytes,
    )


@router.post(
    "/agent/cameras/{camera_id}/recordings",
    response_model=RecordingSegmentRead,
)
async def report_recording_segment(
    camera_id: str,
    payload: RecordingSegmentReport,
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> RecordingSegmentRead:
    camera = await session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera is unavailable")
    ensure_edge_organization(principal, camera.organization_id)
    existing = await session.get(RecordingSegment, payload.segment_id)
    if existing is not None:
        if (
            existing.organization_id != camera.organization_id
            or existing.camera_id != camera_id
            or existing.source_key != payload.source_key
        ):
            raise HTTPException(status_code=409, detail="Recording segment identity conflicts")
        return recording_response(existing, settings)
    duplicate = await session.scalar(
        select(RecordingSegment).where(
            RecordingSegment.camera_id == camera_id,
            RecordingSegment.source_key == payload.source_key,
        )
    )
    if duplicate is not None:
        return recording_response(duplicate, settings)
    segment = RecordingSegment(
        id=payload.segment_id,
        organization_id=camera.organization_id,
        camera_id=camera_id,
        edge_device_id=principal.device_id,
        source_key=payload.source_key,
        source_filename=Path(payload.source_filename).name,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_seconds=payload.duration_seconds,
        frame_count=payload.frame_count,
        fps=payload.fps,
        width=payload.width,
        height=payload.height,
        expires_at=payload.ended_at + timedelta(hours=settings.recording_retention_hours),
    )
    session.add(segment)
    await session.commit()
    await session.refresh(segment)
    return recording_response(segment, settings)


@router.put("/agent/recordings/{recording_id}/content", response_model=RecordingSegmentRead)
async def upload_recording_content(
    recording_id: str,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> RecordingSegmentRead:
    segment = await session.get(RecordingSegment, recording_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Recording segment is unavailable")
    ensure_edge_organization(principal, segment.organization_id)
    if (
        segment.edge_device_id is not None
        and principal.device_id is not None
        and segment.edge_device_id != principal.device_id
    ):
        raise HTTPException(status_code=409, detail="Edge device does not own this segment")
    media_type = request.headers.get("content-type", "video/mp4").split(";", maxsplit=1)[0]
    if not media_type.startswith("video/"):
        raise HTTPException(status_code=415, detail="Recording must use a video media type")
    # Cloud uploads must stage in the OS temporary directory: serverless app
    # bundles are read-only. Unique files also isolate concurrent retries.
    with NamedTemporaryFile(prefix="artae-recording-", suffix=".part", delete=False) as staged:
        partial_path = Path(staged.name)
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        async with await anyio.open_file(partial_path, "wb") as output:
            async for chunk in request.stream():
                size_bytes += len(chunk)
                if size_bytes > settings.recording_upload_max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="Recording segment exceeds the archive upload limit",
                    )
                digest.update(chunk)
                await output.write(chunk)
        if size_bytes == 0:
            raise HTTPException(status_code=400, detail="Recording segment is empty")
        if segment.status == RecordingSegmentStatus.READY:
            if segment.sha256 == digest.hexdigest() and segment.size_bytes == size_bytes:
                # A successful upload response can be lost in transit. Retrying
                # the same bytes must not upload a duplicate cloud object.
                return recording_response(segment, settings)
            raise HTTPException(status_code=409, detail="This recording already has different content")
        storage = recording_storage(settings)
        storage_uri = await anyio.to_thread.run_sync(
            lambda: storage.put(
                partial_path,
                organization_id=segment.organization_id,
                camera_id=segment.camera_id,
                recording_id=segment.id,
                media_type=media_type,
            )
        )
    except RecordingStorageError as exc:
        partial_path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise
    finally:
        partial_path.unlink(missing_ok=True)
    segment.storage_uri = storage_uri
    segment.media_type = media_type
    segment.size_bytes = size_bytes
    segment.sha256 = digest.hexdigest()
    segment.status = RecordingSegmentStatus.READY
    segment.last_error = None
    await session.commit()
    await enforce_camera_history_limit(
        session=session,
        settings=settings,
        organization_id=segment.organization_id,
        camera_id=segment.camera_id,
    )
    await session.refresh(segment)
    return recording_response(segment, settings)


@router.get("/recordings/{recording_id}/content", response_model=None)
async def get_recording_content(
    recording_id: str,
    session: SessionDependency,
    settings: SettingsDependency,
    organization_id: Annotated[str | None, Query(max_length=36)] = None,
    expires: Annotated[int | None, Query(ge=0)] = None,
    signature: Annotated[str | None, Query(min_length=64, max_length=64)] = None,
    x_agent_key: Annotated[str | None, Header()] = None,
) -> FileResponse | RedirectResponse:
    agent_authorized = x_agent_key is not None and hmac.compare_digest(
        x_agent_key, settings.agent_key.get_secret_value()
    )
    if not agent_authorized and (
        organization_id is None
        or expires is None
        or signature is None
        or not recording_signature_is_valid(
            recording_id, organization_id, expires, signature, settings
        )
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired recording URL")
    statement = select(RecordingSegment).where(RecordingSegment.id == recording_id)
    if not agent_authorized:
        statement = statement.where(RecordingSegment.organization_id == organization_id)
    segment = await session.scalar(statement)
    if (
        segment is None
        or segment.status != RecordingSegmentStatus.READY
        or segment.storage_uri is None
    ):
        raise HTTPException(status_code=404, detail="Recording content is not available")
    try:
        storage = recording_storage(settings)
        path = storage.local_path(segment.storage_uri)
        if path is not None:
            return FileResponse(path, media_type=segment.media_type or "video/mp4")
        download_url = await anyio.to_thread.run_sync(
            lambda: storage.download_url(segment.storage_uri or "")
        )
    except RecordingStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if download_url is None:
        raise HTTPException(status_code=404, detail="Recording content is missing")
    return RedirectResponse(download_url, status_code=307)


@router.put("/recordings/{recording_id}/legal-hold", response_model=RecordingSegmentRead)
async def update_recording_legal_hold(
    recording_id: str,
    payload: RecordingLegalHoldUpdate,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: AdminDependency,
) -> RecordingSegmentRead:
    segment = await session.scalar(
        select(RecordingSegment).where(
            RecordingSegment.id == recording_id,
            RecordingSegment.organization_id == actor.organization_id,
        )
    )
    if segment is None:
        raise HTTPException(status_code=404, detail="Recording segment not found")
    segment.legal_hold = payload.enabled
    await session.commit()
    await session.refresh(segment)
    return recording_response(segment, settings)


@router.post("/recordings/retention/run", response_model=RecordingRetentionResult)
async def run_recording_retention(
    session: SessionDependency,
    settings: SettingsDependency,
    actor: AdminDependency,
) -> RecordingRetentionResult:
    segments = (
        await session.scalars(
            select(RecordingSegment)
            .where(
                RecordingSegment.organization_id == actor.organization_id,
                RecordingSegment.status == RecordingSegmentStatus.READY,
                RecordingSegment.legal_hold.is_(False),
                RecordingSegment.expires_at <= utc_now(),
            )
            .with_for_update(skip_locked=True)
            .limit(500)
        )
    ).all()
    storage = recording_storage(settings)
    deleted_bytes = 0
    expired_segments = 0
    for segment in segments:
        if segment.storage_uri:
            try:
                deleted = await anyio.to_thread.run_sync(
                    lambda uri=segment.storage_uri: storage.delete(uri)
                )
            except RecordingStorageError as exc:
                segment.last_error = str(exc)[:1000]
                continue
            if deleted:
                deleted_bytes += segment.size_bytes or 0
        segment.storage_uri = None
        segment.status = RecordingSegmentStatus.EXPIRED
        segment.last_error = None
        expired_segments += 1
    await session.commit()
    return RecordingRetentionResult(
        expired_segments=expired_segments,
        deleted_bytes=deleted_bytes,
    )
