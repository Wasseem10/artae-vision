from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from video_intelligence_api.dependencies import SessionDependency
from video_intelligence_api.device_credentials import device_id_from_token, hash_device_token
from video_intelligence_api.models import EdgeDevice, EdgeDeviceStatus, utc_now


@dataclass(frozen=True, slots=True)
class EdgePrincipal:
    device_id: str | None
    organization_id: str | None
    legacy_development_key: bool = False


async def require_agent_key(
    request: Request,
    x_agent_key: Annotated[str | None, Header()] = None,
) -> None:
    """Authenticate non-camera background workers on the internal service boundary."""
    expected = request.app.state.settings.agent_key.get_secret_value()
    if x_agent_key is None or not hmac.compare_digest(x_agent_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent key",
        )


async def require_edge_device(
    request: Request,
    session: SessionDependency,
    x_device_token: Annotated[str | None, Header()] = None,
    x_agent_key: Annotated[str | None, Header()] = None,
) -> EdgePrincipal:
    """Authenticate an inference host, with an explicit local-development fallback."""
    settings = request.app.state.settings
    if x_device_token is not None:
        device_id = device_id_from_token(x_device_token)
        device = await session.get(EdgeDevice, device_id) if device_id else None
        if (
            device is not None
            and device.status == EdgeDeviceStatus.ACTIVE
            and device.revoked_at is None
            and hmac.compare_digest(hash_device_token(x_device_token), device.credential_hash)
        ):
            device.last_seen_at = utc_now()
            await session.commit()
            return EdgePrincipal(
                device_id=device.id,
                organization_id=device.organization_id,
            )

    if settings.edge_auth_mode == "development":
        expected = settings.agent_key.get_secret_value()
        if x_agent_key is not None and hmac.compare_digest(x_agent_key, expected):
            return EdgePrincipal(
                device_id=None,
                organization_id=None,
                legacy_development_key=True,
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid edge-device credentials",
        headers={"WWW-Authenticate": "Device"},
    )


def ensure_edge_organization(principal: EdgePrincipal, organization_id: str) -> None:
    if principal.organization_id is not None and principal.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Camera reference not found")
