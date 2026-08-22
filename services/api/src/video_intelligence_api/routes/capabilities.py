"""Public description of what the configured inference stack can deploy."""

from fastapi import APIRouter

from video_intelligence_api.capabilities import registry_payload
from video_intelligence_api.dependencies import SettingsDependency

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get("")
async def get_capabilities(settings: SettingsDependency) -> dict[str, object]:
    return registry_payload(settings)
