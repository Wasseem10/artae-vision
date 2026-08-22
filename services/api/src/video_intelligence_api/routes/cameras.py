from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.dependencies import SessionDependency
from video_intelligence_api.models import Camera
from video_intelligence_api.schemas import CameraCreate, CameraRead, CameraStatusUpdate
from video_intelligence_api.source_utils import infer_source_type, redact_source_uri
from video_intelligence_api.tenancy import tenant_camera

router = APIRouter(prefix="/cameras", tags=["cameras"])


def camera_response(camera: Camera) -> CameraRead:
    return CameraRead(
        id=camera.id,
        organization_id=camera.organization_id,
        name=camera.name,
        source_uri=redact_source_uri(camera.source_uri),
        source_type=camera.source_type,
        status=camera.status,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )


@router.post("", response_model=CameraRead, status_code=status.HTTP_201_CREATED)
async def create_camera(
    payload: CameraCreate, session: SessionDependency, actor: EditorDependency
) -> CameraRead:
    camera = Camera(
        organization_id=actor.organization_id,
        name=payload.name,
        source_uri=payload.source_uri,
        source_type=infer_source_type(payload.source_uri),
    )
    session.add(camera)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Camera name already exists") from exc
    await session.refresh(camera)
    return camera_response(camera)


@router.get("", response_model=list[CameraRead])
async def list_cameras(session: SessionDependency, actor: ActorDependency) -> list[CameraRead]:
    cameras = (
        await session.scalars(
            select(Camera)
            .where(Camera.organization_id == actor.organization_id)
            .order_by(Camera.name)
        )
    ).all()
    return [camera_response(camera) for camera in cameras]


@router.get("/{camera_id}", response_model=CameraRead)
async def get_camera(
    camera_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: ActorDependency,
) -> CameraRead:
    camera = await tenant_camera(session, actor, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera_response(camera)


@router.patch("/{camera_id}/status", response_model=CameraRead)
async def update_camera_status(
    camera_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: CameraStatusUpdate,
    session: SessionDependency,
    actor: EditorDependency,
) -> CameraRead:
    camera = await tenant_camera(session, actor, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    camera.status = payload.status
    await session.commit()
    await session.refresh(camera)
    return camera_response(camera)
