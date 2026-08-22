from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import ValidationError
from sqlalchemy import func, select

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.dependencies import SessionDependency
from video_intelligence_api.job_specs import validate_job_spec
from video_intelligence_api.models import (
    Camera,
    ReplaySuiteRun,
    ReplaySuiteRunStatus,
    Rule,
    RuleCompilation,
    RuleStatus,
    VisualAgentPlan,
    VisualAgentPlanStatus,
    VisualAgentSimulation,
    utc_now,
)
from video_intelligence_api.schemas import (
    VisualAgentPlanApprove,
    VisualAgentPlanCreate,
    VisualAgentPlanRead,
    VisualAgentSimulationRead,
)
from video_intelligence_api.visual_agent_plans import (
    VisualAgentPlanDocument,
    compile_visual_agent_plan,
    required_capabilities,
    unsupported_capabilities,
)

router = APIRouter(prefix="/agent-plans", tags=["visual agent plans"])


async def _tenant_plan(
    session: SessionDependency, organization_id: str, plan_id: str
) -> VisualAgentPlan | None:
    return await session.scalar(
        select(VisualAgentPlan).where(
            VisualAgentPlan.id == plan_id,
            VisualAgentPlan.organization_id == organization_id,
        )
    )


@router.post("", response_model=VisualAgentPlanRead, status_code=status.HTTP_201_CREATED)
async def create_agent_plan(
    payload: VisualAgentPlanCreate,
    session: SessionDependency,
    actor: EditorDependency,
) -> VisualAgentPlan:
    rule = await session.scalar(
        select(Rule)
        .join(Camera, Camera.id == Rule.camera_id)
        .where(Rule.id == payload.rule_id, Camera.organization_id == actor.organization_id)
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if rule.spec is None:
        raise HTTPException(
            status_code=409, detail="This legacy rule does not have a compiled job specification"
        )
    try:
        spec = validate_job_spec(rule.spec)
    except ValidationError as exc:
        raise HTTPException(
            status_code=409, detail="The rule specification is no longer supported"
        ) from exc

    latest = await session.scalar(
        select(VisualAgentPlan)
        .where(VisualAgentPlan.camera_id == rule.camera_id)
        .order_by(VisualAgentPlan.revision.desc())
        .limit(1)
    )
    compilation = await session.scalar(
        select(RuleCompilation)
        .where(RuleCompilation.accepted_rule_id == rule.id)
        .order_by(RuleCompilation.created_at.desc())
        .limit(1)
    )
    prompt = rule.original_prompt or rule.name
    document = compile_visual_agent_plan(spec, prompt)
    plan = VisualAgentPlan(
        organization_id=actor.organization_id,
        camera_id=rule.camera_id,
        rule_id=rule.id,
        compilation_id=compilation.id if compilation else None,
        parent_id=latest.id if latest else None,
        revision=(latest.revision + 1) if latest else 1,
        prompt=prompt,
        plan=document.model_dump(mode="json"),
        required_capabilities=required_capabilities(document),
        unsupported_capabilities=unsupported_capabilities(document),
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return plan


@router.get("", response_model=list[VisualAgentPlanRead])
async def list_agent_plans(
    session: SessionDependency,
    actor: ActorDependency,
    camera_id: Annotated[str | None, Query(max_length=36)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[VisualAgentPlan]:
    statement = (
        select(VisualAgentPlan)
        .where(VisualAgentPlan.organization_id == actor.organization_id)
        .order_by(VisualAgentPlan.created_at.desc())
        .limit(limit)
    )
    if camera_id:
        statement = statement.where(VisualAgentPlan.camera_id == camera_id)
    return list((await session.scalars(statement)).all())


@router.get("/{plan_id}", response_model=VisualAgentPlanRead)
async def get_agent_plan(
    plan_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: ActorDependency,
) -> VisualAgentPlan:
    plan = await _tenant_plan(session, actor.organization_id, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Agent plan not found")
    return plan


@router.post(
    "/{plan_id}/simulate",
    response_model=VisualAgentSimulationRead,
    status_code=status.HTTP_201_CREATED,
)
async def simulate_agent_plan(
    plan_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: EditorDependency,
) -> VisualAgentSimulation:
    plan = await _tenant_plan(session, actor.organization_id, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Agent plan not found")
    document = VisualAgentPlanDocument.model_validate(plan.plan)
    trace = [
        {
            "node_id": node.id,
            "kind": node.kind,
            "title": node.title,
            "outcome": "blocked in simulation" if node.side_effect else "simulated successfully",
            "side_effect_performed": False,
        }
        for node in document.nodes
    ]
    simulation = VisualAgentSimulation(
        organization_id=actor.organization_id,
        plan_id=plan.id,
        trace=trace,
        summary=(
            f"Checked {len(trace)} steps. No alerts, webhooks, calls, tickets, "
            "gates, or locks were triggered."
        ),
    )
    session.add(simulation)
    await session.commit()
    await session.refresh(simulation)
    return simulation


async def _approve(
    plan: VisualAgentPlan,
    run: ReplaySuiteRun,
    session: SessionDependency,
    actor_subject: str,
) -> VisualAgentPlan:
    previous = list(
        (
            await session.scalars(
                select(VisualAgentPlan).where(
                    VisualAgentPlan.camera_id == plan.camera_id,
                    VisualAgentPlan.status == VisualAgentPlanStatus.APPROVED,
                    VisualAgentPlan.id != plan.id,
                )
            )
        ).all()
    )
    for existing in previous:
        existing.status = VisualAgentPlanStatus.SUPERSEDED
        existing_rule = await session.get(Rule, existing.rule_id)
        if existing_rule is not None:
            existing_rule.status = RuleStatus.PAUSED
    rule = await session.get(Rule, plan.rule_id)
    if rule is None:
        raise HTTPException(status_code=409, detail="The plan's rule is no longer available")
    rule.status = RuleStatus.ACTIVE
    plan.status = VisualAgentPlanStatus.APPROVED
    plan.regression_run_id = run.id
    plan.approved_by = actor_subject
    plan.approved_at = utc_now()
    await session.commit()
    await session.refresh(plan)
    return plan


@router.post("/{plan_id}/approve", response_model=VisualAgentPlanRead)
async def approve_agent_plan(
    plan_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: VisualAgentPlanApprove,
    session: SessionDependency,
    actor: EditorDependency,
) -> VisualAgentPlan:
    plan = await _tenant_plan(session, actor.organization_id, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Agent plan not found")
    if plan.unsupported_capabilities:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Connect the missing capabilities before deployment",
                "capabilities": plan.unsupported_capabilities,
            },
        )
    simulation_count = await session.scalar(
        select(func.count())
        .select_from(VisualAgentSimulation)
        .where(VisualAgentSimulation.plan_id == plan.id)
    )
    if not simulation_count:
        raise HTTPException(status_code=409, detail="Run the safe simulation before deployment")
    run = await session.scalar(
        select(ReplaySuiteRun).where(
            ReplaySuiteRun.id == payload.regression_run_id,
            ReplaySuiteRun.organization_id == actor.organization_id,
        )
    )
    if run is None or run.status != ReplaySuiteRunStatus.PASSED:
        raise HTTPException(
            status_code=409, detail="Deployment requires a passed replay regression run"
        )
    return await _approve(plan, run, session, actor.subject)


@router.post("/{plan_id}/rollback", response_model=VisualAgentPlanRead)
async def rollback_agent_plan(
    plan_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: EditorDependency,
) -> VisualAgentPlan:
    plan = await _tenant_plan(session, actor.organization_id, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Agent plan not found")
    if plan.status != VisualAgentPlanStatus.SUPERSEDED or plan.regression_run_id is None:
        raise HTTPException(
            status_code=409, detail="Only a previously approved plan can be restored"
        )
    run = await session.get(ReplaySuiteRun, plan.regression_run_id)
    if run is None or run.status != ReplaySuiteRunStatus.PASSED:
        raise HTTPException(
            status_code=409, detail="The plan no longer has a valid passed regression gate"
        )
    return await _approve(plan, run, session, actor.subject)
