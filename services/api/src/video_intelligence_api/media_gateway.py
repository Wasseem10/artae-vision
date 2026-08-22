"""Small asynchronous client for the private MediaMTX Control API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import httpx


class MediaGatewayError(RuntimeError):
    """Raised when the media gateway is unavailable or rejects a request."""


@dataclass(frozen=True, slots=True)
class MediaPathState:
    configured: bool
    ready: bool
    readers: int


class MediaGateway(Protocol):
    """Boundary shared by the production gateway and native local mode."""

    async def close(self) -> None: ...

    async def provision(self, path: str, source: str) -> MediaPathState: ...

    async def state(self, path: str) -> MediaPathState: ...


def camera_path(camera_id: str) -> str:
    """Return the stable, credential-free gateway path for a camera."""
    return f"camera-{camera_id}"


class MediaGatewayClient:
    """Provision camera paths without exposing the Control API to browser code."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def provision(self, path: str, source: str) -> MediaPathState:
        encoded_path = quote(path, safe="")
        payload = {
            "source": source,
            "sourceOnDemand": source.lower().startswith(("rtsp://", "rtsps://")),
        }
        try:
            current = await self._client.get(f"/v3/config/paths/get/{encoded_path}")
            if current.status_code == 404:
                response = await self._client.post(
                    f"/v3/config/paths/add/{encoded_path}", json=payload
                )
            else:
                current.raise_for_status()
                response = await self._client.patch(
                    f"/v3/config/paths/patch/{encoded_path}", json=payload
                )
            response.raise_for_status()
            return await self._active_state(path, configured=True)
        except httpx.HTTPError as exc:
            raise MediaGatewayError("Media gateway could not provision the camera path") from exc

    async def state(self, path: str) -> MediaPathState:
        encoded_path = quote(path, safe="")
        try:
            configured = await self._client.get(f"/v3/config/paths/get/{encoded_path}")
            if configured.status_code == 404:
                return MediaPathState(configured=False, ready=False, readers=0)
            configured.raise_for_status()
            return await self._active_state(path, configured=True)
        except httpx.HTTPError as exc:
            raise MediaGatewayError("Media gateway status is unavailable") from exc

    async def _active_state(self, path: str, *, configured: bool) -> MediaPathState:
        response = await self._client.get(f"/v3/paths/get/{quote(path, safe='')}")
        if response.status_code == 404:
            return MediaPathState(configured=configured, ready=False, readers=0)
        response.raise_for_status()
        body = response.json()
        readers = body.get("readers")
        return MediaPathState(
            configured=configured,
            ready=bool(body.get("ready", False)),
            readers=len(readers) if isinstance(readers, list) else 0,
        )


class DisabledMediaGateway:
    """Return an honest offline stream state when local mode has no MediaMTX."""

    async def close(self) -> None:
        return None

    async def provision(self, path: str, source: str) -> MediaPathState:
        return MediaPathState(configured=False, ready=False, readers=0)

    async def state(self, path: str) -> MediaPathState:
        return MediaPathState(configured=False, ready=False, readers=0)
