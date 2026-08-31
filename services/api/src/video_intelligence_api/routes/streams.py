"""Camera stream provisioning and status endpoints."""

from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Path

from video_intelligence_api.auth import Actor, ActorDependency, EditorDependency
from video_intelligence_api.camera_secrets import CameraSecretError, resolved_camera_source
from video_intelligence_api.config import ApiSettings
from video_intelligence_api.dependencies import (
    MediaGatewayDependency,
    SessionDependency,
    SettingsDependency,
)
from video_intelligence_api.media_gateway import (
    MediaGatewayError,
    MediaPathState,
    camera_path,
)
from video_intelligence_api.models import Camera, SourceType
from video_intelligence_api.schemas import CameraStreamRead
from video_intelligence_api.tenancy import tenant_camera

router = APIRouter(prefix="/cameras", tags=["camera streams"])


def stream_response(
    camera: Camera,
    state: MediaPathState,
    settings: ApiSettings,
) -> CameraStreamRead:
    path = camera_path(camera.id)
    encoded_path = quote(path, safe="")
    mode: Literal["proxy", "publisher"] = (
        "proxy"
        if camera.source_type == SourceType.RTSP and camera.edge_device_id is None
        else "publisher"
    )
    webrtc_base = settings.media_gateway_webrtc_url.rstrip("/")
    rtsp_base = settings.media_gateway_rtsp_url.rstrip("/")
    playback_url = (
        f"{webrtc_base}/{encoded_path}?controls=false&muted=true&autoplay=true&playsInline=true"
    )
    return CameraStreamRead(
        camera_id=camera.id,
        path=path,
        mode=mode,
        configured=state.configured,
        ready=state.ready,
        readers=state.readers,
        playback_url=playback_url,
        whep_url=f"{webrtc_base}/{encoded_path}/whep",
        publish_url=f"{rtsp_base}/{encoded_path}" if mode == "publisher" else None,
    )


async def _camera_or_404(camera_id: str, session: SessionDependency, actor: Actor) -> Camera:
    camera = await tenant_camera(session, actor, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@router.put("/{camera_id}/stream", response_model=CameraStreamRead)
async def provision_camera_stream(
    camera_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    gateway: MediaGatewayDependency,
    settings: SettingsDependency,
    actor: EditorDependency,
) -> CameraStreamRead:
    camera = await _camera_or_404(camera_id, session, actor)
    try:
        source = (
            resolved_camera_source(camera, settings)
            if camera.source_type == SourceType.RTSP and camera.edge_device_id is None
            else "publisher"
        )
    except CameraSecretError as exc:
        raise HTTPException(status_code=503, detail="Camera credentials are unavailable") from exc
    try:
        state = await gateway.provision(camera_path(camera.id), source)
    except MediaGatewayError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return stream_response(camera, state, settings)


@router.get("/{camera_id}/stream", response_model=CameraStreamRead)
async def get_camera_stream(
    camera_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    gateway: MediaGatewayDependency,
    settings: SettingsDependency,
    actor: ActorDependency,
) -> CameraStreamRead:
    camera = await _camera_or_404(camera_id, session, actor)
    try:
        state = await gateway.state(camera_path(camera.id))
    except MediaGatewayError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return stream_response(camera, state, settings)
