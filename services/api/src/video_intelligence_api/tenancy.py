from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from video_intelligence_api.auth import Actor
from video_intelligence_api.models import (
    Alert,
    Camera,
    Event,
    ReplayEvaluation,
    ReplaySuite,
    ReplaySuiteRun,
    Rule,
    RuleCompilation,
    Zone,
)


async def tenant_camera(session: AsyncSession, actor: Actor, camera_id: str) -> Camera | None:
    return await session.scalar(
        select(Camera).where(
            Camera.id == camera_id,
            Camera.organization_id == actor.organization_id,
        )
    )


async def tenant_zone(session: AsyncSession, actor: Actor, zone_id: str) -> Zone | None:
    return await session.scalar(
        select(Zone)
        .join(Camera, Camera.id == Zone.camera_id)
        .where(Zone.id == zone_id, Camera.organization_id == actor.organization_id)
    )


async def tenant_rule(session: AsyncSession, actor: Actor, rule_id: str) -> Rule | None:
    return await session.scalar(
        select(Rule)
        .join(Camera, Camera.id == Rule.camera_id)
        .where(Rule.id == rule_id, Camera.organization_id == actor.organization_id)
    )


async def tenant_compilation(
    session: AsyncSession, actor: Actor, compilation_id: str
) -> RuleCompilation | None:
    return await session.scalar(
        select(RuleCompilation)
        .join(Camera, Camera.id == RuleCompilation.camera_id)
        .where(
            RuleCompilation.id == compilation_id,
            Camera.organization_id == actor.organization_id,
        )
    )


async def tenant_event(session: AsyncSession, actor: Actor, event_id: str) -> Event | None:
    return await session.scalar(
        select(Event)
        .join(Camera, Camera.id == Event.camera_id)
        .where(Event.id == event_id, Camera.organization_id == actor.organization_id)
    )


async def tenant_alert(session: AsyncSession, actor: Actor, alert_id: str) -> Alert | None:
    return await session.scalar(
        select(Alert)
        .join(Event, Event.id == Alert.event_id)
        .join(Camera, Camera.id == Event.camera_id)
        .where(Alert.id == alert_id, Camera.organization_id == actor.organization_id)
    )


async def tenant_replay_evaluation(
    session: AsyncSession, actor: Actor, evaluation_id: str
) -> ReplayEvaluation | None:
    return await session.scalar(
        select(ReplayEvaluation).where(
            ReplayEvaluation.id == evaluation_id,
            ReplayEvaluation.organization_id == actor.organization_id,
        )
    )


async def tenant_replay_suite(
    session: AsyncSession, actor: Actor, suite_id: str
) -> ReplaySuite | None:
    return await session.scalar(
        select(ReplaySuite).where(
            ReplaySuite.id == suite_id,
            ReplaySuite.organization_id == actor.organization_id,
        )
    )


async def tenant_replay_suite_run(
    session: AsyncSession, actor: Actor, run_id: str
) -> ReplaySuiteRun | None:
    return await session.scalar(
        select(ReplaySuiteRun).where(
            ReplaySuiteRun.id == run_id,
            ReplaySuiteRun.organization_id == actor.organization_id,
        )
    )
