import type {
  AlertChannel,
  ActionExecution,
  AlertIncident,
  Camera,
  CameraAgent,
  CameraStream,
  CompileRuleInput,
  CreateAlertChannelInput,
  CreateAlertRouteInput,
  CreateCameraInput,
  CreateReplaySuiteInput,
  CreateRuleInput,
  CreateZoneInput,
  CurrentActor,
  ConnectorType,
  ContextSource,
  CorrelationEvaluation,
  EdgeDevice,
  EdgeDeviceCredential,
  EdgeFleetDevice,
  EdgeStationProfile,
  AuditLog,
  EvidenceAsset,
  EvidenceSearch,
  Rule,
  RuleCompilation,
  PlatformCapabilities,
  ProductionReadiness,
  RuleStatus,
  ReplayEvaluation,
  ReplaySuite,
  ReplaySuiteRun,
  ReplayUpload,
  CreateReplayEvaluationInput,
  ScoreReplayEvaluationInput,
  AgentDesiredStatus,
  VideoEvent,
  IntegrationConnector,
  RuleActionBinding,
  RuleCorrelationPolicy,
  SceneChange,
  SceneMemoryItem,
  Site,
  SiteMap,
  InvestigationSearch,
  Zone,
  VisualAgentPlan,
  VisualAgentSimulation,
} from "@/lib/types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function authenticationHeaders(): Record<string, string> {
  const accessToken = typeof window === "undefined" ? null : sessionStorage.getItem("access_token");
  return {
    ...(process.env.NEXT_PUBLIC_DASHBOARD_KEY
      ? { "X-Dashboard-Key": process.env.NEXT_PUBLIC_DASHBOARD_KEY }
      : {}),
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...authenticationHeaders(),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      `Could not reach the control plane at ${API_URL}. Is the API running?`,
      0,
    );
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string | { message?: string };
    } | null;
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : detail?.message;
    throw new ApiError(message ?? `Request failed with HTTP ${response.status}.`, response.status);
  }
  return (await response.json()) as T;
}

async function cameraPreview(cameraId: string): Promise<Blob | null> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1/cameras/${cameraId}/preview`, {
      cache: "no-store",
      headers: authenticationHeaders(),
    });
  } catch {
    return null;
  }
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new ApiError(`Preview request failed with HTTP ${response.status}.`, response.status);
  }
  return response.blob();
}

export const api = {
  getIdentity: () => request<CurrentActor>("/identity/me"),
  listEdgeDevices: () => request<EdgeDevice[]>("/edge-devices"),
  listEdgeFleet: () => request<EdgeFleetDevice[]>("/edge-devices/fleet"),
  createEdgeDevice: (name: string, maxConcurrentStreams: number) =>
    request<EdgeDeviceCredential>("/edge-devices", {
      method: "POST",
      body: JSON.stringify({ name, max_concurrent_streams: maxConcurrentStreams }),
    }),
  rotateEdgeDeviceCredential: (deviceId: string) =>
    request<EdgeDeviceCredential>(`/edge-devices/${deviceId}/rotate-credential`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  revokeEdgeDevice: (deviceId: string) =>
    request<EdgeDevice>(`/edge-devices/${deviceId}/revoke`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  createDemoFleetProfile: (deviceId: string) =>
    request<EdgeStationProfile>(`/edge-devices/${deviceId}/fleet/demo-profile`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  listAuditLogs: () => request<AuditLog[]>("/audit-logs?limit=50"),
  getCapabilities: () => request<PlatformCapabilities>("/capabilities"),
  getProductionReadiness: () =>
    request<ProductionReadiness>("/production/readiness"),
  listCameras: () => request<Camera[]>("/cameras"),
  createCamera: (input: CreateCameraInput) =>
    request<Camera>("/cameras", { method: "POST", body: JSON.stringify(input) }),
  provisionCameraStream: (cameraId: string) =>
    request<CameraStream>(`/cameras/${cameraId}/stream`, { method: "PUT" }),
  getCameraStream: (cameraId: string) =>
    request<CameraStream>(`/cameras/${cameraId}/stream`),
  getCameraAgent: (cameraId: string) => request<CameraAgent>(`/cameras/${cameraId}/agent`),
  getCameraPreview: cameraPreview,
  updateCameraAgent: (cameraId: string, desiredStatus: AgentDesiredStatus) =>
    request<CameraAgent>(`/cameras/${cameraId}/agent`, {
      method: "PUT",
      body: JSON.stringify({ desired_status: desiredStatus }),
    }),
  listZones: () => request<Zone[]>("/zones"),
  createZone: (input: CreateZoneInput) =>
    request<Zone>("/zones", { method: "POST", body: JSON.stringify(input) }),
  listRules: () => request<Rule[]>("/rules"),
  createRule: (input: CreateRuleInput) =>
    request<Rule>("/rules", { method: "POST", body: JSON.stringify(input) }),
  compileRule: (input: CompileRuleInput) =>
    request<RuleCompilation>("/rule-compilations", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  clarifyRuleCompilation: (compilationId: string, answer: string) =>
    request<RuleCompilation>("/rule-compilations/" + compilationId + "/clarifications", {
      method: "POST",
      body: JSON.stringify({ answer }),
    }),
  acceptRuleCompilation: (compilationId: string) =>
    request<Rule>("/rule-compilations/" + compilationId + "/accept", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  updateRuleStatus: (ruleId: string, status: RuleStatus) =>
    request<Rule>(`/rules/${ruleId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  listEvents: () => request<VideoEvent[]>("/events?limit=100"),
  listAlerts: () => request<AlertIncident[]>("/alerts?limit=100"),
  listAlertChannels: () => request<AlertChannel[]>("/alert-channels"),
  createAlertChannel: (input: CreateAlertChannelInput) =>
    request<AlertChannel>("/alert-channels", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  createAlertRoute: (ruleId: string, input: CreateAlertRouteInput) =>
    request(`/rules/${ruleId}/alert-routes`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  createTestAlert: (ruleId: string) =>
    request<AlertIncident>(`/rules/${ruleId}/test-alert`, {
      method: "POST",
      body: JSON.stringify({ deliver_outbound: false }),
    }),
  acknowledgeAlert: (alertId: string) =>
    request<AlertIncident>(`/alerts/${alertId}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({ actor: "dashboard-operator" }),
    }),
  resolveAlert: (alertId: string) =>
    request<AlertIncident>(`/alerts/${alertId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ actor: "dashboard-operator" }),
    }),
  listEvidence: () => request<EvidenceAsset[]>("/evidence?limit=100"),
  createEvidenceSearch: (query: string, cameraId: string | null) =>
    request<EvidenceSearch>("/evidence/searches", {
      method: "POST",
      body: JSON.stringify({ query, camera_id: cameraId, provider: "auto", limit: 12 }),
    }),
  getEvidenceSearch: (searchId: string) =>
    request<EvidenceSearch>(`/evidence/searches/${searchId}`),
  listReplayEvaluations: () => request<ReplayEvaluation[]>("/evaluations?limit=50"),
  uploadReplayVideo: async (file: File) => {
    let response: Response;
    try {
      response = await fetch(`${API_URL}/api/v1/evaluations/uploads`, {
        method: "POST",
        headers: {
          ...authenticationHeaders(),
          "Content-Type": file.type || "application/octet-stream",
          "X-Replay-Filename": encodeURIComponent(file.name),
        },
        body: file,
      });
    } catch {
      throw new ApiError(
        `Could not reach the control plane at ${API_URL}. Is the API running?`,
        0,
      );
    }
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as { detail?: string } | null;
      throw new ApiError(body?.detail ?? `Upload failed with HTTP ${response.status}.`, response.status);
    }
    return (await response.json()) as ReplayUpload;
  },
  getReplayEvaluation: (evaluationId: string) =>
    request<ReplayEvaluation>(`/evaluations/${evaluationId}`),
  createReplayEvaluation: (input: CreateReplayEvaluationInput) =>
    request<ReplayEvaluation>("/evaluations", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  scoreReplayEvaluation: (evaluationId: string, input: ScoreReplayEvaluationInput) =>
    request<ReplayEvaluation>(`/evaluations/${evaluationId}/score`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  runReplayEvaluation: (evaluationId: string) =>
    request<ReplayEvaluation>(`/evaluations/${evaluationId}/run`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  listReplaySuites: () => request<ReplaySuite[]>("/evaluation-suites?limit=50"),
  getReplaySuite: (suiteId: string) =>
    request<ReplaySuite>(`/evaluation-suites/${suiteId}`),
  createReplaySuite: (input: CreateReplaySuiteInput) =>
    request<ReplaySuite>("/evaluation-suites", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  runReplaySuite: (suiteId: string) =>
    request<ReplaySuiteRun>(`/evaluation-suites/${suiteId}/runs`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  listReplaySuiteRuns: (suiteId: string) =>
    request<ReplaySuiteRun[]>(`/evaluation-suites/${suiteId}/runs?limit=20`),
  listAgentPlans: (cameraId?: string) =>
    request<VisualAgentPlan[]>(`/agent-plans${cameraId ? `?camera_id=${encodeURIComponent(cameraId)}` : ""}`),
  createAgentPlan: (ruleId: string) =>
    request<VisualAgentPlan>("/agent-plans", {
      method: "POST",
      body: JSON.stringify({ rule_id: ruleId }),
    }),
  simulateAgentPlan: (planId: string) =>
    request<VisualAgentSimulation>(`/agent-plans/${planId}/simulate`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  approveAgentPlan: (planId: string, regressionRunId: string) =>
    request<VisualAgentPlan>(`/agent-plans/${planId}/approve`, {
      method: "POST",
      body: JSON.stringify({ regression_run_id: regressionRunId }),
    }),
  rollbackAgentPlan: (planId: string) =>
    request<VisualAgentPlan>(`/agent-plans/${planId}/rollback`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  listConnectors: () => request<IntegrationConnector[]>("/connectors"),
  createConnector: (input: {
    name: string;
    connector_type: ConnectorType;
    endpoint_url?: string;
    credential: string;
    scopes: string[];
  }) => request<IntegrationConnector>("/connectors", {
    method: "POST",
    body: JSON.stringify(input),
  }),
  listRuleActions: (ruleId: string) =>
    request<RuleActionBinding[]>(`/rules/${ruleId}/actions`),
  createRuleAction: (ruleId: string, input: {
    connector_id: string;
    action_type: "send_notification" | "create_ticket" | "invoke_webhook";
    approval_mode?: "automatic" | "manual";
    rate_limit_per_minute?: number;
  }) => request<RuleActionBinding>(`/rules/${ruleId}/actions`, {
    method: "POST",
    body: JSON.stringify(input),
  }),
  listActionExecutions: () => request<ActionExecution[]>("/action-executions?limit=50"),
  approveActionExecution: (executionId: string) =>
    request<ActionExecution>(`/action-executions/${executionId}/approve`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  denyActionExecution: (executionId: string, reason: string) =>
    request<ActionExecution>(`/action-executions/${executionId}/deny`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  retryActionExecution: (executionId: string) =>
    request<ActionExecution>(`/action-executions/${executionId}/retry`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  listContextSources: () => request<ContextSource[]>("/context-sources"),
  createContextSource: (name: string) =>
    request<ContextSource>("/context-sources", {
      method: "POST",
      body: JSON.stringify({ name, source_type: "simulated_access_control" }),
    }),
  listCorrelationPolicies: (ruleId: string) =>
    request<RuleCorrelationPolicy[]>(`/rules/${ruleId}/correlation-policies`),
  createCorrelationPolicy: (ruleId: string, sourceId: string) =>
    request<RuleCorrelationPolicy>(`/rules/${ruleId}/correlation-policies`, {
      method: "POST",
      body: JSON.stringify({
        source_id: sourceId,
        correlation_type: "count_exceeds_authorizations",
        observation_type: "access_granted",
        visual_count_field: "person_count",
        window_before_seconds: 5,
        window_after_seconds: 1,
      }),
    }),
  listCorrelationEvaluations: () =>
    request<CorrelationEvaluation[]>("/correlation-evaluations?limit=20"),
  runTailgatingDemo: (ruleId: string) =>
    request<VideoEvent>(`/rules/${ruleId}/correlation-demo`, {
      method: "POST",
      body: JSON.stringify({ visual_people: 2, authorized_entries: 1 }),
    }),
  listSceneMemory: (cameraId: string) =>
    request<SceneMemoryItem[]>(`/cameras/${cameraId}/scene-memory`),
  listSceneChanges: (cameraId: string) =>
    request<SceneChange[]>(`/cameras/${cameraId}/scene-changes?limit=20`),
  runSceneDiscoveryDemo: (cameraId: string) =>
    request<SceneMemoryItem[]>(`/cameras/${cameraId}/scene-memory/demo-discovery`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  reviewSceneMemory: (
    itemId: string,
    reviewStatus: "confirmed" | "rejected",
  ) =>
    request<SceneMemoryItem>(`/scene-memory/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({ review_status: reviewStatus }),
    }),
  listSites: () => request<Site[]>("/sites"),
  getSiteMap: (siteId: string) => request<SiteMap>(`/sites/${siteId}/map`),
  setupOperationsDemo: (cameraId: string) =>
    request<SiteMap>(`/cameras/${cameraId}/operations/demo`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  searchInvestigations: (query: string, cameraIds: string[] = []) =>
    request<InvestigationSearch>("/investigations/search", {
      method: "POST",
      body: JSON.stringify({ query, camera_ids: cameraIds, limit: 50 }),
    }),
};

export function evidenceContentUrl(path: string): string {
  return `${API_URL}${path}`;
}

export function eventWebSocketUrl(): string | null {
  const key = typeof window === "undefined" ? null : sessionStorage.getItem("access_token");
  const token = key ?? process.env.NEXT_PUBLIC_DASHBOARD_KEY;
  if (!token) return null;
  const url = new URL(API_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/api/v1/ws/events";
  url.search = new URLSearchParams({ token }).toString();
  return url.toString();
}
