"""Closed-loop field labels, accuracy reports, audits, and missed-event capture."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.dependencies import SessionDependency
from video_intelligence_api.field_accuracy import (
    accuracy_policy,
    record_case_label,
    refresh_accuracy_snapshot,
)
from video_intelligence_api.models import (
    AccuracyLabelOutcome,
    Camera,
    Event,
    FieldAccuracyLabel,
    FieldAccuracySnapshot,
    RecordingSegment,
    Rule,
    RuleAccuracyPolicy,
    VerificationCase,
    VerificationStatus,
    new_id,
    utc_now,
)
from video_intelligence_api.schemas import (
    FieldAccuracyLabelRead,
    FieldAccuracyPolicyRead,
    FieldAccuracyPolicyUpdate,
    FieldAccuracyReportRead,
    FieldAccuracySnapshotRead,
    FieldMissCreate,
    VerificationAuditCreate,
)
from video_intelligence_api.tenancy import tenant_rule

router = APIRouter(prefix="/field-accuracy", tags=["field accuracy"])


async def _report(
    session: SessionDependency,
    camera: Camera,
    rule: Rule,
) -> FieldAccuracyReportRead:
    policy = await accuracy_policy(session, rule.id)
    latest = await session.scalar(
        select(FieldAccuracySnapshot)
        .where(FieldAccuracySnapshot.rule_id == rule.id)
        .order_by(FieldAccuracySnapshot.created_at.desc(), FieldAccuracySnapshot.id.desc())
        .limit(1)
    )
    unlabeled = int(
        await session.scalar(
            select(func.count())
            .select_from(VerificationCase)
            .join(Event, Event.id == VerificationCase.event_id)
            .outerjoin(
                FieldAccuracyLabel,
                FieldAccuracyLabel.verification_case_id == VerificationCase.id,
            )
            .where(
                Event.rule_id == rule.id,
                VerificationCase.status.in_(
                    [VerificationStatus.CONFIRMED, VerificationStatus.REJECTED]
                ),
                FieldAccuracyLabel.id.is_(None),
            )
        )
        or 0
    )
    return FieldAccuracyReportRead(
        camera_id=camera.id,
        camera_name=camera.name,
        rule_id=rule.id,
        rule_name=rule.name,
        policy=FieldAccuracyPolicyRead(**asdict(policy)),
        latest_snapshot=(FieldAccuracySnapshotRead.model_validate(latest) if latest else None),
        unlabeled_case_count=unlabeled,
    )


@router.get("/rules", response_model=list[FieldAccuracyReportRead])
async def list_field_accuracy_reports(
    session: SessionDependency,
    actor: ActorDependency,
    camera_id: Annotated[str | None, Query(max_length=36)] = None,
) -> list[FieldAccuracyReportRead]:
    statement = (
        select(Camera, Rule)
        .join(Rule, Rule.camera_id == Camera.id)
        .where(
            Camera.organization_id == actor.organization_id,
            Rule.rule_type == "semantic_vision",
        )
        .order_by(Camera.name, Rule.name)
    )
    if camera_id is not None:
        statement = statement.where(Camera.id == camera_id)
    rows = (await session.execute(statement)).all()
    return [await _report(session, camera, rule) for camera, rule in rows]


@router.put("/rules/{rule_id}/policy", response_model=FieldAccuracyReportRead)
async def update_field_accuracy_policy(
    rule_id: str,
    payload: FieldAccuracyPolicyUpdate,
    session: SessionDependency,
    actor: EditorDependency,
) -> FieldAccuracyReportRead:
    rule = await tenant_rule(session, actor, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if rule.rule_type != "semantic_vision":
        raise HTTPException(status_code=409, detail="Accuracy policies apply to semantic jobs")
    camera = await session.get(Camera, rule.camera_id)
    if camera is None or camera.organization_id != actor.organization_id:
        raise HTTPException(status_code=404, detail="Camera not found")
    stored = await session.scalar(
        select(RuleAccuracyPolicy).where(RuleAccuracyPolicy.rule_id == rule.id)
    )
    now = utc_now()
    values = payload.model_dump()
    if stored is None:
        stored = RuleAccuracyPolicy(
            id=new_id(),
            organization_id=actor.organization_id,
            camera_id=camera.id,
            rule_id=rule.id,
            updated_by=actor.subject,
            created_at=now,
            updated_at=now,
            **values,
        )
        session.add(stored)
    else:
        for field, value in values.items():
            setattr(stored, field, value)
        stored.updated_by = actor.subject
        stored.updated_at = now
    label_count = int(
        await session.scalar(
            select(func.count())
            .select_from(FieldAccuracyLabel)
            .where(FieldAccuracyLabel.rule_id == rule.id)
        )
        or 0
    )
    if label_count:
        await refresh_accuracy_snapshot(
            session,
            organization_id=actor.organization_id,
            camera_id=camera.id,
            rule_id=rule.id,
        )
    await session.commit()
    return await _report(session, camera, rule)


@router.get("/labels", response_model=list[FieldAccuracyLabelRead])
async def list_field_accuracy_labels(
    session: SessionDependency,
    actor: ActorDependency,
    rule_id: Annotated[str | None, Query(max_length=36)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[FieldAccuracyLabel]:
    statement = (
        select(FieldAccuracyLabel)
        .where(FieldAccuracyLabel.organization_id == actor.organization_id)
        .order_by(FieldAccuracyLabel.created_at.desc())
        .limit(limit)
    )
    if rule_id is not None:
        statement = statement.where(FieldAccuracyLabel.rule_id == rule_id)
    return list((await session.scalars(statement)).all())


@router.post(
    "/verification-cases/{case_id}/audit",
    response_model=FieldAccuracyLabelRead,
    status_code=status.HTTP_201_CREATED,
)
async def audit_verification_case(
    case_id: str,
    payload: VerificationAuditCreate,
    session: SessionDependency,
    actor: EditorDependency,
) -> FieldAccuracyLabel:
    row = (
        await session.execute(
            select(VerificationCase, Event, Camera, Rule)
            .join(Event, Event.id == VerificationCase.event_id)
            .join(Camera, Camera.id == Event.camera_id)
            .join(Rule, Rule.id == Event.rule_id)
            .where(
                VerificationCase.id == case_id,
                VerificationCase.organization_id == actor.organization_id,
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Verification case not found")
    case, event, camera, rule = row
    if case.status not in {VerificationStatus.CONFIRMED, VerificationStatus.REJECTED}:
        raise HTTPException(status_code=409, detail="Decide the pending case before auditing it")
    existing = await session.scalar(
        select(FieldAccuracyLabel).where(FieldAccuracyLabel.verification_case_id == case.id)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="This case already has a field label")
    label, _ = await record_case_label(
        session,
        case=case,
        event=event,
        camera=camera,
        rule=rule,
        event_occurred=payload.actual_outcome == "event",
        source="operator_audit",
        notes=payload.reasoning,
        environment_tags=list(payload.environment_tags),
        reviewed_by=actor.subject,
    )
    await session.commit()
    await session.refresh(label)
    return label


@router.post(
    "/misses",
    response_model=FieldAccuracyLabelRead,
    status_code=status.HTTP_201_CREATED,
)
async def report_missed_event(
    payload: FieldMissCreate,
    session: SessionDependency,
    actor: EditorDependency,
) -> FieldAccuracyLabel:
    rule = await tenant_rule(session, actor, payload.rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if rule.rule_type != "semantic_vision":
        raise HTTPException(
            status_code=409,
            detail="Field semantic scoring requires a semantic job",
        )
    camera = await session.get(Camera, rule.camera_id)
    if camera is None or camera.organization_id != actor.organization_id:
        raise HTTPException(status_code=404, detail="Camera not found")
    if payload.recording_id is not None:
        recording = await session.scalar(
            select(RecordingSegment).where(
                RecordingSegment.id == payload.recording_id,
                RecordingSegment.organization_id == actor.organization_id,
                RecordingSegment.camera_id == camera.id,
            )
        )
        if recording is None:
            raise HTTPException(status_code=404, detail="Recording not found")
    label = FieldAccuracyLabel(
        id=new_id(),
        organization_id=actor.organization_id,
        camera_id=camera.id,
        rule_id=rule.id,
        recording_id=payload.recording_id,
        outcome=AccuracyLabelOutcome.FALSE_NEGATIVE,
        source="reported_miss",
        environment_tags=list(payload.environment_tags),
        notes=payload.reasoning,
        occurred_at=payload.occurred_at,
        reviewed_by=actor.subject,
        created_at=utc_now(),
    )
    session.add(label)
    await refresh_accuracy_snapshot(
        session,
        organization_id=actor.organization_id,
        camera_id=camera.id,
        rule_id=rule.id,
    )
    await session.commit()
    await session.refresh(label)
    return label
