export type CameraStatus = "offline" | "online" | "error" | "disabled";
export type SourceType = "webcam" | "file" | "rtsp";
export type GeometryType = "polygon" | "line";
export type RuleStatus = "draft" | "active" | "paused";
export type RuleCompilationStatus = "needs_clarification" | "ready_for_review" | "accepted";
export type AlertStatus = "open" | "acknowledged" | "resolved";
export type AlertDeliveryStatus =
  | "queued"
  | "delivering"
  | "retrying"
  | "delivered"
  | "failed"
  | "suppressed";
export type OrganizationRole = "owner" | "admin" | "operator" | "viewer";
export type EdgeDeviceStatus = "active" | "revoked";
export type AgentDesiredStatus = "stopped" | "running";
export type AgentObservedStatus =
  | "stopped"
  | "waiting"
  | "starting"
  | "running"
  | "stopping"
  | "error";
export type EvidenceStatus =
  | "awaiting_upload"
  | "queued"
  | "indexing"
  | "ready"
  | "unavailable"
  | "failed";
export type EvidenceSearchStatus =
  | "queued"
  | "searching"
  | "completed"
  | "unavailable"
  | "failed";
export type ReplayEvaluationStatus = "draft" | "queued" | "running" | "scored" | "failed";
export type ReplaySuiteRunStatus = "queued" | "running" | "passed" | "failed";
export type VisualAgentPlanStatus = "draft" | "approved" | "superseded";
export type ConnectorType = "mock" | "generic_webhook" | "messaging_webhook" | "ticket_webhook";
export type ActionRiskLevel = "low" | "medium" | "high";
export type ActionApprovalMode = "automatic" | "manual";
export type ActionExecutionStatus =
  | "awaiting_approval"
  | "queued"
  | "running"
  | "retrying"
  | "succeeded"
  | "dead_lettered"
  | "denied"
  | "suppressed";
export type ContextSourceType = "simulated_access_control" | "generic_event_feed";
export type CorrelationEvaluationStatus = "pending" | "matched" | "clear" | "failed";
export type SceneItemKind = "region" | "equipment" | "display" | "tracked_entity" | "other";
export type SceneReviewStatus = "proposed" | "confirmed" | "rejected";

export interface Camera {
  id: string;
  organization_id: string;
  name: string;
  source_uri: string;
  source_type: SourceType;
  status: CameraStatus;
  created_at: string;
  updated_at: string;
}

export interface CameraStream {
  camera_id: string;
  path: string;
  mode: "proxy" | "publisher";
  configured: boolean;
  ready: boolean;
  readers: number;
  playback_url: string;
  whep_url: string;
  publish_url: string | null;
}

export interface CameraAgent {
  camera_id: string;
  desired_status: AgentDesiredStatus;
  observed_status: AgentObservedStatus;
  worker_id: string | null;
  edge_device_id: string | null;
  lease_expires_at: string | null;
  last_heartbeat_at: string | null;
  fps: number | null;
  inference_latency_ms: number | null;
  frame_width: number | null;
  frame_height: number | null;
  last_error: string | null;
  updated_at: string | null;
}

export interface PlatformCapabilities {
  schema_version: number;
  detector: { model: string; object_classes: string[] };
  event_types: string[];
  platform_event_types: string[];
  capabilities: string[];
}

export interface LiveDetection {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label: string;
  confidence: number;
  track_id: number | null;
}

export interface AgentTelemetry {
  worker_id: string;
  camera_id: string;
  observed_status: AgentObservedStatus;
  desired_status: AgentDesiredStatus;
  fps: number | null;
  inference_latency_ms: number | null;
  frame_width: number | null;
  frame_height: number | null;
  detections: LiveDetection[];
  error: string | null;
  analysis_state: string | null;
  analysis_sequence: number | null;
  analysis_triggered: boolean | null;
  analysis_confidence: number | null;
  analysis_summary: string | null;
  analysis_error: string | null;
  analysis_requests_today: number;
  analysis_request_limit_day: number;
  analysis_request_limit_minute: number;
}

export interface ZonePoint {
  x: number;
  y: number;
}

export interface Zone {
  id: string;
  camera_id: string;
  name: string;
  geometry_type: GeometryType;
  points: ZonePoint[];
  created_at: string;
  updated_at: string;
}

export interface Rule {
  id: string;
  camera_id: string;
  zone_id: string;
  key: string;
  name: string;
  rule_type: string;
  object_class: string;
  duration_seconds: number;
  minimum_confidence: number;
  absence_grace_seconds: number;
  status: RuleStatus;
  original_prompt: string | null;
  spec_version: number;
  spec: CameraJobSpec | null;
  execution_plan: ExecutionPlan | null;
  created_at: string;
  updated_at: string;
}

export interface LegacyObjectDwellJob {
  schema_version: 1;
  rule_type: "object_dwell";
  object_class: string;
  zone_id: string;
  zone_name: string;
  duration_seconds: number;
  minimum_confidence: number;
  absence_grace_seconds: number;
}

interface JobV2Base {
  schema_version: 2;
  object_class: string;
  minimum_confidence: number;
  absence_grace_seconds: number;
}

interface ZoneJobBase extends JobV2Base {
  zone_id: string;
  zone_name: string;
}

export interface ZoneDwellJob extends ZoneJobBase {
  rule_type: "zone_dwell";
  duration_seconds: number;
}

export interface ZonePresenceJob extends ZoneJobBase {
  rule_type: "zone_presence";
  confirmation_seconds: number;
}

export interface ZoneEntryJob extends ZoneJobBase { rule_type: "zone_entry"; }
export interface ZoneExitJob extends ZoneJobBase { rule_type: "zone_exit"; }

export interface CountThresholdJob extends ZoneJobBase {
  rule_type: "count_threshold";
  comparison: "at_least" | "at_most";
  threshold: number;
  confirmation_seconds: number;
}

export interface LineCrossingJob extends JobV2Base {
  rule_type: "line_crossing";
  line_id: string;
  line_name: string;
  direction: "any" | "forward" | "reverse";
}

export interface SemanticVisionJob {
  schema_version: 3;
  rule_type: "semantic_vision";
  instruction: string;
  object_class: string;
  zone_id: string;
  zone_name: string;
  minimum_confidence: number;
  absence_grace_seconds: number;
  confirmation_windows: number;
  cooldown_seconds: number;
}

export type CameraJobSpec =
  | LegacyObjectDwellJob
  | ZoneDwellJob
  | ZonePresenceJob
  | ZoneEntryJob
  | ZoneExitJob
  | CountThresholdJob
  | LineCrossingJob
  | SemanticVisionJob;

export interface ExecutionStage {
  id: string;
  label: string;
  executor: string;
  cadence: "every_frame" | "sampled_window" | "on_candidate" | "on_event";
  locality: "edge" | "vision_provider";
  purpose: string;
}

export interface ExecutionPlan {
  schema_version: 1;
  strategy: "deterministic_tracking" | "semantic_window";
  summary: string;
  provider_requests: boolean;
  stages: ExecutionStage[];
}

export interface RuleCompilation {
  id: string;
  camera_id: string;
  parent_id: string | null;
  revision: number;
  prompt: string;
  provider: string;
  provider_model: string | null;
  compiler_version: string;
  status: RuleCompilationStatus;
  compiled_rule: CameraJobSpec | null;
  execution_plan: ExecutionPlan | null;
  explanation: string;
  clarification_question: string | null;
  warnings: string[];
  accepted_rule_id: string | null;
  created_at: string;
  reviewed_at: string | null;
}

export interface VideoEvent {
  id: string;
  source_event_id: string;
  schema_version: number;
  event_type: string;
  camera_id: string;
  rule_id: string | null;
  track_id: number | null;
  object_class: string;
  zone_name: string;
  entered_at_seconds: number;
  occurred_at_seconds: number;
  dwell_seconds: number;
  confidence: number;
  occurred_at: string;
  clip_uri: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AlertChannel {
  id: string;
  organization_id: string;
  name: string;
  webhook_url: string;
  enabled: boolean;
  timeout_seconds: number;
  max_attempts: number;
  created_at: string;
  updated_at: string;
}

export interface AlertDelivery {
  id: string;
  channel_id: string;
  channel_name: string;
  status: AlertDeliveryStatus;
  attempt_count: number;
  next_attempt_at: string;
  last_status_code: number | null;
  last_error: string | null;
  delivered_at: string | null;
}

export interface AlertIncident {
  id: string;
  event_id: string;
  status: AlertStatus;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  created_at: string;
  updated_at: string;
  event: VideoEvent;
  deliveries: AlertDelivery[];
}

export interface CreateAlertChannelInput {
  name: string;
  webhook_url: string;
  signing_secret: string;
}

export interface CreateAlertRouteInput {
  channel_id: string;
  cooldown_seconds: number;
  delay_seconds: number;
}

export interface EvidenceAsset {
  id: string;
  event_id: string;
  status: EvidenceStatus;
  media_type: string | null;
  size_bytes: number | null;
  sha256: string | null;
  duration_seconds: number | null;
  provider: string;
  external_index_id: string | null;
  external_video_id: string | null;
  retry_count: number;
  last_error: string | null;
  content_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvidenceSearchHit {
  evidence_id: string;
  event_id: string;
  camera_id: string;
  camera_name: string;
  time_start: number;
  time_end: number;
  similarity: number;
  summary: string;
  occurred_at: string;
  content_url: string;
}

export interface EvidenceSearch {
  id: string;
  organization_id: string;
  query: string;
  camera_id: string | null;
  limit: number;
  provider: string;
  status: EvidenceSearchStatus;
  results: EvidenceSearchHit[];
  latency_ms: number | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvaluationInterval {
  start_seconds: number;
  end_seconds: number;
  label: string;
  detected_at_seconds?: number;
  confidence?: number;
}

export interface ReplayEvaluationMetrics {
  true_positives?: number;
  false_positives?: number;
  false_negatives?: number;
  precision?: number;
  recall?: number;
  f1?: number;
  mean_latency_seconds?: number | null;
  provider_requests?: number;
  input_tokens?: number;
  output_tokens?: number;
  estimated_cost_usd?: number;
  pricing_configured?: boolean;
}

export interface ReplayEvaluation {
  id: string;
  organization_id: string;
  camera_id: string;
  compilation_id: string;
  name: string;
  source_uri: string;
  prompt: string;
  duration_seconds: number;
  execution_strategy: ExecutionPlan["strategy"];
  compiled_rule: CameraJobSpec;
  execution_plan: ExecutionPlan;
  expected_intervals: EvaluationInterval[];
  predicted_intervals: EvaluationInterval[];
  metrics: ReplayEvaluationMetrics;
  provider_requests: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  status: ReplayEvaluationStatus;
  worker_id: string | null;
  lease_expires_at: string | null;
  started_at: string | null;
  processed_seconds: number;
  progress_percent: number;
  last_progress_at: string | null;
  last_error: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReplayUpload {
  source_uri: string;
  filename: string;
  media_type: string;
  size_bytes: number;
}

export interface CreateReplayEvaluationInput {
  name: string;
  camera_id: string;
  source_uri: string;
  prompt: string;
  duration_seconds: number;
  expected_intervals: EvaluationInterval[];
}

export interface ScoreReplayEvaluationInput {
  predicted_intervals: EvaluationInterval[];
  provider_requests: number;
  input_tokens: number;
  output_tokens: number;
  input_price_per_million_usd: number;
  output_price_per_million_usd: number;
}

export interface ReplayGateResult {
  key: string;
  label: string;
  actual: number | boolean;
  operator: string;
  threshold: number | boolean;
  passed: boolean;
}

export interface ReplaySuiteRun {
  id: string;
  organization_id: string;
  suite_id: string;
  evaluation_ids: string[];
  thresholds: Record<string, number | boolean>;
  status: ReplaySuiteRunStatus;
  results: Array<{
    evaluation_id: string;
    name: string;
    status: ReplayEvaluationStatus;
    execution_strategy: ExecutionPlan["strategy"];
    metrics: ReplayEvaluationMetrics;
    estimated_cost_usd: number;
    last_error: string | null;
  }>;
  metrics: {
    evaluation_count?: number;
    completed_count?: number;
    scored_count?: number;
    failed_count?: number;
    macro_precision?: number;
    macro_recall?: number;
    macro_f1?: number;
    false_positives?: number;
    false_negatives?: number;
    provider_requests?: number;
    estimated_cost_usd?: number;
    pricing_complete?: boolean;
  };
  gate_results: ReplayGateResult[];
  started_at: string;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReplaySuite {
  id: string;
  organization_id: string;
  name: string;
  evaluation_ids: string[];
  minimum_macro_f1: number;
  minimum_macro_recall: number;
  maximum_false_positives: number;
  maximum_estimated_cost_usd: number;
  require_pricing: boolean;
  latest_run: ReplaySuiteRun | null;
  created_at: string;
  updated_at: string;
}

export interface CreateReplaySuiteInput {
  name: string;
  evaluation_ids: string[];
  minimum_macro_f1: number;
  minimum_macro_recall: number;
  maximum_false_positives: number;
  maximum_estimated_cost_usd: number;
  require_pricing: boolean;
}

export interface VisualAgentNode {
  id: string;
  kind: "observe" | "query" | "decide" | "verify" | "act";
  title: string;
  description: string;
  executor: string;
  capability: string;
  depends_on: string[];
  side_effect: boolean;
}

export interface VisualAgentPlan {
  id: string;
  organization_id: string;
  camera_id: string;
  rule_id: string;
  compilation_id: string | null;
  parent_id: string | null;
  revision: number;
  prompt: string;
  status: VisualAgentPlanStatus;
  plan: {
    schema_version: 1;
    summary: string;
    strategy: ExecutionPlan["strategy"];
    nodes: VisualAgentNode[];
  };
  required_capabilities: string[];
  unsupported_capabilities: string[];
  approved_by: string | null;
  approved_at: string | null;
  regression_run_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface VisualAgentSimulation {
  id: string;
  organization_id: string;
  plan_id: string;
  trace: Array<{
    node_id: string;
    kind: VisualAgentNode["kind"];
    title: string;
    outcome: string;
    side_effect_performed: boolean;
  }>;
  summary: string;
  created_at: string;
}

export interface IntegrationConnector {
  id: string;
  organization_id: string;
  name: string;
  connector_type: ConnectorType;
  endpoint_url: string | null;
  scopes: string[];
  enabled: boolean;
  timeout_seconds: number;
  max_attempts: number;
  created_at: string;
  updated_at: string;
}

export interface RuleActionBinding {
  id: string;
  organization_id: string;
  rule_id: string;
  connector_id: string;
  connector_name: string;
  action_type: "send_notification" | "create_ticket" | "invoke_webhook" | "control_physical";
  risk_level: ActionRiskLevel;
  approval_mode: ActionApprovalMode;
  rate_limit_per_minute: number;
  payload_template: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ActionExecution {
  id: string;
  organization_id: string;
  alert_id: string;
  event_id: string;
  binding_id: string;
  connector_id: string;
  connector_name: string;
  action_type: string;
  risk_level: ActionRiskLevel;
  status: ActionExecutionStatus;
  idempotency_key: string;
  payload: Record<string, unknown>;
  attempt_count: number;
  manual_retry_count: number;
  next_attempt_at: string;
  last_status_code: number | null;
  last_error: string | null;
  approved_by: string | null;
  approved_at: string | null;
  denied_by: string | null;
  denied_at: string | null;
  denial_reason: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContextSource {
  id: string;
  organization_id: string;
  name: string;
  source_type: ContextSourceType;
  endpoint_url: string | null;
  configuration: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface RuleCorrelationPolicy {
  id: string;
  organization_id: string;
  rule_id: string;
  source_id: string;
  source_name: string;
  correlation_type: "count_exceeds_authorizations";
  observation_type: string;
  visual_count_field: string;
  window_before_seconds: number;
  window_after_seconds: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CorrelationEvaluation {
  id: string;
  organization_id: string;
  event_id: string;
  policy_id: string;
  source_id: string;
  source_name: string;
  status: CorrelationEvaluationStatus;
  visual_count: number;
  observation_count: number;
  window_start: string;
  window_end: string;
  due_at: string;
  explanation: string | null;
  evaluated_at: string | null;
  created_at: string;
}

export interface VisualSkillDefinition {
  id: string;
  label: string;
  capability: string;
  preferred_executor: string;
  fallback_executor: string;
  status: "available" | "planned";
  benchmark_policy: string;
}

export interface SceneMemoryItem {
  id: string;
  organization_id: string;
  camera_id: string;
  stable_key: string;
  label: string;
  kind: SceneItemKind;
  bounding_box: { x: number; y: number; width: number; height: number };
  description: string;
  current_state: string;
  confidence: number;
  attributes: Record<string, unknown>;
  relationships: Array<Record<string, unknown>>;
  source: "automatic" | "operator";
  review_status: SceneReviewStatus;
  first_seen_at: string;
  last_seen_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SceneChange {
  id: string;
  organization_id: string;
  camera_id: string;
  item_id: string;
  event_id: string | null;
  previous_state: string | null;
  new_state: string;
  confidence: number;
  details: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
}

export interface Site {
  id: string;
  organization_id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface SiteArea {
  id: string;
  organization_id: string;
  site_id: string;
  name: string;
  area_type: string;
  x: number;
  y: number;
  width: number;
  height: number;
  created_at: string;
}

export interface CameraPlacement {
  id: string;
  organization_id: string;
  site_id: string;
  area_id: string | null;
  area_name: string | null;
  camera_id: string;
  camera_name: string;
  x: number;
  y: number;
  heading_degrees: number;
  created_at: string;
  updated_at: string;
}

export interface EntitySighting {
  id: string;
  organization_id: string;
  camera_id: string;
  camera_name: string;
  area_id: string | null;
  area_name: string | null;
  event_id: string | null;
  entity_key: string;
  label: string;
  bounding_box: { x: number; y: number; width: number; height: number };
  confidence: number;
  attributes: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
}

export interface SiteMap {
  site: Site;
  areas: SiteArea[];
  placements: CameraPlacement[];
  recent_sightings: EntitySighting[];
}

export interface InvestigationResult {
  kind: "event" | "scene" | "entity";
  id: string;
  camera_id: string;
  occurred_at: string;
  title: string;
  summary: string;
  event_id: string | null;
  entity_key: string | null;
  clip_uri: string | null;
}

export interface InvestigationSearch {
  query: string;
  results: InvestigationResult[];
}

export interface CurrentActor {
  subject: string;
  organization_id: string;
  role: OrganizationRole;
  issuer: string;
  email: string | null;
  display_name: string | null;
}

export interface EdgeDevice {
  id: string;
  organization_id: string;
  name: string;
  status: EdgeDeviceStatus;
  max_concurrent_streams: number;
  credential_fingerprint: string;
  last_seen_at: string | null;
  last_worker_id: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EdgeDeviceCredential {
  device: EdgeDevice;
  token: string;
}

export interface EdgeStationProfile {
  device_id: string;
  organization_id: string;
  hostname: string;
  os_name: string;
  architecture: string;
  cpu_count: number;
  memory_mb: number;
  accelerator: string | null;
  storage_available_mb: number;
  worker_version: string;
  health_status: "healthy" | "degraded" | "offline";
  offline_queue_depth: number;
  last_sync_at: string | null;
  details: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface EdgeConfigBundle {
  id: string;
  organization_id: string;
  device_id: string;
  revision: number;
  configuration: Record<string, unknown>;
  content_sha256: string;
  signature: string;
  created_by: string;
  created_at: string;
}

export interface EdgeUpdateDeployment {
  id: string;
  organization_id: string;
  device_id: string;
  from_version: string;
  target_version: string;
  rollback_version: string;
  status: "pending" | "downloading" | "applying" | "succeeded" | "failed" | "rolled_back";
  error: string | null;
  requested_by: string;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EdgeFleetDevice {
  device: EdgeDevice;
  profile: EdgeStationProfile | null;
  config: EdgeConfigBundle | null;
  update: EdgeUpdateDeployment | null;
}

export interface ProductionReadinessCheck {
  key: string;
  label: string;
  passed: boolean;
  guidance: string;
}

export interface ProductionReadiness {
  ready: boolean;
  environment: "development" | "test" | "production";
  checks: ProductionReadinessCheck[];
  blocking_checks: string[];
}

export interface AuditLog {
  id: string;
  organization_id: string;
  actor_subject: string;
  actor_issuer: string;
  actor_role: OrganizationRole;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  status_code: number;
  request_id: string;
  client_host: string | null;
  details: { query_keys: string[] };
  created_at: string;
}

export interface CreateCameraInput {
  name: string;
  source_uri: string;
}

export interface CreateZoneInput {
  camera_id: string;
  name: string;
  geometry_type: GeometryType;
  points: ZonePoint[];
}

export interface CreateRuleInput {
  camera_id: string;
  zone_id: string;
  key: string;
  name: string;
  rule_type: "object_dwell";
  object_class: string;
  duration_seconds: number;
  minimum_confidence: number;
  absence_grace_seconds: number;
  original_prompt: string | null;
}

export interface CompileRuleInput {
  camera_id: string;
  prompt: string;
}

export type StreamStatus = "connecting" | "live" | "offline";
