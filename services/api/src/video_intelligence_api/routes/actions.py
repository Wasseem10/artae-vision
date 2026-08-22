from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.alert_secrets import (
    AlertSecretError,
    decrypt_alert_secret,
    encrypt_alert_secret,
)
from video_intelligence_api.auth import ActorDependency, AdminDependency, EditorDependency
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.guarded_actions import (
    action_definition,
    action_registry_payload,
    validate_connector_scopes,
)
from video_intelligence_api.models import (
    ActionExecution,
    ActionExecutionStatus,
    Alert,
    AlertStatus,
    Camera,
    ConnectorType,
    Event,
    IntegrationConnector,
    Rule,
    RuleActionBinding,
    utc_now,
)
from video_intelligence_api.schemas import (
    ActionDecision,
    ActionExecutionAssignment,
    ActionExecutionRead,
    ActionExecutionResult,
    ActionWorkerClaim,
    ConnectorCreate,
    ConnectorRead,
    ConnectorUpdate,
    RuleActionBindingCreate,
    RuleActionBindingRead,
)
from video_intelligence_api.security import require_agent_key
from video_intelligence_api.tenancy import tenant_rule

router = APIRouter(tags=["guarded actions"])


def connector_response(connector: IntegrationConnector) -> ConnectorRead:
    return ConnectorRead.model_validate(connector)


def binding_response(
    binding: RuleActionBinding, connector: IntegrationConnector
) -> RuleActionBindingRead:
    return RuleActionBindingRead(
        **{
            column: getattr(binding, column)
            for column in (
                "id",
                "organization_id",
                "rule_id",
                "connector_id",
                "action_type",
                "risk_level",
                "approval_mode",
                "rate_limit_per_minute",
                "payload_template",
                "enabled",
                "created_at",
                "updated_at",
            )
        },
        connector_name=connector.name,
    )


def execution_response(
    execution: ActionExecution, connector: IntegrationConnector
) -> ActionExecutionRead:
    return ActionExecutionRead(
        **{
            column: getattr(execution, column)
            for column in (
                "id",
                "organization_id",
                "alert_id",
                "event_id",
                "binding_id",
                "connector_id",
                "action_type",
                "risk_level",
                "status",
                "idempotency_key",
                "payload",
                "attempt_count",
                "manual_retry_count",
                "next_attempt_at",
                "last_status_code",
                "last_error",
                "approved_by",
                "approved_at",
                "denied_by",
                "denied_at",
                "denial_reason",
                "completed_at",
                "created_at",
                "updated_at",
            )
        },
        connector_name=connector.name,
    )


async def tenant_execution(
    session: SessionDependency, organization_id: str, execution_id: str
) -> tuple[ActionExecution, IntegrationConnector] | None:
    return (
        await session.execute(
            select(ActionExecution, IntegrationConnector)
            .join(
                IntegrationConnector,
                IntegrationConnector.id == ActionExecution.connector_id,
            )
            .where(
                ActionExecution.id == execution_id,
                ActionExecution.organization_id == organization_id,
            )
        )
    ).first()


@router.get("/action-registry")
async def get_action_registry(actor: ActorDependency) -> dict[str, object]:
    del actor
    return action_registry_payload()


@router.post("/connectors", response_model=ConnectorRead, status_code=status.HTTP_201_CREATED)
async def create_connector(
    payload: ConnectorCreate,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: AdminDependency,
) -> ConnectorRead:
    if (
        settings.environment == "production"
        and payload.connector_type != ConnectorType.MOCK
        and payload.endpoint_url is not None
        and payload.endpoint_url.scheme != "https"
    ):
        raise HTTPException(status_code=422, detail="Production connectors must use HTTPS")
    try:
        scopes = validate_connector_scopes(payload.connector_type, payload.scopes)
        credential = encrypt_alert_secret(payload.credential, settings)
    except (ValueError, AlertSecretError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    connector = IntegrationConnector(
        organization_id=actor.organization_id,
        name=payload.name,
        connector_type=payload.connector_type,
        endpoint_url=str(payload.endpoint_url) if payload.endpoint_url else None,
        credential_encrypted=credential,
        scopes=scopes,
        enabled=payload.enabled,
        timeout_seconds=payload.timeout_seconds,
        max_attempts=payload.max_attempts,
    )
    session.add(connector)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Connector name already exists") from exc
    await session.refresh(connector)
    return connector_response(connector)


@router.get("/connectors", response_model=list[ConnectorRead])
async def list_connectors(
    session: SessionDependency, actor: ActorDependency
) -> list[ConnectorRead]:
    connectors = list(
        (
            await session.scalars(
                select(IntegrationConnector)
                .where(IntegrationConnector.organization_id == actor.organization_id)
                .order_by(IntegrationConnector.name)
            )
        ).all()
    )
    return [connector_response(connector) for connector in connectors]


@router.patch("/connectors/{connector_id}", response_model=ConnectorRead)
async def update_connector(
    connector_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: ConnectorUpdate,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: AdminDependency,
) -> ConnectorRead:
    connector = await session.scalar(
        select(IntegrationConnector).where(
            IntegrationConnector.id == connector_id,
            IntegrationConnector.organization_id == actor.organization_id,
        )
    )
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    changes = payload.model_dump(exclude_unset=True)
    credential = changes.pop("credential", None)
    endpoint_url = changes.get("endpoint_url")
    if (
        settings.environment == "production"
        and endpoint_url is not None
        and endpoint_url.scheme != "https"
    ):
        raise HTTPException(status_code=422, detail="Production connectors must use HTTPS")
    if credential is not None:
        try:
            connector.credential_encrypted = encrypt_alert_secret(credential, settings)
        except AlertSecretError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    for field, value in changes.items():
        setattr(connector, field, str(value) if field == "endpoint_url" and value else value)
    await session.commit()
    await session.refresh(connector)
    return connector_response(connector)


@router.post(
    "/rules/{rule_id}/actions",
    response_model=RuleActionBindingRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_action_binding(
    rule_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: RuleActionBindingCreate,
    session: SessionDependency,
    actor: AdminDependency,
) -> RuleActionBindingRead:
    if await tenant_rule(session, actor, rule_id) is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    connector = await session.scalar(
        select(IntegrationConnector).where(
            IntegrationConnector.id == payload.connector_id,
            IntegrationConnector.organization_id == actor.organization_id,
        )
    )
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    try:
        definition = action_definition(payload.action_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not definition.available:
        raise HTTPException(
            status_code=409,
            detail=(
                "Physical-system actions are disabled until an explicitly authorized adapter exists"
            ),
        )
    if definition.required_scope not in connector.scopes:
        raise HTTPException(
            status_code=409,
            detail=f"Connector is missing required scope '{definition.required_scope}'",
        )
    approval_mode = payload.approval_mode or definition.default_approval
    binding = RuleActionBinding(
        organization_id=actor.organization_id,
        rule_id=rule_id,
        connector_id=connector.id,
        action_type=definition.action_type,
        risk_level=definition.risk_level,
        approval_mode=approval_mode,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        payload_template=payload.payload_template,
        enabled=payload.enabled,
    )
    session.add(binding)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="This action is already attached") from exc
    await session.refresh(binding)
    return binding_response(binding, connector)


@router.get("/rules/{rule_id}/actions", response_model=list[RuleActionBindingRead])
async def list_action_bindings(
    rule_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: ActorDependency,
) -> list[RuleActionBindingRead]:
    if await tenant_rule(session, actor, rule_id) is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    rows = (
        await session.execute(
            select(RuleActionBinding, IntegrationConnector)
            .join(
                IntegrationConnector,
                IntegrationConnector.id == RuleActionBinding.connector_id,
            )
            .where(RuleActionBinding.rule_id == rule_id)
            .order_by(RuleActionBinding.created_at)
        )
    ).all()
    return [binding_response(binding, connector) for binding, connector in rows]


@router.get("/action-executions", response_model=list[ActionExecutionRead])
async def list_action_executions(
    session: SessionDependency,
    actor: ActorDependency,
    execution_status: Annotated[ActionExecutionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ActionExecutionRead]:
    statement = (
        select(ActionExecution, IntegrationConnector)
        .join(IntegrationConnector, IntegrationConnector.id == ActionExecution.connector_id)
        .where(ActionExecution.organization_id == actor.organization_id)
        .order_by(ActionExecution.created_at.desc())
        .limit(limit)
    )
    if execution_status is not None:
        statement = statement.where(ActionExecution.status == execution_status)
    rows = (await session.execute(statement)).all()
    return [execution_response(execution, connector) for execution, connector in rows]


@router.post("/action-executions/{execution_id}/approve", response_model=ActionExecutionRead)
async def approve_action_execution(
    execution_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: ActionDecision,
    session: SessionDependency,
    actor: EditorDependency,
) -> ActionExecutionRead:
    del payload
    row = await tenant_execution(session, actor.organization_id, execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Action execution not found")
    execution, connector = row
    if execution.status != ActionExecutionStatus.AWAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="Action is not awaiting approval")
    execution.status = ActionExecutionStatus.QUEUED
    execution.approved_by = actor.subject
    execution.approved_at = utc_now()
    execution.next_attempt_at = utc_now()
    await session.commit()
    await session.refresh(execution)
    return execution_response(execution, connector)


@router.post("/action-executions/{execution_id}/deny", response_model=ActionExecutionRead)
async def deny_action_execution(
    execution_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: ActionDecision,
    session: SessionDependency,
    actor: EditorDependency,
) -> ActionExecutionRead:
    row = await tenant_execution(session, actor.organization_id, execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Action execution not found")
    execution, connector = row
    if execution.status != ActionExecutionStatus.AWAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="Action is not awaiting approval")
    execution.status = ActionExecutionStatus.DENIED
    execution.denied_by = actor.subject
    execution.denied_at = utc_now()
    execution.denial_reason = payload.reason or "Denied by operator"
    execution.completed_at = utc_now()
    await session.commit()
    await session.refresh(execution)
    return execution_response(execution, connector)


@router.post("/action-executions/{execution_id}/retry", response_model=ActionExecutionRead)
async def retry_action_execution(
    execution_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: EditorDependency,
) -> ActionExecutionRead:
    row = await tenant_execution(session, actor.organization_id, execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Action execution not found")
    execution, connector = row
    if execution.status != ActionExecutionStatus.DEAD_LETTERED:
        raise HTTPException(status_code=409, detail="Only dead-lettered actions can be retried")
    execution.status = ActionExecutionStatus.QUEUED
    execution.manual_retry_count += 1
    execution.attempt_count = 0
    execution.next_attempt_at = utc_now()
    execution.last_error = "Manually requeued by operator"
    execution.completed_at = None
    await session.commit()
    await session.refresh(execution)
    return execution_response(execution, connector)


@router.post(
    "/agent/action-executions/claim",
    response_model=ActionExecutionAssignment | None,
    dependencies=[Depends(require_agent_key)],
)
async def claim_action_execution(
    payload: ActionWorkerClaim,
    session: SessionDependency,
    settings: SettingsDependency,
) -> ActionExecutionAssignment | Response:
    now = utc_now()
    row = (
        await session.execute(
            select(
                ActionExecution,
                IntegrationConnector,
                RuleActionBinding,
                Alert,
                Event,
                Camera,
                Rule,
            )
            .join(
                IntegrationConnector,
                IntegrationConnector.id == ActionExecution.connector_id,
            )
            .join(RuleActionBinding, RuleActionBinding.id == ActionExecution.binding_id)
            .join(Alert, Alert.id == ActionExecution.alert_id)
            .join(Event, Event.id == ActionExecution.event_id)
            .join(Camera, Camera.id == Event.camera_id)
            .join(Rule, Rule.id == Event.rule_id)
            .where(
                Alert.status == AlertStatus.OPEN,
                IntegrationConnector.enabled.is_(True),
                RuleActionBinding.enabled.is_(True),
                ActionExecution.next_attempt_at <= now,
                or_(
                    ActionExecution.status.in_(
                        [ActionExecutionStatus.QUEUED, ActionExecutionStatus.RETRYING]
                    ),
                    (
                        (ActionExecution.status == ActionExecutionStatus.RUNNING)
                        & (ActionExecution.lease_expires_at < now)
                    ),
                ),
            )
            .order_by(ActionExecution.next_attempt_at, ActionExecution.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
    ).first()
    if row is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    execution, connector, binding, alert, _event, camera, rule = row
    if execution.attempt_count >= connector.max_attempts:
        execution.status = ActionExecutionStatus.DEAD_LETTERED
        execution.last_error = "Maximum action attempts reached after expired leases"
        execution.completed_at = now
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    recent_count = await session.scalar(
        select(func.count())
        .select_from(ActionExecution)
        .where(
            ActionExecution.binding_id == binding.id,
            ActionExecution.status == ActionExecutionStatus.SUCCEEDED,
            ActionExecution.completed_at >= now - timedelta(minutes=1),
        )
    )
    if (recent_count or 0) >= binding.rate_limit_per_minute:
        execution.status = ActionExecutionStatus.RETRYING
        execution.next_attempt_at = now + timedelta(minutes=1)
        execution.last_error = "Deferred by per-minute action rate limit"
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        credential = decrypt_alert_secret(connector.credential_encrypted, settings)
    except AlertSecretError as exc:
        execution.status = ActionExecutionStatus.DEAD_LETTERED
        execution.last_error = str(exc)
        execution.completed_at = now
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    execution.status = ActionExecutionStatus.RUNNING
    execution.worker_id = payload.worker_id
    execution.lease_expires_at = now + timedelta(seconds=settings.alert_lease_seconds)
    execution.attempt_count += 1
    await session.commit()
    return ActionExecutionAssignment(
        execution_id=execution.id,
        connector_type=connector.connector_type,
        endpoint_url=connector.endpoint_url,
        credential=credential,
        timeout_seconds=connector.timeout_seconds,
        idempotency_key=execution.idempotency_key,
        action_type=execution.action_type,
        payload={
            **execution.payload,
            "alert_id": alert.id,
            "camera_name": camera.name,
            "rule_name": rule.name,
        },
    )


@router.post(
    "/agent/action-executions/{execution_id}/result",
    response_model=ActionExecutionRead,
    dependencies=[Depends(require_agent_key)],
)
async def complete_action_execution(
    execution_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: ActionExecutionResult,
    session: SessionDependency,
    settings: SettingsDependency,
) -> ActionExecutionRead:
    row = (
        await session.execute(
            select(ActionExecution, IntegrationConnector)
            .join(
                IntegrationConnector,
                IntegrationConnector.id == ActionExecution.connector_id,
            )
            .where(ActionExecution.id == execution_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Action execution not found")
    execution, connector = row
    if (
        execution.worker_id != payload.worker_id
        or execution.status != ActionExecutionStatus.RUNNING
    ):
        raise HTTPException(status_code=409, detail="Worker does not hold this action lease")
    now = utc_now()
    execution.last_status_code = payload.status_code
    execution.last_error = payload.error
    execution.worker_id = None
    execution.lease_expires_at = None
    if payload.outcome == "succeeded":
        execution.status = ActionExecutionStatus.SUCCEEDED
        execution.completed_at = now
    elif (
        payload.outcome == "permanent_failure" or execution.attempt_count >= connector.max_attempts
    ):
        execution.status = ActionExecutionStatus.DEAD_LETTERED
        execution.completed_at = now
        if not payload.error:
            execution.last_error = "Action permanently failed or exhausted its retries"
    else:
        execution.status = ActionExecutionStatus.RETRYING
        delay = min(
            settings.alert_retry_base_seconds * 2 ** max(execution.attempt_count - 1, 0),
            settings.alert_retry_max_seconds,
        )
        execution.next_attempt_at = now + timedelta(seconds=delay)
    await session.commit()
    await session.refresh(execution)
    return execution_response(execution, connector)
