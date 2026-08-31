"""Durable labeled-video replay evaluation endpoints."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from pathlib import Path as FilePath
from typing import Annotated
from urllib.parse import unquote
from uuid import NAMESPACE_URL, uuid4, uuid5

import anyio
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from sqlalchemy import or_, select

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.calibration import SCENARIO_BY_KEY
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.evaluation_scoring import TemporalInterval, score_intervals
from video_intelligence_api.execution_plans import plan_job
from video_intelligence_api.job_specs import (
    duration_for_legacy_column,
    spatial_id,
    validate_job_spec,
)
from video_intelligence_api.live_verification import finalize_confirmed_event
from video_intelligence_api.models import (
    Camera,
    Event,
    EvidenceAsset,
    EvidenceStatus,
    ReplayEvaluation,
    ReplayEvaluationStatus,
    ReplaySuite,
    ReplaySuiteRun,
    ReplaySuiteRunStatus,
    RuleCompilationStatus,
    RuleStatus,
    Zone,
    new_id,
    utc_now,
)
from video_intelligence_api.routes.rule_compilations import _compile_and_store
from video_intelligence_api.schemas import (
    AgentRuleConfig,
    AgentZoneConfig,
    EvaluationInterval,
    EventRead,
    ReplayActionDispatch,
    ReplayEvaluationCreate,
    ReplayEvaluationRead,
    ReplayEvaluationScore,
    ReplaySuiteCreate,
    ReplaySuiteRead,
    ReplaySuiteRunRead,
    ReplayUploadRead,
    ReplayWorkerAssignment,
    ReplayWorkerHeartbeat,
    ReplayWorkerResult,
    WorkerClaimRequest,
)
from video_intelligence_api.security import (
    EdgePrincipal,
    ensure_edge_organization,
    require_edge_device,
)
from video_intelligence_api.tenancy import (
    tenant_replay_evaluation,
    tenant_replay_suite,
    tenant_replay_suite_run,
    tenant_rule,
)

router = APIRouter(prefix="/evaluations", tags=["replay evaluations"])
suite_router = APIRouter(prefix="/evaluation-suites", tags=["replay regression suites"])
agent_router = APIRouter(prefix="/agent/evaluations", tags=["replay evaluation worker"])

ACTIVE_SUITE_RUN_STATUSES = {
    ReplaySuiteRunStatus.QUEUED,
    ReplaySuiteRunStatus.RUNNING,
}

ALLOWED_REPLAY_EXTENSIONS = {".avi", ".mkv", ".mov", ".mp4", ".webm"}
ALLOWED_REPLAY_MEDIA_TYPES = {
    "application/octet-stream",
    "video/avi",
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
    "video/x-msvideo",
}


def _copy_uploaded_evidence(source: FilePath, target: FilePath) -> tuple[int, str]:
    digest = hashlib.sha256()
    size_bytes = 0
    with source.open("rb") as input_file, target.open("xb") as output_file:
        while chunk := input_file.read(1024 * 1024):
            digest.update(chunk)
            size_bytes += len(chunk)
            output_file.write(chunk)
    return size_bytes, digest.hexdigest()


def _uploaded_media_type(source: FilePath) -> str:
    return {
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".mov": "video/quicktime",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
    }.get(source.suffix.casefold(), "video/mp4")


def _interval_payload(interval: EvaluationInterval) -> dict:
    return interval.model_dump(mode="json", exclude_none=True)


def _temporal_interval(interval: dict) -> TemporalInterval:
    parsed = EvaluationInterval.model_validate(interval)
    return TemporalInterval(**parsed.model_dump())


def _reset_for_queue(evaluation: ReplayEvaluation) -> None:
    evaluation.status = ReplayEvaluationStatus.QUEUED
    evaluation.worker_id = None
    evaluation.lease_expires_at = None
    evaluation.started_at = None
    evaluation.completed_at = None
    evaluation.last_error = None
    evaluation.predicted_intervals = []
    evaluation.metrics = {}
    evaluation.provider_requests = 0
    evaluation.input_tokens = 0
    evaluation.output_tokens = 0
    evaluation.estimated_cost_usd = 0
    evaluation.processed_seconds = 0
    evaluation.progress_percent = 0
    evaluation.last_progress_at = None


async def _active_suite_runs(
    session: SessionDependency,
    organization_id: str,
) -> list[ReplaySuiteRun]:
    return list(
        (
            await session.scalars(
                select(ReplaySuiteRun).where(
                    ReplaySuiteRun.organization_id == organization_id,
                    ReplaySuiteRun.status.in_(ACTIVE_SUITE_RUN_STATUSES),
                )
            )
        ).all()
    )


def _suite_thresholds(suite: ReplaySuite) -> dict[str, object]:
    return {
        "minimum_macro_f1": suite.minimum_macro_f1,
        "minimum_macro_recall": suite.minimum_macro_recall,
        "maximum_false_positives": suite.maximum_false_positives,
        "maximum_estimated_cost_usd": suite.maximum_estimated_cost_usd,
        "require_pricing": suite.require_pricing,
    }


def _gate(
    key: str,
    label: str,
    *,
    actual: object,
    operator: str,
    threshold: object,
    passed: bool,
) -> dict[str, object]:
    return {
        "key": key,
        "label": label,
        "actual": actual,
        "operator": operator,
        "threshold": threshold,
        "passed": passed,
    }


def _scenario_metrics(scored: list[ReplayEvaluation]) -> dict[str, dict[str, object]]:
    """Keep suite averages from hiding a weak capability or evidence source."""

    grouped: dict[str, list[ReplayEvaluation]] = {}
    for item in scored:
        grouped.setdefault(item.scenario_key or "unclassified", []).append(item)
    metrics: dict[str, dict[str, object]] = {}
    for key, items in grouped.items():
        count = len(items)
        metrics[key] = {
            "evaluation_count": count,
            "macro_precision": round(
                sum(float(item.metrics.get("precision", 0)) for item in items) / count,
                6,
            ),
            "macro_recall": round(
                sum(float(item.metrics.get("recall", 0)) for item in items) / count,
                6,
            ),
            "macro_f1": round(
                sum(float(item.metrics.get("f1", 0)) for item in items) / count,
                6,
            ),
            "false_positives": sum(int(item.metrics.get("false_positives", 0)) for item in items),
            "source_kinds": sorted({item.source_kind for item in items}),
            "variants": sorted({item.scenario_variant for item in items}),
        }
    return metrics


async def _refresh_suite_runs_for_evaluation(
    session: SessionDependency,
    evaluation: ReplayEvaluation,
) -> None:
    """Update every active batch containing this evaluation and freeze completed results."""

    for run in await _active_suite_runs(session, evaluation.organization_id):
        if evaluation.id not in run.evaluation_ids:
            continue
        evaluations = list(
            (
                await session.scalars(
                    select(ReplayEvaluation).where(
                        ReplayEvaluation.organization_id == evaluation.organization_id,
                        ReplayEvaluation.id.in_(run.evaluation_ids),
                    )
                )
            ).all()
        )
        by_id = {item.id: item for item in evaluations}
        if len(by_id) != len(run.evaluation_ids):
            run.status = ReplaySuiteRunStatus.FAILED
            run.metrics = {"error": "One or more replay baselines were removed"}
            run.completed_at = utc_now()
            continue
        ordered = [by_id[evaluation_id] for evaluation_id in run.evaluation_ids]
        if any(item.status == ReplayEvaluationStatus.RUNNING for item in ordered):
            run.status = ReplaySuiteRunStatus.RUNNING
        completed = [
            item
            for item in ordered
            if item.status in {ReplayEvaluationStatus.SCORED, ReplayEvaluationStatus.FAILED}
        ]
        run.metrics = {
            "evaluation_count": len(ordered),
            "completed_count": len(completed),
            "scored_count": sum(item.status == ReplayEvaluationStatus.SCORED for item in completed),
            "failed_count": sum(item.status == ReplayEvaluationStatus.FAILED for item in completed),
        }
        if any(
            item.status in {ReplayEvaluationStatus.QUEUED, ReplayEvaluationStatus.RUNNING}
            for item in ordered
        ):
            continue

        results = [
            {
                "evaluation_id": item.id,
                "name": item.name,
                "status": item.status.value,
                "execution_strategy": item.execution_strategy,
                "scenario_key": item.scenario_key,
                "scenario_variant": item.scenario_variant,
                "source_kind": item.source_kind,
                "environment_tags": item.environment_tags,
                "metrics": item.metrics,
                "estimated_cost_usd": round(item.estimated_cost_usd, 8),
                "last_error": item.last_error,
            }
            for item in ordered
        ]
        scored = [item for item in ordered if item.status == ReplayEvaluationStatus.SCORED]
        failed_count = len(ordered) - len(scored)
        divisor = len(scored) or 1
        macro_precision = round(
            sum(float(item.metrics.get("precision", 0)) for item in scored) / divisor,
            6,
        )
        macro_recall = round(
            sum(float(item.metrics.get("recall", 0)) for item in scored) / divisor,
            6,
        )
        macro_f1 = round(
            sum(float(item.metrics.get("f1", 0)) for item in scored) / divisor,
            6,
        )
        false_positives = sum(int(item.metrics.get("false_positives", 0)) for item in scored)
        false_negatives = sum(int(item.metrics.get("false_negatives", 0)) for item in scored)
        total_cost = round(sum(item.estimated_cost_usd for item in scored), 8)
        pricing_complete = all(
            item.metrics.get("pricing_configured", True) is not False for item in scored
        )
        thresholds = run.thresholds
        gate_results = [
            _gate(
                "worker_failures",
                "Every replay completed",
                actual=failed_count,
                operator="==",
                threshold=0,
                passed=failed_count == 0,
            ),
            _gate(
                "macro_f1",
                "Macro F1",
                actual=macro_f1,
                operator=">=",
                threshold=thresholds["minimum_macro_f1"],
                passed=macro_f1 >= float(thresholds["minimum_macro_f1"]),
            ),
            _gate(
                "macro_recall",
                "Macro recall",
                actual=macro_recall,
                operator=">=",
                threshold=thresholds["minimum_macro_recall"],
                passed=macro_recall >= float(thresholds["minimum_macro_recall"]),
            ),
            _gate(
                "false_positives",
                "Total false alarms",
                actual=false_positives,
                operator="<=",
                threshold=thresholds["maximum_false_positives"],
                passed=false_positives <= int(thresholds["maximum_false_positives"]),
            ),
            _gate(
                "estimated_cost_usd",
                "Total estimated cost",
                actual=total_cost,
                operator="<=",
                threshold=thresholds["maximum_estimated_cost_usd"],
                passed=total_cost <= float(thresholds["maximum_estimated_cost_usd"]),
            ),
            _gate(
                "pricing_complete",
                "Paid-provider pricing configured",
                actual=pricing_complete,
                operator="==",
                threshold=True,
                passed=(not bool(thresholds["require_pricing"]) or pricing_complete),
            ),
        ]
        run.results = results
        run.metrics = {
            "evaluation_count": len(ordered),
            "completed_count": len(ordered),
            "scored_count": len(scored),
            "failed_count": failed_count,
            "macro_precision": macro_precision,
            "macro_recall": macro_recall,
            "macro_f1": macro_f1,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "provider_requests": sum(item.provider_requests for item in scored),
            "estimated_cost_usd": total_cost,
            "pricing_complete": pricing_complete,
            "scenario_metrics": _scenario_metrics(scored),
        }
        run.gate_results = gate_results
        run.status = (
            ReplaySuiteRunStatus.PASSED
            if all(bool(gate["passed"]) for gate in gate_results)
            else ReplaySuiteRunStatus.FAILED
        )
        run.completed_at = utc_now()


async def _suite_payload(
    session: SessionDependency,
    suite: ReplaySuite,
) -> dict[str, object]:
    latest_run = await session.scalar(
        select(ReplaySuiteRun)
        .where(ReplaySuiteRun.suite_id == suite.id)
        .order_by(ReplaySuiteRun.created_at.desc())
        .limit(1)
    )
    payload = {column.name: getattr(suite, column.name) for column in ReplaySuite.__table__.columns}
    payload["latest_run"] = latest_run
    return payload


def _apply_score(
    evaluation: ReplayEvaluation,
    *,
    predicted_intervals: list[EvaluationInterval],
    provider_requests: int,
    input_tokens: int,
    output_tokens: int,
    input_price_per_million_usd: float,
    output_price_per_million_usd: float,
    minimum_iou: float = 0.1,
    tolerance_seconds: float = 1.0,
) -> None:
    if any(interval.end_seconds > evaluation.duration_seconds for interval in predicted_intervals):
        raise HTTPException(
            status_code=422,
            detail="Predicted intervals must fit inside the replay duration",
        )
    predictions = [_interval_payload(interval) for interval in predicted_intervals]
    metrics = score_intervals(
        [_temporal_interval(interval) for interval in evaluation.expected_intervals],
        [_temporal_interval(interval) for interval in predictions],
        minimum_iou=minimum_iou,
        tolerance_seconds=tolerance_seconds,
    )
    estimated_cost = (
        input_tokens * input_price_per_million_usd + output_tokens * output_price_per_million_usd
    ) / 1_000_000
    metrics.update(
        {
            "provider_requests": provider_requests,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(estimated_cost, 8),
            "pricing_configured": (
                provider_requests == 0
                or input_price_per_million_usd > 0
                or output_price_per_million_usd > 0
            ),
        }
    )
    evaluation.predicted_intervals = predictions
    evaluation.metrics = metrics
    evaluation.provider_requests = provider_requests
    evaluation.input_tokens = input_tokens
    evaluation.output_tokens = output_tokens
    evaluation.estimated_cost_usd = estimated_cost
    evaluation.status = ReplayEvaluationStatus.SCORED
    evaluation.processed_seconds = evaluation.duration_seconds
    evaluation.progress_percent = 100.0
    evaluation.last_progress_at = utc_now()
    evaluation.last_error = None
    evaluation.completed_at = utc_now()
    evaluation.worker_id = None
    evaluation.lease_expires_at = None


@router.post("", response_model=ReplayEvaluationRead, status_code=status.HTTP_201_CREATED)
async def create_evaluation(
    payload: ReplayEvaluationCreate,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: EditorDependency,
) -> ReplayEvaluation:
    if payload.scenario_key is not None and payload.scenario_key not in SCENARIO_BY_KEY:
        raise HTTPException(status_code=422, detail="Unknown calibration scenario key")
    if payload.scenario_key is not None:
        scenario = SCENARIO_BY_KEY[payload.scenario_key]
        if payload.source_kind == "unclassified" or payload.scenario_variant == "unclassified":
            raise HTTPException(
                status_code=422,
                detail="Calibration scenarios require a source kind and positive/negative variant.",
            )
        if payload.prompt.strip().casefold() != scenario.prompt.casefold():
            raise HTTPException(
                status_code=422,
                detail="The prompt must match the selected calibration scenario.",
            )
        if payload.scenario_variant == "negative" and payload.expected_intervals:
            raise HTTPException(
                status_code=422,
                detail="Negative calibration clips cannot contain expected event intervals.",
            )
        if (
            scenario.metric_family == "temporal_event"
            and payload.scenario_variant == "positive"
            and not payload.expected_intervals
        ):
            raise HTTPException(
                status_code=422,
                detail="Positive temporal calibration clips require expected event intervals.",
            )
    compilation = await _compile_and_store(
        camera_id=payload.camera_id,
        prompt=payload.prompt,
        revision=1,
        parent_id=None,
        session=session,
        settings=settings,
        actor=actor,
    )
    if (
        compilation.status != RuleCompilationStatus.READY_FOR_REVIEW
        or compilation.compiled_rule is None
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "The replay job needs clarification before it can be evaluated.",
                "compilation_id": compilation.id,
                "question": compilation.clarification_question,
            },
        )
    job = validate_job_spec(compilation.compiled_rule)
    execution_plan = plan_job(job, payload.prompt)
    evaluation = ReplayEvaluation(
        organization_id=actor.organization_id,
        camera_id=payload.camera_id,
        compilation_id=compilation.id,
        name=payload.name,
        source_uri=payload.source_uri,
        prompt=payload.prompt,
        scenario_key=payload.scenario_key,
        scenario_variant=payload.scenario_variant,
        source_kind=payload.source_kind,
        environment_tags=payload.environment_tags,
        duration_seconds=payload.duration_seconds,
        execution_strategy=execution_plan.strategy,
        compiled_rule=job.model_dump(mode="json"),
        execution_plan=execution_plan.model_dump(mode="json"),
        expected_intervals=[_interval_payload(interval) for interval in payload.expected_intervals],
    )
    session.add(evaluation)
    await session.commit()
    await session.refresh(evaluation)
    return evaluation


@router.get("", response_model=list[ReplayEvaluationRead])
async def list_evaluations(
    session: SessionDependency,
    actor: ActorDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ReplayEvaluation]:
    return list(
        (
            await session.scalars(
                select(ReplayEvaluation)
                .where(ReplayEvaluation.organization_id == actor.organization_id)
                .order_by(ReplayEvaluation.created_at.desc())
                .limit(limit)
            )
        ).all()
    )


@router.post("/uploads", response_model=ReplayUploadRead, status_code=status.HTTP_201_CREATED)
async def upload_replay_video(
    request: Request,
    settings: SettingsDependency,
    actor: EditorDependency,
) -> ReplayUploadRead:
    """Store one bounded, authenticated replay video for a later evaluation."""

    raw_filename = request.headers.get("x-replay-filename", "")
    filename = FilePath(unquote(raw_filename)).name
    extension = FilePath(filename).suffix.casefold()
    if not filename or extension not in ALLOWED_REPLAY_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Replay uploads must be MP4, MOV, MKV, WEBM, or AVI video files",
        )
    media_type = request.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
    if media_type.casefold() not in ALLOWED_REPLAY_MEDIA_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported replay video content type")
    content_length = request.headers.get("content-length")
    try:
        declared_size = int(content_length) if content_length else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Content-Length header") from exc
    if declared_size is not None and declared_size > settings.replay_max_bytes:
        raise HTTPException(
            status_code=413,
            detail="Replay video exceeds the configured upload limit",
        )

    root = settings.replay_directory.resolve()
    organization_directory = (root / actor.organization_id).resolve()
    if root not in organization_directory.parents:
        raise HTTPException(status_code=400, detail="Invalid replay storage path")
    organization_directory.mkdir(parents=True, exist_ok=True)
    target = (organization_directory / f"{uuid4().hex}{extension}").resolve()
    if organization_directory not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid replay filename")

    size_bytes = 0
    try:
        with target.open("xb") as destination:
            async for chunk in request.stream():
                size_bytes += len(chunk)
                if size_bytes > settings.replay_max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="Replay video exceeds the configured upload limit",
                    )
                destination.write(chunk)
        if size_bytes == 0:
            raise HTTPException(status_code=422, detail="Replay video is empty")
    except Exception:
        target.unlink(missing_ok=True)
        raise

    return ReplayUploadRead(
        source_uri=str(target),
        filename=filename,
        media_type=media_type,
        size_bytes=size_bytes,
    )


@router.get("/{evaluation_id}", response_model=ReplayEvaluationRead)
async def get_evaluation(
    evaluation_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: ActorDependency,
) -> ReplayEvaluation:
    evaluation = await tenant_replay_evaluation(session, actor, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Replay evaluation not found")
    return evaluation


@router.post("/{evaluation_id}/score", response_model=ReplayEvaluationRead)
async def score_evaluation(
    evaluation_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: ReplayEvaluationScore,
    session: SessionDependency,
    actor: EditorDependency,
) -> ReplayEvaluation:
    evaluation = await tenant_replay_evaluation(session, actor, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Replay evaluation not found")
    _apply_score(
        evaluation,
        predicted_intervals=payload.predicted_intervals,
        provider_requests=payload.provider_requests,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        input_price_per_million_usd=payload.input_price_per_million_usd,
        output_price_per_million_usd=payload.output_price_per_million_usd,
        minimum_iou=payload.minimum_iou,
        tolerance_seconds=payload.tolerance_seconds,
    )
    await _refresh_suite_runs_for_evaluation(session, evaluation)
    await session.commit()
    await session.refresh(evaluation)
    return evaluation


@router.post("/{evaluation_id}/run", response_model=ReplayEvaluationRead)
async def queue_evaluation(
    evaluation_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: EditorDependency,
) -> ReplayEvaluation:
    evaluation = await tenant_replay_evaluation(session, actor, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Replay evaluation not found")
    if evaluation.status == ReplayEvaluationStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Replay evaluation is already running")
    active_runs = await _active_suite_runs(session, actor.organization_id)
    if any(evaluation.id in run.evaluation_ids for run in active_runs):
        raise HTTPException(
            status_code=409,
            detail="This replay belongs to an active regression suite run",
        )
    _reset_for_queue(evaluation)
    await session.commit()
    await session.refresh(evaluation)
    return evaluation


@router.post(
    "/{evaluation_id}/dispatch",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
)
async def dispatch_uploaded_video_result(
    evaluation_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: ReplayActionDispatch,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: EditorDependency,
) -> Event:
    """Turn a confirmed uploaded-video match into a real incident and guarded actions."""

    evaluation = await tenant_replay_evaluation(session, actor, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Uploaded-video analysis not found")
    if evaluation.status != ReplayEvaluationStatus.SCORED:
        raise HTTPException(status_code=409, detail="Uploaded-video analysis is not complete")
    if not evaluation.predicted_intervals:
        raise HTTPException(status_code=409, detail="The uploaded video did not match this rule")

    rule = await tenant_rule(session, actor, payload.rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if rule.camera_id != evaluation.camera_id:
        raise HTTPException(status_code=409, detail="Rule and uploaded video use different cameras")
    if rule.status != RuleStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Activate the rule before dispatching actions")

    source_event_id = str(uuid5(NAMESPACE_URL, f"uploaded-video:{evaluation.id}:{rule.id}"))
    existing = await session.scalar(select(Event).where(Event.source_event_id == source_event_id))
    if existing is not None:
        return existing

    camera = await session.get(Camera, evaluation.camera_id)
    zone = await session.get(Zone, rule.zone_id)
    if camera is None:
        raise HTTPException(status_code=409, detail="Rule camera is unavailable")

    replay_root = settings.replay_directory.expanduser().resolve()
    organization_root = (replay_root / actor.organization_id).resolve()
    source = FilePath(evaluation.source_uri).expanduser().resolve()
    if not source.is_file() or not source.is_relative_to(organization_root):
        raise HTTPException(status_code=409, detail="Uploaded video file is unavailable")

    evidence_id = new_id()
    evidence_root = settings.evidence_directory.expanduser().resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    evidence_path = (evidence_root / f"{evidence_id}{source.suffix.casefold()}").resolve()
    if not evidence_path.is_relative_to(evidence_root):
        raise HTTPException(status_code=400, detail="Invalid evidence path")
    try:
        size_bytes, digest = await anyio.to_thread.run_sync(
            _copy_uploaded_evidence,
            source,
            evidence_path,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="Evidence file already exists") from exc

    first = evaluation.predicted_intervals[0]
    start_seconds = float(first.get("start_seconds", 0))
    end_seconds = float(first.get("end_seconds", start_seconds))
    confidence = max(
        float(interval.get("confidence") or rule.minimum_confidence)
        for interval in evaluation.predicted_intervals
    )
    details: dict[str, object] = {
        "uploaded_video": True,
        "evaluation_id": evaluation.id,
        "source_name": evaluation.name,
        "match_count": len(evaluation.predicted_intervals),
        "matched_intervals": evaluation.predicted_intervals,
        "summary": (
            f"Uploaded video matched '{rule.name}' "
            f"{len(evaluation.predicted_intervals)} time(s)."
        ),
    }
    event = Event(
        id=new_id(),
        source_event_id=source_event_id,
        schema_version=2,
        event_type=rule.rule_type,
        camera_id=camera.id,
        rule_id=rule.id,
        track_id=None,
        object_class=rule.object_class,
        zone_name=zone.name if zone is not None else "Full camera view",
        entered_at_seconds=start_seconds,
        occurred_at_seconds=float(first.get("detected_at_seconds") or start_seconds),
        dwell_seconds=max(0, end_seconds - start_seconds),
        confidence=min(1, max(0, confidence)),
        occurred_at=utc_now(),
        clip_uri=str(evidence_path),
        raw_payload={
            "schema_version": 2,
            "id": source_event_id,
            "uploaded_video": True,
            "evaluation_id": evaluation.id,
        },
        details=details,
    )
    evidence = EvidenceAsset(
        id=evidence_id,
        event_id=event.id,
        status=EvidenceStatus.QUEUED,
        storage_uri=str(evidence_path),
        media_type=_uploaded_media_type(source),
        size_bytes=size_bytes,
        sha256=digest,
        duration_seconds=evaluation.duration_seconds,
    )
    session.add(event)
    session.add(evidence)
    await finalize_confirmed_event(session, event, camera)
    try:
        await session.commit()
    except Exception:
        evidence_path.unlink(missing_ok=True)
        raise
    await session.refresh(event)

    event_payload = EventRead.model_validate(event).model_dump(mode="json")
    await request.app.state.event_connections.broadcast(
        {"type": "event.created", "data": event_payload},
        organization_id=camera.organization_id,
    )
    return event


@suite_router.post("", response_model=ReplaySuiteRead, status_code=status.HTTP_201_CREATED)
async def create_replay_suite(
    payload: ReplaySuiteCreate,
    session: SessionDependency,
    actor: EditorDependency,
) -> dict[str, object]:
    evaluations = list(
        (
            await session.scalars(
                select(ReplayEvaluation).where(
                    ReplayEvaluation.organization_id == actor.organization_id,
                    ReplayEvaluation.id.in_(payload.evaluation_ids),
                )
            )
        ).all()
    )
    if len(evaluations) != len(payload.evaluation_ids):
        raise HTTPException(
            status_code=422,
            detail="Every suite baseline must exist in the current organization",
        )
    suite = ReplaySuite(
        organization_id=actor.organization_id,
        **payload.model_dump(),
    )
    session.add(suite)
    await session.commit()
    await session.refresh(suite)
    return await _suite_payload(session, suite)


@suite_router.get("", response_model=list[ReplaySuiteRead])
async def list_replay_suites(
    session: SessionDependency,
    actor: ActorDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, object]]:
    suites = list(
        (
            await session.scalars(
                select(ReplaySuite)
                .where(ReplaySuite.organization_id == actor.organization_id)
                .order_by(ReplaySuite.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
    return [await _suite_payload(session, suite) for suite in suites]


@suite_router.get("/{suite_id}", response_model=ReplaySuiteRead)
async def get_replay_suite(
    suite_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: ActorDependency,
) -> dict[str, object]:
    suite = await tenant_replay_suite(session, actor, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="Replay suite not found")
    return await _suite_payload(session, suite)


@suite_router.post("/{suite_id}/runs", response_model=ReplaySuiteRunRead)
async def run_replay_suite(
    suite_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: EditorDependency,
) -> ReplaySuiteRun:
    suite = await tenant_replay_suite(session, actor, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="Replay suite not found")
    active_runs = await _active_suite_runs(session, actor.organization_id)
    requested_ids = set(suite.evaluation_ids)
    if any(requested_ids.intersection(run.evaluation_ids) for run in active_runs):
        raise HTTPException(
            status_code=409,
            detail="One or more baselines already belong to an active suite run",
        )
    evaluations = list(
        (
            await session.scalars(
                select(ReplayEvaluation).where(
                    ReplayEvaluation.organization_id == actor.organization_id,
                    ReplayEvaluation.id.in_(suite.evaluation_ids),
                )
            )
        ).all()
    )
    by_id = {evaluation.id: evaluation for evaluation in evaluations}
    if len(by_id) != len(suite.evaluation_ids):
        raise HTTPException(status_code=409, detail="A suite baseline is no longer available")
    if any(
        evaluation.status in {ReplayEvaluationStatus.QUEUED, ReplayEvaluationStatus.RUNNING}
        for evaluation in evaluations
    ):
        raise HTTPException(status_code=409, detail="A suite baseline is already running")
    for evaluation_id in suite.evaluation_ids:
        _reset_for_queue(by_id[evaluation_id])
    run = ReplaySuiteRun(
        organization_id=actor.organization_id,
        suite_id=suite.id,
        evaluation_ids=list(suite.evaluation_ids),
        thresholds=_suite_thresholds(suite),
        status=ReplaySuiteRunStatus.QUEUED,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


@suite_router.get("/{suite_id}/runs", response_model=list[ReplaySuiteRunRead])
async def list_replay_suite_runs(
    suite_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: ActorDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ReplaySuiteRun]:
    suite = await tenant_replay_suite(session, actor, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="Replay suite not found")
    return list(
        (
            await session.scalars(
                select(ReplaySuiteRun)
                .where(ReplaySuiteRun.suite_id == suite.id)
                .order_by(ReplaySuiteRun.created_at.desc())
                .limit(limit)
            )
        ).all()
    )


@suite_router.get("/runs/{run_id}", response_model=ReplaySuiteRunRead)
async def get_replay_suite_run(
    run_id: Annotated[str, Path(min_length=1, max_length=36)],
    session: SessionDependency,
    actor: ActorDependency,
) -> ReplaySuiteRun:
    run = await tenant_replay_suite_run(session, actor, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Replay suite run not found")
    return run


@agent_router.post("/claim", response_model=ReplayWorkerAssignment | None)
async def claim_replay_evaluation(
    payload: WorkerClaimRequest,
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> ReplayWorkerAssignment | Response:
    now = utc_now()
    statement = (
        select(ReplayEvaluation)
        .where(
            or_(
                ReplayEvaluation.status == ReplayEvaluationStatus.QUEUED,
                (
                    (ReplayEvaluation.status == ReplayEvaluationStatus.RUNNING)
                    & (ReplayEvaluation.lease_expires_at < now)
                ),
            )
        )
        .order_by(ReplayEvaluation.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if principal.organization_id is not None:
        statement = statement.where(ReplayEvaluation.organization_id == principal.organization_id)
    evaluation = await session.scalar(statement)
    if evaluation is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    spec = validate_job_spec(evaluation.compiled_rule)
    zone = await session.get(Zone, spatial_id(spec))
    if zone is None or zone.camera_id != evaluation.camera_id:
        evaluation.status = ReplayEvaluationStatus.FAILED
        evaluation.last_error = "The compiled replay geometry is no longer available"
        evaluation.completed_at = now
        await _refresh_suite_runs_for_evaluation(session, evaluation)
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    evaluation.status = ReplayEvaluationStatus.RUNNING
    evaluation.worker_id = payload.worker_id
    evaluation.lease_expires_at = now + timedelta(seconds=settings.replay_lease_seconds)
    evaluation.started_at = now
    evaluation.processed_seconds = 0
    evaluation.progress_percent = 0
    evaluation.last_progress_at = now
    evaluation.completed_at = None
    evaluation.last_error = None
    await _refresh_suite_runs_for_evaluation(session, evaluation)
    await session.commit()
    return ReplayWorkerAssignment(
        worker_id=payload.worker_id,
        evaluation_id=evaluation.id,
        source_uri=evaluation.source_uri,
        duration_seconds=evaluation.duration_seconds,
        rule=AgentRuleConfig(
            id=evaluation.id,
            key=f"replay-{evaluation.id[:8]}",
            rule_type=spec.rule_type,
            object_class=spec.object_class,
            duration_seconds=duration_for_legacy_column(spec),
            minimum_confidence=spec.minimum_confidence,
            absence_grace_seconds=spec.absence_grace_seconds,
            zone=AgentZoneConfig(
                id=zone.id,
                name=zone.name,
                geometry_type=zone.geometry_type,
                points=zone.points,
            ),
            spec=spec,
        ),
    )


@agent_router.post("/{evaluation_id}/heartbeat", response_model=ReplayEvaluationRead)
async def heartbeat_replay_evaluation(
    evaluation_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: ReplayWorkerHeartbeat,
    session: SessionDependency,
    settings: SettingsDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> ReplayEvaluation:
    evaluation = await session.get(ReplayEvaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Replay evaluation not found")
    ensure_edge_organization(principal, evaluation.organization_id)
    if (
        evaluation.status != ReplayEvaluationStatus.RUNNING
        or evaluation.worker_id != payload.worker_id
    ):
        raise HTTPException(status_code=409, detail="Worker does not hold this replay lease")
    now = utc_now()
    processed_seconds = min(payload.processed_seconds, evaluation.duration_seconds)
    evaluation.processed_seconds = max(evaluation.processed_seconds, processed_seconds)
    evaluation.progress_percent = min(
        100.0,
        round((evaluation.processed_seconds / evaluation.duration_seconds) * 100, 2),
    )
    evaluation.last_progress_at = now
    evaluation.lease_expires_at = now + timedelta(seconds=settings.replay_lease_seconds)
    await session.commit()
    await session.refresh(evaluation)
    return evaluation


@agent_router.post("/{evaluation_id}/result", response_model=ReplayEvaluationRead)
async def ingest_replay_result(
    evaluation_id: Annotated[str, Path(min_length=1, max_length=36)],
    payload: ReplayWorkerResult,
    session: SessionDependency,
    principal: Annotated[EdgePrincipal, Depends(require_edge_device)],
) -> ReplayEvaluation:
    evaluation = await session.get(ReplayEvaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Replay evaluation not found")
    ensure_edge_organization(principal, evaluation.organization_id)
    if (
        evaluation.status != ReplayEvaluationStatus.RUNNING
        or evaluation.worker_id != payload.worker_id
    ):
        raise HTTPException(status_code=409, detail="Worker does not hold this replay lease")
    if payload.error:
        evaluation.status = ReplayEvaluationStatus.FAILED
        evaluation.last_error = payload.error
        evaluation.completed_at = utc_now()
        evaluation.worker_id = None
        evaluation.lease_expires_at = None
    else:
        _apply_score(
            evaluation,
            predicted_intervals=payload.predicted_intervals,
            provider_requests=payload.provider_requests,
            input_tokens=payload.input_tokens,
            output_tokens=payload.output_tokens,
            input_price_per_million_usd=payload.input_price_per_million_usd,
            output_price_per_million_usd=payload.output_price_per_million_usd,
        )
    await _refresh_suite_runs_for_evaluation(session, evaluation)
    await session.commit()
    await session.refresh(evaluation)
    return evaluation
