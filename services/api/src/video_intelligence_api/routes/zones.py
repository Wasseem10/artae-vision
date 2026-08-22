from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.dependencies import SessionDependency
from video_intelligence_api.models import Camera, Zone
from video_intelligence_api.schemas import ZoneCreate, ZoneRead
from video_intelligence_api.tenancy import tenant_camera

router = APIRouter(prefix="/zones", tags=["zones"])


@router.post("", response_model=ZoneRead, status_code=status.HTTP_201_CREATED)
async def create_zone(
    payload: ZoneCreate, session: SessionDependency, actor: EditorDependency
) -> Zone:
    if await tenant_camera(session, actor, payload.camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    zone = Zone(
        camera_id=payload.camera_id,
        name=payload.name,
        geometry_type=payload.geometry_type,
        points=[point.model_dump() for point in payload.points],
    )
    session.add(zone)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Zone name already exists for this camera",
        ) from exc
    await session.refresh(zone)
    return zone


@router.get("", response_model=list[ZoneRead])
async def list_zones(
    session: SessionDependency,
    actor: ActorDependency,
    camera_id: Annotated[str | None, Query(max_length=36)] = None,
) -> list[Zone]:
    statement = (
        select(Zone)
        .join(Camera, Camera.id == Zone.camera_id)
        .where(Camera.organization_id == actor.organization_id)
        .order_by(Zone.name)
    )
    if camera_id:
        statement = statement.where(Zone.camera_id == camera_id)
    return list((await session.scalars(statement)).all())
