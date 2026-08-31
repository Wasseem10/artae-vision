"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CameraPanel } from "@/components/camera-panel";
import { CameraCommissioningPanel } from "@/components/camera-commissioning-panel";
import { CameraDiscoveryPanel } from "@/components/camera-discovery-panel";
import { AgentControl } from "@/components/agent-control";
import { AlertPanel } from "@/components/alert-panel";
import { ActiveLearningPanel } from "@/components/active-learning-panel";
import { AuditLogPanel } from "@/components/audit-log-panel";
import { CameraAutomationsWorkspace } from "@/components/camera-automations-workspace";
import { EvidenceSearchPanel } from "@/components/evidence-search";
import { FieldAccuracyPanel } from "@/components/field-accuracy-panel";
import { EdgeDevicesPanel } from "@/components/edge-devices-panel";
import { EventFeed } from "@/components/event-feed";
import { Icon, type IconName } from "@/components/icon";
import { LiveOperationsWorkspace } from "@/components/live-operations-workspace";
import { MvpLaunchpad } from "@/components/mvp-launchpad";
import { OperationalHealthPanel } from "@/components/operational-health-panel";
import { ProductionReadinessPanel } from "@/components/production-readiness-panel";
import { PromotionControlPanel } from "@/components/promotion-control-panel";
import { RecordingTimelinePanel } from "@/components/recording-timeline-panel";
import { RulePanel } from "@/components/rule-panel";
import { ReplayEvaluationPanel } from "@/components/replay-evaluation-panel";
import { VerificationInbox } from "@/components/verification-inbox";
import { ZoneEditor } from "@/components/zone-editor";
import { useEventStream } from "@/hooks/use-event-stream";
import { API_URL, api } from "@/lib/api";
import { prependUniqueEvent } from "@/lib/events";
import { alertsForCamera, evidenceForEvents, eventsForCamera } from "@/lib/incidents";
import { signOut } from "@/lib/supabase";
import type {
  AlertChannel,
  AlertIncident,
  Camera,
  CameraCommissioningRun,
  CameraDiscoveryRun,
  CameraOnboardingRun,
  CameraAgent,
  CameraStream,
  CompileRuleInput,
  CreateAlertChannelInput,
  CreateAlertRouteInput,
  CreateCameraInput,
  CreateCameraCommissioningInput,
  CreateCameraOnboardingInput,
  CreateZoneInput,
  CurrentActor,
  EvidenceAsset,
  Rule,
  RuleCompilation,
  RuleStatus,
  VideoEvent,
  Zone,
  LiveDetection,
  AgentTelemetry,
  AuditLog,
  EdgeDevice,
  EdgeDeviceCredential,
  EdgeFleetDevice,
  PlatformCapabilities,
  OperationalHealthIncident,
  ProductionReadiness,
  RecordingSegment,
  AccuracyEnvironmentTag,
  FieldAccuracyReport,
  VerificationCase,
} from "@/lib/types";

type AdvancedSection =
  | "hub"
  | "cameras"
  | "rules"
  | "evaluations"
  | "verification-inbox"
  | "alerts"
  | "search"
  | "recordings"
  | "agent"
  | "devices"
  | "health"
  | "discovery"
  | "commissioning"
  | "readiness"
  | "accuracy"
  | "learning"
  | "promotion"
  | "audit";

const ADVANCED_TOOL_COPY: Record<AdvancedSection, { title: string; description: string }> = {
  hub: { title: "Advanced tools", description: "Choose one maintenance tool. Only that tool appears on the page." },
  cameras: { title: "Camera setup", description: "Add a camera and define the part of the scene it should watch." },
  rules: { title: "Automation rules", description: "Review, activate, or pause the camera commands you created." },
  evaluations: { title: "Upload testing", description: "Test an automation against recorded video before using it live." },
  "verification-inbox": { title: "Cases", description: "Review uncertain incidents that need a person to decide." },
  alerts: { title: "Alerts", description: "Review incidents and manage delivery destinations." },
  search: { title: "Evidence search", description: "Find recorded moments and recent camera events." },
  recordings: { title: "Recordings", description: "Review retained video from the selected camera." },
  agent: { title: "Camera runtime", description: "Inspect detailed camera-worker status and throughput." },
  devices: { title: "Computer and edge devices", description: "Manage the computers that run camera analysis." },
  health: { title: "System health", description: "Review current camera and worker reliability incidents." },
  discovery: { title: "Network camera discovery", description: "Find and connect ONVIF cameras on the local network." },
  commissioning: { title: "Camera health check", description: "Run a technical quality check when a feed is not usable." },
  readiness: { title: "Production readiness", description: "Review security and hosting requirements for deployment." },
  accuracy: { title: "Field accuracy", description: "Review misses and control conservative automation policies." },
  learning: { title: "Review dataset", description: "Curate difficult examples for future model improvements." },
  promotion: { title: "Model promotion", description: "Compare model versions and control production rollout." },
  audit: { title: "Audit log", description: "Review administrative changes without exposing request secrets." },
};

export function Dashboard() {
  const [consoleMode, setConsoleMode] = useState<"guided" | "advanced">("guided");
  const [guidedView, setGuidedView] = useState<"live" | "automations">("automations");
  const [advancedSection, setAdvancedSection] = useState<AdvancedSection>("hub");
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [events, setEvents] = useState<VideoEvent[]>([]);
  const [alerts, setAlerts] = useState<AlertIncident[]>([]);
  const [alertChannels, setAlertChannels] = useState<AlertChannel[]>([]);
  const [evidence, setEvidence] = useState<EvidenceAsset[]>([]);
  const [verificationCases, setVerificationCases] = useState<VerificationCase[]>([]);
  const [fieldAccuracyReports, setFieldAccuracyReports] = useState<FieldAccuracyReport[]>([]);
  const [edgeDevices, setEdgeDevices] = useState<EdgeDevice[]>([]);
  const [edgeFleet, setEdgeFleet] = useState<EdgeFleetDevice[]>([]);
  const [productionReadiness, setProductionReadiness] = useState<ProductionReadiness | null>(null);
  const [recordings, setRecordings] = useState<RecordingSegment[]>([]);
  const [discoveryRuns, setDiscoveryRuns] = useState<CameraDiscoveryRun[]>([]);
  const [onboardingRuns, setOnboardingRuns] = useState<CameraOnboardingRun[]>([]);
  const [commissioningRuns, setCommissioningRuns] = useState<CameraCommissioningRun[]>([]);
  const [operationalHealthIncidents, setOperationalHealthIncidents] = useState<OperationalHealthIncident[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(null);
  const selectedCameraIdRef = useRef<string | null>(null);
  const [cameraStream, setCameraStream] = useState<CameraStream | null>(null);
  const [streamLoading, setStreamLoading] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [cameraAgent, setCameraAgent] = useState<CameraAgent | null>(null);
  const [capabilities, setCapabilities] = useState<PlatformCapabilities | null>(null);
  const [identity, setIdentity] = useState<CurrentActor | null>(null);
  const [liveDetections, setLiveDetections] = useState<LiveDetection[]>([]);
  const [lastTelemetry, setLastTelemetry] = useState<AgentTelemetry | null>(null);
  const [notificationPermission, setNotificationPermission] = useState<
    NotificationPermission | "unsupported"
  >("unsupported");
  const browserNotificationsEnabledRef = useRef(false);
  const knownHealthIncidentIdsRef = useRef<Set<string> | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reportError = useCallback((message: string) => setError(message), []);

  useEffect(() => {
    if (!("Notification" in window)) return;
    const initialize = window.setTimeout(() => {
      setNotificationPermission(Notification.permission);
      browserNotificationsEnabledRef.current =
        Notification.permission === "granted" &&
        window.localStorage.getItem("artae-browser-alerts") === "enabled";
    }, 0);
    return () => window.clearTimeout(initialize);
  }, []);

  const loadAuditLogs = useCallback(async () => {
    try {
      setAuditLogs(await api.listAuditLogs());
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load audit records.");
    }
  }, []);

  const loadEvidence = useCallback(async () => {
    try {
      setEvidence(await api.listEvidence());
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load evidence state.");
    }
  }, []);

  const loadAlerts = useCallback(async () => {
    try {
      setAlerts(await api.listAlerts());
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load alerts.");
    }
  }, []);

  const loadVerificationCases = useCallback(async () => {
    try {
      setVerificationCases(await api.listVerificationCases());
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load verification cases.");
    }
  }, []);

  const loadFieldAccuracyReports = useCallback(async () => {
    try {
      setFieldAccuracyReports(await api.listFieldAccuracyReports());
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load field accuracy.");
    }
  }, []);

  const loadStream = useCallback(async (cameraId: string, provision = false) => {
    setStreamLoading(true);
    try {
      const nextStream = provision
        ? await api.provisionCameraStream(cameraId)
        : await api.getCameraStream(cameraId);
      if (selectedCameraIdRef.current === cameraId) {
        setCameraStream(nextStream);
        setCameras((current) =>
          current.map((camera) =>
            camera.id === cameraId
              ? { ...camera, status: nextStream.ready ? "online" : "offline" }
              : camera,
          ),
        );
        setStreamError(null);
      }
    } catch (failure) {
      if (selectedCameraIdRef.current === cameraId) {
        setCameraStream(null);
        setStreamError(
          failure instanceof Error ? failure.message : "Could not connect to the media gateway.",
        );
      }
    } finally {
      if (selectedCameraIdRef.current === cameraId) setStreamLoading(false);
    }
  }, []);

  const loadAgent = useCallback(async (cameraId: string) => {
    try {
      const nextAgent = await api.getCameraAgent(cameraId);
      if (selectedCameraIdRef.current === cameraId) setCameraAgent(nextAgent);
    } catch (failure) {
      if (selectedCameraIdRef.current === cameraId) {
        setError(failure instanceof Error ? failure.message : "Could not load agent state.");
      }
    }
  }, []);

  const loadRecordings = useCallback(async (cameraId?: string | null) => {
    const targetCameraId = cameraId ?? selectedCameraIdRef.current;
    if (!targetCameraId) {
      setRecordings([]);
      return;
    }
    try {
      const nextRecordings = await api.listCameraRecordings(targetCameraId);
      if (selectedCameraIdRef.current === targetCameraId) setRecordings(nextRecordings);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load recordings.");
    }
  }, []);

  const loadDiscoveryRuns = useCallback(async () => {
    try {
      setDiscoveryRuns(await api.listCameraDiscoveryRuns());
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load camera discovery.");
    }
  }, []);

  const loadOnboardingRuns = useCallback(async () => {
    try {
      const nextRuns = await api.listCameraOnboardingRuns();
      setOnboardingRuns(nextRuns);
      if (nextRuns.some((run) => run.status === "completed" && run.camera_id)) {
        setCameras(await api.listCameras());
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load camera onboarding.");
    }
  }, []);

  const loadOperationalHealthIncidents = useCallback(async () => {
    try {
      const nextIncidents = await api.listOperationalHealthIncidents();
      const knownIds = knownHealthIncidentIdsRef.current;
      if (knownIds && browserNotificationsEnabledRef.current && "Notification" in window) {
        for (const incident of nextIncidents) {
          if (incident.status === "open" && !knownIds.has(incident.id)) {
            const notification = new Notification(`System health: ${incident.resource_name}`, {
              body: incident.detail,
              tag: `health-${incident.id}`,
            });
            notification.onclick = () => {
              window.focus();
              window.location.hash = "fleet-health-incidents";
              notification.close();
            };
          }
        }
      }
      knownHealthIncidentIdsRef.current = new Set(nextIncidents.map((incident) => incident.id));
      setOperationalHealthIncidents(nextIncidents);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load operational health.");
    }
  }, []);

  const loadCommissioningRuns = useCallback(async (cameraId?: string | null) => {
    const targetCameraId = cameraId ?? selectedCameraIdRef.current;
    if (!targetCameraId) {
      setCommissioningRuns([]);
      return;
    }
    try {
      const nextRuns = await api.listCameraCommissioningRuns(targetCameraId);
      if (selectedCameraIdRef.current === targetCameraId) setCommissioningRuns(nextRuns);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load camera health checks.");
    }
  }, []);

  const selectCamera = useCallback(
    (cameraId: string) => {
      selectedCameraIdRef.current = cameraId;
      setSelectedCameraId(cameraId);
      setCameraStream(null);
      setCameraAgent(null);
      setLiveDetections([]);
      setLastTelemetry(null);
      void loadStream(cameraId, true);
      void loadAgent(cameraId);
      void loadRecordings(cameraId);
      void loadCommissioningRuns(cameraId);
    },
    [loadAgent, loadCommissioningRuns, loadRecordings, loadStream],
  );

  const load = useCallback(async () => {
    try {
      const nextIdentity = await api.getIdentity();
      const canAdminister = nextIdentity.role === "owner" || nextIdentity.role === "admin";
      const [nextCameras, nextZones, nextRules, nextEvents, nextVerificationCases, nextFieldAccuracyReports, nextEvidence, nextCapabilities, nextAlerts, nextAlertChannels, nextEdgeDevices, nextEdgeFleet, nextAuditLogs, nextProductionReadiness, nextDiscoveryRuns, nextOnboardingRuns, nextOperationalHealth] = await Promise.all([
        api.listCameras(),
        api.listZones(),
        api.listRules(),
        api.listEvents(),
        api.listVerificationCases(),
        api.listFieldAccuracyReports(),
        api.listEvidence(),
        api.getCapabilities(),
        api.listAlerts(),
        api.listAlertChannels(),
        api.listEdgeDevices(),
        api.listEdgeFleet(),
        canAdminister ? api.listAuditLogs() : Promise.resolve([]),
        canAdminister ? api.getProductionReadiness() : Promise.resolve(null),
        api.listCameraDiscoveryRuns(),
        api.listCameraOnboardingRuns(),
        api.listOperationalHealthIncidents(),
      ]);
      setCameras(nextCameras);
      setZones(nextZones);
      setRules(nextRules);
      setEvents(nextEvents);
      setVerificationCases(nextVerificationCases);
      setFieldAccuracyReports(nextFieldAccuracyReports);
      setEvidence(nextEvidence);
      setCapabilities(nextCapabilities);
      setAlerts(nextAlerts);
      setAlertChannels(nextAlertChannels);
      setIdentity(nextIdentity);
      setEdgeDevices(nextEdgeDevices);
      setEdgeFleet(nextEdgeFleet);
      setAuditLogs(nextAuditLogs);
      setProductionReadiness(nextProductionReadiness);
      setDiscoveryRuns(nextDiscoveryRuns);
      setOnboardingRuns(nextOnboardingRuns);
      knownHealthIncidentIdsRef.current = new Set(nextOperationalHealth.map((incident) => incident.id));
      setOperationalHealthIncidents(nextOperationalHealth);
      const currentCameraId = selectedCameraIdRef.current;
      const nextCameraId = nextCameras.some((camera) => camera.id === currentCameraId)
        ? currentCameraId
        : (nextCameras[0]?.id ?? null);
      selectedCameraIdRef.current = nextCameraId;
      setSelectedCameraId(nextCameraId);
      if (nextCameraId) {
        void loadStream(nextCameraId, true);
        void loadAgent(nextCameraId);
        void loadRecordings(nextCameraId);
        void loadCommissioningRuns(nextCameraId);
      } else {
        setCameraStream(null);
        setCameraAgent(null);
        setRecordings([]);
        setCommissioningRuns([]);
      }
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load the dashboard.");
    } finally {
      setLoading(false);
    }
  }, [loadAgent, loadCommissioningRuns, loadRecordings, loadStream]);

  useEffect(() => {
    const initialLoad = setTimeout(() => void load(), 0);
    return () => clearTimeout(initialLoad);
  }, [load]);

  useEffect(() => {
    if (!selectedCameraId) return;
    const statusPoll = window.setInterval(
      () => {
        void loadStream(selectedCameraId, false);
        void loadAgent(selectedCameraId);
        void loadEvidence();
        void loadAlerts();
        void loadVerificationCases();
        void loadFieldAccuracyReports();
        void loadRecordings(selectedCameraId);
        void loadDiscoveryRuns();
        void loadOnboardingRuns();
        void loadCommissioningRuns(selectedCameraId);
        void loadOperationalHealthIncidents();
      },
      5000,
    );
    return () => window.clearInterval(statusPoll);
  }, [loadAgent, loadAlerts, loadCommissioningRuns, loadDiscoveryRuns, loadEvidence, loadFieldAccuracyReports, loadOnboardingRuns, loadOperationalHealthIncidents, loadRecordings, loadStream, loadVerificationCases, selectedCameraId]);

  const receiveEvent = useCallback((event: VideoEvent) => {
    setEvents((current) => prependUniqueEvent(current, event));
    void loadAlerts();
    void loadVerificationCases();
    void loadFieldAccuracyReports();
    if (
      browserNotificationsEnabledRef.current &&
      "Notification" in window &&
      Notification.permission === "granted"
    ) {
      const testLabel = event.details.test === true ? "Test alert" : "Camera alert";
      const notification = new Notification(`${testLabel}: ${event.object_class}`, {
        body: `${event.zone_name} · ${Math.round(event.confidence * 100)}% confidence`,
        tag: event.id,
      });
      notification.onclick = () => {
        window.focus();
        window.location.hash = "alerts";
        notification.close();
      };
    }
  }, [loadAlerts, loadFieldAccuracyReports, loadVerificationCases]);
  const receiveTelemetry = useCallback((telemetry: AgentTelemetry) => {
    if (telemetry.camera_id !== selectedCameraIdRef.current) return;
    setLastTelemetry(telemetry);
    setLiveDetections(telemetry.detections);
    setCameraAgent((current) =>
      current
        ? {
            ...current,
            desired_status: telemetry.desired_status,
            observed_status: telemetry.observed_status,
            worker_id: telemetry.worker_id,
            fps: telemetry.fps,
            inference_latency_ms: telemetry.inference_latency_ms,
            frame_width: telemetry.frame_width,
            frame_height: telemetry.frame_height,
            health_status: telemetry.health_status,
            heartbeat_age_seconds: telemetry.heartbeat_age_seconds,
            frames_processed: telemetry.frames_processed ?? current.frames_processed,
            reconnect_count: telemetry.reconnect_count ?? current.reconnect_count,
            recording_state: telemetry.recording_state ?? current.recording_state,
            recording_segments_completed:
              telemetry.recording_segments_completed ?? current.recording_segments_completed,
            recording_dropped_frames:
              telemetry.recording_dropped_frames ?? current.recording_dropped_frames,
            recording_error: telemetry.recording_error,
            failure_count: telemetry.failure_count,
            next_retry_at: telemetry.next_retry_at,
            last_frame_at: telemetry.last_frame_at,
            last_error: telemetry.error,
          }
        : current,
    );
  }, []);
  const receiveAgentStatus = useCallback((status: CameraAgent) => {
    if (status.camera_id !== selectedCameraIdRef.current) return;
    setCameraAgent(status);
    if (status.desired_status === "stopped") setLiveDetections([]);
  }, []);
  const streamStatus = useEventStream(receiveEvent, receiveTelemetry, receiveAgentStatus);

  const selectedCamera = cameras.find((camera) => camera.id === selectedCameraId) ?? null;
  const cameraZones = zones.filter((zone) => zone.camera_id === selectedCameraId);
  const cameraRules = rules.filter((rule) => rule.camera_id === selectedCameraId);
  const cameraAlerts = alertsForCamera(alerts, selectedCameraId);
  const cameraEvents = eventsForCamera(events, selectedCameraId);
  const cameraEvidence = evidenceForEvents(evidence, cameraEvents);
  const activeHealthIncidentCount = operationalHealthIncidents.filter(
    (incident) => incident.status !== "resolved",
  ).length;
  const liveFeedRunning = cameraAgent?.desired_status === "running";

  const stats = useMemo(() => {
    const today = new Date().toDateString();
    const todayEvents = events.filter((event) => new Date(event.occurred_at).toDateString() === today);
    const averageConfidence = events.length
      ? Math.round((events.reduce((sum, event) => sum + event.confidence, 0) / events.length) * 100)
      : 0;
    return [
      { label: "Registered cameras", value: cameras.length, detail: `${cameras.filter((c) => c.status === "online").length} online`, icon: "camera" as IconName },
      { label: "Active jobs", value: rules.filter((rule) => rule.status === "active").length, detail: `${rules.filter((rule) => rule.status === "draft").length} awaiting review`, icon: "rule" as IconName },
      { label: "Events today", value: todayEvents.length, detail: `${events.length} retained in view`, icon: "event" as IconName },
      { label: "Avg. confidence", value: `${averageConfidence}%`, detail: events.length ? "Across recent events" : "Waiting for events", icon: "activity" as IconName },
    ];
  }, [cameras, events, rules]);

  async function createCamera(input: CreateCameraInput) {
    setBusy(true);
    try {
      const camera = await api.createCamera(input);
      setCameras((current) => [...current, camera]);
      selectedCameraIdRef.current = camera.id;
      setSelectedCameraId(camera.id);
      setCameraStream(null);
      setCameraAgent(null);
      setLiveDetections([]);
      void loadStream(camera.id, true);
      void loadAgent(camera.id);
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not create the camera.");
      throw failure;
    } finally {
      setBusy(false);
    }
  }

  async function createWebcamCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
      const message = "This browser cannot access a webcam. Try a current version of Chrome, Edge, or Safari.";
      setError(message);
      throw new Error(message);
    }
    try {
      const media = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      media.getTracks().forEach((track) => track.stop());
      await createCamera({ name: "My webcam", source_uri: "webcam:0" });
    } catch (failure) {
      const message = failure instanceof DOMException && failure.name === "NotAllowedError"
        ? "Camera access was blocked. Allow camera access for Artae, then click Use my webcam again."
        : failure instanceof Error ? failure.message : "Could not connect this webcam.";
      setError(message);
    }
  }

  async function createZone(input: CreateZoneInput) {
    setBusy(true);
    try {
      const zone = await api.createZone(input);
      setZones((current) => [...current, zone]);
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not save the zone.");
      throw failure;
    } finally {
      setBusy(false);
    }
  }

  async function compileRule(input: CompileRuleInput): Promise<RuleCompilation> {
    setBusy(true);
    try {
      const compilation = await api.compileRule(input);
      setError(null);
      return compilation;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not compile the rule.");
      throw failure;
    } finally {
      setBusy(false);
    }
  }

  async function clarifyRule(compilationId: string, answer: string): Promise<RuleCompilation> {
    setBusy(true);
    try {
      const compilation = await api.clarifyRuleCompilation(compilationId, answer);
      setError(null);
      return compilation;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not apply the clarification.");
      throw failure;
    } finally {
      setBusy(false);
    }
  }

  async function acceptRule(compilationId: string) {
    setBusy(true);
    try {
      const rule = await api.acceptRuleCompilation(compilationId);
      const nextZones = await api.listZones();
      setZones(nextZones);
      setRules((current) => [rule, ...current]);
      setError(null);
      return rule;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not create the reviewed draft.");
      throw failure;
    } finally {
      setBusy(false);
    }
  }

  async function changeRuleStatus(ruleId: string, status: RuleStatus) {
    setBusy(true);
    try {
      const updated = await api.updateRuleStatus(ruleId, status);
      setRules((current) => current.map((rule) => (rule.id === updated.id ? updated : rule)));
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not update the rule.");
      throw failure;
    } finally {
      setBusy(false);
    }
  }

  async function changeAgentStatus(desiredStatus: "running" | "stopped") {
    if (!selectedCameraId) return;
    setBusy(true);
    try {
      const updated = await api.updateCameraAgent(selectedCameraId, desiredStatus);
      setCameraAgent(updated);
      if (desiredStatus === "stopped") setLiveDetections([]);
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not control the agent.");
      throw failure;
    } finally {
      setBusy(false);
    }
  }

  async function createAlertChannel(input: CreateAlertChannelInput) {
    setBusy(true);
    try {
      const channel = await api.createAlertChannel(input);
      setAlertChannels((current) => [...current, channel]);
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not create alert destination.");
      throw failure;
    } finally {
      setBusy(false);
    }
  }

  async function createAlertRoute(ruleId: string, input: CreateAlertRouteInput) {
    setBusy(true);
    try {
      await api.createAlertRoute(ruleId, input);
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not enable the alert route.");
      throw failure;
    } finally {
      setBusy(false);
    }
  }

  async function transitionAlert(alertId: string, action: "acknowledge" | "resolve") {
    setBusy(true);
    try {
      const updated = action === "acknowledge"
        ? await api.acknowledgeAlert(alertId)
        : await api.resolveAlert(alertId);
      setAlerts((current) => current.map((alert) => alert.id === updated.id ? updated : alert));
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not update the alert.");
    } finally {
      setBusy(false);
    }
  }

  async function createTestAlert(ruleId: string) {
    setBusy(true);
    try {
      const alert = await api.createTestAlert(ruleId);
      setAlerts((current) => [alert, ...current.filter((item) => item.id !== alert.id)]);
      setError(null);
      window.location.hash = "alerts";
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not create the test alert.");
    } finally {
      setBusy(false);
    }
  }

  async function runSafeTest(ruleId: string, connectorId: string): Promise<AlertIncident> {
    setBusy(true);
    try {
      const alert = await api.createOutboundTestAlert(ruleId, connectorId);
      setAlerts((current) => [alert, ...current.filter((item) => item.id !== alert.id)]);
      setEvents((current) => prependUniqueEvent(current, alert.event));
      setError(null);
      return alert;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not run the safe action test.");
      throw failure;
    } finally {
      setBusy(false);
    }
  }

  async function enableBrowserNotifications() {
    if (!("Notification" in window)) {
      setNotificationPermission("unsupported");
      setError("This browser does not support desktop notifications.");
      return;
    }
    const permission = await Notification.requestPermission();
    setNotificationPermission(permission);
    browserNotificationsEnabledRef.current = permission === "granted";
    if (permission === "granted") {
      window.localStorage.setItem("artae-browser-alerts", "enabled");
      new Notification("Artae Vision alerts enabled", {
        body: "Confirmed camera incidents can now notify this browser.",
        tag: "artae-notifications-enabled",
      });
      setError(null);
    } else if (permission === "denied") {
      setError("Browser notifications are blocked. Allow them in this site's browser settings.");
    }
  }

  async function createEdgeDevice(
    name: string,
    capacity: number,
  ): Promise<EdgeDeviceCredential> {
    setBusy(true);
    try {
      const created = await api.createEdgeDevice(name, capacity);
      setEdgeDevices((current) => [created.device, ...current]);
      setEdgeFleet(await api.listEdgeFleet());
      void loadAuditLogs();
      setError(null);
      return created;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not enroll the edge device.");
      throw failure;
    } finally {
      setBusy(false);
    }
  }

  async function rotateEdgeDevice(deviceId: string): Promise<EdgeDeviceCredential> {
    setBusy(true);
    try {
      const rotated = await api.rotateEdgeDeviceCredential(deviceId);
      setEdgeDevices((current) =>
        current.map((device) => (device.id === deviceId ? rotated.device : device)),
      );
      setEdgeFleet(await api.listEdgeFleet());
      void loadAuditLogs();
      setError(null);
      return rotated;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not rotate the device token.");
      throw failure;
    } finally {
      setBusy(false);
    }
  }

  async function revokeEdgeDevice(deviceId: string) {
    setBusy(true);
    try {
      const revoked = await api.revokeEdgeDevice(deviceId);
      setEdgeDevices((current) =>
        current.map((device) => (device.id === deviceId ? revoked : device)),
      );
      setEdgeFleet(await api.listEdgeFleet());
      void loadAuditLogs();
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not revoke the edge device.");
    } finally {
      setBusy(false);
    }
  }

  async function createDemoFleetProfile(deviceId: string) {
    setBusy(true);
    try {
      await api.createDemoFleetProfile(deviceId);
      setEdgeFleet(await api.listEdgeFleet());
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not preview fleet health.");
    } finally {
      setBusy(false);
    }
  }

  async function startCameraDiscovery(deviceId: string) {
    setBusy(true);
    try {
      const run = await api.createCameraDiscoveryRun(deviceId);
      setDiscoveryRuns((current) => [run, ...current]);
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not start camera discovery.");
    } finally {
      setBusy(false);
    }
  }

  async function startCameraOnboarding(input: CreateCameraOnboardingInput) {
    setBusy(true);
    try {
      const run = await api.createCameraOnboardingRun(input);
      setOnboardingRuns((current) => [run, ...current]);
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not connect the ONVIF camera.");
    } finally {
      setBusy(false);
    }
  }

  async function startCameraCommissioning(input: CreateCameraCommissioningInput) {
    setBusy(true);
    try {
      const run = await api.createCameraCommissioningRun(input);
      setCommissioningRuns((current) => [
        run,
        ...current.filter((item) => item.id !== run.id),
      ]);
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not start camera health check.");
    } finally {
      setBusy(false);
    }
  }

  async function acknowledgeOperationalHealth(incidentId: string) {
    setBusy(true);
    try {
      const updated = await api.acknowledgeOperationalHealthIncident(incidentId);
      setOperationalHealthIncidents((current) =>
        current.map((incident) => incident.id === updated.id ? updated : incident),
      );
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not acknowledge health incident.");
    } finally {
      setBusy(false);
    }
  }

  async function changeRecordingLegalHold(recordingId: string, enabled: boolean) {
    setBusy(true);
    try {
      const updated = await api.updateRecordingLegalHold(recordingId, enabled);
      setRecordings((current) =>
        current.map((recording) => recording.id === updated.id ? updated : recording),
      );
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not update legal hold.");
    } finally {
      setBusy(false);
    }
  }

  async function runRecordingRetention() {
    setBusy(true);
    try {
      await api.runRecordingRetention();
      await loadRecordings();
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not run recording retention.");
    } finally {
      setBusy(false);
    }
  }

  async function decideVerification(
    caseId: string,
    status: "confirmed" | "rejected",
    reasoning: string,
    environmentTags: AccuracyEnvironmentTag[],
  ) {
    setBusy(true);
    try {
      await api.decideVerificationCase(caseId, status, reasoning, environmentTags);
      const [nextCases, nextReports, nextEvents, nextAlerts, nextEvidence] = await Promise.all([
        api.listVerificationCases(),
        api.listFieldAccuracyReports(),
        api.listEvents(),
        api.listAlerts(),
        api.listEvidence(),
      ]);
      setVerificationCases(nextCases);
      setFieldAccuracyReports(nextReports);
      setEvents(nextEvents);
      setAlerts(nextAlerts);
      setEvidence(nextEvidence);
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not record the decision.");
    } finally {
      setBusy(false);
    }
  }

  async function auditVerification(
    caseId: string,
    actualOutcome: "event" | "no_event",
    reasoning: string,
    environmentTags: AccuracyEnvironmentTag[],
  ) {
    setBusy(true);
    try {
      await api.auditVerificationCase(caseId, actualOutcome, reasoning, environmentTags);
      await Promise.all([loadVerificationCases(), loadFieldAccuracyReports()]);
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not audit the outcome.");
    } finally {
      setBusy(false);
    }
  }

  async function reportMissedEvent(
    ruleId: string,
    occurredAt: string,
    reasoning: string,
    environmentTags: AccuracyEnvironmentTag[],
  ) {
    setBusy(true);
    try {
      await api.reportMissedEvent(ruleId, occurredAt, reasoning, environmentTags);
      await loadFieldAccuracyReports();
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not record the missed event.");
    } finally {
      setBusy(false);
    }
  }

  async function updateAccuracyManualOnly(report: FieldAccuracyReport, enabled: boolean) {
    setBusy(true);
    try {
      await api.updateFieldAccuracyPolicy(report.rule_id, {
        ...report.policy,
        manual_only: enabled,
      });
      await loadFieldAccuracyReports();
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not update accuracy policy.");
    } finally {
      setBusy(false);
    }
  }

  const canAdminister = identity?.role === "owner" || identity?.role === "admin";
  const canOperate = Boolean(identity && identity.role !== "viewer");
  const openAdvancedSection = useCallback((sectionId: string) => {
    const nextSection = sectionId in ADVANCED_TOOL_COPY ? sectionId as AdvancedSection : "hub";
    setAdvancedSection(nextSection);
    setConsoleMode("advanced");
  }, []);

  function renderAdvancedTool() {
    switch (advancedSection) {
      case "cameras":
        return (
          <div className="advancedToolColumns">
            <CameraPanel busy={busy} cameras={cameras} onCreate={createCamera} onSelect={selectCamera} selectedCameraId={selectedCameraId} />
            <ZoneEditor
              busy={busy}
              camera={selectedCamera}
              detections={liveDetections}
              stream={cameraStream}
              streamError={streamError}
              streamLoading={streamLoading}
              key={selectedCameraId ?? "no-camera"}
              onCreate={createZone}
              onRefreshStream={() => { if (selectedCameraId) void loadStream(selectedCameraId, true); }}
              zones={cameraZones}
            />
          </div>
        );
      case "rules":
        return <RulePanel busy={busy} camera={selectedCamera} onAccept={async (compilationId) => { await acceptRule(compilationId); }} onClarify={clarifyRule} onCompile={compileRule} onStatusChange={changeRuleStatus} rules={cameraRules} zones={cameraZones} capabilities={capabilities} />;
      case "evaluations":
        return <ReplayEvaluationPanel cameras={cameras} onError={reportError} />;
      case "verification-inbox":
        return <VerificationInbox busy={busy} canOperate={canOperate} cases={verificationCases} onAudit={auditVerification} onDecision={decideVerification} onRefresh={loadVerificationCases} />;
      case "alerts":
        return <AlertPanel alerts={cameraAlerts} busy={busy} cameraName={selectedCamera?.name ?? null} channels={alertChannels} onCreateChannel={createAlertChannel} onCreateRoute={createAlertRoute} onTransition={transitionAlert} rules={cameraRules} />;
      case "search":
        return (
          <div className="advancedToolStack">
            <EvidenceSearchPanel camera={selectedCamera} key={selectedCameraId ?? "no-camera-search"} onError={reportError} />
            <EventFeed cameras={cameras} evidence={cameraEvidence} events={cameraEvents} streamStatus={streamStatus} />
          </div>
        );
      case "recordings":
        return <RecordingTimelinePanel busy={busy} camera={selectedCamera} canAdminister={canAdminister} onLegalHold={changeRecordingLegalHold} onRefresh={() => loadRecordings()} onRunRetention={runRecordingRetention} recordings={recordings} />;
      case "agent":
        return <AgentControl agent={cameraAgent} busy={busy} camera={selectedCamera} onStart={() => void changeAgentStatus("running")} onStop={() => void changeAgentStatus("stopped")} rules={cameraRules} telemetry={lastTelemetry} />;
      case "devices":
        return <EdgeDevicesPanel busy={busy} canAdminister={canAdminister} devices={edgeDevices} fleet={edgeFleet} onCreate={createEdgeDevice} onDemoProfile={createDemoFleetProfile} onRevoke={revokeEdgeDevice} onRotate={rotateEdgeDevice} />;
      case "health":
        return <OperationalHealthPanel busy={busy} canOperate={canOperate} incidents={operationalHealthIncidents} onAcknowledge={acknowledgeOperationalHealth} onRefresh={loadOperationalHealthIncidents} />;
      case "discovery":
        return <CameraDiscoveryPanel busy={busy} canAdminister={canAdminister} devices={edgeDevices} onboardingRuns={onboardingRuns} onConnect={startCameraOnboarding} onRefresh={async () => { await Promise.all([loadDiscoveryRuns(), loadOnboardingRuns()]); }} onScan={startCameraDiscovery} runs={discoveryRuns} />;
      case "commissioning":
        return <CameraCommissioningPanel busy={busy} camera={selectedCamera} canAdminister={canAdminister} devices={edgeDevices} key={selectedCameraId ?? "no-camera-commissioning"} onRefresh={() => loadCommissioningRuns(selectedCameraId)} onRun={startCameraCommissioning} runs={commissioningRuns} />;
      case "readiness":
        return <ProductionReadinessPanel report={productionReadiness} visible={canAdminister} />;
      case "accuracy":
        return <FieldAccuracyPanel busy={busy} canOperate={canOperate} onMiss={reportMissedEvent} onManualOnly={updateAccuracyManualOnly} onRefresh={loadFieldAccuracyReports} reports={fieldAccuracyReports} />;
      case "learning":
        return <ActiveLearningPanel canOperate={canOperate} onError={reportError} />;
      case "promotion":
        return <PromotionControlPanel canAdminister={canAdminister} canOperate={canOperate} onError={reportError} />;
      case "audit":
        return <AuditLogPanel records={auditLogs} visible={canAdminister} />;
      case "hub":
      default:
        return (
          <section className="advancedToolHub" aria-label="Advanced maintenance tools">
            <button onClick={() => setAdvancedSection("devices")} type="button"><Icon name="activity" /><span><strong>Computers</strong><small>Manage analysis devices</small></span><Icon name="chevron" /></button>
            <button onClick={() => setAdvancedSection("health")} type="button"><Icon name="shield" /><span><strong>System health</strong><small>See reliability incidents</small></span><Icon name="chevron" /></button>
            <button onClick={() => setAdvancedSection("discovery")} type="button"><Icon name="camera" /><span><strong>Find network cameras</strong><small>ONVIF discovery and setup</small></span><Icon name="chevron" /></button>
            <button onClick={() => setAdvancedSection("commissioning")} type="button"><Icon name="camera" /><span><strong>Camera quality check</strong><small>Use only when a feed has problems</small></span><Icon name="chevron" /></button>
            <button onClick={() => setAdvancedSection("readiness")} type="button"><Icon name="shield" /><span><strong>Production readiness</strong><small>Hosting and security checklist</small></span><Icon name="chevron" /></button>
            <button onClick={() => setAdvancedSection("agent")} type="button"><Icon name="activity" /><span><strong>Runtime details</strong><small>Technical worker telemetry</small></span><Icon name="chevron" /></button>
            <button onClick={() => setAdvancedSection("accuracy")} type="button"><Icon name="rule" /><span><strong>Field accuracy</strong><small>Review misses and policies</small></span><Icon name="chevron" /></button>
            <button onClick={() => setAdvancedSection("learning")} type="button"><Icon name="event" /><span><strong>Review dataset</strong><small>Curate difficult examples</small></span><Icon name="chevron" /></button>
            <button onClick={() => setAdvancedSection("promotion")} type="button"><Icon name="rule" /><span><strong>Model promotion</strong><small>Compare and release versions</small></span><Icon name="chevron" /></button>
            <button onClick={() => setAdvancedSection("audit")} type="button"><Icon name="clock" /><span><strong>Audit log</strong><small>Administrative history</small></span><Icon name="chevron" /></button>
          </section>
        );
    }
  }

  return (
    <div className={`appShell ${consoleMode === "guided" ? "appShellSimple" : ""}`}>
      {consoleMode === "guided" && error && (
        <div className="guidedErrorToast" role="alert">
          <Icon name="activity" />
          <span><strong>Artae needs your attention</strong>{error}</span>
          <button aria-label="Dismiss message" onClick={() => setError(null)} type="button">×</button>
        </div>
      )}
      <aside className="sidebar">
        <a className="brand" href="#overview">
          <span className="brandMark">
            <Icon name="spark" />
          </span>
          <span>
            <strong>Artae Vision</strong>
            <small>Operator console</small>
          </span>
        </a>
        <nav aria-label="Main navigation">
          <button className={consoleMode === "guided" ? "navActive" : ""} onClick={() => setConsoleMode("guided")} type="button">
            <Icon name="spark" /> Automations
          </button>
          <button className={consoleMode === "advanced" ? "navActive" : ""} onClick={() => openAdvancedSection("hub")} type="button">
            <Icon name="settings" /> Advanced tools
          </button>
        </nav>
        <div className="sidebarFoot">
          <div className="edgeCard">
            <span className="edgeIcon">
              <Icon name="shield" />
            </span>
            <div>
              <strong>Edge-first</strong>
              <small>Video stays near the source</small>
            </div>
          </div>
          <a href={`${API_URL}/docs`} rel="noreferrer" target="_blank">
            <Icon name="settings" /> API documentation
          </a>
        </div>
      </aside>

      <main>
        {consoleMode === "guided" ? (
          guidedView === "automations" ? (
            <CameraAutomationsWorkspace
              agent={cameraAgent}
              alerts={alerts}
              busy={busy}
              cameras={cameras}
              detections={liveDetections}
              events={events}
              key={selectedCameraId ?? "no-automation-camera"}
              loading={loading}
              identity={identity}
              recordings={recordings}
              onAddWebcam={createWebcamCamera}
              onClarify={clarifyRule}
              onCompile={compileRule}
              onDecideVerification={(caseId, status) => decideVerification(caseId, status, "Reviewed from the monitoring conversation.", [])}
              onOpenAdvanced={openAdvancedSection}
              onRefreshRecordings={loadRecordings}
              onRuleCreated={(rule) => setRules((current) => [rule, ...current.filter((item) => item.id !== rule.id)])}
              onRuleStatusChange={changeRuleStatus}
              onSafeTest={runSafeTest}
              onSelectCamera={selectCamera}
              onSignOut={async () => {
                await signOut();
                window.location.assign("/login");
              }}
              onStart={() => changeAgentStatus("running")}
              onStop={() => changeAgentStatus("stopped")}
              rules={cameraRules}
              selectedCamera={selectedCamera}
              stream={cameraStream}
              verificationCases={verificationCases}
            />
          ) : (
          <>
            <header className="liveOpsTopbar">
              <button className="liveOpsBrand" onClick={() => { setConsoleMode("guided"); setGuidedView("automations"); }} type="button">
                <span><Icon name="spark" /></span>
                <strong>Artae Vision</strong>
              </button>
              <nav aria-label="Operator navigation">
                <button aria-current={guidedView === "live" ? "page" : undefined} className={guidedView === "live" ? "isActive" : ""} onClick={() => setGuidedView("live")} type="button">Live</button>
                <button onClick={() => setGuidedView("automations")} type="button">Automations</button>
                <button onClick={() => openAdvancedSection("search")} type="button">Investigate</button>
                <button onClick={() => openAdvancedSection("verification-inbox")} type="button">Cases</button>
                <button onClick={() => openAdvancedSection("alerts")} type="button">Alerts</button>
                <button onClick={() => openAdvancedSection("rules")} type="button">Settings</button>
              </nav>
              <div className="liveOpsHeaderActions">
                <button
                  className={`liveFeedToggle ${liveFeedRunning ? "isRunning" : ""}`}
                  disabled={busy || !selectedCamera}
                  onClick={() => void (liveFeedRunning ? changeAgentStatus("stopped") : changeAgentStatus("running"))}
                  type="button"
                >
                  <i /> {liveFeedRunning ? "Stop live feed" : "Start live feed"}
                </button>
                {guidedView === "live" && (
                  <>
                    <button className="liveOpsLocation" type="button"><Icon name="map" /><span>All locations</span><Icon name="chevron" /></button>
                    <button aria-label="Search evidence" onClick={() => openAdvancedSection("search")} type="button"><Icon name="search" /></button>
                    <button aria-label={`${cameraAlerts.length} alerts`} className="liveOpsAlertButton" onClick={() => openAdvancedSection("alerts")} type="button"><Icon name="event" />{cameraAlerts.length > 0 && <span>{Math.min(9, cameraAlerts.length)}</span>}</button>
                  </>
                )}
                <button aria-label="Operator profile" className="liveOpsAvatar" type="button">OP<i /></button>
              </div>
            </header>
            {error && (
              <div className="liveOpsNotice" role="status"><Icon name="activity" /><span><strong>Some secondary data needs attention</strong>The live workspace remains available while the system retries.</span><button onClick={() => setError(null)} type="button">Dismiss</button></div>
            )}
            <LiveOperationsWorkspace
              agent={cameraAgent}
              alerts={alerts}
              busy={busy}
              cameras={cameras}
              key={selectedCameraId ?? "no-live-camera"}
              loading={loading}
              onAddWebcam={createWebcamCamera}
              onClarify={clarifyRule}
              onCompile={compileRule}
              onOpenAdvanced={openAdvancedSection}
              onRuleCreated={(rule) => setRules((current) => [rule, ...current.filter((item) => item.id !== rule.id)])}
              onSelectCamera={selectCamera}
              onStart={() => changeAgentStatus("running")}
              onStop={() => changeAgentStatus("stopped")}
              selectedCamera={selectedCamera}
              stream={cameraStream}
            />
          </>
          )
        ) : (
          <>
            <header className="advancedToolHeader" id="overview">
              <button className="advancedBackButton" onClick={() => setConsoleMode("guided")} type="button"><Icon name="chevron" /> Back to Automations</button>
              <div>
                <span>ADVANCED</span>
                <h1>{ADVANCED_TOOL_COPY[advancedSection].title}</h1>
                <p>{ADVANCED_TOOL_COPY[advancedSection].description}</p>
              </div>
              <label>
                <span>Choose a tool</span>
                <select onChange={(event) => setAdvancedSection(event.target.value as AdvancedSection)} value={advancedSection}>
                  <optgroup label="Common tools">
                    <option value="cameras">Camera setup</option>
                    <option value="rules">Automation rules</option>
                    <option value="evaluations">Upload testing</option>
                    <option value="verification-inbox">Cases</option>
                    <option value="alerts">Alerts</option>
                    <option value="search">Evidence search</option>
                    <option value="recordings">Recordings</option>
                  </optgroup>
                  <optgroup label="Technical maintenance">
                    <option value="hub">Advanced tools home</option>
                    <option value="devices">Computers and edge devices</option>
                    <option value="health">System health</option>
                    <option value="discovery">Network camera discovery</option>
                    <option value="commissioning">Camera quality check</option>
                    <option value="readiness">Production readiness</option>
                    <option value="agent">Camera runtime</option>
                    <option value="accuracy">Field accuracy</option>
                    <option value="learning">Review dataset</option>
                    <option value="promotion">Model promotion</option>
                    <option value="audit">Audit log</option>
                  </optgroup>
                </select>
              </label>
            </header>

            <nav className="advancedQuickNav" aria-label="Common advanced tools">
              {([
                ["cameras", "Cameras"],
                ["rules", "Rules"],
                ["evaluations", "Upload tests"],
                ["verification-inbox", "Cases"],
                ["alerts", "Alerts"],
                ["search", "Search"],
                ["hub", "System"],
              ] as Array<[AdvancedSection, string]>).map(([section, label]) => (
                <button className={advancedSection === section ? "isActive" : ""} key={section} onClick={() => setAdvancedSection(section)} type="button">{label}</button>
              ))}
            </nav>

            <div className="advancedToolStage">{renderAdvancedTool()}</div>

            {false && (
              <>
        <header className="topbar" id="overview">
          <div>
            <span className="eyebrow">
              {process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "native"
                ? "Native local mode · SQLite · No Docker"
                : "Managed multi-camera edge fleet"}
            </span>
            <h1>Video operations</h1>
            <p>Configure what your cameras watch for and review events as they happen.</p>
          </div>
          <div className="topbarActions">
            {identity && (
              <span className="tenantContext" title={identity?.organization_id}>
                {identity?.role} · {identity?.display_name ?? identity?.subject}
              </span>
            )}
            <span className={`apiState ${error || activeHealthIncidentCount ? "apiStateError" : ""}`}>
              <i /> {error ? "API attention needed" : loading ? "Connecting" : activeHealthIncidentCount ? `${activeHealthIncidentCount} health issue${activeHealthIncidentCount === 1 ? "" : "s"}` : "Control plane ready"}
            </span>
            <button
              className="buttonSecondary"
              disabled={loading}
              onClick={() => {
                setLoading(true);
                void load();
              }}
              type="button"
            >
              Refresh
            </button>
          </div>
        </header>

        {error && (
          <div className="errorBanner" role="alert">
            <Icon name="activity" />
            <span>
              <strong>Control-plane request failed</strong>
              {error}
            </span>
            <button onClick={() => setError(null)} type="button">
              Dismiss
            </button>
          </div>
        )}

        <section aria-label="Platform summary" className="statGrid">
          {stats.map((stat) => (
            <article className="statCard" key={stat.label}>
              <span className="statIcon">
                <Icon name={stat.icon} />
              </span>
              <div>
                <small>{stat.label}</small>
                <strong>{loading ? "—" : stat.value}</strong>
                <span>{stat.detail}</span>
              </div>
            </article>
          ))}
        </section>

        <MvpLaunchpad
          agent={cameraAgent}
          busy={busy}
          camera={selectedCamera}
          latestEvent={
            events.find((event) => event.camera_id === selectedCameraId) ?? null
          }
          notificationPermission={notificationPermission}
          onEnableNotifications={() => void enableBrowserNotifications()}
          onStart={() => void changeAgentStatus("running")}
          onStop={() => void changeAgentStatus("stopped")}
          onTestAlert={(ruleId) => void createTestAlert(ruleId)}
          rules={cameraRules}
          telemetry={lastTelemetry}
        />

        <div className="workspaceGrid">
          <CameraPanel
            busy={busy}
            cameras={cameras}
            onCreate={createCamera}
            onSelect={selectCamera}
            selectedCameraId={selectedCameraId}
          />
          <ZoneEditor
            busy={busy}
            camera={selectedCamera}
            detections={liveDetections}
            stream={cameraStream}
            streamError={streamError}
            streamLoading={streamLoading}
            key={selectedCameraId ?? "no-camera"}
            onCreate={createZone}
            onRefreshStream={() => {
              if (selectedCameraId) void loadStream(selectedCameraId, true);
            }}
            zones={cameraZones}
          />
        </div>

        <EdgeDevicesPanel
          busy={busy}
          canAdminister={canAdminister}
          devices={edgeDevices}
          fleet={edgeFleet}
          onCreate={createEdgeDevice}
          onDemoProfile={createDemoFleetProfile}
          onRevoke={revokeEdgeDevice}
          onRotate={rotateEdgeDevice}
        />

        <OperationalHealthPanel
          busy={busy}
          canOperate={canOperate}
          incidents={operationalHealthIncidents}
          onAcknowledge={acknowledgeOperationalHealth}
          onRefresh={loadOperationalHealthIncidents}
        />

        <CameraDiscoveryPanel
          busy={busy}
          canAdminister={canAdminister}
          devices={edgeDevices}
          onboardingRuns={onboardingRuns}
          onConnect={startCameraOnboarding}
          onRefresh={async () => {
            await Promise.all([loadDiscoveryRuns(), loadOnboardingRuns()]);
          }}
          onScan={startCameraDiscovery}
          runs={discoveryRuns}
        />

        <CameraCommissioningPanel
          busy={busy}
          camera={selectedCamera}
          canAdminister={canAdminister}
          devices={edgeDevices}
          key={selectedCameraId ?? "no-camera-commissioning"}
          onRefresh={() => loadCommissioningRuns(selectedCameraId)}
          onRun={startCameraCommissioning}
          runs={commissioningRuns}
        />

        <ProductionReadinessPanel
          report={productionReadiness}
          visible={canAdminister}
        />

        <AgentControl
          agent={cameraAgent}
          busy={busy}
          camera={selectedCamera}
          onStart={() => void changeAgentStatus("running")}
          onStop={() => void changeAgentStatus("stopped")}
          rules={cameraRules}
          telemetry={lastTelemetry}
        />

        <RecordingTimelinePanel
          busy={busy}
          camera={selectedCamera}
          canAdminister={canAdminister}
          onLegalHold={changeRecordingLegalHold}
          onRefresh={() => loadRecordings()}
          onRunRetention={runRecordingRetention}
          recordings={recordings}
        />

        <RulePanel
          busy={busy}
          camera={selectedCamera}
          onAccept={async (compilationId) => { await acceptRule(compilationId); }}
          onClarify={clarifyRule}
          onCompile={compileRule}
          onStatusChange={changeRuleStatus}
          rules={cameraRules}
          zones={cameraZones}
          capabilities={capabilities}
        />
        <ReplayEvaluationPanel cameras={cameras} onError={reportError} />
        <VerificationInbox
          busy={busy}
          canOperate={canOperate}
          cases={verificationCases}
          onAudit={auditVerification}
          onDecision={decideVerification}
          onRefresh={loadVerificationCases}
        />
        <FieldAccuracyPanel
          busy={busy}
          canOperate={canOperate}
          onMiss={reportMissedEvent}
          onManualOnly={updateAccuracyManualOnly}
          onRefresh={loadFieldAccuracyReports}
          reports={fieldAccuracyReports}
        />
        <ActiveLearningPanel canOperate={canOperate} onError={reportError} />
        <PromotionControlPanel canAdminister={canAdminister} canOperate={canOperate} onError={reportError} />
        <AlertPanel
          alerts={cameraAlerts}
          busy={busy}
          cameraName={selectedCamera?.name ?? null}
          channels={alertChannels}
          onCreateChannel={createAlertChannel}
          onCreateRoute={createAlertRoute}
          onTransition={transitionAlert}
          rules={cameraRules}
        />
        <EvidenceSearchPanel
          camera={selectedCamera}
          key={selectedCameraId ?? "no-camera-search"}
          onError={reportError}
        />
        <EventFeed
          cameras={cameras}
          evidence={cameraEvidence}
          events={cameraEvents}
          streamStatus={streamStatus}
        />
        <AuditLogPanel records={auditLogs} visible={canAdminister} />
        <footer>
          <span>Artae Vision · Local development console</span>
          <span>Bounded multi-camera inference · Tenant-owned edge credentials</span>
        </footer>
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}
