from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.auth import ActorDependency
from video_intelligence_api.camera_secrets import CameraSecretError, resolved_camera_source
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.execution_plans import plan_job
from video_intelligence_api.field_accuracy import automatic_release_allowed
from video_intelligence_api.job_specs import validate_job_spec
from video_intelligence_api.live_verification import (
    assess_semantic_event,
    finalize_confirmed_event,
    scene_observations,
)
from video_intelligence_api.models import (
    Camera,
    Event,
    EvidenceAsset,
    Rule,
    RuleStatus,
    VerificationCase,
    VerificationStatus,
    Zone,
    new_id,
    utc_now,
)
from video_intelligence_api.routes.agents import assignment_rule
from video_intelligence_api.schemas import (
    AgentCameraConfig,
    AgentEventIngest,
    EventRead,
)
from video_intelligence_api.security import (
    EdgePrincipal,
    ensure_edge_organization,
    require_edge_device,
)
from video_intelligence_api.strands_orchestrator import coordinate_incident
from video_intelligence_api.tenancy import tenant_event

router = APIRouter(tags=["events"])


@router.get(
    "/agent/config",
    response_model=AgentCameraConfig,
)
async def get_agent_config(
    camera_ref: Annotated[str, Query(min_length=1, max_length=120)],
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> AgentCameraConfig:
    """Return unredacted source details only to an authenticated camera agent."""
    camera_statement = select(Camera).where(or_(Camera.id == camera_ref, Camera.name == camera_ref))
    if principal.organization_id is not None:
        camera_statement = camera_statement.where(
            Camera.organization_id == principal.organization_id
        )
    camera = await session.scalar(camera_statement.limit(1))
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera reference not found")
    if (
        principal.device_id is not None
        and camera.edge_device_id is not None
        and camera.edge_device_id != principal.device_id
    ):
        raise HTTPException(status_code=404, detail="Camera reference not found")

    rows = (
        await session.execute(
            select(Rule, Zone)
            .join(Zone, Rule.zone_id == Zone.id)
            .where(Rule.camera_id == camera.id, Rule.status == RuleStatus.ACTIVE)
            .order_by(Rule.created_at)
        )
    ).all()
    try:
        source_uri = resolved_camera_source(camera, settings)
    except CameraSecretError as exc:
        raise HTTPException(status_code=503, detail="Camera credentials are unavailable") from exc
    return AgentCameraConfig(
        camera_id=camera.id,
        camera_name=camera.name,
        source_uri=source_uri,
        source_type=camera.source_type,
        rules=[assignment_rule(rule, zone) for rule, zone in rows],
    )


@router.get("/events", response_model=list[EventRead])
async def list_events(
    session: SessionDependency,
    actor: ActorDependency,
    camera_id: Annotated[str | None, Query(max_length=36)] = None,
    rule_id: Annotated[str | None, Query(max_length=36)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[Event]:
    statement = (
        select(Event)
        .join(Camera, Camera.id == Event.camera_id)
        .where(
            Camera.organization_id == actor.organization_id,
            Event.verification_status.in_(
                [VerificationStatus.NOT_REQUIRED, VerificationStatus.CONFIRMED]
            ),
        )
        .order_by(Event.occurred_at.desc())
        .limit(limit)
    )
    if camera_id:
        statement = statement.where(Event.camera_id == camera_id)
    if rule_id:
        statement = statement.where(Event.rule_id == rule_id)
    return list((await session.scalars(statement)).all())


@router.get("/events/{event_id}", response_model=EventRead)
async def get_event(event_id: str, session: SessionDependency, actor: ActorDependency) -> Event:
    event = await tenant_event(session, actor, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post(
    "/agent/events",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_agent_event(
    payload: AgentEventIngest,
    request: Request,
    response: Response,
    session: SessionDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> Event:
    existing_row = (
        await session.execute(
            select(Event, Camera)
            .join(Camera, Camera.id == Event.camera_id)
            .where(Event.source_event_id == payload.id)
        )
    ).first()
    if existing_row is not None:
        existing, existing_camera = existing_row
        ensure_edge_organization(principal, existing_camera.organization_id)
        response.status_code = status.HTTP_200_OK
        return existing

    camera_statement = select(Camera).where(
        or_(Camera.id == payload.camera_id, Camera.name == payload.camera_id)
    )
    if principal.organization_id is not None:
        camera_statement = camera_statement.where(
            Camera.organization_id == principal.organization_id
        )
    camera = await session.scalar(camera_statement.limit(1))
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera reference not found")

    rule = await session.scalar(
        select(Rule)
        .where(
            Rule.camera_id == camera.id,
            or_(Rule.id == payload.rule_id, Rule.key == payload.rule_id),
        )
        .limit(1)
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule reference not found")
    if rule.status != RuleStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Rule is not active")

    raw_payload = payload.model_dump(mode="json")
    specialized_pose = False
    if rule.spec is not None:
        try:
            specialized_pose = (
                plan_job(
                    validate_job_spec(rule.spec),
                    rule.original_prompt or rule.name,
                ).strategy
                == "specialized_pose"
            )
        except ValidationError:
            specialized_pose = False
    if payload.event_type == "person_fall" and not specialized_pose:
        raise HTTPException(
            status_code=422,
            detail="This rule is not configured for specialized fall detection",
        )
    is_semantic = (
        rule.rule_type == "semantic_vision" and not specialized_pose
    ) or payload.event_type == "semantic_vision"
    assessment = assess_semantic_event(rule, payload.details) if is_semantic else None
    if (
        assessment is not None
        and assessment.decision_source == "automatic_verifier"
        and not await automatic_release_allowed(session, rule.id)
    ):
        proposed_status = assessment.status.value
        assessment = replace(
            assessment,
            status=VerificationStatus.PENDING,
            reasoning=(
                f"The independent verifier proposed '{proposed_status}', but this camera/job "
                "has not passed its human-grounded field accuracy gate. Operator review is "
                "required."
            ),
            decision_source="field_gate_required",
        )
    verification_status = (
        assessment.status if assessment is not None else VerificationStatus.NOT_REQUIRED
    )
    # Validate semantic scene memory before persisting, but release it only after confirmation.
    try:
        scene_observations(payload.details)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Event scene observations are invalid") from exc
    event = Event(
        id=new_id(),
        source_event_id=payload.id,
        schema_version=payload.schema_version,
        event_type=payload.event_type,
        camera_id=camera.id,
        rule_id=rule.id,
        track_id=payload.track_id,
        object_class=payload.object_class,
        zone_name=payload.zone_name,
        entered_at_seconds=payload.entered_at_seconds,
        occurred_at_seconds=payload.occurred_at_seconds,
        dwell_seconds=payload.dwell_seconds,
        confidence=payload.confidence,
        occurred_at=payload.occurred_at,
        clip_uri=payload.clip_path,
        raw_payload=raw_payload,
        details=payload.details,
        verification_status=verification_status,
        verified_at=utc_now()
        if verification_status in {VerificationStatus.CONFIRMED, VerificationStatus.REJECTED}
        else None,
        verified_by="automatic-verifier"
        if verification_status in {VerificationStatus.CONFIRMED, VerificationStatus.REJECTED}
        else None,
    )
    agent_run = None
    if verification_status in {VerificationStatus.NOT_REQUIRED, VerificationStatus.CONFIRMED}:
        agent_run = await coordinate_incident(
            event,
            camera,
            rule,
            request.app.state.settings,
        )
        if agent_run is not None:
            event.details = {
                **event.details,
                "strands_agent": agent_run.model_dump(mode="json"),
            }
    session.add(event)
    if agent_run is None or agent_run.requested("preserve_evidence"):
        session.add(EvidenceAsset(event_id=event.id))
    if assessment is not None:
        session.add(
            VerificationCase(
                id=new_id(),
                organization_id=camera.organization_id,
                event_id=event.id,
                status=assessment.status,
                proposer_model=assessment.proposer_model,
                verifier_model=assessment.verifier_model,
                proposer_confidence=payload.confidence,
                verifier_confidence=assessment.verifier_confidence,
                proposal_summary=assessment.proposal_summary,
                verifier_summary=assessment.verifier_summary,
                reasoning=assessment.reasoning,
                decision_source=assessment.decision_source,
                reviewed_at=event.verified_at,
                reviewed_by=event.verified_by,
            )
        )
    if verification_status in {VerificationStatus.NOT_REQUIRED, VerificationStatus.CONFIRMED}:
        await finalize_confirmed_event(
            session,
            event,
            camera,
            notify_responder=(
                agent_run is None or agent_run.requested("notify_responder")
            ),
        )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing_row = (
            await session.execute(
                select(Event, Camera)
                .join(Camera, Camera.id == Event.camera_id)
                .where(Event.source_event_id == payload.id)
            )
        ).first()
        if existing_row is not None:
            existing, existing_camera = existing_row
            ensure_edge_organization(principal, existing_camera.organization_id)
            response.status_code = status.HTTP_200_OK
            return existing
        raise
    await session.refresh(event)

    if verification_status in {VerificationStatus.NOT_REQUIRED, VerificationStatus.CONFIRMED}:
        event_payload = EventRead.model_validate(event).model_dump(mode="json")
        await request.app.state.event_connections.broadcast(
            {"type": "event.created", "data": event_payload},
            organization_id=camera.organization_id,
        )
    return event
