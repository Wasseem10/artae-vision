from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from video_intelligence_api.auth import authenticate_websocket

router = APIRouter(tags=["events"])


@router.websocket("/ws/events")
async def event_websocket(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    actor = await authenticate_websocket(websocket, token)
    if actor is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    manager = websocket.app.state.event_connections
    await manager.connect(websocket, actor.organization_id)
    await websocket.send_json({"type": "connected"})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
