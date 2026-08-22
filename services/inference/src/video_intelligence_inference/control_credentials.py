from __future__ import annotations

from video_intelligence_inference.config import Settings


def control_plane_headers(settings: Settings) -> dict[str, str]:
    """Prefer the per-device token and retain the shared key only for local development."""
    if settings.control_plane_device_token is not None:
        return {
            "X-Device-Token": settings.control_plane_device_token.get_secret_value(),
        }
    if settings.control_plane_agent_key is not None:
        return {"X-Agent-Key": settings.control_plane_agent_key.get_secret_value()}
    return {}
