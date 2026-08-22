"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CameraPanel } from "@/components/camera-panel";
import { AgentControl } from "@/components/agent-control";
import { AlertPanel } from "@/components/alert-panel";
import { AuditLogPanel } from "@/components/audit-log-panel";
import { EvidenceSearchPanel } from "@/components/evidence-search";
import { EdgeDevicesPanel } from "@/components/edge-devices-panel";
import { EventFeed } from "@/components/event-feed";
import { GuidedAgentWorkspace } from "@/components/guided-agent-workspace";
import { Icon, type IconName } from "@/components/icon";
import { MvpLaunchpad } from "@/components/mvp-launchpad";
import { ProductionReadinessPanel } from "@/components/production-readiness-panel";
import { RulePanel } from "@/components/rule-panel";
import { ReplayEvaluationPanel } from "@/components/replay-evaluation-panel";
import { ZoneEditor } from "@/components/zone-editor";
import { useEventStream } from "@/hooks/use-event-stream";
import { API_URL, api } from "@/lib/api";
import { prependUniqueEvent } from "@/lib/events";
import type {
  AlertChannel,
  AlertIncident,
  Camera,
  CameraAgent,
  CameraStream,
  CompileRuleInput,
  CreateAlertChannelInput,
  CreateAlertRouteInput,
  CreateCameraInput,
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
  ProductionReadiness,
} from "@/lib/types";

export function Dashboard() {
  const [consoleMode, setConsoleMode] = useState<"guided" | "advanced">("guided");
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [events, setEvents] = useState<VideoEvent[]>([]);
  const [alerts, setAlerts] = useState<AlertIncident[]>([]);
  const [alertChannels, setAlertChannels] = useState<AlertChannel[]>([]);
  const [evidence, setEvidence] = useState<EvidenceAsset[]>([]);
  const [edgeDevices, setEdgeDevices] = useState<EdgeDevice[]>([]);
  const [edgeFleet, setEdgeFleet] = useState<EdgeFleetDevice[]>([]);
  const [productionReadiness, setProductionReadiness] = useState<ProductionReadiness | null>(null);
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
    },
    [loadAgent, loadStream],
  );

  const load = useCallback(async () => {
    try {
      const nextIdentity = await api.getIdentity();
      const canAdminister = nextIdentity.role === "owner" || nextIdentity.role === "admin";
      const [nextCameras, nextZones, nextRules, nextEvents, nextEvidence, nextCapabilities, nextAlerts, nextAlertChannels, nextEdgeDevices, nextEdgeFleet, nextAuditLogs, nextProductionReadiness] = await Promise.all([
        api.listCameras(),
        api.listZones(),
        api.listRules(),
        api.listEvents(),
        api.listEvidence(),
        api.getCapabilities(),
        api.listAlerts(),
        api.listAlertChannels(),
        api.listEdgeDevices(),
        api.listEdgeFleet(),
        canAdminister ? api.listAuditLogs() : Promise.resolve([]),
        canAdminister ? api.getProductionReadiness() : Promise.resolve(null),
      ]);
      setCameras(nextCameras);
      setZones(nextZones);
      setRules(nextRules);
      setEvents(nextEvents);
      setEvidence(nextEvidence);
      setCapabilities(nextCapabilities);
      setAlerts(nextAlerts);
      setAlertChannels(nextAlertChannels);
      setIdentity(nextIdentity);
      setEdgeDevices(nextEdgeDevices);
      setEdgeFleet(nextEdgeFleet);
      setAuditLogs(nextAuditLogs);
      setProductionReadiness(nextProductionReadiness);
      const currentCameraId = selectedCameraIdRef.current;
      const nextCameraId = nextCameras.some((camera) => camera.id === currentCameraId)
        ? currentCameraId
        : (nextCameras[0]?.id ?? null);
      selectedCameraIdRef.current = nextCameraId;
      setSelectedCameraId(nextCameraId);
      if (nextCameraId) {
        void loadStream(nextCameraId, true);
        void loadAgent(nextCameraId);
      } else {
        setCameraStream(null);
        setCameraAgent(null);
      }
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load the dashboard.");
    } finally {
      setLoading(false);
    }
  }, [loadAgent, loadStream]);

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
      },
      5000,
    );
    return () => window.clearInterval(statusPoll);
  }, [loadAgent, loadAlerts, loadEvidence, loadStream, selectedCameraId]);

  const receiveEvent = useCallback((event: VideoEvent) => {
    setEvents((current) => prependUniqueEvent(current, event));
    void loadAlerts();
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
  }, [loadAlerts]);
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

  const canAdminister = identity?.role === "owner" || identity?.role === "admin";

  return (
    <div className="appShell">
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
          <button className={consoleMode === "advanced" ? "navActive" : ""} onClick={() => setConsoleMode("advanced")} type="button">
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
          <>
            <header className="guidedTopbar">
              <div>
                <span className="eyebrow">Artae Vision</span>
                <h2>Automations</h2>
              </div>
              <div className="topbarActions">
                <span className={`apiState ${error ? "apiStateError" : ""}`}><i /> {error ? "Needs attention" : loading ? "Connecting" : "System ready"}</span>
                <button className="buttonSecondary" disabled={loading} onClick={() => { setLoading(true); void load(); }} type="button">Refresh</button>
              </div>
            </header>
            {error && (
              <div className="errorBanner" role="alert"><Icon name="activity" /><span><strong>Something needs attention</strong>{error}</span><button onClick={() => setError(null)} type="button">Dismiss</button></div>
            )}
            <GuidedAgentWorkspace
              agent={cameraAgent}
              alerts={alerts}
              busy={busy}
              cameras={cameras}
              onClarify={clarifyRule}
              onCompile={compileRule}
              onError={reportError}
              onOpenAdvanced={() => setConsoleMode("advanced")}
              onRuleCreated={(rule) => setRules((current) => [rule, ...current.filter((item) => item.id !== rule.id)])}
              onSelectCamera={selectCamera}
              onStart={() => void changeAgentStatus("running")}
              onStop={() => void changeAgentStatus("stopped")}
              selectedCamera={selectedCamera}
            />
          </>
        ) : (
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
              <span className="tenantContext" title={identity.organization_id}>
                {identity.role} · {identity.display_name ?? identity.subject}
              </span>
            )}
            <span className={`apiState ${error ? "apiStateError" : ""}`}>
              <i /> {error ? "API attention needed" : loading ? "Connecting" : "Control plane ready"}
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
        <AlertPanel
          alerts={alerts}
          busy={busy}
          channels={alertChannels}
          onCreateChannel={createAlertChannel}
          onCreateRoute={createAlertRoute}
          onTransition={transitionAlert}
          rules={rules}
        />
        <EvidenceSearchPanel camera={selectedCamera} onError={reportError} />
        <EventFeed
          cameras={cameras}
          evidence={evidence}
          events={events}
          streamStatus={streamStatus}
        />
        <AuditLogPanel records={auditLogs} visible={canAdminister} />
        <footer>
          <span>Artae Vision · Local development console</span>
          <span>Bounded multi-camera inference · Tenant-owned edge credentials</span>
        </footer>
          </>
        )}
      </main>
    </div>
  );
}
