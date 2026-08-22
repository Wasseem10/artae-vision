from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.auth import Actor, ActorDependency, EditorDependency
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.job_specs import (
    duration_for_legacy_column,
    spatial_id,
    spatial_name,
    validate_job_spec,
)
from video_intelligence_api.models import (
    Camera,
    Rule,
    RuleCompilation,
    RuleCompilationStatus,
    RuleStatus,
    Zone,
    utc_now,
)
from video_intelligence_api.rule_compiler import (
    COMPILER_VERSION,
    FULL_FRAME_ZONE_NAME,
    RuleCompilerProviderError,
    compile_rule_prompt,
)
from video_intelligence_api.schemas import (
    RuleCompilationAccept,
    RuleCompilationClarify,
    RuleCompilationCreate,
    RuleCompilationRead,
    RuleRead,
)
from video_intelligence_api.tenancy import tenant_camera, tenant_compilation, tenant_zone

router = APIRouter(prefix="/rule-compilations", tags=["rule compilations"])


def _key_part(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


async def _camera_zones(camera_id: str, session: SessionDependency, actor: Actor) -> list[Zone]:
    if await tenant_camera(session, actor, camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    zones = list(
        (
            await session.scalars(
                select(Zone).where(Zone.camera_id == camera_id).order_by(Zone.name)
            )
        ).all()
    )
    if not any(zone.name == FULL_FRAME_ZONE_NAME for zone in zones):
        automatic = Zone(
            camera_id=camera_id,
            name=FULL_FRAME_ZONE_NAME,
            points=[
                {"x": 0.0, "y": 0.0},
                {"x": 1.0, "y": 0.0},
                {"x": 1.0, "y": 1.0},
                {"x": 0.0, "y": 1.0},
            ],
        )
        session.add(automatic)
        await session.flush()
        zones.append(automatic)
    return zones


async def _compile_and_store(
    *,
    camera_id: str,
    prompt: str,
    revision: int,
    parent_id: str | None,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: Actor,
) -> RuleCompilation:
    zones = await _camera_zones(camera_id, session, actor)
    try:
        result = await compile_rule_prompt(settings, prompt, zones)
    except RuleCompilerProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    candidate = result.candidate
    compilation = RuleCompilation(
        camera_id=camera_id,
        parent_id=parent_id,
        revision=revision,
        prompt=prompt,
        provider=result.provider,
        provider_model=result.provider_model,
        compiler_version=COMPILER_VERSION,
        status=(
            RuleCompilationStatus.READY_FOR_REVIEW
            if result.compiled_rule
            else RuleCompilationStatus.NEEDS_CLARIFICATION
        ),
        compiled_rule=(
            result.compiled_rule.model_dump(mode="json") if result.compiled_rule else None
        ),
        explanation=candidate.explanation,
        clarification_question=candidate.clarification_question,
        warnings=result.warnings,
    )
    session.add(compilation)
    await session.commit()
    await session.refresh(compilation)
    return compilation


@router.post("", response_model=RuleCompilationRead, status_code=status.HTTP_201_CREATED)
async def compile_rule(
    payload: RuleCompilationCreate,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: EditorDependency,
) -> RuleCompilation:
    return await _compile_and_store(
        camera_id=payload.camera_id,
        prompt=payload.prompt,
        revision=1,
        parent_id=None,
        session=session,
        settings=settings,
        actor=actor,
    )


@router.get("", response_model=list[RuleCompilationRead])
async def list_compilations(
    session: SessionDependency,
    actor: ActorDependency,
    camera_id: Annotated[str | None, Query(max_length=36)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[RuleCompilation]:
    statement = (
        select(RuleCompilation)
        .join(Camera, Camera.id == RuleCompilation.camera_id)
        .where(Camera.organization_id == actor.organization_id)
        .order_by(RuleCompilation.created_at.desc())
        .limit(limit)
    )
    if camera_id:
        statement = statement.where(RuleCompilation.camera_id == camera_id)
    return list((await session.scalars(statement)).all())


@router.get("/{compilation_id}", response_model=RuleCompilationRead)
async def get_compilation(
    compilation_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: ActorDependency,
) -> RuleCompilation:
    compilation = await tenant_compilation(session, actor, compilation_id)
    if compilation is None:
        raise HTTPException(status_code=404, detail="Rule compilation not found")
    return compilation


@router.post(
    "/{compilation_id}/clarifications",
    response_model=RuleCompilationRead,
    status_code=status.HTTP_201_CREATED,
)
async def clarify_compilation(
    compilation_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: RuleCompilationClarify,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: EditorDependency,
) -> RuleCompilation:
    compilation = await tenant_compilation(session, actor, compilation_id)
    if compilation is None:
        raise HTTPException(status_code=404, detail="Rule compilation not found")
    if compilation.status == RuleCompilationStatus.ACCEPTED:
        raise HTTPException(status_code=409, detail="Accepted compilations cannot be revised")
    if compilation.status != RuleCompilationStatus.NEEDS_CLARIFICATION:
        raise HTTPException(status_code=409, detail="This compilation does not need clarification")

    revised_prompt = f"{compilation.prompt}\nClarification answer: {payload.answer.strip()}"
    if len(revised_prompt) > 2000:
        raise HTTPException(
            status_code=422,
            detail="The request plus clarification is longer than 2,000 characters.",
        )
    return await _compile_and_store(
        camera_id=compilation.camera_id,
        prompt=revised_prompt,
        revision=compilation.revision + 1,
        parent_id=compilation.id,
        session=session,
        settings=settings,
        actor=actor,
    )


@router.post(
    "/{compilation_id}/accept",
    response_model=RuleRead,
    status_code=status.HTTP_201_CREATED,
)
async def accept_compilation(
    compilation_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: RuleCompilationAccept,
    session: SessionDependency,
    actor: EditorDependency,
) -> Rule:
    compilation = await tenant_compilation(session, actor, compilation_id)
    if compilation is None:
        raise HTTPException(status_code=404, detail="Rule compilation not found")
    if compilation.status == RuleCompilationStatus.ACCEPTED:
        raise HTTPException(status_code=409, detail="Compilation has already been accepted")
    if (
        compilation.status != RuleCompilationStatus.READY_FOR_REVIEW
        or compilation.compiled_rule is None
    ):
        raise HTTPException(
            status_code=409,
            detail="Resolve clarification before accepting this rule",
        )

    try:
        compiled = validate_job_spec(compilation.compiled_rule)
    except ValidationError as exc:
        raise HTTPException(
            status_code=409,
            detail="Stored compilation no longer matches the supported rule schema.",
        ) from exc
    geometry_id = spatial_id(compiled)
    geometry_name = spatial_name(compiled)
    zone = await tenant_zone(session, actor, geometry_id)
    if zone is None or zone.camera_id != compilation.camera_id:
        raise HTTPException(status_code=409, detail="The compiled zone is no longer available")

    behavior = {
        "zone_dwell": "remains in",
        "zone_presence": "is present in",
        "zone_entry": "enters",
        "zone_exit": "exits",
        "count_threshold": "count changes in",
        "line_crossing": "crosses",
        "object_dwell": "remains in",
        "semantic_vision": "matches the visual condition in",
    }[compiled.rule_type]
    suggested_name = (
        f"Visual alert: {compilation.prompt[:180]}"
        if compiled.rule_type == "semantic_vision"
        else f"{compiled.object_class.title()} {behavior} {geometry_name}"
    )
    generated_key = (
        f"{_key_part(compiled.object_class)}-{_key_part(geometry_name)}-"
        f"{compiled.rule_type.replace('_', '-')}-{compilation.id[:8]}"
    )[:120]
    rule = Rule(
        camera_id=compilation.camera_id,
        zone_id=geometry_id,
        key=payload.key or generated_key,
        name=payload.name or suggested_name,
        rule_type=compiled.rule_type,
        object_class=compiled.object_class,
        duration_seconds=duration_for_legacy_column(compiled),
        minimum_confidence=compiled.minimum_confidence,
        absence_grace_seconds=compiled.absence_grace_seconds,
        status=RuleStatus.DRAFT,
        original_prompt=compilation.prompt,
        spec_version=compiled.schema_version,
        spec=compiled.model_dump(mode="json"),
    )
    session.add(rule)
    try:
        await session.flush()
        compilation.status = RuleCompilationStatus.ACCEPTED
        compilation.accepted_rule_id = rule.id
        compilation.reviewed_at = utc_now()
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Rule key already exists for this camera",
        ) from exc
    await session.refresh(rule)
    return rule
