from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.dependencies import SessionDependency
from video_intelligence_api.models import (
    Camera,
    Event,
    SceneChange,
    SceneItemKind,
    SceneMemoryItem,
    SceneMemorySource,
    SceneReviewStatus,
    new_id,
    utc_now,
)
from video_intelligence_api.scene_memory import (
    NormalizedBoundingBox,
    SceneObservationData,
    apply_scene_observations,
)
from video_intelligence_api.schemas import (
    SceneChangeRead,
    SceneMemoryBatchIngest,
    SceneMemoryItemRead,
    SceneMemoryReview,
)
from video_intelligence_api.security import (
    EdgePrincipal,
    ensure_edge_organization,
    require_edge_device,
)
from video_intelligence_api.tenancy import tenant_camera
from video_intelligence_api.visual_skills import registry_payload

router = APIRouter(tags=["visual skills and scene memory"])


@router.get("/visual-skills")
async def visual_skills(actor: ActorDependency) -> dict[str, object]:
    del actor
    return registry_payload()


@router.get("/cameras/{camera_id}/scene-memory", response_model=list[SceneMemoryItemRead])
async def list_scene_memory(
    camera_id: str,
    session: SessionDependency,
    actor: ActorDependency,
    include_rejected: bool = False,
) -> list[SceneMemoryItem]:
    if await tenant_camera(session, actor, camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    statement = (
        select(SceneMemoryItem)
        .where(
            SceneMemoryItem.camera_id == camera_id,
            SceneMemoryItem.organization_id == actor.organization_id,
        )
        .order_by(SceneMemoryItem.last_seen_at.desc())
    )
    if not include_rejected:
        statement = statement.where(SceneMemoryItem.review_status != SceneReviewStatus.REJECTED)
    return list((await session.scalars(statement)).all())


@router.get("/cameras/{camera_id}/scene-changes", response_model=list[SceneChangeRead])
async def list_scene_changes(
    camera_id: str,
    session: SessionDependency,
    actor: ActorDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[SceneChange]:
    if await tenant_camera(session, actor, camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return list(
        (
            await session.scalars(
                select(SceneChange)
                .where(
                    SceneChange.camera_id == camera_id,
                    SceneChange.organization_id == actor.organization_id,
                )
                .order_by(SceneChange.occurred_at.desc())
                .limit(limit)
            )
        ).all()
    )


@router.patch("/scene-memory/{item_id}", response_model=SceneMemoryItemRead)
async def review_scene_memory(
    item_id: str,
    payload: SceneMemoryReview,
    session: SessionDependency,
    actor: EditorDependency,
) -> SceneMemoryItem:
    item = await session.scalar(
        select(SceneMemoryItem).where(
            SceneMemoryItem.id == item_id,
            SceneMemoryItem.organization_id == actor.organization_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Scene item not found")
    previous_state = item.current_state
    if payload.label is not None:
        item.label = payload.label.strip()
    if payload.description is not None:
        item.description = payload.description.strip()
    if payload.current_state is not None:
        item.current_state = payload.current_state.strip()
    item.review_status = payload.review_status
    item.source = SceneMemorySource.OPERATOR
    item.reviewed_by = actor.subject
    item.reviewed_at = utc_now()
    if item.current_state != previous_state:
        session.add(
            SceneChange(
                id=new_id(),
                organization_id=actor.organization_id,
                camera_id=item.camera_id,
                item_id=item.id,
                previous_state=previous_state,
                new_state=item.current_state,
                confidence=1,
                details={"source": "operator_review"},
                occurred_at=item.reviewed_at,
            )
        )
    await session.commit()
    await session.refresh(item)
    return item


@router.post(
    "/agent/scene-memory",
    response_model=list[SceneMemoryItemRead],
)
async def ingest_scene_memory(
    payload: SceneMemoryBatchIngest,
    session: SessionDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> list[SceneMemoryItem]:
    camera = await session.get(Camera, payload.camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    ensure_edge_organization(principal, camera.organization_id)
    if payload.event_id is not None:
        event = await session.get(Event, payload.event_id)
        if event is None or event.camera_id != camera.id:
            raise HTTPException(status_code=409, detail="Scene-memory event is unavailable")
    items = await apply_scene_observations(
        session,
        organization_id=camera.organization_id,
        camera_id=camera.id,
        observations=payload.observations,
        occurred_at=payload.occurred_at,
        event_id=payload.event_id,
    )
    await session.commit()
    for item in items:
        await session.refresh(item)
    return items


@router.post(
    "/cameras/{camera_id}/scene-memory/demo-discovery",
    response_model=list[SceneMemoryItemRead],
    status_code=status.HTTP_201_CREATED,
)
async def demo_scene_discovery(
    camera_id: str,
    session: SessionDependency,
    actor: EditorDependency,
) -> list[SceneMemoryItem]:
    camera = await tenant_camera(session, actor, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    now = utc_now()
    observations = [
        SceneObservationData(
            stable_key="auto-primary-work-area",
            label="Primary work area",
            kind=SceneItemKind.REGION,
            bounding_box=NormalizedBoundingBox(x=0.08, y=0.18, width=0.72, height=0.72),
            description="Automatically proposed main activity region.",
            state="active",
            confidence=0.86,
            attributes={"simulated_discovery": True},
        ),
        SceneObservationData(
            stable_key="auto-control-display",
            label="Control display",
            kind=SceneItemKind.DISPLAY,
            bounding_box=NormalizedBoundingBox(x=0.68, y=0.12, width=0.2, height=0.18),
            description="Automatically proposed equipment display.",
            state="on",
            confidence=0.81,
            attributes={"simulated_discovery": True},
            relationships=[{"type": "inside", "target": "auto-primary-work-area"}],
        ),
    ]
    items = await apply_scene_observations(
        session,
        organization_id=actor.organization_id,
        camera_id=camera.id,
        observations=observations,
        occurred_at=now,
    )
    await session.commit()
    for item in items:
        await session.refresh(item)
    return items
