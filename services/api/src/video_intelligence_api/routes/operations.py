from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.dependencies import SessionDependency
from video_intelligence_api.models import (
    Camera,
    CameraPlacement,
    EntitySighting,
    Event,
    SceneMemoryItem,
    Site,
    SiteArea,
    new_id,
)
from video_intelligence_api.scene_memory import NormalizedBoundingBox
from video_intelligence_api.schemas import (
    CameraPlacementRead,
    CameraPlacementUpsert,
    EntitySightingIngest,
    EntitySightingRead,
    InvestigationResult,
    InvestigationSearchCreate,
    InvestigationSearchRead,
    SiteAreaCreate,
    SiteAreaRead,
    SiteCreate,
    SiteRead,
)
from video_intelligence_api.security import (
    EdgePrincipal,
    ensure_edge_organization,
    require_edge_device,
)
from video_intelligence_api.tenancy import tenant_camera

router = APIRouter(tags=["multi-camera operations"])


async def _tenant_site(session: SessionDependency, actor: ActorDependency, site_id: str) -> Site:
    site = await session.scalar(
        select(Site).where(
            Site.id == site_id,
            Site.organization_id == actor.organization_id,
        )
    )
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


def _placement_read(
    placement: CameraPlacement, camera: Camera, area: SiteArea | None
) -> CameraPlacementRead:
    return CameraPlacementRead(
        id=placement.id,
        organization_id=placement.organization_id,
        site_id=placement.site_id,
        area_id=placement.area_id,
        area_name=area.name if area else None,
        camera_id=placement.camera_id,
        camera_name=camera.name,
        x=placement.x,
        y=placement.y,
        heading_degrees=placement.heading_degrees,
        created_at=placement.created_at,
        updated_at=placement.updated_at,
    )


def _sighting_read(
    sighting: EntitySighting, camera: Camera, area: SiteArea | None
) -> EntitySightingRead:
    return EntitySightingRead(
        id=sighting.id,
        organization_id=sighting.organization_id,
        camera_id=sighting.camera_id,
        camera_name=camera.name,
        area_id=sighting.area_id,
        area_name=area.name if area else None,
        event_id=sighting.event_id,
        entity_key=sighting.entity_key,
        label=sighting.label,
        bounding_box=sighting.bounding_box,
        confidence=sighting.confidence,
        attributes=sighting.attributes,
        occurred_at=sighting.occurred_at,
        created_at=sighting.created_at,
    )


async def _site_map_payload(
    session: SessionDependency, organization_id: str, site: Site
) -> dict[str, object]:
    areas = list(
        (
            await session.scalars(
                select(SiteArea).where(SiteArea.site_id == site.id).order_by(SiteArea.name)
            )
        ).all()
    )
    placement_rows = (
        await session.execute(
            select(CameraPlacement, Camera, SiteArea)
            .join(Camera, Camera.id == CameraPlacement.camera_id)
            .outerjoin(SiteArea, SiteArea.id == CameraPlacement.area_id)
            .where(
                CameraPlacement.site_id == site.id,
                CameraPlacement.organization_id == organization_id,
            )
            .order_by(Camera.name)
        )
    ).all()
    recent_sighting_rows = (
        await session.execute(
            select(EntitySighting, Camera, SiteArea)
            .join(Camera, Camera.id == EntitySighting.camera_id)
            .outerjoin(SiteArea, SiteArea.id == EntitySighting.area_id)
            .join(CameraPlacement, CameraPlacement.camera_id == Camera.id)
            .where(
                CameraPlacement.site_id == site.id,
                EntitySighting.organization_id == organization_id,
            )
            .order_by(EntitySighting.occurred_at.desc())
            .limit(50)
        )
    ).all()
    return {
        "site": SiteRead.model_validate(site),
        "areas": [SiteAreaRead.model_validate(area) for area in areas],
        "placements": [
            _placement_read(placement, camera, area) for placement, camera, area in placement_rows
        ],
        "recent_sightings": [
            _sighting_read(sighting, camera, area)
            for sighting, camera, area in recent_sighting_rows
        ],
    }


@router.post("/sites", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
async def create_site(
    payload: SiteCreate, session: SessionDependency, actor: EditorDependency
) -> Site:
    site = Site(
        id=new_id(),
        organization_id=actor.organization_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
    )
    session.add(site)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Site name already exists") from exc
    await session.refresh(site)
    return site


@router.get("/sites", response_model=list[SiteRead])
async def list_sites(session: SessionDependency, actor: ActorDependency) -> list[Site]:
    return list(
        (
            await session.scalars(
                select(Site)
                .where(Site.organization_id == actor.organization_id)
                .order_by(Site.name)
            )
        ).all()
    )


@router.post(
    "/sites/{site_id}/areas",
    response_model=SiteAreaRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_site_area(
    site_id: str,
    payload: SiteAreaCreate,
    session: SessionDependency,
    actor: EditorDependency,
) -> SiteArea:
    await _tenant_site(session, actor, site_id)
    area = SiteArea(
        id=new_id(),
        organization_id=actor.organization_id,
        site_id=site_id,
        **payload.model_dump(),
    )
    session.add(area)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Area name already exists") from exc
    await session.refresh(area)
    return area


@router.get("/sites/{site_id}/areas", response_model=list[SiteAreaRead])
async def list_site_areas(
    site_id: str, session: SessionDependency, actor: ActorDependency
) -> list[SiteArea]:
    await _tenant_site(session, actor, site_id)
    return list(
        (
            await session.scalars(
                select(SiteArea).where(SiteArea.site_id == site_id).order_by(SiteArea.name)
            )
        ).all()
    )


@router.put(
    "/sites/{site_id}/cameras/{camera_id}/placement",
    response_model=CameraPlacementRead,
)
async def upsert_camera_placement(
    site_id: str,
    camera_id: str,
    payload: CameraPlacementUpsert,
    session: SessionDependency,
    actor: EditorDependency,
) -> CameraPlacementRead:
    await _tenant_site(session, actor, site_id)
    camera = await tenant_camera(session, actor, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    area = None
    if payload.area_id:
        area = await session.scalar(
            select(SiteArea).where(
                SiteArea.id == payload.area_id,
                SiteArea.site_id == site_id,
                SiteArea.organization_id == actor.organization_id,
            )
        )
        if area is None:
            raise HTTPException(status_code=409, detail="Area does not belong to this site")
    placement = await session.scalar(
        select(CameraPlacement).where(CameraPlacement.camera_id == camera_id)
    )
    if placement is None:
        placement = CameraPlacement(
            id=new_id(),
            organization_id=actor.organization_id,
            site_id=site_id,
            camera_id=camera_id,
        )
        session.add(placement)
    placement.site_id = site_id
    placement.area_id = payload.area_id
    placement.x = payload.x
    placement.y = payload.y
    placement.heading_degrees = payload.heading_degrees
    await session.commit()
    await session.refresh(placement)
    return _placement_read(placement, camera, area)


@router.get("/sites/{site_id}/map")
async def get_site_map(
    site_id: str, session: SessionDependency, actor: ActorDependency
) -> dict[str, object]:
    site = await _tenant_site(session, actor, site_id)
    return await _site_map_payload(session, actor.organization_id, site)


@router.post("/cameras/{camera_id}/operations/demo", status_code=status.HTTP_201_CREATED)
async def setup_demo_site(
    camera_id: str, session: SessionDependency, actor: EditorDependency
) -> dict[str, object]:
    """Create a reversible, provider-free local layout for guided product evaluation."""
    camera = await tenant_camera(session, actor, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    site = await session.scalar(
        select(Site).where(
            Site.organization_id == actor.organization_id,
            Site.name == "Local operations demo",
        )
    )
    if site is None:
        site = Site(
            id=new_id(),
            organization_id=actor.organization_id,
            name="Local operations demo",
            description=(
                "Automatically created local map. Replace it with a real site layout later."
            ),
        )
        session.add(site)
        await session.flush()
    area_specs = (
        ("Entry", "access", 0.04, 0.12, 0.25, 0.76),
        ("Work area", "operations", 0.34, 0.12, 0.36, 0.76),
        ("Exit", "access", 0.75, 0.12, 0.21, 0.76),
    )
    areas: list[SiteArea] = []
    for name, area_type, x, y, width, height in area_specs:
        area = await session.scalar(
            select(SiteArea).where(SiteArea.site_id == site.id, SiteArea.name == name)
        )
        if area is None:
            area = SiteArea(
                id=new_id(),
                organization_id=actor.organization_id,
                site_id=site.id,
                name=name,
                area_type=area_type,
                x=x,
                y=y,
                width=width,
                height=height,
            )
            session.add(area)
        areas.append(area)
    await session.flush()
    work_area = next(area for area in areas if area.name == "Work area")
    placement = await session.scalar(
        select(CameraPlacement).where(CameraPlacement.camera_id == camera.id)
    )
    if placement is None:
        placement = CameraPlacement(
            id=new_id(),
            organization_id=actor.organization_id,
            camera_id=camera.id,
        )
        session.add(placement)
    placement.site_id = site.id
    placement.area_id = work_area.id
    placement.x = 0.52
    placement.y = 0.5
    placement.heading_degrees = 90
    await session.commit()
    await session.refresh(site)
    return await _site_map_payload(session, actor.organization_id, site)


@router.post(
    "/agent/entity-sightings",
    response_model=EntitySightingRead,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_entity_sighting(
    payload: EntitySightingIngest,
    session: SessionDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> EntitySightingRead:
    camera = await session.get(Camera, payload.camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    ensure_edge_organization(principal, camera.organization_id)
    try:
        box = NormalizedBoundingBox.model_validate(payload.bounding_box)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Bounding box is invalid") from exc
    if payload.event_id is not None:
        event = await session.get(Event, payload.event_id)
        if event is None or event.camera_id != camera.id:
            raise HTTPException(status_code=409, detail="Sighting event is unavailable")
    existing = await session.scalar(
        select(EntitySighting).where(
            EntitySighting.camera_id == camera.id,
            EntitySighting.entity_key == payload.entity_key,
            EntitySighting.occurred_at == payload.occurred_at,
        )
    )
    if existing is not None:
        area = await session.get(SiteArea, existing.area_id) if existing.area_id else None
        return _sighting_read(existing, camera, area)
    placement = await session.scalar(
        select(CameraPlacement).where(CameraPlacement.camera_id == camera.id)
    )
    sighting = EntitySighting(
        id=new_id(),
        organization_id=camera.organization_id,
        camera_id=camera.id,
        area_id=placement.area_id if placement else None,
        event_id=payload.event_id,
        entity_key=payload.entity_key.strip(),
        label=payload.label.strip(),
        bounding_box=box.model_dump(),
        confidence=payload.confidence,
        attributes=payload.attributes,
        occurred_at=payload.occurred_at,
    )
    session.add(sighting)
    await session.commit()
    await session.refresh(sighting)
    area = await session.get(SiteArea, sighting.area_id) if sighting.area_id else None
    return _sighting_read(sighting, camera, area)


@router.get("/entities/{entity_key}/journey", response_model=list[EntitySightingRead])
async def entity_journey(
    entity_key: str,
    session: SessionDependency,
    actor: ActorDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[EntitySightingRead]:
    rows = (
        await session.execute(
            select(EntitySighting, Camera, SiteArea)
            .join(Camera, Camera.id == EntitySighting.camera_id)
            .outerjoin(SiteArea, SiteArea.id == EntitySighting.area_id)
            .where(
                EntitySighting.organization_id == actor.organization_id,
                EntitySighting.entity_key == entity_key,
            )
            .order_by(EntitySighting.occurred_at)
            .limit(limit)
        )
    ).all()
    return [_sighting_read(sighting, camera, area) for sighting, camera, area in rows]


def _matches(query_tokens: list[str], *values: Any) -> bool:
    searchable = " ".join(
        value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)
        for value in values
        if value is not None
    ).casefold()
    return all(token in searchable for token in query_tokens)


@router.post("/investigations/search", response_model=InvestigationSearchRead)
async def search_investigations(
    payload: InvestigationSearchCreate,
    session: SessionDependency,
    actor: ActorDependency,
) -> InvestigationSearchRead:
    """Search events, learned scene state, and cross-camera sightings as one timeline."""
    camera_filter = set(payload.camera_ids)
    query_tokens = payload.query.casefold().split()
    event_rows = (
        await session.execute(
            select(Event, Camera)
            .join(Camera, Camera.id == Event.camera_id)
            .where(Camera.organization_id == actor.organization_id)
            .order_by(Event.occurred_at.desc())
            .limit(500)
        )
    ).all()
    scene_rows = (
        await session.execute(
            select(SceneMemoryItem, Camera)
            .join(Camera, Camera.id == SceneMemoryItem.camera_id)
            .where(SceneMemoryItem.organization_id == actor.organization_id)
            .order_by(SceneMemoryItem.last_seen_at.desc())
            .limit(500)
        )
    ).all()
    sighting_rows = (
        await session.execute(
            select(EntitySighting, Camera, SiteArea)
            .join(Camera, Camera.id == EntitySighting.camera_id)
            .outerjoin(SiteArea, SiteArea.id == EntitySighting.area_id)
            .where(EntitySighting.organization_id == actor.organization_id)
            .order_by(EntitySighting.occurred_at.desc())
            .limit(500)
        )
    ).all()
    results: list[InvestigationResult] = []
    for event, camera in event_rows:
        if camera_filter and event.camera_id not in camera_filter:
            continue
        if _matches(
            query_tokens,
            event.event_type,
            event.object_class,
            event.zone_name,
            event.details,
            event.raw_payload,
            camera.name,
        ):
            results.append(
                InvestigationResult(
                    kind="event",
                    id=event.id,
                    camera_id=event.camera_id,
                    occurred_at=event.occurred_at,
                    title=f"{event.object_class} · {event.event_type}",
                    summary=(
                        f"{camera.name} in {event.zone_name} · {event.confidence:.0%} confidence"
                    ),
                    event_id=event.id,
                    clip_uri=event.clip_uri,
                )
            )
    for item, camera in scene_rows:
        if camera_filter and item.camera_id not in camera_filter:
            continue
        if _matches(
            query_tokens,
            item.label,
            item.kind.value,
            item.description,
            item.current_state,
            item.attributes,
            item.relationships,
            camera.name,
        ):
            results.append(
                InvestigationResult(
                    kind="scene",
                    id=item.id,
                    camera_id=item.camera_id,
                    occurred_at=item.last_seen_at,
                    title=item.label,
                    summary=f"{camera.name} · {item.kind.value} is {item.current_state}",
                )
            )
    for sighting, camera, area in sighting_rows:
        if camera_filter and sighting.camera_id not in camera_filter:
            continue
        if _matches(
            query_tokens,
            sighting.entity_key,
            sighting.label,
            sighting.attributes,
            camera.name,
            area.name if area else None,
        ):
            location = area.name if area else camera.name
            results.append(
                InvestigationResult(
                    kind="entity",
                    id=sighting.id,
                    camera_id=sighting.camera_id,
                    occurred_at=sighting.occurred_at,
                    title=sighting.label,
                    summary=f"Seen at {location} · {sighting.confidence:.0%} confidence",
                    event_id=sighting.event_id,
                    entity_key=sighting.entity_key,
                )
            )
    results.sort(key=lambda result: result.occurred_at, reverse=True)
    return InvestigationSearchRead(query=payload.query, results=results[: payload.limit])
