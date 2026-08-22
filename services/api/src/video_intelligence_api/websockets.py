import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class EventConnectionManager:
    """Fan events out within one API process; Redis fan-out comes later."""

    def __init__(self) -> None:
        self._connections: dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, organization_id: str) -> None:
        await websocket.accept()
        self._connections[websocket] = organization_id

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    async def broadcast(self, message: dict[str, object], *, organization_id: str) -> None:
        failed: list[WebSocket] = []
        for connection, connection_organization_id in self._connections.copy().items():
            if connection_organization_id != organization_id:
                continue
            try:
                await connection.send_json(message)
            except RuntimeError:
                failed.append(connection)
        for connection in failed:
            self.disconnect(connection)
        if failed:
            logger.info("Removed %d disconnected WebSocket client(s)", len(failed))
