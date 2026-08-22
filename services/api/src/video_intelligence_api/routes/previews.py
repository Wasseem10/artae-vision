"""Authenticated native-preview upload and read endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, Response, status

from video_intelligence_api.auth import ActorDependency
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.models import Camera
from video_intelligence_api.security import (
    EdgePrincipal,
    ensure_edge_organization,
    require_edge_device,
)
from video_intelligence_api.tenancy import tenant_camera

router = APIRouter(tags=["native camera previews"])


@router.put(
    "/agent/cameras/{camera_id}/preview",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def upload_camera_preview(
    camera_id: Annotated[str, Path(min_length=1, max_length=36)],
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
    content_type: Annotated[str | None, Header(alias="Content-Type")] = None,
) -> Response:
    camera = await session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    ensure_edge_organization(principal, camera.organization_id)
    if content_type is None or content_type.split(";", maxsplit=1)[0] != "image/jpeg":
        raise HTTPException(status_code=415, detail="Preview must use image/jpeg")

    jpeg = await request.body()
    if not jpeg:
        raise HTTPException(status_code=400, detail="Preview is empty")
    if len(jpeg) > settings.preview_max_bytes:
        raise HTTPException(status_code=413, detail="Preview exceeds the size limit")
    if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
        raise HTTPException(status_code=400, detail="Preview is not a valid JPEG envelope")

    await request.app.state.preview_store.put(camera.id, camera.organization_id, jpeg)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/cameras/{camera_id}/preview")
async def get_camera_preview(
    camera_id: Annotated[str, Path(min_length=1, max_length=36)],
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: ActorDependency,
) -> Response:
    camera = await tenant_camera(session, actor, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    frame = await request.app.state.preview_store.get(
        camera.id,
        max_age_seconds=settings.preview_ttl_seconds,
    )
    if frame is None or frame.organization_id != actor.organization_id:
        raise HTTPException(status_code=404, detail="A recent camera preview is not available")
    return Response(
        content=frame.jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, max-age=0"},
    )
