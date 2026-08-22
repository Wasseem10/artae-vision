from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.alert_secrets import AlertSecretError, encrypt_alert_secret
from video_intelligence_api.alerting import enqueue_event_alert
from video_intelligence_api.auth import ActorDependency, AdminDependency, EditorDependency
from video_intelligence_api.correlations import enqueue_event_correlations, evaluate_correlation
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.models import (
    Alert,
    Camera,
    ContextObservation,
    ContextSource,
    CorrelationEvaluation,
    CorrelationEvaluationStatus,
    Event,
    EvidenceAsset,
    RuleCorrelationPolicy,
    Zone,
    new_id,
    utc_now,
)
from video_intelligence_api.schemas import (
    ContextObservationCreate,
    ContextObservationRead,
    ContextSourceCreate,
    ContextSourceRead,
    CorrelationDemoCreate,
    CorrelationEvaluationRead,
    EventRead,
    RuleCorrelationPolicyCreate,
    RuleCorrelationPolicyRead,
)
from video_intelligence_api.security import require_agent_key
from video_intelligence_api.tenancy import tenant_rule

router = APIRouter(tags=["external context"])


def policy_response(
    policy: RuleCorrelationPolicy, source: ContextSource
) -> RuleCorrelationPolicyRead:
    return RuleCorrelationPolicyRead(
        **{
            field: getattr(policy, field)
            for field in (
                "id",
                "organization_id",
                "rule_id",
                "source_id",
                "correlation_type",
                "observation_type",
                "visual_count_field",
                "window_before_seconds",
                "window_after_seconds",
                "enabled",
                "created_at",
                "updated_at",
            )
        },
        source_name=source.name,
    )


def evaluation_response(
    evaluation: CorrelationEvaluation, source: ContextSource
) -> CorrelationEvaluationRead:
    return CorrelationEvaluationRead(
        **{
            field: getattr(evaluation, field)
            for field in (
                "id",
                "organization_id",
                "event_id",
                "policy_id",
                "source_id",
                "status",
                "visual_count",
                "observation_count",
                "window_start",
                "window_end",
                "due_at",
                "explanation",
                "evaluated_at",
                "created_at",
            )
        },
        source_name=source.name,
    )


@router.post(
    "/context-sources", response_model=ContextSourceRead, status_code=status.HTTP_201_CREATED
)
async def create_context_source(
    payload: ContextSourceCreate,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: AdminDependency,
) -> ContextSource:
    if (
        settings.environment == "production"
        and payload.endpoint_url is not None
        and payload.endpoint_url.scheme != "https"
    ):
        raise HTTPException(status_code=422, detail="Production context sources must use HTTPS")
    credential_encrypted = None
    if payload.credential is not None:
        try:
            credential_encrypted = encrypt_alert_secret(payload.credential, settings)
        except AlertSecretError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    source = ContextSource(
        id=new_id(),
        organization_id=actor.organization_id,
        name=payload.name.strip(),
        source_type=payload.source_type,
        endpoint_url=str(payload.endpoint_url) if payload.endpoint_url is not None else None,
        credential_encrypted=credential_encrypted,
        configuration=payload.configuration,
        enabled=payload.enabled,
    )
    session.add(source)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Context source name already exists") from exc
    await session.refresh(source)
    return source


@router.get("/context-sources", response_model=list[ContextSourceRead])
async def list_context_sources(
    session: SessionDependency, actor: ActorDependency
) -> list[ContextSource]:
    return list(
        (
            await session.scalars(
                select(ContextSource)
                .where(ContextSource.organization_id == actor.organization_id)
                .order_by(ContextSource.created_at.desc())
            )
        ).all()
    )


@router.post(
    "/context-sources/{source_id}/observations",
    response_model=ContextObservationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_context_observation(
    source_id: str,
    payload: ContextObservationCreate,
    response: Response,
    session: SessionDependency,
    actor: EditorDependency,
) -> ContextObservation:
    source = await session.scalar(
        select(ContextSource).where(
            ContextSource.id == source_id,
            ContextSource.organization_id == actor.organization_id,
        )
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Context source not found")
    source_event_id = payload.source_event_id or new_id()
    existing = await session.scalar(
        select(ContextObservation).where(
            ContextObservation.source_id == source.id,
            ContextObservation.source_event_id == source_event_id,
        )
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return existing
    observation = ContextObservation(
        id=new_id(),
        organization_id=actor.organization_id,
        source_id=source.id,
        source_event_id=source_event_id,
        observation_type=payload.observation_type,
        occurred_at=payload.occurred_at,
        entity_key=payload.entity_key,
        attributes=payload.attributes,
    )
    session.add(observation)
    await session.commit()
    await session.refresh(observation)
    return observation


@router.get("/context-observations", response_model=list[ContextObservationRead])
async def list_context_observations(
    session: SessionDependency,
    actor: ActorDependency,
    source_id: Annotated[str | None, Query(max_length=36)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ContextObservation]:
    statement = (
        select(ContextObservation)
        .where(ContextObservation.organization_id == actor.organization_id)
        .order_by(ContextObservation.occurred_at.desc())
        .limit(limit)
    )
    if source_id is not None:
        statement = statement.where(ContextObservation.source_id == source_id)
    return list((await session.scalars(statement)).all())


@router.post(
    "/rules/{rule_id}/correlation-policies",
    response_model=RuleCorrelationPolicyRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_correlation_policy(
    rule_id: str,
    payload: RuleCorrelationPolicyCreate,
    session: SessionDependency,
    actor: EditorDependency,
) -> RuleCorrelationPolicyRead:
    rule = await tenant_rule(session, actor, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    source = await session.scalar(
        select(ContextSource).where(
            ContextSource.id == payload.source_id,
            ContextSource.organization_id == actor.organization_id,
        )
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Context source not found")
    policy = RuleCorrelationPolicy(
        id=new_id(),
        organization_id=actor.organization_id,
        rule_id=rule.id,
        source_id=source.id,
        correlation_type=payload.correlation_type,
        observation_type=payload.observation_type,
        visual_count_field=payload.visual_count_field,
        window_before_seconds=payload.window_before_seconds,
        window_after_seconds=payload.window_after_seconds,
        enabled=payload.enabled,
    )
    session.add(policy)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Correlation policy already exists") from exc
    await session.refresh(policy)
    return policy_response(policy, source)


@router.get(
    "/rules/{rule_id}/correlation-policies",
    response_model=list[RuleCorrelationPolicyRead],
)
async def list_correlation_policies(
    rule_id: str, session: SessionDependency, actor: ActorDependency
) -> list[RuleCorrelationPolicyRead]:
    if await tenant_rule(session, actor, rule_id) is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    rows = (
        await session.execute(
            select(RuleCorrelationPolicy, ContextSource)
            .join(ContextSource, ContextSource.id == RuleCorrelationPolicy.source_id)
            .where(
                RuleCorrelationPolicy.rule_id == rule_id,
                RuleCorrelationPolicy.organization_id == actor.organization_id,
            )
            .order_by(RuleCorrelationPolicy.created_at.desc())
        )
    ).all()
    return [policy_response(policy, source) for policy, source in rows]


@router.get("/correlation-evaluations", response_model=list[CorrelationEvaluationRead])
async def list_correlation_evaluations(
    session: SessionDependency,
    actor: ActorDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[CorrelationEvaluationRead]:
    rows = (
        await session.execute(
            select(CorrelationEvaluation, ContextSource)
            .join(ContextSource, ContextSource.id == CorrelationEvaluation.source_id)
            .where(CorrelationEvaluation.organization_id == actor.organization_id)
            .order_by(CorrelationEvaluation.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [evaluation_response(evaluation, source) for evaluation, source in rows]


@router.post(
    "/rules/{rule_id}/correlation-demo",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_correlation_demo(
    rule_id: str,
    payload: CorrelationDemoCreate,
    request: Request,
    session: SessionDependency,
    actor: EditorDependency,
) -> Event:
    rule = await tenant_rule(session, actor, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    row = (
        await session.execute(
            select(RuleCorrelationPolicy, ContextSource)
            .join(ContextSource, ContextSource.id == RuleCorrelationPolicy.source_id)
            .where(
                RuleCorrelationPolicy.rule_id == rule.id,
                RuleCorrelationPolicy.enabled.is_(True),
                ContextSource.enabled.is_(True),
            )
            .limit(1)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=409, detail="Create a correlation policy first")
    policy, source = row
    camera = await session.get(Camera, rule.camera_id)
    zone = await session.get(Zone, rule.zone_id)
    if camera is None:
        raise HTTPException(status_code=409, detail="Rule camera is unavailable")

    now = utc_now()
    for index in range(payload.authorized_entries):
        session.add(
            ContextObservation(
                id=new_id(),
                organization_id=actor.organization_id,
                source_id=source.id,
                source_event_id=f"demo-swipe-{new_id()}",
                observation_type=policy.observation_type,
                occurred_at=now - timedelta(milliseconds=100 * index),
                entity_key=f"demo-card-{index + 1}",
                attributes={"simulated": True, "result": "granted"},
            )
        )
    source_event_id = new_id()
    event = Event(
        id=new_id(),
        source_event_id=source_event_id,
        schema_version=3,
        event_type="count_threshold",
        camera_id=camera.id,
        rule_id=rule.id,
        track_id=None,
        object_class="person",
        zone_name=zone.name if zone is not None else "Entrance",
        entered_at_seconds=0,
        occurred_at_seconds=0,
        dwell_seconds=0,
        confidence=1,
        occurred_at=now,
        clip_uri="",
        raw_payload={"id": source_event_id, "demo": "tailgating"},
        details={"person_count": payload.visual_people, "simulated": True},
    )
    session.add(event)
    session.add(EvidenceAsset(event_id=event.id))
    if not await enqueue_event_correlations(session, event):
        raise HTTPException(status_code=409, detail="Correlation policy is unavailable")
    await session.commit()
    await session.refresh(event)
    await request.app.state.event_connections.broadcast(
        {"type": "event.created", "data": EventRead.model_validate(event).model_dump(mode="json")},
        organization_id=camera.organization_id,
    )
    return event


@router.post(
    "/agent/correlation-evaluations/process-next",
    response_model=CorrelationEvaluationRead,
    dependencies=[Depends(require_agent_key)],
)
async def process_next_correlation(
    session: SessionDependency,
) -> CorrelationEvaluationRead | Response:
    now = utc_now()
    row = (
        await session.execute(
            select(CorrelationEvaluation, RuleCorrelationPolicy, ContextSource, Event)
            .join(
                RuleCorrelationPolicy,
                RuleCorrelationPolicy.id == CorrelationEvaluation.policy_id,
            )
            .join(ContextSource, ContextSource.id == CorrelationEvaluation.source_id)
            .join(Event, Event.id == CorrelationEvaluation.event_id)
            .where(
                CorrelationEvaluation.status == CorrelationEvaluationStatus.PENDING,
                CorrelationEvaluation.due_at <= now,
            )
            .order_by(CorrelationEvaluation.due_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
    ).first()
    if row is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    evaluation, policy, source, event = row
    matched = await evaluate_correlation(session, evaluation, policy)
    if matched:
        existing_alert = await session.scalar(select(Alert.id).where(Alert.event_id == event.id))
        if existing_alert is None:
            await enqueue_event_alert(session, event)
    await session.commit()
    await session.refresh(evaluation)
    return evaluation_response(evaluation, source)
