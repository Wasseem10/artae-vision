"""Durable clip upload, provider work leasing, and timecoded evidence search."""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.config import ApiSettings
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.media_access import (
    evidence_signature_is_valid,
    signed_evidence_url,
)
from video_intelligence_api.models import (
    Camera,
    Event,
    EvidenceAsset,
    EvidenceSearch,
    EvidenceSearchStatus,
    EvidenceStatus,
    utc_now,
)
from video_intelligence_api.schemas import (
    EvidenceIndexAssignment,
    EvidenceIndexResult,
    EvidenceRead,
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


def evidence_response(
    asset: EvidenceAsset,
    organization_id: str | None = None,
    settings: ApiSettings | None = None,
) -> EvidenceRead:
    body = EvidenceRead.model_validate(asset)
    if asset.storage_uri and organization_id and settings:
        body.content_url = signed_evidence_url(asset.id, organization_id, settings)
    return body


def search_response(search: EvidenceSearch, settings: ApiSettings) -> EvidenceSearchRead:
    results: list[EvidenceSearchHit] = []
    for item in search.results:
        hit = EvidenceSearchHit.model_validate(item)
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
    return search_response(search, settings)


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
    return search_response(search, settings)


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
    if asset is None or asset.storage_uri is None:
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
    asset = await session.scalar(select(EvidenceAsset).where(EvidenceAsset.event_id == event.id))
    if asset is None:
        raise HTTPException(status_code=409, detail="Evidence record is missing")

    media_type = request.headers.get("content-type", "video/mp4").split(";", maxsplit=1)[0]
    if not media_type.startswith("video/"):
        raise HTTPException(status_code=415, detail="Evidence must use a video media type")
    directory = settings.evidence_directory.expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    final_path = directory / f"{asset.id}.mp4"
    partial_path = directory / f"{asset.id}.part"
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
                digest.update(chunk)
                await output.write(chunk)
        if size_bytes == 0:
            raise HTTPException(status_code=400, detail="Evidence clip is empty")
        await anyio.to_thread.run_sync(partial_path.replace, final_path)
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise

    asset.storage_uri = str(final_path)
    asset.media_type = media_type
    asset.size_bytes = size_bytes
    asset.sha256 = digest.hexdigest()
    asset.duration_seconds = duration_seconds
    asset.status = EvidenceStatus.QUEUED
    asset.worker_id = None
    asset.lease_expires_at = None
    asset.last_error = None
    await session.commit()
    await session.refresh(asset)
    return evidence_response(asset, camera.organization_id, settings)


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
    return search_response(search, settings)
