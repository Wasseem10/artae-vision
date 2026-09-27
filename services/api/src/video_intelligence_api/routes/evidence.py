"""Durable clip upload, provider work leasing, and timecoded evidence search."""

from __future__ import annotations

import errno
import hashlib
import hmac
import re
import shutil
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from typing import Annotated
from uuid import uuid4

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select, update

from video_intelligence_api.auth import ActorDependency, AdminDependency, EditorDependency
from video_intelligence_api.config import ApiSettings
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.media_access import (
    evidence_signature_is_valid,
    signed_evidence_url,
)
from video_intelligence_api.models import (
    Alert,
    AlertStatus,
    Camera,
    Event,
    EvidenceAsset,
    EvidenceReviewSample,
    EvidenceSearch,
    EvidenceSearchStatus,
    EvidenceStatus,
    ReplayEvaluation,
    VerificationCase,
    utc_now,
)
from video_intelligence_api.schemas import (
    EvidenceIndexAssignment,
    EvidenceIndexResult,
    EvidenceLegalHoldUpdate,
    EvidenceRead,
    EvidenceRetentionResult,
    EvidenceRetentionStatus,
    EvidenceSearchAssignment,
    EvidenceSearchCreate,
    EvidenceSearchHit,
    EvidenceSearchRead,
    EvidenceSearchResult,
    EvidenceWorkerClaim,
)
from video_intelligence_api.security import (
    EdgePrincipal,
    ensure_edge_organization,
    require_agent_key,
    require_edge_device,
)
from video_intelligence_api.tenancy import tenant_camera

router = APIRouter(tags=["searchable evidence"])
_TOKENS = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "in",
    "near",
    "of",
    "on",
    "the",
    "to",
    "with",
}


def _storage_failure(exc: OSError) -> HTTPException:
    exhausted = {errno.ENOSPC, getattr(errno, "EDQUOT", -1)}
    if exc.errno in exhausted:
        return HTTPException(status_code=507, detail="Evidence storage is full")
    return HTTPException(status_code=503, detail="Evidence storage is unavailable")


def _check_upload_capacity(directory: Path, settings: ApiSettings, next_bytes: int) -> None:
    """Reject a chunk before writing it when the local evidence volume is full.

    The directory includes concurrent .part files. This is a visible local
    capacity gate, while the filesystem remains the final authority for races
    between API processes.
    """
    try:
        maximum = settings.evidence_storage_max_bytes
        if maximum is not None:
            used = 0
            for path in directory.iterdir():
                try:
                    if path.is_file():
                        used += path.stat().st_size
                except FileNotFoundError:
                    continue
            if used + next_bytes > maximum:
                raise HTTPException(status_code=507, detail="Evidence storage capacity exceeded")
        if shutil.disk_usage(directory).free - next_bytes < settings.evidence_min_free_bytes:
            raise HTTPException(
                status_code=507, detail="Evidence storage free-space reserve reached"
            )
    except OSError as exc:
        raise _storage_failure(exc) from exc


async def _incoming_digest(request: Request, maximum_bytes: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    size_bytes = 0
    async for chunk in request.stream():
        size_bytes += len(chunk)
        if size_bytes > maximum_bytes:
            raise HTTPException(status_code=413, detail="Evidence clip exceeds the size limit")
        digest.update(chunk)
    if size_bytes == 0:
        raise HTTPException(status_code=400, detail="Evidence clip is empty")
    return size_bytes, digest.hexdigest()


def _stored_clip_matches(asset: EvidenceAsset, settings: ApiSettings) -> bool:
    if asset.storage_uri is None or asset.sha256 is None or asset.size_bytes is None:
        return False
    root = settings.evidence_directory.expanduser().resolve()
    path = Path(asset.storage_uri).expanduser().resolve()
    if not path.is_relative_to(root) or path.name != f"{asset.id}.mp4" or not path.is_file():
        return False
    if path.stat().st_size != asset.size_bytes:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return hmac.compare_digest(digest.hexdigest(), asset.sha256)


def evidence_response(
    asset: EvidenceAsset,
    organization_id: str | None = None,
    settings: ApiSettings | None = None,
) -> EvidenceRead:
    body = EvidenceRead.model_validate(asset)
    if (
        asset.storage_uri
        and asset.status != EvidenceStatus.EXPIRED
        and organization_id
        and settings
    ):
        body.content_url = signed_evidence_url(asset.id, organization_id, settings)
    return body


async def search_response(
    search: EvidenceSearch, settings: ApiSettings, session: SessionDependency
) -> EvidenceSearchRead:
    ids = [str(item.get("evidence_id")) for item in search.results if item.get("evidence_id")]
    available = set(
        (
            await session.scalars(
                select(EvidenceAsset.id)
                .join(Event, Event.id == EvidenceAsset.event_id)
                .join(Camera, Camera.id == Event.camera_id)
                .where(
                    EvidenceAsset.id.in_(ids),
                    EvidenceAsset.storage_uri.is_not(None),
                    EvidenceAsset.status != EvidenceStatus.EXPIRED,
                    Camera.organization_id == search.organization_id,
                )
            )
        ).all()
    ) if ids else set()
    results: list[EvidenceSearchHit] = []
    for item in search.results:
        hit = EvidenceSearchHit.model_validate(item)
        if hit.evidence_id not in available:
            continue
        signed_url = signed_evidence_url(hit.evidence_id, search.organization_id, settings)
        if signed_url:
            hit.content_url = signed_url
        results.append(hit)
    return EvidenceSearchRead(
        id=search.id,
        organization_id=search.organization_id,
        query=search.query,
        camera_id=search.camera_id,
        limit=search.limit,
        provider=search.provider,
        status=search.status,
        results=results,
        latency_ms=search.latency_ms,
        last_error=search.last_error,
        created_at=search.created_at,
        updated_at=search.updated_at,
    )


async def local_results(
    session: SessionDependency,
    query: str,
    camera_id: str | None,
    limit: int,
    organization_id: str,
) -> list[dict[str, object]]:
    statement = (
        select(EvidenceAsset, Event, Camera)
        .join(Event, Event.id == EvidenceAsset.event_id)
        .join(Camera, Camera.id == Event.camera_id)
        .where(
            EvidenceAsset.storage_uri.is_not(None),
            EvidenceAsset.status != EvidenceStatus.EXPIRED,
            Camera.organization_id == organization_id,
        )
        .order_by(Event.occurred_at.desc())
    )
    if camera_id:
        statement = statement.where(Event.camera_id == camera_id)
    rows = (await session.execute(statement)).all()
    query_tokens = {token for token in _TOKENS.findall(query.lower()) if token not in _STOP_WORDS}
    matches: list[tuple[float, float, EvidenceSearchHit]] = []
    for asset, event, camera in rows:
        haystack = " ".join(
            [camera.name, event.object_class, event.zone_name, event.event_type.replace("_", " ")]
        ).lower()
        matched = sum(token in haystack for token in query_tokens)
        if query_tokens and matched == 0:
            continue
        coverage = matched / len(query_tokens) if query_tokens else 0.25
        similarity = min(0.99, 0.35 + 0.64 * coverage)
        hit = EvidenceSearchHit(
            evidence_id=asset.id,
            event_id=event.id,
            camera_id=camera.id,
            camera_name=camera.name,
            time_start=0,
            time_end=max(asset.duration_seconds or event.dwell_seconds, 0.1),
            similarity=similarity,
            summary=f"{event.object_class.title()} in {event.zone_name} at {camera.name}",
            occurred_at=event.occurred_at,
            content_url=f"/api/v1/evidence/{asset.id}/content",
        )
        matches.append((similarity, event.confidence, hit))
    matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [hit.model_dump(mode="json") for _, _, hit in matches[:limit]]


@router.get("/evidence", response_model=list[EvidenceRead])
async def list_evidence(
    session: SessionDependency,
    settings: SettingsDependency,
    actor: ActorDependency,
    camera_id: Annotated[str | None, Query(max_length=36)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[EvidenceRead]:
    statement = (
        select(EvidenceAsset)
        .join(Event, Event.id == EvidenceAsset.event_id)
        .join(Camera, Camera.id == Event.camera_id)
        .where(Camera.organization_id == actor.organization_id)
        .order_by(EvidenceAsset.created_at.desc())
        .limit(limit)
    )
    if camera_id:
        statement = statement.where(Event.camera_id == camera_id)
    assets = (await session.scalars(statement)).all()
    return [evidence_response(asset, actor.organization_id, settings) for asset in assets]


async def _tenant_asset(
    session: SessionDependency, organization_id: str, evidence_id: str, *, lock: bool = False
) -> EvidenceAsset | None:
    statement = (
        select(EvidenceAsset)
        .join(Event, Event.id == EvidenceAsset.event_id)
        .join(Camera, Camera.id == Event.camera_id)
        .where(EvidenceAsset.id == evidence_id, Camera.organization_id == organization_id)
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(statement)


@router.post("/evidence/{evidence_id}/review", response_model=EvidenceRead)
async def mark_evidence_reviewed(
    evidence_id: str,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: EditorDependency,
) -> EvidenceRead:
    tenant_events = select(Event.id).join(Camera).where(
        Camera.organization_id == actor.organization_id
    )
    reviewed = await session.scalar(
        update(EvidenceAsset)
        .where(
            EvidenceAsset.id == evidence_id,
            EvidenceAsset.event_id.in_(tenant_events),
            EvidenceAsset.status != EvidenceStatus.EXPIRED,
            EvidenceAsset.storage_uri.is_not(None),
            EvidenceAsset.reviewed_at.is_(None),
        )
        .values(reviewed_at=utc_now(), reviewed_by=actor.subject)
        .returning(EvidenceAsset.id)
    )
    if reviewed is not None:
        await session.commit()
    asset = await _tenant_asset(session, actor.organization_id, evidence_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if asset.status == EvidenceStatus.EXPIRED or asset.storage_uri is None:
        raise HTTPException(status_code=409, detail="Evidence clip is not available for review")
    return evidence_response(asset, actor.organization_id, settings)


@router.put("/evidence/{evidence_id}/legal-hold", response_model=EvidenceRead)
async def update_evidence_legal_hold(
    evidence_id: str,
    payload: EvidenceLegalHoldUpdate,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: AdminDependency,
) -> EvidenceRead:
    tenant_events = select(Event.id).join(Camera).where(
        Camera.organization_id == actor.organization_id
    )
    held = await session.scalar(
        update(EvidenceAsset)
        .where(
            EvidenceAsset.id == evidence_id,
            EvidenceAsset.event_id.in_(tenant_events),
            EvidenceAsset.status != EvidenceStatus.EXPIRED,
        )
        .values(legal_hold=payload.enabled)
        .returning(EvidenceAsset.id)
    )
    if held is None:
        asset = await _tenant_asset(session, actor.organization_id, evidence_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Evidence not found")
        raise HTTPException(status_code=409, detail="Expired evidence cannot be placed on hold")
    await session.commit()
    asset = await _tenant_asset(session, actor.organization_id, evidence_id)
    assert asset is not None
    return evidence_response(asset, actor.organization_id, settings)


@router.get("/evidence/retention/status", response_model=EvidenceRetentionStatus)
async def evidence_retention_status(
    session: SessionDependency,
    settings: SettingsDependency,
    actor: AdminDependency,
) -> EvidenceRetentionStatus:
    awaiting_review = int(
        await session.scalar(
            select(func.count())
            .select_from(EvidenceAsset)
            .join(Event, Event.id == EvidenceAsset.event_id)
            .join(Camera, Camera.id == Event.camera_id)
            .where(
                Camera.organization_id == actor.organization_id,
                EvidenceAsset.storage_uri.is_not(None),
                EvidenceAsset.status != EvidenceStatus.EXPIRED,
                EvidenceAsset.reviewed_at.is_(None),
            )
        )
        or 0
    )
    tenant_evidence_bytes = int(
        await session.scalar(
            select(func.coalesce(func.sum(EvidenceAsset.size_bytes), 0))
            .select_from(EvidenceAsset)
            .join(Event, Event.id == EvidenceAsset.event_id)
            .join(Camera, Camera.id == Event.camera_id)
            .where(
                Camera.organization_id == actor.organization_id,
                EvidenceAsset.storage_uri.is_not(None),
            )
        )
        or 0
    )
    return EvidenceRetentionStatus(
        policy_approved=settings.retention_policy_configured,
        retention_hours=settings.evidence_retention_hours,
        capacity_limit_configured=settings.evidence_storage_max_bytes is not None,
        free_space_reserve_configured=settings.evidence_min_free_bytes > 0,
        tenant_evidence_bytes=tenant_evidence_bytes,
        awaiting_review=awaiting_review,
    )


async def _retention_protected(session: SessionDependency, asset: EvidenceAsset) -> bool:
    """Keep footage while any live incident or downstream review still needs it."""
    if await session.scalar(
        select(Alert.id).where(
            Alert.event_id == asset.event_id, Alert.status != AlertStatus.RESOLVED
        )
    ):
        return True
    if await session.scalar(
        select(VerificationCase.id).where(VerificationCase.event_id == asset.event_id)
    ):
        return True
    if await session.scalar(
        select(EvidenceReviewSample.id).where(EvidenceReviewSample.event_id == asset.event_id)
    ):
        return True
    return bool(
        await session.scalar(
            select(ReplayEvaluation.id).where(ReplayEvaluation.source_uri == asset.storage_uri)
        )
    )


@router.post("/evidence/retention/run", response_model=EvidenceRetentionResult)
async def run_evidence_retention(
    session: SessionDependency,
    settings: SettingsDependency,
    actor: AdminDependency,
    dry_run: bool = True,
) -> EvidenceRetentionResult:
    if not settings.retention_policy_configured or settings.evidence_retention_hours is None:
        raise HTTPException(
            status_code=409, detail="Incident-evidence retention policy is not enabled"
        )
    now = utc_now()
    base = (
        select(EvidenceAsset)
        .join(Event, Event.id == EvidenceAsset.event_id)
        .join(Camera, Camera.id == Event.camera_id)
        .where(Camera.organization_id == actor.organization_id)
        .with_for_update(skip_locked=True)
        .limit(100)
    )
    pending = list(
        (
            await session.scalars(
                base.where(
                    EvidenceAsset.status == EvidenceStatus.EXPIRED,
                    EvidenceAsset.storage_uri.is_not(None),
                )
            )
        ).all()
    )
    candidates = list(
        (
            await session.scalars(
                base.where(
                    EvidenceAsset.status.in_(
                        [
                            EvidenceStatus.READY,
                            EvidenceStatus.UNAVAILABLE,
                            EvidenceStatus.FAILED,
                        ]
                    ),
                    EvidenceAsset.storage_uri.is_not(None),
                    EvidenceAsset.expires_at <= now,
                    EvidenceAsset.legal_hold.is_(False),
                    EvidenceAsset.reviewed_at.is_not(None),
                    EvidenceAsset.worker_id.is_(None),
                    EvidenceAsset.external_index_id.is_(None),
                    EvidenceAsset.external_video_id.is_(None),
                )
            )
        ).all()
    )
    eligible: list[EvidenceAsset] = []
    for asset in candidates:
        if not await _retention_protected(session, asset):
            eligible.append(asset)
    count = len(pending) + len(eligible)
    if dry_run:
        return EvidenceRetentionResult(
            dry_run=True, candidates=count, expired_assets=0, deleted_bytes=0, cleanup_errors=0
        )

    # Release the candidate read transaction before conditional writes. SQLite
    # ignores SELECT FOR UPDATE; each UPDATE below rechecks every protection in
    # the same write statement, so a concurrent hold cannot be bypassed.
    await session.commit()
    tombstoned: list[EvidenceAsset] = []
    for asset in eligible:
        marked = await session.scalar(
            update(EvidenceAsset)
            .where(
                EvidenceAsset.id == asset.id,
                EvidenceAsset.status.in_(
                    [EvidenceStatus.READY, EvidenceStatus.UNAVAILABLE, EvidenceStatus.FAILED]
                ),
                EvidenceAsset.storage_uri == asset.storage_uri,
                EvidenceAsset.expires_at <= now,
                EvidenceAsset.legal_hold.is_(False),
                EvidenceAsset.reviewed_at.is_not(None),
                EvidenceAsset.worker_id.is_(None),
                EvidenceAsset.external_index_id.is_(None),
                EvidenceAsset.external_video_id.is_(None),
                ~select(Alert.id)
                .where(
                    Alert.event_id == EvidenceAsset.event_id,
                    Alert.status != AlertStatus.RESOLVED,
                )
                .exists(),
                ~select(VerificationCase.id)
                .where(VerificationCase.event_id == EvidenceAsset.event_id)
                .exists(),
                ~select(EvidenceReviewSample.id)
                .where(EvidenceReviewSample.event_id == EvidenceAsset.event_id)
                .exists(),
                ~select(ReplayEvaluation.id)
                .where(ReplayEvaluation.source_uri == EvidenceAsset.storage_uri)
                .exists(),
            )
            .values(status=EvidenceStatus.EXPIRED)
            .returning(EvidenceAsset.id)
        )
        if marked is None:
            await session.rollback()
            continue
        await session.commit()
        await session.refresh(asset)
        tombstoned.append(asset)

    # The committed EXPIRED state is the durable tombstone. A crash between it
    # and unlink leaves the clip inaccessible and a later run resumes cleanup.
    root = settings.evidence_directory.expanduser().resolve()
    deleted_bytes = 0
    expired_assets = 0
    cleanup_errors = 0
    for asset in [*pending, *tombstoned]:
        if asset.storage_uri is None:
            continue
        path = Path(asset.storage_uri).expanduser().resolve()
        if not path.is_relative_to(root) or path.name != f"{asset.id}.mp4":
            asset.retention_error = "Evidence path is outside the managed storage boundary"
            cleanup_errors += 1
            await session.commit()
            continue
        try:
            existed = path.is_file()
            await anyio.to_thread.run_sync(lambda candidate=path: candidate.unlink(missing_ok=True))
        except OSError as exc:
            asset.retention_error = str(exc)[:1000]
            cleanup_errors += 1
            await session.commit()
            continue
        if existed:
            deleted_bytes += asset.size_bytes or 0
        asset.storage_uri = None
        asset.expired_at = utc_now()
        asset.retention_error = None
        expired_assets += 1
        await session.commit()
    return EvidenceRetentionResult(
        dry_run=False,
        candidates=count,
        expired_assets=expired_assets,
        deleted_bytes=deleted_bytes,
        cleanup_errors=cleanup_errors,
    )


@router.get("/evidence/searches/{search_id}", response_model=EvidenceSearchRead)
async def get_evidence_search(
    search_id: str,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: ActorDependency,
) -> EvidenceSearchRead:
    search = await session.scalar(
        select(EvidenceSearch).where(
            EvidenceSearch.id == search_id,
            EvidenceSearch.organization_id == actor.organization_id,
        )
    )
    if search is None:
        raise HTTPException(status_code=404, detail="Evidence search not found")
    return await search_response(search, settings, session)


@router.post(
    "/evidence/searches", response_model=EvidenceSearchRead, status_code=status.HTTP_201_CREATED
)
async def create_evidence_search(
    payload: EvidenceSearchCreate,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: EditorDependency,
) -> EvidenceSearchRead:
    if payload.camera_id and await tenant_camera(session, actor, payload.camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    ready_statement = (
        select(func.count())
        .select_from(EvidenceAsset)
        .join(Event, Event.id == EvidenceAsset.event_id)
        .join(Camera, Camera.id == Event.camera_id)
        .where(
            EvidenceAsset.status == EvidenceStatus.READY,
            Camera.organization_id == actor.organization_id,
        )
    )
    if payload.camera_id:
        ready_statement = ready_statement.where(Event.camera_id == payload.camera_id)
    ready_count = int(await session.scalar(ready_statement) or 0)
    if payload.provider == "artae_labs" and ready_count == 0:
        raise HTTPException(status_code=409, detail="No Artae-indexed evidence is ready yet")

    use_artae = payload.provider == "artae_labs" or (payload.provider == "auto" and ready_count > 0)
    started = perf_counter()
    search = EvidenceSearch(
        organization_id=actor.organization_id,
        query=payload.query,
        camera_id=payload.camera_id,
        limit=payload.limit,
        provider="artae_labs" if use_artae else "local_metadata",
        status=EvidenceSearchStatus.QUEUED if use_artae else EvidenceSearchStatus.COMPLETED,
        results=[],
    )
    if not use_artae:
        search.results = await local_results(
            session,
            payload.query,
            payload.camera_id,
            payload.limit,
            actor.organization_id,
        )
        search.latency_ms = round((perf_counter() - started) * 1000)
        if payload.provider == "auto":
            search.last_error = "Artae-indexed clips are not ready; showing local metadata matches."
    session.add(search)
    await session.commit()
    await session.refresh(search)
    return await search_response(search, settings, session)


@router.get("/evidence/{evidence_id}/content")
async def get_evidence_content(
    evidence_id: str,
    session: SessionDependency,
    settings: SettingsDependency,
    organization_id: Annotated[str | None, Query(max_length=36)] = None,
    expires: Annotated[int | None, Query(ge=0)] = None,
    signature: Annotated[str | None, Query(min_length=64, max_length=64)] = None,
    x_agent_key: Annotated[str | None, Header()] = None,
) -> FileResponse:
    agent_authorized = x_agent_key is not None and hmac.compare_digest(
        x_agent_key, settings.agent_key.get_secret_value()
    )
    if not agent_authorized and (
        organization_id is None
        or expires is None
        or signature is None
        or not evidence_signature_is_valid(
            evidence_id, organization_id, expires, signature, settings
        )
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired evidence URL")
    statement = (
        select(EvidenceAsset)
        .join(Event, Event.id == EvidenceAsset.event_id)
        .join(Camera, Camera.id == Event.camera_id)
        .where(EvidenceAsset.id == evidence_id)
    )
    if not agent_authorized:
        statement = statement.where(Camera.organization_id == organization_id)
    asset = await session.scalar(statement)
    if asset is None or asset.storage_uri is None or asset.status == EvidenceStatus.EXPIRED:
        raise HTTPException(status_code=404, detail="Evidence content is not available")
    root = settings.evidence_directory.expanduser().resolve()
    path = Path(asset.storage_uri).expanduser().resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Evidence content is missing")
    return FileResponse(
        path, media_type=asset.media_type or "video/mp4", filename=f"{asset.id}.mp4"
    )


@router.post("/evidence/{evidence_id}/retry", response_model=EvidenceRead)
async def retry_evidence(
    evidence_id: str,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: EditorDependency,
) -> EvidenceRead:
    asset = await session.scalar(
        select(EvidenceAsset)
        .join(Event, Event.id == EvidenceAsset.event_id)
        .join(Camera, Camera.id == Event.camera_id)
        .where(
            EvidenceAsset.id == evidence_id,
            Camera.organization_id == actor.organization_id,
        )
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if asset.status == EvidenceStatus.EXPIRED:
        raise HTTPException(status_code=409, detail="Expired evidence cannot be indexed")
    if asset.storage_uri is None:
        raise HTTPException(status_code=409, detail="Upload the clip before retrying indexing")
    asset.status = EvidenceStatus.QUEUED
    asset.worker_id = None
    asset.lease_expires_at = None
    asset.last_error = None
    await session.commit()
    await session.refresh(asset)
    return evidence_response(asset, actor.organization_id, settings)


@router.put(
    "/agent/events/{source_event_id}/clip",
    response_model=EvidenceRead,
)
async def upload_event_clip(
    source_event_id: str,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
    duration_seconds: Annotated[
        float | None, Header(alias="X-Evidence-Duration-Seconds", ge=0)
    ] = None,
) -> EvidenceRead:
    event = await session.scalar(select(Event).where(Event.source_event_id == source_event_id))
    if event is None:
        raise HTTPException(status_code=404, detail="Event is not available yet")
    camera = await session.get(Camera, event.camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Event camera is unavailable")
    ensure_edge_organization(principal, camera.organization_id)
    media_type = request.headers.get("content-type", "video/mp4").split(";", maxsplit=1)[0]
    if not media_type.startswith("video/"):
        raise HTTPException(status_code=415, detail="Evidence must use a video media type")
    existing = await session.scalar(
        select(EvidenceAsset).where(EvidenceAsset.event_id == event.id)
    )
    if existing is None:
        raise HTTPException(status_code=409, detail="Evidence record is missing")
    if existing.storage_uri is not None or existing.status == EvidenceStatus.EXPIRED:
        size_bytes, checksum = await _incoming_digest(request, settings.evidence_max_bytes)
        asset = await session.scalar(
            select(EvidenceAsset)
            .where(EvidenceAsset.event_id == event.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if asset is None:
            raise HTTPException(status_code=409, detail="Evidence record is missing")
        if asset.sha256 != checksum or asset.size_bytes != size_bytes:
            raise HTTPException(
                status_code=409, detail="A different clip is already stored for this event"
            )
        if asset.status != EvidenceStatus.EXPIRED:
            try:
                available = await anyio.to_thread.run_sync(
                    lambda: _stored_clip_matches(asset, settings)
                )
            except OSError as exc:
                raise _storage_failure(exc) from exc
            if not available:
                raise HTTPException(status_code=503, detail="Stored evidence clip is unavailable")
        return evidence_response(asset, camera.organization_id, settings)
    directory = settings.evidence_directory.expanduser().resolve()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _storage_failure(exc) from exc
    # A request-private file prevents overlapping retries from sharing a .part path.
    partial_path = directory / f"upload-{uuid4().hex}.part"
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        async with await anyio.open_file(partial_path, "wb") as output:
            async for chunk in request.stream():
                size_bytes += len(chunk)
                if size_bytes > settings.evidence_max_bytes:
                    raise HTTPException(
                        status_code=413, detail="Evidence clip exceeds the size limit"
                    )
                _check_upload_capacity(directory, settings, len(chunk))
                digest.update(chunk)
                await output.write(chunk)
        if size_bytes == 0:
            raise HTTPException(status_code=400, detail="Evidence clip is empty")
        checksum = digest.hexdigest()
        # Decide under the asset row lock after receiving the body. A retry of the
        # same bytes must not replace evidence or send an indexed asset through
        # the provider again. populate_existing avoids a stale identity-map row.
        asset = await session.scalar(
            select(EvidenceAsset)
            .where(EvidenceAsset.event_id == event.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if asset is None:
            raise HTTPException(status_code=409, detail="Evidence record is missing")
        if asset.status == EvidenceStatus.EXPIRED:
            if asset.sha256 != checksum or asset.size_bytes != size_bytes:
                raise HTTPException(
                    status_code=409,
                    detail="A different clip is already stored for this event",
                )
            return evidence_response(asset, camera.organization_id, settings)
        if asset.storage_uri is not None:
            if asset.sha256 != checksum or asset.size_bytes != size_bytes:
                raise HTTPException(
                    status_code=409,
                    detail="A different clip is already stored for this event",
                )
            if not await anyio.to_thread.run_sync(lambda: _stored_clip_matches(asset, settings)):
                raise HTTPException(status_code=503, detail="Stored evidence clip is unavailable")
            return evidence_response(asset, camera.organization_id, settings)

        final_path = directory / f"{asset.id}.mp4"
        await anyio.to_thread.run_sync(partial_path.replace, final_path)
        asset.storage_uri = str(final_path)
        asset.media_type = media_type
        asset.size_bytes = size_bytes
        asset.sha256 = checksum
        asset.duration_seconds = duration_seconds
        if settings.evidence_retention_hours is not None:
            asset.expires_at = utc_now() + timedelta(hours=settings.evidence_retention_hours)
        asset.status = EvidenceStatus.QUEUED
        asset.worker_id = None
        asset.lease_expires_at = None
        asset.last_error = None
        await session.commit()
        await session.refresh(asset)
        return evidence_response(asset, camera.organization_id, settings)
    except OSError as exc:
        raise _storage_failure(exc) from exc
    finally:
        partial_path.unlink(missing_ok=True)


@router.post(
    "/agent/evidence/index-assignments/claim",
    response_model=EvidenceIndexAssignment | None,
    dependencies=[Depends(require_agent_key)],
)
async def claim_evidence_index(
    payload: EvidenceWorkerClaim,
    session: SessionDependency,
    settings: SettingsDependency,
) -> EvidenceIndexAssignment | Response:
    now = utc_now()
    statement = (
        select(EvidenceAsset, Event, Camera)
        .join(Event, Event.id == EvidenceAsset.event_id)
        .join(Camera, Camera.id == Event.camera_id)
        .where(
            EvidenceAsset.storage_uri.is_not(None),
            or_(
                EvidenceAsset.status == EvidenceStatus.QUEUED,
                (
                    (EvidenceAsset.status == EvidenceStatus.INDEXING)
                    & (EvidenceAsset.lease_expires_at < now)
                ),
            ),
        )
        .order_by(EvidenceAsset.updated_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    row = (await session.execute(statement)).first()
    if row is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    asset, event, camera = row
    asset.status = EvidenceStatus.INDEXING
    asset.worker_id = payload.worker_id
    asset.lease_expires_at = now + timedelta(seconds=settings.evidence_lease_seconds)
    asset.retry_count += 1
    await session.commit()
    return EvidenceIndexAssignment(
        asset_id=asset.id,
        event_id=event.id,
        title=f"{camera.name} - {event.object_class} in {event.zone_name}",
        duration_seconds=asset.duration_seconds,
    )


@router.post(
    "/agent/evidence/{evidence_id}/index-result",
    response_model=EvidenceRead,
    dependencies=[Depends(require_agent_key)],
)
async def complete_evidence_index(
    evidence_id: str,
    payload: EvidenceIndexResult,
    session: SessionDependency,
) -> EvidenceRead:
    asset = await session.get(EvidenceAsset, evidence_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if asset.worker_id != payload.worker_id:
        raise HTTPException(status_code=409, detail="Worker does not hold this evidence lease")
    asset.status = EvidenceStatus(payload.status)
    asset.external_index_id = payload.external_index_id
    asset.external_video_id = payload.external_video_id
    asset.last_error = payload.error
    asset.worker_id = None
    asset.lease_expires_at = None
    await session.commit()
    await session.refresh(asset)
    return evidence_response(asset)


@router.post(
    "/agent/evidence/search-assignments/claim",
    response_model=EvidenceSearchAssignment | None,
    dependencies=[Depends(require_agent_key)],
)
async def claim_evidence_search(
    payload: EvidenceWorkerClaim,
    session: SessionDependency,
    settings: SettingsDependency,
) -> EvidenceSearchAssignment | Response:
    now = utc_now()
    statement = (
        select(EvidenceSearch)
        .where(
            EvidenceSearch.provider == "artae_labs",
            or_(
                EvidenceSearch.status == EvidenceSearchStatus.QUEUED,
                (
                    (EvidenceSearch.status == EvidenceSearchStatus.SEARCHING)
                    & (EvidenceSearch.lease_expires_at < now)
                ),
            ),
        )
        .order_by(EvidenceSearch.updated_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    search = await session.scalar(statement)
    if search is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    search.status = EvidenceSearchStatus.SEARCHING
    search.worker_id = payload.worker_id
    search.lease_expires_at = now + timedelta(seconds=settings.evidence_lease_seconds)
    await session.commit()
    return EvidenceSearchAssignment(
        search_id=search.id,
        query=search.query,
        camera_id=search.camera_id,
        limit=search.limit,
    )


@router.post(
    "/agent/evidence/searches/{search_id}/result",
    response_model=EvidenceSearchRead,
    dependencies=[Depends(require_agent_key)],
)
async def complete_evidence_search(
    search_id: str,
    payload: EvidenceSearchResult,
    session: SessionDependency,
    settings: SettingsDependency,
) -> EvidenceSearchRead:
    search = await session.get(EvidenceSearch, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="Evidence search not found")
    if search.worker_id != payload.worker_id:
        raise HTTPException(status_code=409, detail="Worker does not hold this search lease")

    if payload.status == "unavailable":
        search.provider = "local_metadata"
        search.status = EvidenceSearchStatus.COMPLETED
        search.results = await local_results(
            session,
            search.query,
            search.camera_id,
            search.limit,
            search.organization_id,
        )
        search.last_error = payload.error or "Artae Labs is unavailable; showing local matches."
    elif payload.status == "failed":
        search.status = EvidenceSearchStatus.FAILED
        search.results = []
        search.last_error = payload.error
    else:
        video_ids = [hit.video_id for hit in payload.results]
        rows = (
            await session.execute(
                select(EvidenceAsset, Event, Camera)
                .join(Event, Event.id == EvidenceAsset.event_id)
                .join(Camera, Camera.id == Event.camera_id)
                .where(
                    EvidenceAsset.external_video_id.in_(video_ids),
                    Camera.organization_id == search.organization_id,
                )
            )
        ).all()
        mapped = {asset.external_video_id: (asset, event, camera) for asset, event, camera in rows}
        results: list[dict[str, object]] = []
        for provider_hit in payload.results:
            row = mapped.get(provider_hit.video_id)
            if row is None:
                continue
            asset, event, camera = row
            if search.camera_id and event.camera_id != search.camera_id:
                continue
            hit = EvidenceSearchHit(
                evidence_id=asset.id,
                event_id=event.id,
                camera_id=camera.id,
                camera_name=camera.name,
                time_start=provider_hit.time_start,
                time_end=max(provider_hit.time_end, provider_hit.time_start),
                similarity=provider_hit.similarity,
                summary=provider_hit.summary
                or f"{event.object_class.title()} in {event.zone_name} at {camera.name}",
                occurred_at=event.occurred_at,
                content_url=f"/api/v1/evidence/{asset.id}/content",
            )
            results.append(hit.model_dump(mode="json"))
        search.status = EvidenceSearchStatus.COMPLETED
        search.results = results[: search.limit]
        search.last_error = None
    search.latency_ms = payload.latency_ms
    search.worker_id = None
    search.lease_expires_at = None
    await session.commit()
    await session.refresh(search)
    return await search_response(search, settings, session)
