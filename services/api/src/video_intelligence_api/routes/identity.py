from fastapi import APIRouter

from video_intelligence_api.auth import ActorDependency
from video_intelligence_api.schemas import ActorRead

router = APIRouter(prefix="/identity", tags=["identity"])


@router.get("/me", response_model=ActorRead)
async def get_identity(actor: ActorDependency) -> ActorRead:
    return ActorRead(
        subject=actor.subject,
        organization_id=actor.organization_id,
        role=actor.role,
        issuer=actor.issuer,
        email=actor.email,
        display_name=actor.display_name,
    )
