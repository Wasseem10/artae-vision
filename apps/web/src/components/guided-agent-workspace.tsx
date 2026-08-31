"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Icon } from "@/components/icon";
import { NativePreview } from "@/components/native-preview";
import { StatusPill } from "@/components/status-pill";
import { api } from "@/lib/api";
import { formatLocalTimestamp } from "@/lib/dates";
import type {
  ActionExecution,
  AgentTelemetry,
  AlertIncident,
  Camera,
  CameraAgent,
  ConnectorType,
  ContextSource,
  CorrelationEvaluation,
  IntegrationConnector,
  InvestigationResult,
  LiveDetection,
  ReplaySuite,
  Rule,
  RuleCompilation,
  RuleActionBinding,
  RuleCorrelationPolicy,
  SceneChange,
  SceneMemoryItem,
  Site,
  SiteMap,
  TelegramChat,
  VisualAgentPlan,
  VisualAgentSimulation,
} from "@/lib/types";

interface GuidedAgentWorkspaceProps {
  cameras: Camera[];
  selectedCamera: Camera | null;
  agent: CameraAgent | null;
  alerts: AlertIncident[];
  detections: LiveDetection[];
  telemetry: AgentTelemetry | null;
  busy: boolean;
  onAddWebcam: () => Promise<void>;
  onSelectCamera: (cameraId: string) => void;
  onCompile: (input: { camera_id: string; prompt: string }) => Promise<RuleCompilation>;
  onClarify: (compilationId: string, answer: string) => Promise<RuleCompilation>;
  onRuleCreated: (rule: Rule) => void;
  onStart: () => Promise<void>;
  onStop: () => Promise<void>;
  onOpenAdvanced: () => void;
  onError: (message: string) => void;
}

const examples = [
  "Alert me when a person enters without a hard hat.",
  "Notify me if someone tailgates through the entrance.",
  "Tell me when a product falls off the production line.",
];

function alertTitle(alert: AlertIncident) {
  const objectName = alert.event.object_class.replaceAll("_", " ");
  if (objectName === "visual event") return "Activity matched your alert";
  return `${objectName.charAt(0).toUpperCase()}${objectName.slice(1)} detected`;
}

function alertLocation(alert: AlertIncident) {
  return alert.event.zone_name.toLowerCase().includes("full frame")
    ? "Seen in the camera view"
    : `Seen in ${alert.event.zone_name}`;
}

export function GuidedAgentWorkspace({
  cameras,
  selectedCamera,
  agent,
  alerts,
  detections,
  telemetry,
  busy,
  onAddWebcam,
  onSelectCamera,
  onCompile,
  onClarify,
  onRuleCreated,
  onStart,
  onStop,
  onOpenAdvanced,
  onError,
}: GuidedAgentWorkspaceProps) {
  const [prompt, setPrompt] = useState("");
  const [clarification, setClarification] = useState("");
  const [compilation, setCompilation] = useState<RuleCompilation | null>(null);
  const [plans, setPlans] = useState<VisualAgentPlan[]>([]);
  const [suites, setSuites] = useState<ReplaySuite[]>([]);
  const [simulation, setSimulation] = useState<VisualAgentSimulation | null>(null);
  const [working, setWorking] = useState(false);
  const [connectors, setConnectors] = useState<IntegrationConnector[]>([]);
  const [actionBindings, setActionBindings] = useState<RuleActionBinding[]>([]);
  const [actionExecutions, setActionExecutions] = useState<ActionExecution[]>([]);
  const [contextSources, setContextSources] = useState<ContextSource[]>([]);
  const [correlationPolicies, setCorrelationPolicies] = useState<RuleCorrelationPolicy[]>([]);
  const [correlationEvaluations, setCorrelationEvaluations] = useState<CorrelationEvaluation[]>([]);
  const [sceneItems, setSceneItems] = useState<SceneMemoryItem[]>([]);
  const [sceneChanges, setSceneChanges] = useState<SceneChange[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [siteMap, setSiteMap] = useState<SiteMap | null>(null);
  const [investigationQuery, setInvestigationQuery] = useState("");
  const [investigationResults, setInvestigationResults] = useState<InvestigationResult[]>([]);
  const [connectorName, setConnectorName] = useState("");
  const [connectorType, setConnectorType] = useState<Exclude<ConnectorType, "mock">>("messaging_webhook");
  const [connectorUrl, setConnectorUrl] = useState("");
  const [connectorCredential, setConnectorCredential] = useState("");
  const [telegramChatId, setTelegramChatId] = useState("");
  const [telegramChats, setTelegramChats] = useState<TelegramChat[]>([]);
  const [telegramDiscoveryMessage, setTelegramDiscoveryMessage] = useState("");
  const [previewReady, setPreviewReady] = useState(false);
  const [showAllAlerts, setShowAllAlerts] = useState(false);
  const selectedCameraId = selectedCamera?.id ?? null;

  const loadPlans = useCallback(async () => {
    if (!selectedCameraId) {
      setPlans([]);
      setSceneItems([]);
      setSceneChanges([]);
      setSiteMap(null);
      return;
    }
    try {
      const [nextPlans, nextSuites, nextConnectors, nextExecutions, nextSources, nextEvaluations, nextSceneItems, nextSceneChanges, nextSites] = await Promise.all([
        api.listAgentPlans(selectedCameraId),
        api.listReplaySuites(),
        api.listConnectors(),
        api.listActionExecutions(),
        api.listContextSources(),
        api.listCorrelationEvaluations(),
        api.listSceneMemory(selectedCameraId),
        api.listSceneChanges(selectedCameraId),
        api.listSites(),
      ]);
      setPlans(nextPlans);
      setSuites(nextSuites);
      setConnectors(nextConnectors);
      setActionExecutions(nextExecutions);
      setContextSources(nextSources);
      setCorrelationEvaluations(nextEvaluations);
      setSceneItems(nextSceneItems);
      setSceneChanges(nextSceneChanges);
      setSites(nextSites);
      setSiteMap(nextSites[0] ? await api.getSiteMap(nextSites[0].id) : null);
      const ruleId = nextPlans[0]?.rule_id;
      setActionBindings(ruleId ? await api.listRuleActions(ruleId) : []);
      setCorrelationPolicies(ruleId ? await api.listCorrelationPolicies(ruleId) : []);
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not load deployment plans.");
    }
  }, [onError, selectedCameraId]);

  useEffect(() => {
    const refresh = window.setTimeout(() => {
      void loadPlans();
      setCompilation(null);
      setSimulation(null);
    }, 0);
    return () => window.clearTimeout(refresh);
  }, [loadPlans]);

  const currentPlan = plans[0] ?? null;
  const passedRun = useMemo(
    () => suites.map((suite) => suite.latest_run).find((run) => run?.status === "passed") ?? null,
    [suites],
  );
  const running = agent?.desired_status === "running";
  const deployed = currentPlan?.status === "approved";
  const cameraAlerts = selectedCamera
    ? alerts.filter((alert) =>
      alert.event.camera_id === selectedCamera.id &&
      (!currentPlan || alert.event.rule_id === currentPlan.rule_id),
    )
    : [];
  const visibleAlerts = showAllAlerts ? cameraAlerts : cameraAlerts.slice(0, 3);
  const previewDetections = detections.filter((detection) => detection.confidence >= 0.5);
  const currentCorrelationEvaluation = correlationEvaluations.find((evaluation) =>
    correlationPolicies.some((policy) => policy.id === evaluation.policy_id),
  );
  const selectedSkillNodes = currentPlan?.plan.nodes.filter((node) =>
    node.capability.startsWith("vision.skill."),
  ) ?? [];

  async function compile() {
    if (!selectedCamera || prompt.trim().length < 5) return;
    setWorking(true);
    try {
      setCompilation(await onCompile({ camera_id: selectedCamera.id, prompt: prompt.trim() }));
      setSimulation(null);
    } finally {
      setWorking(false);
    }
  }

  async function answerClarification() {
    if (!compilation || !clarification.trim()) return;
    setWorking(true);
    try {
      setCompilation(await onClarify(compilation.id, clarification.trim()));
      setClarification("");
    } finally {
      setWorking(false);
    }
  }

  async function createPlan() {
    if (!compilation) return;
    setWorking(true);
    try {
      const rule = await api.acceptRuleCompilation(compilation.id);
      onRuleCreated(rule);
      let plan = await api.createAgentPlan(rule.id);
      const planSimulation = await api.simulateAgentPlan(plan.id);
      setSimulation(planSimulation);
      if (
        passedRun &&
        plan.unsupported_capabilities.length === 0 &&
        plan.plan.support?.deployable !== false
      ) {
        plan = await api.approveAgentPlan(plan.id, passedRun.id);
      }
      setPlans((current) => [plan, ...current]);
      setCompilation(null);
      setPrompt("");
      if (plan.status === "approved") {
        if (running) {
          await onStop();
          for (let attempt = 0; attempt < 20; attempt += 1) {
            const status = await api.getCameraAgent(plan.camera_id);
            if (status.observed_status === "stopped" || status.observed_status === "waiting") break;
            await new Promise((resolve) => window.setTimeout(resolve, 250));
          }
        }
        await onStart();
      }
      await loadPlans();
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not create the camera plan.");
    } finally {
      setWorking(false);
    }
  }

  async function simulate() {
    if (!currentPlan) return;
    setWorking(true);
    try {
      setSimulation(await api.simulateAgentPlan(currentPlan.id));
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not run the safe simulation.");
    } finally {
      setWorking(false);
    }
  }

  async function deploy() {
    if (!currentPlan || !passedRun) return;
    setWorking(true);
    try {
      const approved = await api.approveAgentPlan(currentPlan.id, passedRun.id);
      setPlans((current) => current.map((plan) => plan.id === approved.id ? approved : plan));
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not deploy the plan.");
    } finally {
      setWorking(false);
    }
  }

  async function refreshActions() {
    const [nextConnectors, nextExecutions, nextBindings] = await Promise.all([
      api.listConnectors(),
      api.listActionExecutions(),
      currentPlan ? api.listRuleActions(currentPlan.rule_id) : Promise.resolve([]),
    ]);
    setConnectors(nextConnectors);
    setActionExecutions(nextExecutions);
    setActionBindings(nextBindings);
  }

  async function addSafeDemoAction() {
    if (!currentPlan) return;
    setWorking(true);
    try {
      let connector = connectors.find(
        (item) => item.connector_type === "mock" && item.scopes.includes("notifications:write"),
      );
      if (!connector) {
        connector = await api.createConnector({
          name: `Safe local demo ${Date.now().toString().slice(-6)}`,
          connector_type: "mock",
          credential: "local-mock-credential",
          scopes: ["notifications:write", "tickets:write", "webhooks:invoke"],
        });
      }
      await api.createRuleAction(currentPlan.rule_id, {
        connector_id: connector.id,
        action_type: "send_notification",
        approval_mode: "automatic",
        rate_limit_per_minute: 10,
      });
      await refreshActions();
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not add the safe demo action.");
    } finally {
      setWorking(false);
    }
  }

  async function connectRealTool() {
    const isTelegram = connectorType === "telegram";
    if (
      !currentPlan ||
      !connectorName.trim() ||
      !connectorCredential.trim() ||
      (!isTelegram && !connectorUrl.trim()) ||
      (isTelegram && !telegramChatId.trim())
    ) return;
    setWorking(true);
    try {
      const definition = {
        messaging_webhook: { scope: "notifications:write", action: "send_notification" as const },
        telegram: { scope: "notifications:write", action: "send_notification" as const },
        ticket_webhook: { scope: "tickets:write", action: "create_ticket" as const },
        generic_webhook: { scope: "webhooks:invoke", action: "invoke_webhook" as const },
      }[connectorType];
      const connector = await api.createConnector({
        name: connectorName.trim(),
        connector_type: connectorType,
        endpoint_url: isTelegram ? undefined : connectorUrl.trim(),
        credential: connectorCredential.trim(),
        configuration: isTelegram ? { chat_id: telegramChatId.trim() } : undefined,
        scopes: [definition.scope],
      });
      await api.createRuleAction(currentPlan.rule_id, {
        connector_id: connector.id,
        action_type: definition.action,
        approval_mode: definition.action === "send_notification" ? "automatic" : "manual",
        rate_limit_per_minute: 10,
      });
      setConnectorName("");
      setConnectorUrl("");
      setConnectorCredential("");
      setTelegramChatId("");
      setTelegramChats([]);
      setTelegramDiscoveryMessage("");
      await refreshActions();
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not connect the external tool.");
    } finally {
      setWorking(false);
    }
  }

  async function sendTelegramTest(connectorId: string) {
    if (!currentPlan) return;
    setWorking(true);
    try {
      await api.createOutboundTestAlert(currentPlan.rule_id, connectorId);
      await refreshActions();
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not queue the Telegram test.");
    } finally {
      setWorking(false);
    }
  }

  async function discoverTelegramChats() {
    if (connectorCredential.trim().length < 8) return;
    setWorking(true);
    try {
      const chats = await api.discoverTelegramChats(connectorCredential.trim());
      setTelegramChats(chats);
      setTelegramDiscoveryMessage(
        chats.length
          ? "Found " + chats.length + " recent " + (chats.length === 1 ? "chat." : "chats.")
          : "No chats found yet. Send /start to the bot in Telegram, then try again.",
      );
      if (chats.length === 1) setTelegramChatId(chats[0].chat_id);
    } catch (failure) {
      setTelegramChats([]);
      setTelegramDiscoveryMessage("");
      onError(failure instanceof Error ? failure.message : "Could not discover Telegram chats.");
    } finally {
      setWorking(false);
    }
  }

  async function decideAction(executionId: string, decision: "approve" | "deny" | "retry") {
    setWorking(true);
    try {
      if (decision === "approve") await api.approveActionExecution(executionId);
      if (decision === "deny") await api.denyActionExecution(executionId, "Denied from operator dashboard");
      if (decision === "retry") await api.retryActionExecution(executionId);
      await refreshActions();
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not update the action.");
    } finally {
      setWorking(false);
    }
  }

  async function refreshCorrelations() {
    const [nextSources, nextEvaluations, nextPolicies] = await Promise.all([
      api.listContextSources(),
      api.listCorrelationEvaluations(),
      currentPlan ? api.listCorrelationPolicies(currentPlan.rule_id) : Promise.resolve([]),
    ]);
    setContextSources(nextSources);
    setCorrelationEvaluations(nextEvaluations);
    setCorrelationPolicies(nextPolicies);
  }

  async function setupTailgatingDemo() {
    if (!currentPlan) return;
    setWorking(true);
    try {
      let source = contextSources.find((item) => item.source_type === "simulated_access_control");
      if (!source) {
        source = await api.createContextSource(`Safe badge reader ${Date.now().toString().slice(-6)}`);
      }
      await api.createCorrelationPolicy(currentPlan.rule_id, source.id);
      await refreshCorrelations();
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not set up camera and access correlation.");
    } finally {
      setWorking(false);
    }
  }

  async function runTailgatingDemo() {
    if (!currentPlan) return;
    setWorking(true);
    try {
      await api.runTailgatingDemo(currentPlan.rule_id);
      await new Promise((resolve) => window.setTimeout(resolve, 1800));
      await Promise.all([refreshCorrelations(), refreshActions()]);
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not run the tailgating demonstration.");
    } finally {
      setWorking(false);
    }
  }

  async function refreshSceneMemory() {
    if (!selectedCameraId) return;
    const [items, changes] = await Promise.all([
      api.listSceneMemory(selectedCameraId),
      api.listSceneChanges(selectedCameraId),
    ]);
    setSceneItems(items);
    setSceneChanges(changes);
  }

  async function discoverScene() {
    if (!selectedCameraId) return;
    setWorking(true);
    try {
      await api.runSceneDiscoveryDemo(selectedCameraId);
      await refreshSceneMemory();
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not preview scene discovery.");
    } finally {
      setWorking(false);
    }
  }

  async function reviewSceneItem(itemId: string, status: "confirmed" | "rejected") {
    setWorking(true);
    try {
      await api.reviewSceneMemory(itemId, status);
      await refreshSceneMemory();
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not review the scene item.");
    } finally {
      setWorking(false);
    }
  }

  async function setupOperationsMap() {
    if (!selectedCameraId) return;
    setWorking(true);
    try {
      const nextMap = await api.setupOperationsDemo(selectedCameraId);
      setSiteMap(nextMap);
      setSites(await api.listSites());
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not create the site map.");
    } finally {
      setWorking(false);
    }
  }

  async function searchOperations() {
    if (investigationQuery.trim().length < 2) return;
    setWorking(true);
    try {
      const search = await api.searchInvestigations(investigationQuery.trim());
      setInvestigationResults(search.results);
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not search operations history.");
    } finally {
      setWorking(false);
    }
  }

  if (!selectedCamera) {
    return (
      <section className="guidedEmpty">
        <span className="guidedIcon"><Icon name="camera" /></span>
        <h2>Start with your webcam</h2>
        <p>Use the webcam connected to this computer now. You can add network cameras later.</p>
        <button
          className="buttonPrimary buttonWithIcon"
          disabled={busy}
          onClick={() => void onAddWebcam().catch(() => undefined)}
          type="button"
        >
          <Icon name="camera" />
          {busy ? "Connecting webcam…" : "Use my webcam"}
        </button>
        <button className="textButton" onClick={onOpenAdvanced} type="button">Add another camera source</button>
      </section>
    );
  }

  return (
    <div className="guidedWorkspace">
      <section className="guidedHero">
        <div className="guidedHeroTop">
          <div>
            <span className="eyebrow">Camera monitor</span>
            <h1>Live camera</h1>
            <p>Tell the camera what to watch for. An alert appears below when it happens.</p>
          </div>
          <label className="cameraPicker">
            <span>Camera</span>
            <select value={selectedCamera.id} onChange={(event) => onSelectCamera(event.target.value)}>
              {cameras.map((camera) => <option key={camera.id} value={camera.id}>{camera.name}</option>)}
            </select>
            <StatusPill status={previewReady ? "online" : selectedCamera.status} />
          </label>
        </div>

        <div className="webcamQuickStart">
          <div className="webcamPreviewFrame">
            {process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "native" && running && (
              <NativePreview
                cameraId={selectedCamera.id}
                name={selectedCamera.name}
                onAvailabilityChange={setPreviewReady}
              />
            )}
            {previewReady && previewDetections.length > 0 && (
              <svg aria-label="Live object tracking" className="simpleTrackingOverlay" preserveAspectRatio="none" viewBox="0 0 100 100">
                {previewDetections.map((detection, index) => (
                  <g key={`${detection.track_id ?? "detection"}-${index}`}>
                    <rect
                      className="simpleTrackingBox"
                      height={(detection.y2 - detection.y1) * 100}
                      width={(detection.x2 - detection.x1) * 100}
                      x={detection.x1 * 100}
                      y={detection.y1 * 100}
                    />
                    <text className="simpleTrackingLabel" x={detection.x1 * 100} y={Math.max(3, detection.y1 * 100 - 1)}>
                      {detection.label} {Math.round(detection.confidence * 100)}%
                    </text>
                  </g>
                ))}
              </svg>
            )}
            {!previewReady && (
              <div className="webcamPreviewWaiting">
                <Icon name="camera" />
                <strong>{running ? "Starting webcam preview…" : "Webcam is off"}</strong>
              </div>
            )}
            <span className={`webcamLiveBadge ${previewReady ? "isLive" : ""}`}>
              <i /> {previewReady ? "Live webcam" : "Not live"}
            </span>
          </div>
          <div className="webcamControl">
            <div>
              <span className="eyebrow">This computer</span>
              <strong>{selectedCamera.name}</strong>
              <p>{previewReady ? "Your webcam is on and the camera agent is receiving frames." : running ? "The camera agent is connecting to your webcam." : "Turn on the webcam when you are ready to begin analysis."}</p>
            </div>
            <div className="webcamControlButtons">
              <button className="buttonPrimary buttonWithIcon" disabled={busy || running || !deployed} onClick={() => void onStart()} type="button"><Icon name="camera" /> Start camera</button>
              <button className="buttonSecondary" disabled={busy || !running} onClick={() => void onStop()} type="button">Stop camera</button>
            </div>
          </div>
        </div>

        <div className="watchPromptLabel">
          <strong>What should I watch for?</strong>
          <span>Describe it in normal words.</span>
        </div>
        <div className="instructionComposer">
          <textarea
            aria-label="Camera instruction"
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Example: Tell me when someone enters the room."
            rows={3}
            value={prompt}
          />
          <div className="composerFooter">
            <span>{prompt.length}/2000</span>
            <button className="buttonPrimary" disabled={busy || working || prompt.trim().length < 5} onClick={() => void compile()} type="button">
              Watch for this
            </button>
          </div>
        </div>
        <div className="exampleRow">
          <span>Examples:</span>
          {examples.map((example) => <button key={example} onClick={() => setPrompt(example)} type="button">{example}</button>)}
        </div>
      </section>

      {compilation && (
        <section className="reviewCard">
          <div className="reviewHeader"><div><small>New alert</small><h2>{compilation.status === "needs_clarification" ? "One quick question" : "Start watching for this?"}</h2></div></div>
          {compilation.status === "needs_clarification" ? (
            <div className="clarificationBox">
              <p>{compilation.clarification_question}</p>
              <div><input value={clarification} onChange={(event) => setClarification(event.target.value)} placeholder="Type your answer" /><button className="buttonPrimary" disabled={!clarification.trim() || working} onClick={() => void answerClarification()} type="button">Continue</button></div>
            </div>
          ) : (
            <>
              <div className="simpleAlertReview"><Icon name="camera" /><div><small>Your camera will watch for</small><strong>{compilation.prompt}</strong></div></div>
              <button className="buttonPrimary" disabled={working} onClick={() => void createPlan()} type="button">{working ? "Starting…" : "Start watching"}</button>
            </>
          )}
        </section>
      )}

      {currentPlan && (
        <section className="simpleWatchCard">
          <div><span className={`simpleWatchDot ${deployed && running ? "active" : ""}`} /><div><small>{deployed && running ? "Watching now" : "Saved alert"}</small><strong>{currentPlan.prompt}</strong><span className={`watchCadence ${telemetry?.analysis_error ? "watchCadenceError" : ""}`}>{!running ? "Camera stopped — press Start camera to continue." : telemetry?.analysis_error ? `AI check failed: ${telemetry.analysis_error}` : telemetry?.analysis_state === "complete" || telemetry?.analysis_state === "analyzing" ? `AI check ${telemetry.analysis_sequence ?? ""} · 8 snapshots · ${telemetry.analysis_triggered ? "match found" : "no match in the latest check"}` : "Collecting the next 8 snapshots…"}</span></div></div>
          {!deployed && passedRun && !simulation && <button className="buttonPrimary" disabled={working} onClick={() => void simulate()} type="button">Check alert</button>}
          {!deployed && passedRun && simulation && <button className="buttonPrimary" disabled={working} onClick={() => void deploy()} type="button">Turn on alert</button>}
          {!deployed && !passedRun && <button className="buttonSecondary" onClick={onOpenAdvanced} type="button">Finish setup</button>}
        </section>
      )}

      <section className="sceneMemoryPanel">
        <div className="simpleSectionHeader">
          <div><span className="eyebrow">Automatic scene understanding</span><h2>What this camera knows</h2></div>
          {sceneItems.length === 0 && <button className="buttonSecondary" disabled={working} onClick={() => void discoverScene()} type="button">Preview discovery</button>}
        </div>
        <p className="sceneMemoryIntro">The camera can propose stable regions, equipment, displays, and relationships. You may confirm or reject them, but you do not have to draw every box manually.</p>
        <div className="selectedSkills">
          <strong>Skills selected for this job</strong>
          <div>{selectedSkillNodes.length ? selectedSkillNodes.map((node) => <span key={node.id}>{node.title}</span>) : <span>General visual reasoning</span>}</div>
        </div>
        {sceneItems.length ? (
          <div className="sceneItemGrid">
            {sceneItems.map((item) => (
              <article key={item.id}>
                <div><span className={`sceneReview scene-${item.review_status}`}>{item.review_status}</span><small>{item.kind.replaceAll("_", " ")}</small></div>
                <strong>{item.label}</strong>
                <p>{item.description}</p>
                <span className="sceneState">State: {item.current_state} · {Math.round(item.confidence * 100)}%</span>
                {item.review_status === "proposed" && <div className="sceneReviewButtons"><button className="buttonPrimary" disabled={working} onClick={() => void reviewSceneItem(item.id, "confirmed")} type="button">Confirm</button><button className="buttonSecondary" disabled={working} onClick={() => void reviewSceneItem(item.id, "rejected")} type="button">Reject</button></div>}
              </article>
            ))}
          </div>
        ) : <p className="emptyCopy">No scene memory yet. Preview the safe discovery workflow or start a deployed camera job later.</p>}
        {sceneChanges.length > 0 && <p className="sceneChangeSummary">{sceneChanges.length} recorded scene {sceneChanges.length === 1 ? "change" : "changes"}; latest state: {sceneChanges[0].new_state}.</p>}
      </section>

      <section className="operationsPanel">
        <div className="simpleSectionHeader">
          <div>
            <span className="eyebrow">Across every camera</span>
            <h2>Map the site and investigate</h2>
          </div>
          {siteMap ? (
            <label className="sitePicker">
              <span>Site</span>
              <select
                value={siteMap.site.id}
                onChange={(event) => {
                  void api.getSiteMap(event.target.value).then(setSiteMap).catch((failure: unknown) => {
                    onError(failure instanceof Error ? failure.message : "Could not load the site map.");
                  });
                }}
              >
                {sites.map((site) => <option key={site.id} value={site.id}>{site.name}</option>)}
              </select>
            </label>
          ) : (
            <button className="buttonSecondary" disabled={working} onClick={() => void setupOperationsMap()} type="button">Create local site map</button>
          )}
        </div>
        <p className="operationsIntro">See where cameras are located, follow anonymous tracked entities between views, and search events, scene text, and sightings from one place.</p>
        {siteMap ? (
          <div className="operationsGrid">
            <div className="siteMapCard">
              <div className="siteMapCanvas" aria-label={`${siteMap.site.name} camera map`}>
                {siteMap.areas.map((area) => (
                  <div
                    className="siteArea"
                    key={area.id}
                    style={{
                      height: `${area.height * 100}%`,
                      left: `${area.x * 100}%`,
                      top: `${area.y * 100}%`,
                      width: `${area.width * 100}%`,
                    }}
                  >
                    <span>{area.name}</span>
                  </div>
                ))}
                {siteMap.placements.map((placement) => (
                  <span
                    className="cameraMapMarker"
                    key={placement.id}
                    style={{ left: `${placement.x * 100}%`, top: `${placement.y * 100}%` }}
                    title={`${placement.camera_name}${placement.area_name ? ` · ${placement.area_name}` : ""}`}
                  >
                    <Icon name="camera" />
                  </span>
                ))}
              </div>
              <div className="siteMapLegend">
                <strong>{siteMap.site.name}</strong>
                <span>{siteMap.placements.length} {siteMap.placements.length === 1 ? "camera" : "cameras"} · {siteMap.recent_sightings.length} recent sightings</span>
              </div>
            </div>
            <div className="investigationCard">
              <label htmlFor="investigation-search">Find what happened</label>
              <p>Try “red parcel,” “FAULT 42,” or a tracked entity description.</p>
              <div className="investigationComposer">
                <input
                  id="investigation-search"
                  onChange={(event) => setInvestigationQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void searchOperations();
                  }}
                  placeholder="Search all cameras and learned scene state"
                  value={investigationQuery}
                />
                <button className="buttonPrimary" disabled={working || investigationQuery.trim().length < 2} onClick={() => void searchOperations()} type="button">Search</button>
              </div>
              {investigationResults.length ? (
                <div className="investigationResults">
                  {investigationResults.slice(0, 6).map((result) => (
                    <article key={`${result.kind}-${result.id}`}>
                      <span>{result.kind}</span>
                      <div><strong>{result.title}</strong><p>{result.summary}</p></div>
                      <time>{new Date(result.occurred_at).toLocaleString()}</time>
                    </article>
                  ))}
                </div>
              ) : (
                <span className="investigationEmpty">Search results will appear as one chronological incident timeline.</span>
              )}
            </div>
          </div>
        ) : (
          <div className="operationsEmpty">
            <Icon name="camera" />
            <div><strong>Start with an automatic layout</strong><p>This safe local preview places this camera on a simple three-area map. You can replace it with a real facility layout later.</p></div>
          </div>
        )}
      </section>

      <section className="operationStrip">
        <div><span className={`operationDot ${running ? "running" : ""}`} /><div><small>Camera analysis</small><strong>{running ? "Running" : "Stopped — no vision usage"}</strong></div></div>
        {running ? <button className="buttonSecondary" disabled={busy} onClick={() => void onStop()} type="button">Stop analysis</button> : <button className="buttonPrimary" disabled={busy || !deployed} onClick={() => void onStart()} type="button">Start analysis</button>}
      </section>

      <section className="actionCenter">
        <div className="simpleSectionHeader">
          <div><span className="eyebrow">After confirmation</span><h2>Choose what happens next</h2></div>
          <span className="guardedLabel"><Icon name="shield" /> Guarded actions</span>
        </div>
        {!currentPlan ? (
          <p className="emptyCopy">Save a camera plan first. Then you can attach notifications, tickets, or an approved webhook.</p>
        ) : (
          <>
            <div className="actionSafetyGrid">
              <article><strong>Notifications</strong><p>Low risk · may run automatically within its rate limit.</p></article>
              <article><strong>Tickets and webhooks</strong><p>Medium risk · wait for operator approval by default.</p></article>
              <article className="lockedAction"><strong>Doors and machines</strong><p>High risk · disabled until a customer-authorized adapter exists.</p></article>
            </div>
            <div className="contextDemo">
              <div>
                <span className="eyebrow">Camera + business context</span>
                <h3>Tailgating reference workflow</h3>
                <p>Compare people seen at the entrance with successful badge swipes in the same time window. The demo uses synthetic access records and never controls a door.</p>
              </div>
              {correlationPolicies.length ? (
                <button className="buttonSecondary" disabled={working} onClick={() => void runTailgatingDemo()} type="button">Run 2 people / 1 swipe</button>
              ) : (
                <button className="buttonSecondary" disabled={working} onClick={() => void setupTailgatingDemo()} type="button">Set up safe demo</button>
              )}
            </div>
            {currentCorrelationEvaluation && (
              <article className={`correlationResult correlation-${currentCorrelationEvaluation.status}`}>
                <span>{currentCorrelationEvaluation.status}</span>
                <div><strong>{currentCorrelationEvaluation.visual_count} people · {currentCorrelationEvaluation.observation_count} authorized {currentCorrelationEvaluation.observation_count === 1 ? "swipe" : "swipes"}</strong><p>{currentCorrelationEvaluation.explanation ?? "Waiting for the correlation window to close."}</p></div>
              </article>
            )}
            {actionBindings.length ? (
              <div className="configuredActions">
                {actionBindings.map((binding) => (
                  <article key={binding.id}>
                    <span className={`riskDot risk-${binding.risk_level}`} />
                    <div><strong>{binding.action_type.replaceAll("_", " ")}</strong><p>{binding.connector_name} · {binding.approval_mode} approval · {binding.rate_limit_per_minute}/minute</p></div>
                    <span className="actionReady">Ready</span>
                    {connectors.find((connector) => connector.id === binding.connector_id)?.connector_type === "telegram" && (
                      <button className="buttonSecondary" disabled={working} onClick={() => void sendTelegramTest(binding.connector_id)} type="button">Send Telegram test</button>
                    )}
                  </article>
                ))}
              </div>
            ) : (
              <button className="safeActionButton" disabled={working} onClick={() => void addSafeDemoAction()} type="button">
                <Icon name="spark" /><span><strong>Add a safe demo notification</strong><small>Runs locally and makes no network request.</small></span>
              </button>
            )}
            <details className="connectorSetup">
              <summary>Connect a real messaging, ticket, or webhook tool</summary>
              <div className="connectorForm">
                <label><span>Tool type</span><select value={connectorType} onChange={(event) => setConnectorType(event.target.value as Exclude<ConnectorType, "mock">)}><option value="telegram">Telegram</option><option value="messaging_webhook">Messaging webhook</option><option value="ticket_webhook">Ticket webhook</option><option value="generic_webhook">Generic webhook</option></select></label>
                <label><span>Name</span><input value={connectorName} onChange={(event) => setConnectorName(event.target.value)} placeholder={connectorType === "telegram" ? "Security Telegram" : "Operations Slack"} /></label>
                {connectorType === "telegram" ? (
                  <>
                    <label className="connectorWide"><span>BotFather token</span><input type="password" value={connectorCredential} onChange={(event) => setConnectorCredential(event.target.value)} placeholder="Stored encrypted; never shown again" /></label>
                    <button className="buttonSecondary" disabled={working || connectorCredential.trim().length < 8} onClick={() => void discoverTelegramChats()} type="button">Find recent chats</button>
                    {telegramChats.length ? (
                      <label className="connectorWide"><span>Destination chat</span><select value={telegramChatId} onChange={(event) => setTelegramChatId(event.target.value)}><option value="">Choose a chat</option>{telegramChats.map((chat) => <option key={chat.chat_id} value={chat.chat_id}>{chat.title} · {chat.chat_type}</option>)}</select></label>
                    ) : (
                      <label className="connectorWide"><span>Chat ID</span><input value={telegramChatId} onChange={(event) => setTelegramChatId(event.target.value)} placeholder="Send /start to the bot, then find recent chats" /></label>
                    )}
                    {telegramDiscoveryMessage && <small className="connectorWide" aria-live="polite">{telegramDiscoveryMessage}</small>}
                  </>
                ) : (
                  <>
                    <label className="connectorWide"><span>HTTPS endpoint</span><input value={connectorUrl} onChange={(event) => setConnectorUrl(event.target.value)} placeholder="https://…" /></label>
                    <label className="connectorWide"><span>Signing credential</span><input type="password" value={connectorCredential} onChange={(event) => setConnectorCredential(event.target.value)} placeholder="Stored encrypted; never shown again" /></label>
                  </>
                )}
                <button className="buttonPrimary" disabled={working || !connectorName.trim() || (connectorType === "telegram" ? !telegramChatId.trim() : !connectorUrl.trim()) || connectorCredential.trim().length < 8} onClick={() => void connectRealTool()} type="button">Connect and attach</button>
              </div>
            </details>
          </>
        )}
        {actionExecutions.length > 0 && (
          <div className="actionQueue">
            <h3>Recent action activity</h3>
            {actionExecutions.slice(0, 6).map((execution) => (
              <article key={execution.id}>
                <span className={`executionState execution-${execution.status}`}>{execution.status.replaceAll("_", " ")}</span>
                <div><strong>{execution.action_type.replaceAll("_", " ")}</strong><p>{execution.connector_name} · attempt {execution.attempt_count}</p>{execution.last_error && <small>{execution.last_error}</small>}</div>
                <div className="actionDecisionButtons">
                  {execution.status === "awaiting_approval" && <><button className="buttonPrimary" disabled={working} onClick={() => void decideAction(execution.id, "approve")} type="button">Approve</button><button className="buttonSecondary" disabled={working} onClick={() => void decideAction(execution.id, "deny")} type="button">Deny</button></>}
                  {execution.status === "dead_lettered" && <button className="buttonSecondary" disabled={working} onClick={() => void decideAction(execution.id, "retry")} type="button">Retry</button>}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="recentAlertsSimple">
        <div className="simpleSectionHeader"><div><span className="eyebrow">Alerts</span><h2>What happened</h2></div>{cameraAlerts.length > 3 && <button className="buttonGhost" onClick={() => setShowAllAlerts((current) => !current)} type="button">{showAllAlerts ? "Show latest" : "See all"}</button>}</div>
        {visibleAlerts.length ? visibleAlerts.map((alert) => <article key={alert.id}><span className="alertMarker"><Icon name="event" /></span><div><strong>{alertTitle(alert)}</strong><p>{alertLocation(alert)}</p></div><time dateTime={alert.event.occurred_at}>{formatLocalTimestamp(alert.event.occurred_at)}</time></article>) : <p className="emptyCopy">No alerts for this instruction yet. When the camera sees what you described, it will appear here.</p>}
      </section>
    </div>
  );
}
