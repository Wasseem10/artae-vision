from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.capabilities import check_job_capability
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.job_specs import legacy_job_spec, validate_job_spec
from video_intelligence_api.models import (
    AgentDesiredStatus,
    Camera,
    CameraAgent,
    Rule,
    RuleStatus,
    Zone,
)
from video_intelligence_api.schemas import RuleCreate, RuleRead, RuleStatusUpdate
from video_intelligence_api.tenancy import tenant_camera, tenant_rule, tenant_zone

router = APIRouter(prefix="/rules", tags=["rules"])


@router.post("", response_model=RuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RuleCreate, session: SessionDependency, actor: EditorDependency
) -> Rule:
    if await tenant_camera(session, actor, payload.camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    zone = await tenant_zone(session, actor, payload.zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    if zone.camera_id != payload.camera_id:
        raise HTTPException(status_code=409, detail="Zone belongs to a different camera")
    if zone.geometry_type.value != "polygon":
        raise HTTPException(status_code=409, detail="Object dwell jobs require a polygon zone")

    legacy_spec = legacy_job_spec(
        object_class=payload.object_class,
        zone_id=zone.id,
        zone_name=zone.name,
        duration_seconds=payload.duration_seconds,
        minimum_confidence=payload.minimum_confidence,
        absence_grace_seconds=payload.absence_grace_seconds,
    )
    rule = Rule(
        **payload.model_dump(),
        status=RuleStatus.DRAFT,
        spec_version=1,
        spec=legacy_spec.model_dump(mode="json"),
    )
    session.add(rule)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Rule key already exists for this camera",
        ) from exc
    await session.refresh(rule)
    return rule


@router.get("", response_model=list[RuleRead])
async def list_rules(
    session: SessionDependency,
    actor: ActorDependency,
    camera_id: Annotated[str | None, Query(max_length=36)] = None,
    rule_status: Annotated[RuleStatus | None, Query(alias="status")] = None,
) -> list[Rule]:
    statement = (
        select(Rule)
        .join(Camera, Camera.id == Rule.camera_id)
        .where(Camera.organization_id == actor.organization_id)
        .order_by(Rule.created_at.desc())
    )
    if camera_id:
        statement = statement.where(Rule.camera_id == camera_id)
    if rule_status:
        statement = statement.where(Rule.status == rule_status)
    return list((await session.scalars(statement)).all())


@router.patch("/{rule_id}/status", response_model=RuleRead)
async def update_rule_status(
    rule_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: RuleStatusUpdate,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: EditorDependency,
) -> Rule:
    rule = await tenant_rule(session, actor, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    agent = await session.get(CameraAgent, rule.camera_id)
    if (
        rule.status != payload.status
        and agent is not None
        and agent.desired_status == AgentDesiredStatus.RUNNING
    ):
        raise HTTPException(
            status_code=409,
            detail="Stop the camera agent before changing deployed jobs",
        )
    if payload.status == RuleStatus.ACTIVE:
        zone = await session.get(Zone, rule.zone_id)
        if zone is None:
            raise HTTPException(status_code=409, detail="The job's scene geometry is unavailable")
        raw_spec = rule.spec or legacy_job_spec(
            object_class=rule.object_class,
            zone_id=zone.id,
            zone_name=zone.name,
            duration_seconds=rule.duration_seconds,
            minimum_confidence=rule.minimum_confidence,
            absence_grace_seconds=rule.absence_grace_seconds,
        ).model_dump(mode="json")
        try:
            spec = validate_job_spec(raw_spec)
        except ValidationError as exc:
            raise HTTPException(
                status_code=409,
                detail="The stored job specification is invalid",
            ) from exc
        capability = check_job_capability(spec, settings)
        if not capability.supported:
            raise HTTPException(status_code=409, detail=capability.reason)
    rule.status = payload.status
    await session.commit()
    await session.refresh(rule)
    return rule
