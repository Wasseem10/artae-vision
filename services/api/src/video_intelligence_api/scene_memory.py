from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from video_intelligence_api.models import (
    CameraPlacement,
    EntitySighting,
    SceneChange,
    SceneItemKind,
    SceneMemoryItem,
    SceneMemorySource,
    SceneReviewStatus,
    new_id,
    utc_now,
)


class NormalizedBoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside_frame(self) -> NormalizedBoundingBox:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Bounding box must remain inside the normalized frame")
        return self


class SceneObservationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_key: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=160)
    kind: SceneItemKind = SceneItemKind.OTHER
    bounding_box: NormalizedBoundingBox
    description: str = Field(default="", max_length=1000)
    state: str = Field(default="observed", min_length=1, max_length=160)
    confidence: float = Field(ge=0, le=1)
    attributes: dict[str, object] = Field(default_factory=dict)
    relationships: list[dict[str, object]] = Field(default_factory=list, max_length=20)


async def apply_scene_observations(
    session: AsyncSession,
    *,
    organization_id: str,
    camera_id: str,
    observations: list[SceneObservationData],
    occurred_at: datetime,
    event_id: str | None = None,
) -> list[SceneMemoryItem]:
    """Upsert stable scene state and append a change only when state actually changes."""
    items: list[SceneMemoryItem] = []
    for observation in observations:
        item = await session.scalar(
            select(SceneMemoryItem).where(
                SceneMemoryItem.camera_id == camera_id,
                SceneMemoryItem.stable_key == observation.stable_key,
            )
        )
        previous_state = item.current_state if item is not None else None
        if item is None:
            item = SceneMemoryItem(
                id=new_id(),
                organization_id=organization_id,
                camera_id=camera_id,
                stable_key=observation.stable_key,
                label=observation.label,
                kind=observation.kind,
                bounding_box=observation.bounding_box.model_dump(),
                description=observation.description,
                current_state=observation.state,
                confidence=observation.confidence,
                attributes=observation.attributes,
                relationships=observation.relationships,
                source=SceneMemorySource.AUTOMATIC,
                review_status=SceneReviewStatus.PROPOSED,
                first_seen_at=occurred_at,
                last_seen_at=occurred_at,
            )
            session.add(item)
        else:
            item.label = observation.label
            item.kind = observation.kind
            item.bounding_box = observation.bounding_box.model_dump()
            item.description = observation.description
            item.current_state = observation.state
            item.confidence = observation.confidence
            item.attributes = observation.attributes
            item.relationships = observation.relationships
            item.last_seen_at = occurred_at

        if previous_state != observation.state:
            session.add(
                SceneChange(
                    id=new_id(),
                    organization_id=organization_id,
                    camera_id=camera_id,
                    item_id=item.id,
                    event_id=event_id,
                    previous_state=previous_state,
                    new_state=observation.state,
                    confidence=observation.confidence,
                    details={"source": "automatic"},
                    occurred_at=occurred_at,
                    created_at=utc_now(),
                )
            )
        if observation.kind == SceneItemKind.TRACKED_ENTITY:
            existing_sighting = await session.scalar(
                select(EntitySighting.id).where(
                    EntitySighting.camera_id == camera_id,
                    EntitySighting.entity_key == observation.stable_key,
                    EntitySighting.occurred_at == occurred_at,
                )
            )
            if existing_sighting is None:
                area_id = await session.scalar(
                    select(CameraPlacement.area_id).where(CameraPlacement.camera_id == camera_id)
                )
                session.add(
                    EntitySighting(
                        id=new_id(),
                        organization_id=organization_id,
                        camera_id=camera_id,
                        area_id=area_id,
                        event_id=event_id,
                        entity_key=observation.stable_key,
                        label=observation.label,
                        bounding_box=observation.bounding_box.model_dump(),
                        confidence=observation.confidence,
                        attributes=observation.attributes,
                        occurred_at=occurred_at,
                    )
                )
        items.append(item)
    return items
