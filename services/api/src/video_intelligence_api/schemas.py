from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    computed_field,
    field_validator,
    model_validator,
)

from video_intelligence_api.execution_plans import ExecutionPlan, plan_job
from video_intelligence_api.job_specs import (
    CameraJobSpec,
)
from video_intelligence_api.models import (
    ActionApprovalMode,
    ActionExecutionStatus,
    ActionRiskLevel,
    AgentDesiredStatus,
    AgentObservedStatus,
    AlertDeliveryStatus,
    AlertStatus,
    CameraStatus,
    ConnectorType,
    ContextSourceType,
    CorrelationEvaluationStatus,
    CorrelationType,
    EdgeDeviceStatus,
    EdgeHealthStatus,
    EdgeUpdateStatus,
    EvidenceSearchStatus,
    EvidenceStatus,
    GeometryType,
    OrganizationRole,
    ReplayEvaluationStatus,
    ReplaySuiteRunStatus,
    RuleCompilationStatus,
    RuleStatus,
    SceneItemKind,
    SceneMemorySource,
    SceneReviewStatus,
    SourceType,
    VisualAgentPlanStatus,
)
from video_intelligence_api.scene_memory import SceneObservationData
from video_intelligence_api.visual_agent_plans import VisualAgentPlanDocument


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EvaluationInterval(ApiModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    label: str = Field(default="event", min_length=1, max_length=80)
    detected_at_seconds: float | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_interval(self) -> EvaluationInterval:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class ReplayEvaluationCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    camera_id: str = Field(min_length=1, max_length=36)
    source_uri: str = Field(min_length=1, max_length=2048)
    prompt: str = Field(min_length=5, max_length=2000)
    duration_seconds: float = Field(gt=0, le=86400)
    expected_intervals: list[EvaluationInterval] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def validate_expected_bounds(self) -> ReplayEvaluationCreate:
        if any(
            interval.end_seconds > self.duration_seconds for interval in self.expected_intervals
        ):
            raise ValueError("Expected intervals must fit inside the replay duration")
        return self


class ReplayEvaluationScore(ApiModel):
    predicted_intervals: list[EvaluationInterval] = Field(default_factory=list, max_length=1000)
    provider_requests: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    input_price_per_million_usd: float = Field(default=0, ge=0)
    output_price_per_million_usd: float = Field(default=0, ge=0)
    minimum_iou: float = Field(default=0.1, gt=0, le=1)
    tolerance_seconds: float = Field(default=1.0, ge=0, le=60)


class ReplayEvaluationRead(ApiModel):
    id: str
    organization_id: str
    camera_id: str
    compilation_id: str
    name: str
    source_uri: str
    prompt: str
    duration_seconds: float
    execution_strategy: str
    compiled_rule: dict
    execution_plan: dict
    expected_intervals: list[EvaluationInterval]
    predicted_intervals: list[EvaluationInterval]
    metrics: dict
    provider_requests: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    status: ReplayEvaluationStatus
    worker_id: str | None
    lease_expires_at: datetime | None
    started_at: datetime | None
    processed_seconds: float
    progress_percent: float
    last_progress_at: datetime | None
    last_error: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CameraCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    source_uri: str = Field(min_length=1, max_length=2048)


class CameraRead(ApiModel):
    id: str
    organization_id: str
    name: str
    source_uri: str
    source_type: SourceType
    status: CameraStatus
    created_at: datetime
    updated_at: datetime


class CameraStatusUpdate(ApiModel):
    status: CameraStatus


class CameraStreamRead(ApiModel):
    camera_id: str
    path: str
    mode: Literal["proxy", "publisher"]
    configured: bool
    ready: bool
    readers: int = Field(ge=0)
    playback_url: str
    whep_url: str
    publish_url: str | None


class AgentControlUpdate(ApiModel):
    desired_status: AgentDesiredStatus


class CameraAgentRead(ApiModel):
    camera_id: str
    desired_status: AgentDesiredStatus
    observed_status: AgentObservedStatus
    worker_id: str | None
    edge_device_id: str | None
    lease_expires_at: datetime | None
    last_heartbeat_at: datetime | None
    fps: float | None
    inference_latency_ms: float | None
    frame_width: int | None
    frame_height: int | None
    last_error: str | None
    updated_at: datetime | None


class WorkerClaimRequest(ApiModel):
    worker_id: str = Field(min_length=1, max_length=120)


class EdgeDeviceCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    max_concurrent_streams: int = Field(default=1, ge=1, le=32)


class EdgeDeviceUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    max_concurrent_streams: int | None = Field(default=None, ge=1, le=32)


class EdgeDeviceRead(ApiModel):
    id: str
    organization_id: str
    name: str
    status: EdgeDeviceStatus
    max_concurrent_streams: int
    credential_fingerprint: str
    last_seen_at: datetime | None
    last_worker_id: str | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EdgeDeviceCredential(ApiModel):
    device: EdgeDeviceRead
    token: str = Field(min_length=40)


class EdgeStationProfileReport(ApiModel):
    hostname: str = Field(min_length=1, max_length=255)
    os_name: str = Field(min_length=1, max_length=120)
    architecture: str = Field(min_length=1, max_length=80)
    cpu_count: int = Field(ge=1, le=4096)
    memory_mb: int = Field(ge=0)
    accelerator: str | None = Field(default=None, max_length=255)
    storage_available_mb: int = Field(ge=0)
    worker_version: str = Field(min_length=1, max_length=80)
    health_status: EdgeHealthStatus
    offline_queue_depth: int = Field(default=0, ge=0)
    last_sync_at: datetime | None = None
    details: dict[str, object] = Field(default_factory=dict)


class EdgeStationProfileRead(EdgeStationProfileReport):
    device_id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime


class EdgeConfigBundleCreate(ApiModel):
    configuration: dict[str, object]


class EdgeConfigBundleRead(ApiModel):
    id: str
    organization_id: str
    device_id: str
    revision: int
    configuration: dict[str, object]
    content_sha256: str
    signature: str
    created_by: str
    created_at: datetime


class EdgeUpdateCreate(ApiModel):
    target_version: str = Field(min_length=1, max_length=80)


class EdgeUpdateReport(ApiModel):
    status: EdgeUpdateStatus
    error: str | None = Field(default=None, max_length=1000)


class EdgeUpdateRead(ApiModel):
    id: str
    organization_id: str
    device_id: str
    from_version: str
    target_version: str
    rollback_version: str
    status: EdgeUpdateStatus
    error: str | None
    requested_by: str
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EdgeFleetDeviceRead(ApiModel):
    device: EdgeDeviceRead
    profile: EdgeStationProfileRead | None
    config: EdgeConfigBundleRead | None
    update: EdgeUpdateRead | None


class AuditLogRead(ApiModel):
    id: str
    organization_id: str
    actor_subject: str
    actor_issuer: str
    actor_role: OrganizationRole
    action: str
    resource_type: str | None
    resource_id: str | None
    status_code: int
    request_id: str
    client_host: str | None
    details: dict[str, object]
    created_at: datetime


class DetectionTelemetry(ApiModel):
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)
    label: str = Field(min_length=1, max_length=80)
    confidence: float = Field(ge=0, le=1)
    track_id: int | None = Field(default=None, ge=0)


class WorkerTelemetry(ApiModel):
    worker_id: str = Field(min_length=1, max_length=120)
    camera_id: str = Field(min_length=1, max_length=36)
    observed_status: AgentObservedStatus
    fps: float | None = Field(default=None, ge=0, le=1000)
    inference_latency_ms: float | None = Field(default=None, ge=0, le=60000)
    frame_width: int | None = Field(default=None, gt=0, le=32768)
    frame_height: int | None = Field(default=None, gt=0, le=32768)
    detections: list[DetectionTelemetry] = Field(default_factory=list, max_length=200)
    error: str | None = Field(default=None, max_length=1000)
    analysis_state: str | None = Field(default=None, max_length=40)
    analysis_sequence: int | None = Field(default=None, ge=1)
    analysis_triggered: bool | None = None
    analysis_confidence: float | None = Field(default=None, ge=0, le=1)
    analysis_summary: str | None = Field(default=None, max_length=1000)
    analysis_error: str | None = Field(default=None, max_length=1000)
    analysis_requests_today: int = Field(default=0, ge=0)
    analysis_request_limit_day: int = Field(default=0, ge=0)
    analysis_request_limit_minute: int = Field(default=0, ge=0)


class WorkerAssignment(ApiModel):
    worker_id: str
    camera_id: str
    camera_name: str
    analysis_source_uri: str
    capture_source_uri: str | None = None
    publish_url: str | None = None
    rules: list[AgentRuleConfig] = Field(min_length=1)


class ReplayWorkerAssignment(ApiModel):
    worker_id: str
    evaluation_id: str
    source_uri: str
    duration_seconds: float = Field(gt=0)
    rule: AgentRuleConfig


class ReplayWorkerHeartbeat(ApiModel):
    worker_id: str = Field(min_length=1, max_length=120)
    processed_seconds: float = Field(ge=0)


class ReplayWorkerResult(ApiModel):
    worker_id: str = Field(min_length=1, max_length=120)
    predicted_intervals: list[EvaluationInterval] = Field(default_factory=list, max_length=1000)
    provider_requests: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    input_price_per_million_usd: float = Field(default=0, ge=0)
    output_price_per_million_usd: float = Field(default=0, ge=0)
    error: str | None = Field(default=None, max_length=1000)


class ReplayUploadRead(ApiModel):
    source_uri: str
    filename: str
    media_type: str
    size_bytes: int = Field(gt=0)


class ReplaySuiteCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    evaluation_ids: list[str] = Field(min_length=1, max_length=100)
    minimum_macro_f1: float = Field(default=0.8, ge=0, le=1)
    minimum_macro_recall: float = Field(default=0.8, ge=0, le=1)
    maximum_false_positives: int = Field(default=0, ge=0, le=100000)
    maximum_estimated_cost_usd: float = Field(default=1.0, ge=0, le=1000000)
    require_pricing: bool = True

    @field_validator("evaluation_ids")
    @classmethod
    def unique_evaluation_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evaluation_ids must be unique")
        return value


class ReplaySuiteRunRead(ApiModel):
    id: str
    organization_id: str
    suite_id: str
    evaluation_ids: list[str]
    thresholds: dict
    status: ReplaySuiteRunStatus
    results: list[dict]
    metrics: dict
    gate_results: list[dict]
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReplaySuiteRead(ApiModel):
    id: str
    organization_id: str
    name: str
    evaluation_ids: list[str]
    minimum_macro_f1: float
    minimum_macro_recall: float
    maximum_false_positives: int
    maximum_estimated_cost_usd: float
    require_pricing: bool
    latest_run: ReplaySuiteRunRead | None = None
    created_at: datetime
    updated_at: datetime


class VisualAgentPlanCreate(ApiModel):
    rule_id: str = Field(min_length=1, max_length=36)


class VisualAgentPlanApprove(ApiModel):
    regression_run_id: str = Field(min_length=1, max_length=36)


class VisualAgentPlanRead(ApiModel):
    id: str
    organization_id: str
    camera_id: str
    rule_id: str
    compilation_id: str | None
    parent_id: str | None
    revision: int
    prompt: str
    status: VisualAgentPlanStatus
    plan: VisualAgentPlanDocument
    required_capabilities: list[str]
    unsupported_capabilities: list[str]
    approved_by: str | None
    approved_at: datetime | None
    regression_run_id: str | None
    created_at: datetime
    updated_at: datetime


class VisualAgentSimulationRead(ApiModel):
    id: str
    organization_id: str
    plan_id: str
    trace: list[dict]
    summary: str
    created_at: datetime


class ConnectorCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    connector_type: ConnectorType
    endpoint_url: HttpUrl | None = None
    credential: str = Field(default="local-mock-credential", min_length=8, max_length=2000)
    scopes: list[str] = Field(min_length=1, max_length=20)
    enabled: bool = True
    timeout_seconds: float = Field(default=10, gt=0, le=60)
    max_attempts: int = Field(default=6, ge=1, le=20)

    @model_validator(mode="after")
    def require_remote_endpoint(self) -> ConnectorCreate:
        if self.connector_type != ConnectorType.MOCK and self.endpoint_url is None:
            raise ValueError("Remote connectors require endpoint_url")
        return self


class ConnectorUpdate(ApiModel):
    endpoint_url: HttpUrl | None = None
    credential: str | None = Field(default=None, min_length=8, max_length=2000)
    enabled: bool | None = None
    timeout_seconds: float | None = Field(default=None, gt=0, le=60)
    max_attempts: int | None = Field(default=None, ge=1, le=20)


class ConnectorRead(ApiModel):
    id: str
    organization_id: str
    name: str
    connector_type: ConnectorType
    endpoint_url: str | None
    scopes: list[str]
    enabled: bool
    timeout_seconds: float
    max_attempts: int
    created_at: datetime
    updated_at: datetime


class RuleActionBindingCreate(ApiModel):
    connector_id: str = Field(min_length=1, max_length=36)
    action_type: Literal["send_notification", "create_ticket", "invoke_webhook", "control_physical"]
    approval_mode: ActionApprovalMode | None = None
    rate_limit_per_minute: int = Field(default=10, ge=1, le=1000)
    payload_template: dict[str, object] = Field(default_factory=dict)
    enabled: bool = True


class RuleActionBindingRead(ApiModel):
    id: str
    organization_id: str
    rule_id: str
    connector_id: str
    connector_name: str
    action_type: str
    risk_level: ActionRiskLevel
    approval_mode: ActionApprovalMode
    rate_limit_per_minute: int
    payload_template: dict[str, object]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ActionExecutionRead(ApiModel):
    id: str
    organization_id: str
    alert_id: str
    event_id: str
    binding_id: str
    connector_id: str
    connector_name: str
    action_type: str
    risk_level: ActionRiskLevel
    status: ActionExecutionStatus
    idempotency_key: str
    payload: dict[str, object]
    attempt_count: int
    manual_retry_count: int
    next_attempt_at: datetime
    last_status_code: int | None
    last_error: str | None
    approved_by: str | None
    approved_at: datetime | None
    denied_by: str | None
    denied_at: datetime | None
    denial_reason: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActionDecision(ApiModel):
    reason: str | None = Field(default=None, max_length=500)


class ActionWorkerClaim(ApiModel):
    worker_id: str = Field(min_length=1, max_length=120)


class ActionExecutionAssignment(ApiModel):
    execution_id: str
    connector_type: ConnectorType
    endpoint_url: HttpUrl | None
    credential: str
    timeout_seconds: float
    idempotency_key: str
    action_type: str
    payload: dict[str, object]


class ActionExecutionResult(ApiModel):
    worker_id: str = Field(min_length=1, max_length=120)
    outcome: Literal["succeeded", "retryable", "permanent_failure"]
    status_code: int | None = Field(default=None, ge=100, le=599)
    error: str | None = Field(default=None, max_length=1000)


class ContextSourceCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    source_type: ContextSourceType
    endpoint_url: HttpUrl | None = None
    credential: str | None = Field(default=None, min_length=8, max_length=2000)
    configuration: dict[str, object] = Field(default_factory=dict)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_remote_source(self) -> ContextSourceCreate:
        if self.source_type == ContextSourceType.GENERIC_EVENT_FEED and (
            self.endpoint_url is None or self.credential is None
        ):
            raise ValueError("Generic event feeds require endpoint_url and credential")
        return self


class ContextSourceRead(ApiModel):
    id: str
    organization_id: str
    name: str
    source_type: ContextSourceType
    endpoint_url: str | None
    configuration: dict[str, object]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ContextObservationCreate(ApiModel):
    source_event_id: str | None = Field(default=None, max_length=160)
    observation_type: str = Field(min_length=1, max_length=80)
    occurred_at: datetime
    entity_key: str | None = Field(default=None, max_length=255)
    attributes: dict[str, object] = Field(default_factory=dict)


class ContextObservationRead(ApiModel):
    id: str
    organization_id: str
    source_id: str
    source_event_id: str
    observation_type: str
    occurred_at: datetime
    entity_key: str | None
    attributes: dict[str, object]
    received_at: datetime


class RuleCorrelationPolicyCreate(ApiModel):
    source_id: str = Field(min_length=1, max_length=36)
    correlation_type: CorrelationType = CorrelationType.COUNT_EXCEEDS_AUTHORIZATIONS
    observation_type: str = Field(default="access_granted", min_length=1, max_length=80)
    visual_count_field: str = Field(default="person_count", min_length=1, max_length=80)
    window_before_seconds: float = Field(default=5, ge=0, le=300)
    window_after_seconds: float = Field(default=1, ge=0, le=60)
    enabled: bool = True


class RuleCorrelationPolicyRead(ApiModel):
    id: str
    organization_id: str
    rule_id: str
    source_id: str
    source_name: str
    correlation_type: CorrelationType
    observation_type: str
    visual_count_field: str
    window_before_seconds: float
    window_after_seconds: float
    enabled: bool
    created_at: datetime
    updated_at: datetime


class CorrelationEvaluationRead(ApiModel):
    id: str
    organization_id: str
    event_id: str
    policy_id: str
    source_id: str
    source_name: str
    status: CorrelationEvaluationStatus
    visual_count: int
    observation_count: int
    window_start: datetime
    window_end: datetime
    due_at: datetime
    explanation: str | None
    evaluated_at: datetime | None
    created_at: datetime


class CorrelationDemoCreate(ApiModel):
    visual_people: int = Field(default=2, ge=1, le=100)
    authorized_entries: int = Field(default=1, ge=0, le=100)


class SceneMemoryBatchIngest(ApiModel):
    camera_id: str = Field(min_length=1, max_length=36)
    event_id: str | None = Field(default=None, max_length=36)
    occurred_at: datetime
    observations: list[SceneObservationData] = Field(min_length=1, max_length=100)


class SceneMemoryItemRead(ApiModel):
    id: str
    organization_id: str
    camera_id: str
    stable_key: str
    label: str
    kind: SceneItemKind
    bounding_box: dict[str, float]
    description: str
    current_state: str
    confidence: float
    attributes: dict[str, object]
    relationships: list[dict[str, object]]
    source: SceneMemorySource
    review_status: SceneReviewStatus
    first_seen_at: datetime
    last_seen_at: datetime
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SceneMemoryReview(ApiModel):
    review_status: SceneReviewStatus
    label: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    current_state: str | None = Field(default=None, min_length=1, max_length=160)


class SceneChangeRead(ApiModel):
    id: str
    organization_id: str
    camera_id: str
    item_id: str
    event_id: str | None
    previous_state: str | None
    new_state: str
    confidence: float
    details: dict[str, object]
    occurred_at: datetime
    created_at: datetime


class SiteCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)


class SiteRead(ApiModel):
    id: str
    organization_id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


class SiteAreaCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    area_type: str = Field(default="operational", min_length=1, max_length=80)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside_layout(self) -> SiteAreaCreate:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Site area must remain inside the normalized layout")
        return self


class SiteAreaRead(ApiModel):
    id: str
    organization_id: str
    site_id: str
    name: str
    area_type: str
    x: float
    y: float
    width: float
    height: float
    created_at: datetime


class CameraPlacementUpsert(ApiModel):
    area_id: str | None = Field(default=None, max_length=36)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    heading_degrees: float = Field(default=0, ge=0, lt=360)


class CameraPlacementRead(ApiModel):
    id: str
    organization_id: str
    site_id: str
    area_id: str | None
    area_name: str | None
    camera_id: str
    camera_name: str
    x: float
    y: float
    heading_degrees: float
    created_at: datetime
    updated_at: datetime


class EntitySightingIngest(ApiModel):
    camera_id: str = Field(min_length=1, max_length=36)
    event_id: str | None = Field(default=None, max_length=36)
    entity_key: str = Field(min_length=1, max_length=255)
    label: str = Field(min_length=1, max_length=160)
    bounding_box: dict[str, float]
    confidence: float = Field(ge=0, le=1)
    attributes: dict[str, object] = Field(default_factory=dict)
    occurred_at: datetime


class EntitySightingRead(ApiModel):
    id: str
    organization_id: str
    camera_id: str
    camera_name: str
    area_id: str | None
    area_name: str | None
    event_id: str | None
    entity_key: str
    label: str
    bounding_box: dict[str, float]
    confidence: float
    attributes: dict[str, object]
    occurred_at: datetime
    created_at: datetime


class InvestigationSearchCreate(ApiModel):
    query: str = Field(min_length=2, max_length=500)
    camera_ids: list[str] = Field(default_factory=list, max_length=100)
    limit: int = Field(default=50, ge=1, le=200)


class InvestigationResult(ApiModel):
    kind: Literal["event", "scene", "entity"]
    id: str
    camera_id: str
    occurred_at: datetime
    title: str
    summary: str
    event_id: str | None = None
    entity_key: str | None = None
    clip_uri: str | None = None


class InvestigationSearchRead(ApiModel):
    query: str
    results: list[InvestigationResult]


class ZonePoint(ApiModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class ZoneCreate(ApiModel):
    camera_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=120)
    geometry_type: GeometryType = GeometryType.POLYGON
    points: list[ZonePoint] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_geometry(self) -> ZoneCreate:
        if self.geometry_type == GeometryType.POLYGON and len(self.points) < 3:
            raise ValueError("A polygon zone requires at least three points")
        if self.geometry_type == GeometryType.LINE and len(self.points) != 2:
            raise ValueError("A line requires exactly two points")
        return self


class ZoneRead(ApiModel):
    id: str
    camera_id: str
    name: str
    geometry_type: GeometryType
    points: list[ZonePoint]
    created_at: datetime
    updated_at: datetime


class RuleCreate(ApiModel):
    camera_id: str = Field(min_length=1, max_length=36)
    zone_id: str = Field(min_length=1, max_length=36)
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=200)
    rule_type: Literal["object_dwell"] = "object_dwell"
    object_class: str = Field(default="person", min_length=1, max_length=80)
    duration_seconds: float = Field(gt=0, le=86400)
    minimum_confidence: float = Field(default=0.25, ge=0, le=1)
    absence_grace_seconds: float = Field(default=1.0, ge=0, le=60)
    original_prompt: str | None = Field(default=None, max_length=2000)


class RuleStatusUpdate(ApiModel):
    status: RuleStatus


class RuleRead(ApiModel):
    id: str
    camera_id: str
    zone_id: str
    key: str
    name: str
    rule_type: str
    object_class: str
    duration_seconds: float
    minimum_confidence: float
    absence_grace_seconds: float
    status: RuleStatus
    original_prompt: str | None
    spec_version: int
    spec: CameraJobSpec | None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def execution_plan(self) -> ExecutionPlan | None:
        return plan_job(self.spec) if self.spec is not None else None


class RuleCompilationCreate(ApiModel):
    camera_id: str = Field(min_length=1, max_length=36)
    prompt: str = Field(min_length=5, max_length=2000)


class RuleCompilationClarify(ApiModel):
    answer: str = Field(min_length=1, max_length=1000)


class RuleCompilationAccept(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    key: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )


class RuleCompilationRead(ApiModel):
    id: str
    camera_id: str
    parent_id: str | None
    revision: int
    prompt: str
    provider: str
    provider_model: str | None
    compiler_version: str
    status: RuleCompilationStatus
    compiled_rule: CameraJobSpec | None
    explanation: str
    clarification_question: str | None
    warnings: list[str]
    accepted_rule_id: str | None
    created_at: datetime
    reviewed_at: datetime | None

    @computed_field
    @property
    def execution_plan(self) -> ExecutionPlan | None:
        return plan_job(self.compiled_rule) if self.compiled_rule is not None else None


class AgentEventIngest(ApiModel):
    schema_version: int = Field(default=2, ge=1)
    id: str = Field(min_length=36, max_length=36)
    event_type: Literal[
        "object_dwell",
        "zone_dwell",
        "zone_presence",
        "zone_entry",
        "zone_exit",
        "count_threshold",
        "line_crossing",
        "semantic_vision",
    ]
    rule_id: str = Field(min_length=1, max_length=120)
    camera_id: str = Field(min_length=1, max_length=120)
    track_id: int | None = Field(default=None, ge=0)
    object_class: str = Field(min_length=1, max_length=80)
    zone_name: str = Field(min_length=1, max_length=120)
    entered_at_seconds: float = Field(ge=0)
    occurred_at_seconds: float = Field(ge=0)
    dwell_seconds: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    occurred_at: datetime
    clip_path: str = Field(min_length=1, max_length=2048)
    details: dict[str, object] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_uuid_text(cls, value: str) -> str:
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise ValueError("id must be a UUID string") from exc
        return value


class EventRead(ApiModel):
    id: str
    source_event_id: str
    schema_version: int
    event_type: str
    camera_id: str
    rule_id: str | None
    track_id: int | None
    object_class: str
    zone_name: str
    entered_at_seconds: float
    occurred_at_seconds: float
    dwell_seconds: float
    confidence: float
    occurred_at: datetime
    clip_uri: str
    details: dict[str, object]
    created_at: datetime


class ActorRead(ApiModel):
    subject: str
    organization_id: str
    role: OrganizationRole
    issuer: str
    email: str | None
    display_name: str | None


class AlertChannelCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    webhook_url: HttpUrl
    signing_secret: str = Field(min_length=16, max_length=500)
    enabled: bool = True
    timeout_seconds: float = Field(default=10, gt=0, le=60)
    max_attempts: int = Field(default=6, ge=1, le=20)


class AlertChannelUpdate(ApiModel):
    webhook_url: HttpUrl | None = None
    signing_secret: str | None = Field(default=None, min_length=16, max_length=500)
    enabled: bool | None = None
    timeout_seconds: float | None = Field(default=None, gt=0, le=60)
    max_attempts: int | None = Field(default=None, ge=1, le=20)


class AlertChannelRead(ApiModel):
    id: str
    organization_id: str
    name: str
    webhook_url: str
    enabled: bool
    timeout_seconds: float
    max_attempts: int
    created_at: datetime
    updated_at: datetime


class RuleAlertRouteCreate(ApiModel):
    channel_id: str = Field(min_length=1, max_length=36)
    cooldown_seconds: int = Field(default=0, ge=0, le=604800)
    delay_seconds: int = Field(default=0, ge=0, le=604800)


class RuleAlertRouteRead(ApiModel):
    id: str
    rule_id: str
    channel_id: str
    channel_name: str
    cooldown_seconds: int
    delay_seconds: int
    created_at: datetime


class AlertDeliveryRead(ApiModel):
    id: str
    channel_id: str
    channel_name: str
    status: AlertDeliveryStatus
    attempt_count: int
    next_attempt_at: datetime
    last_status_code: int | None
    last_error: str | None
    delivered_at: datetime | None


class AlertRead(ApiModel):
    id: str
    event_id: str
    status: AlertStatus
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    resolved_at: datetime | None
    resolved_by: str | None
    created_at: datetime
    updated_at: datetime
    event: EventRead
    deliveries: list[AlertDeliveryRead]


class AlertActor(ApiModel):
    actor: str = Field(default="operator", min_length=1, max_length=120)


class TestAlertCreate(ApiModel):
    """Create an unmistakably synthetic incident for operator workflow testing."""

    deliver_outbound: bool = False


class AlertWorkerClaim(ApiModel):
    worker_id: str = Field(min_length=1, max_length=120)


class AlertDeliveryAssignment(ApiModel):
    delivery_id: str
    alert_id: str
    event_id: str
    webhook_url: HttpUrl
    signing_secret: str
    timeout_seconds: float
    payload: dict[str, object]


class AlertDeliveryResult(ApiModel):
    worker_id: str = Field(min_length=1, max_length=120)
    outcome: Literal["delivered", "retryable", "permanent_failure"]
    status_code: int | None = Field(default=None, ge=100, le=599)
    error: str | None = Field(default=None, max_length=1000)


class EvidenceRead(ApiModel):
    id: str
    event_id: str
    status: EvidenceStatus
    media_type: str | None
    size_bytes: int | None
    sha256: str | None
    duration_seconds: float | None
    provider: str
    external_index_id: str | None
    external_video_id: str | None
    retry_count: int
    last_error: str | None
    content_url: str | None = None
    created_at: datetime
    updated_at: datetime


class EvidenceSearchCreate(ApiModel):
    query: str = Field(min_length=2, max_length=1000)
    camera_id: str | None = Field(default=None, min_length=1, max_length=36)
    limit: int = Field(default=10, ge=1, le=50)
    provider: Literal["auto", "local", "artae_labs"] = "auto"


class EvidenceSearchHit(ApiModel):
    evidence_id: str
    event_id: str
    camera_id: str
    camera_name: str
    time_start: float = Field(ge=0)
    time_end: float = Field(ge=0)
    similarity: float = Field(ge=0, le=1)
    summary: str
    occurred_at: datetime
    content_url: str


class EvidenceSearchRead(ApiModel):
    id: str
    organization_id: str
    query: str
    camera_id: str | None
    limit: int
    provider: str
    status: EvidenceSearchStatus
    results: list[EvidenceSearchHit]
    latency_ms: int | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class EvidenceWorkerClaim(ApiModel):
    worker_id: str = Field(min_length=1, max_length=120)


class EvidenceIndexAssignment(ApiModel):
    asset_id: str
    event_id: str
    title: str
    duration_seconds: float | None


class EvidenceIndexResult(ApiModel):
    worker_id: str = Field(min_length=1, max_length=120)
    status: Literal["ready", "unavailable", "failed"]
    external_index_id: str | None = Field(default=None, max_length=200)
    external_video_id: str | None = Field(default=None, max_length=200)
    error: str | None = Field(default=None, max_length=1000)


class EvidenceSearchAssignment(ApiModel):
    search_id: str
    query: str
    camera_id: str | None
    limit: int


class ProviderSearchHit(ApiModel):
    video_id: str
    time_start: float = Field(ge=0)
    time_end: float = Field(ge=0)
    similarity: float = Field(ge=0, le=1)
    summary: str | None = Field(default=None, max_length=2000)


class EvidenceSearchResult(ApiModel):
    worker_id: str = Field(min_length=1, max_length=120)
    status: Literal["completed", "unavailable", "failed"]
    latency_ms: int | None = Field(default=None, ge=0)
    results: list[ProviderSearchHit] = Field(default_factory=list, max_length=100)
    error: str | None = Field(default=None, max_length=1000)


class AgentZoneConfig(ApiModel):
    id: str
    name: str
    geometry_type: GeometryType = GeometryType.POLYGON
    points: list[ZonePoint] = Field(min_length=2)


class AgentRuleConfig(ApiModel):
    id: str
    key: str
    rule_type: str
    object_class: str
    duration_seconds: float
    minimum_confidence: float
    absence_grace_seconds: float
    zone: AgentZoneConfig
    spec: CameraJobSpec | None = None

    @computed_field
    @property
    def execution_plan(self) -> ExecutionPlan | None:
        return plan_job(self.spec) if self.spec is not None else None


class AgentCameraConfig(ApiModel):
    camera_id: str
    camera_name: str
    source_uri: str
    source_type: SourceType
    rules: list[AgentRuleConfig]


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
