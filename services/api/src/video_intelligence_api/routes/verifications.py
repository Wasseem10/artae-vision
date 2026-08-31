"""Operator inbox for semantic proposer-verifier decisions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.field_accuracy import record_case_label
from video_intelligence_api.live_verification import finalize_confirmed_event
from video_intelligence_api.media_access import signed_evidence_url
from video_intelligence_api.models import (
    Camera,
    Event,
    EvidenceAsset,
    FieldAccuracyLabel,
    Rule,
    VerificationCase,
    VerificationStatus,
    utc_now,
)
from video_intelligence_api.schemas import (
    EventRead,
    VerificationCaseRead,
    VerificationDecisionCreate,
)

router = APIRouter(tags=["live verification"])


def _case_response(
    case: VerificationCase,
    event: Event,
    camera: Camera,
    rule: Rule,
    evidence: EvidenceAsset | None,
    accuracy_label: FieldAccuracyLabel | None,
    settings: SettingsDependency,
) -> VerificationCaseRead:
    content_url = None
    if evidence is not None and evidence.storage_uri:
        content_url = signed_evidence_url(evidence.id, case.organization_id, settings)
    return VerificationCaseRead(
        id=case.id,
        organization_id=case.organization_id,
        event_id=case.event_id,
        status=case.status,
        camera_name=camera.name,
        rule_name=rule.name,
        proposer_model=case.proposer_model,
        verifier_model=case.verifier_model,
        proposer_confidence=case.proposer_confidence,
        verifier_confidence=case.verifier_confidence,
        proposal_summary=case.proposal_summary,
        verifier_summary=case.verifier_summary,
        reasoning=case.reasoning,
        decision_source=case.decision_source,
        reviewed_at=case.reviewed_at,
        reviewed_by=case.reviewed_by,
        evidence_id=evidence.id if evidence else None,
        evidence_status=evidence.status if evidence else None,
        evidence_content_url=content_url,
        accuracy_label=accuracy_label,
        event=EventRead.model_validate(event),
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def _case_query(case_id: str | None = None):
    statement = (
        select(VerificationCase, Event, Camera, Rule, EvidenceAsset, FieldAccuracyLabel)
        .join(Event, Event.id == VerificationCase.event_id)
        .join(Camera, Camera.id == Event.camera_id)
        .join(Rule, Rule.id == Event.rule_id)
        .outerjoin(EvidenceAsset, EvidenceAsset.event_id == Event.id)
        .outerjoin(
            FieldAccuracyLabel,
            FieldAccuracyLabel.verification_case_id == VerificationCase.id,
        )
    )
    if case_id is not None:
        statement = statement.where(VerificationCase.id == case_id)
    return statement


@router.get("/verification-cases", response_model=list[VerificationCaseRead])
async def list_verification_cases(
    session: SessionDependency,
    settings: SettingsDependency,
    actor: ActorDependency,
    case_status: Annotated[VerificationStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[VerificationCaseRead]:
    statement = (
        _case_query()
        .where(VerificationCase.organization_id == actor.organization_id)
        .order_by(VerificationCase.created_at.desc())
        .limit(limit)
    )
    if case_status is not None:
        statement = statement.where(VerificationCase.status == case_status)
    rows = (await session.execute(statement)).all()
    return [_case_response(*row, settings) for row in rows]


@router.get("/verification-cases/{case_id}", response_model=VerificationCaseRead)
async def get_verification_case(
    case_id: str,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: ActorDependency,
) -> VerificationCaseRead:
    row = (
        await session.execute(
            _case_query(case_id).where(
                VerificationCase.organization_id == actor.organization_id
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Verification case not found")
    return _case_response(*row, settings)


@router.post(
    "/verification-cases/{case_id}/decision",
    response_model=VerificationCaseRead,
)
async def decide_verification_case(
    case_id: str,
    payload: VerificationDecisionCreate,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: EditorDependency,
) -> VerificationCaseRead:
    row = (
        await session.execute(
            _case_query(case_id).where(
                VerificationCase.organization_id == actor.organization_id
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Verification case not found")
    case, event, camera, rule, evidence, accuracy_label = row
    desired = VerificationStatus(payload.status)
    if event.verification_status == VerificationStatus.CONFIRMED:
        if desired == VerificationStatus.REJECTED:
            raise HTTPException(
                status_code=409,
                detail="A released event cannot be rejected after alerts or actions may have run",
            )
        return _case_response(case, event, camera, rule, evidence, accuracy_label, settings)

    now = utc_now()
    case.status = desired
    case.reasoning = payload.reasoning
    case.decision_source = "operator"
    case.reviewed_at = now
    case.reviewed_by = actor.subject
    event.verification_status = desired
    event.verified_at = now
    event.verified_by = actor.subject
    if desired == VerificationStatus.CONFIRMED:
        await finalize_confirmed_event(session, event, camera)
    accuracy_label, _ = await record_case_label(
        session,
        case=case,
        event=event,
        camera=camera,
        rule=rule,
        event_occurred=desired == VerificationStatus.CONFIRMED,
        source="operator_verification",
        notes=payload.reasoning,
        environment_tags=list(payload.environment_tags),
        reviewed_by=actor.subject,
    )
    await session.commit()
    await session.refresh(case)
    await session.refresh(event)
    if desired == VerificationStatus.CONFIRMED:
        await request.app.state.event_connections.broadcast(
            {
                "type": "event.created",
                "data": EventRead.model_validate(event).model_dump(mode="json"),
            },
            organization_id=camera.organization_id,
        )
    return _case_response(case, event, camera, rule, evidence, accuracy_label, settings)
