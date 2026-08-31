"""Camera calibration scenario catalog and evidence-readiness endpoints."""

from fastapi import APIRouter
from sqlalchemy import select

from video_intelligence_api.auth import ActorDependency
from video_intelligence_api.calibration import (
    CalibrationReadiness,
    CalibrationScenarioRead,
    assess_calibration_readiness,
    scenario_payloads,
)
from video_intelligence_api.dependencies import SessionDependency
from video_intelligence_api.models import ReplayEvaluation

router = APIRouter(prefix="/calibration", tags=["camera calibration"])


@router.get("/scenarios", response_model=list[CalibrationScenarioRead])
async def list_calibration_scenarios(_actor: ActorDependency) -> list[CalibrationScenarioRead]:
    return scenario_payloads()


@router.get("/readiness", response_model=CalibrationReadiness)
async def get_calibration_readiness(
    session: SessionDependency,
    actor: ActorDependency,
) -> CalibrationReadiness:
    evaluations = list(
        (
            await session.scalars(
                select(ReplayEvaluation)
                .where(ReplayEvaluation.organization_id == actor.organization_id)
                .order_by(ReplayEvaluation.created_at.desc())
            )
        ).all()
    )
    return assess_calibration_readiness(evaluations)
