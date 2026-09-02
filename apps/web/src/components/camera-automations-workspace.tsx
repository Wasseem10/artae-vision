"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "@/components/icon";
import { MonitoringFeed } from "@/components/monitoring-feed";
import { API_URL, api } from "@/lib/api";
import type {
  ActionExecution, AlertIncident, Camera, CameraAgent, CameraStream,
  IntegrationConnector, LiveDetection, RecordingSegment, ReplayEvaluation, Rule,
  RuleActionBinding, RuleCompilation, TelegramChat, VideoEvent,
  VerificationCase, CurrentActor,
} from "@/lib/types";

interface Props {
  agent: CameraAgent | null; alerts: AlertIncident[]; busy: boolean; cameras: Camera[];
  detections: LiveDetection[]; events: VideoEvent[]; loading: boolean;
  recordings: RecordingSegment[];
  onAddWebcam: () => Promise<void>;
  onClarify: (compilationId: string, answer: string) => Promise<RuleCompilation>;
  onCompile: (input: { camera_id: string; prompt: string }) => Promise<RuleCompilation>;
  onDecideVerification: (caseId: string, status: "confirmed" | "rejected") => Promise<void>;
  onOpenAdvanced: (sectionId: string) => void; onRuleCreated: (rule: Rule) => void;
  onRuleStatusChange: (ruleId: string, status: "active" | "paused") => Promise<void>;
  onSafeTest: (ruleId: string, connectorId: string) => Promise<AlertIncident>;
  onRefreshRecordings: () => Promise<void>;
  onSelectCamera: (cameraId: string) => void; onStart: () => Promise<void>;
  onStop: () => Promise<void>; rules: Rule[]; selectedCamera: Camera | null;
  stream: CameraStream | null; verificationCases: VerificationCase[];
  identity: CurrentActor | null; onSignOut: () => Promise<void>;
}

type WorkspaceView = "conversation" | "agents" | "footage" | "investigate" | "alerts" | "settings";

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function ruleTitle(rule: Rule | null) {
  if (!rule) return "New monitoring conversation";
  const text = `${rule.name} ${rule.original_prompt ?? ""}`.toLowerCase();
  if (/\b(fall|falls|fell|fallen|collapse|collapsed)\b/.test(text)) return "Fall detection";
  if (text.includes("hard hat") || text.includes("helmet")) return "Hard hat compliance";
  return rule.name || "Monitoring conversation";
}

function actionTypeForConnector(connector: IntegrationConnector) {
  if (connector.connector_type === "ticket_webhook") return "create_ticket" as const;
  if (connector.connector_type === "generic_webhook") return "invoke_webhook" as const;
  return "send_notification" as const;
}

function actionLabel(connector: IntegrationConnector | null, recipient: string) {
  if (!connector || connector.connector_type === "mock") return `Create an in-app alert for ${recipient.toLowerCase()}`;
  if (connector.connector_type === "telegram") return `Send a Telegram message to ${recipient.toLowerCase()}`;
  if (connector.connector_type === "ticket_webhook") return `Create a ticket in ${connector.name}`;
  if (connector.connector_type === "messaging_webhook") return `Send a message through ${connector.name}`;
  return `Trigger ${connector.name}`;
}

function bindingActionLabel(binding: RuleActionBinding | null) {
  if (!binding) return "No action connected";
  if (binding.action_type === "create_ticket") return `Create a ticket in ${binding.connector_name}`;
  if (binding.action_type === "invoke_webhook") return `Trigger ${binding.connector_name}`;
  return `Send an alert through ${binding.connector_name}`;
}

export function CameraAutomationsWorkspace({
  agent, alerts, busy, cameras, detections, events, loading, onAddWebcam, recordings,
  onClarify, onCompile, onDecideVerification, onOpenAdvanced, onRuleCreated, onRuleStatusChange,
  onRefreshRecordings, onSafeTest, onSelectCamera, onStart, rules, selectedCamera, stream,
  verificationCases, identity, onSignOut, onStop,
}: Props) {
  const [view, setView] = useState<WorkspaceView>("conversation");
  const [prompt, setPrompt] = useState("");
  const [submittedPrompt, setSubmittedPrompt] = useState("");
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  const [compilation, setCompilation] = useState<RuleCompilation | null>(null);
  const [clarification, setClarification] = useState("");
  const [sourceMode, setSourceMode] = useState<"live" | "upload">("live");
  const [recipient, setRecipient] = useState("Safety manager");
  const [actionDestination, setActionDestination] = useState("computer");
  const [connectors, setConnectors] = useState<IntegrationConnector[]>([]);
  const [bindings, setBindings] = useState<RuleActionBinding[]>([]);
  const [agentBindings, setAgentBindings] = useState<Record<string, RuleActionBinding[]>>({});
  const [executions, setExecutions] = useState<ActionExecution[]>([]);
  const [working, setWorking] = useState(false);
  const [reviewingCaseId, setReviewingCaseId] = useState<string | null>(null);
  const [previewReady, setPreviewReady] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [uploadedVideo, setUploadedVideo] = useState<File | null>(null);
  const [uploadedVideoUrl, setUploadedVideoUrl] = useState<string | null>(null);
  const [uploadedDuration, setUploadedDuration] = useState(0);
  const [uploadEvaluation, setUploadEvaluation] = useState<ReplayEvaluation | null>(null);
  const [telegramSetupOpen, setTelegramSetupOpen] = useState(false);
  const [telegramToken, setTelegramToken] = useState("");
  const [telegramChats, setTelegramChats] = useState<TelegramChat[]>([]);
  const [telegramChatId, setTelegramChatId] = useState("");
  const [telegramSetupMessage, setTelegramSetupMessage] = useState<string | null>(null);
  const dispatchedEvaluationId = useRef<string | null>(null);
  const deliveryInitialized = useRef(false);
  const restoredRunningSession = useRef(false);

  const activeRule = rules.find((rule) => rule.id === selectedRuleId) ?? null;
  const running = agent?.desired_status === "running";
  const operating = agent?.observed_status === "running";
  const nativeDeployment = process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "native";
  const nativePreviewEnabled = nativeDeployment && running && Boolean(selectedCamera);
  const telegramConnector = connectors.find((connector) => connector.enabled && connector.connector_type === "telegram") ?? null;
  const selectedActionConnector = actionDestination === "computer"
    ? null
    : connectors.find((connector) => connector.id === actionDestination && connector.enabled) ?? null;
  const sessionStarted = Boolean(submittedPrompt || compilation || activeRule);
  const currentEvents = activeRule ? events.filter((event) => event.rule_id === activeRule.id) : [];
  const currentAlerts = activeRule ? alerts.filter((alert) => alert.event.rule_id === activeRule.id) : [];
  const currentAlertIds = new Set(currentAlerts.map((alert) => alert.id));
  const currentExecutions = executions.filter((execution) => currentAlertIds.has(execution.alert_id));
  const visibleRecordings = recordings.filter((recording) => recording.status !== "expired");
  const activeBinding = bindings.find((binding) => binding.enabled) ?? null;
  const activeRuleRequested = Boolean(activeRule?.status === "active" && running);
  const activeRuleLive = Boolean(activeRule?.status === "active" && operating);
  const currentCases = activeRule
    ? verificationCases.filter((item) => item.event.rule_id === activeRule.id && !["confirmed", "rejected"].includes(item.status))
    : [];

  const refreshActionState = useCallback(async (ruleId?: string | null) => {
    const [nextConnectors, nextExecutions, nextBindings] = await Promise.all([
      api.listConnectors(), api.listActionExecutions(),
      ruleId ? api.listRuleActions(ruleId) : Promise.resolve([]),
    ]);
    setConnectors(nextConnectors); setExecutions(nextExecutions); setBindings(nextBindings);
    if (!deliveryInitialized.current) {
      const connectedTelegram = nextConnectors.find((connector) => connector.enabled && connector.connector_type === "telegram");
      if (connectedTelegram) setActionDestination(connectedTelegram.id);
      deliveryInitialized.current = true;
    }
  }, []);

  useEffect(() => {
    const refresh = () => void refreshActionState(selectedRuleId).catch(() => undefined);
    const timer = window.setTimeout(refresh, 0); const poll = window.setInterval(refresh, 4000);
    return () => { window.clearTimeout(timer); window.clearInterval(poll); };
  }, [refreshActionState, selectedRuleId]);

  useEffect(() => {
    if (view !== "agents" || rules.length === 0) return;
    void Promise.all(rules.map(async (rule) => [rule.id, await api.listRuleActions(rule.id)] as const))
      .then((entries) => setAgentBindings(Object.fromEntries(entries)))
      .catch((failure) => setMessage(failure instanceof Error ? failure.message : "Could not load agent actions."));
  }, [rules, view]);

  useEffect(() => {
    if (view !== "footage" || !selectedCamera) return;
    void onRefreshRecordings().catch((failure) => {
      setMessage(failure instanceof Error ? failure.message : "Could not load saved footage.");
    });
  }, [onRefreshRecordings, selectedCamera, view]);

  useEffect(() => () => { if (uploadedVideoUrl) URL.revokeObjectURL(uploadedVideoUrl); }, [uploadedVideoUrl]);

  useEffect(() => {
    if (restoredRunningSession.current || !agent || rules.length === 0) return;
    restoredRunningSession.current = true;
    const savedRule = agent.desired_status === "running"
      ? rules.find((rule) => rule.status === "active") ?? rules[0]
      : rules[0];
    if (!savedRule) return;
    const restoredPrompt = savedRule.original_prompt ?? savedRule.name;
    const timer = window.setTimeout(() => {
      setSelectedRuleId(savedRule.id);
      setSubmittedPrompt(restoredPrompt);
      setPrompt(restoredPrompt);
      setView("conversation");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [agent, rules]);

  useEffect(() => {
    if (!uploadEvaluation || !["queued", "running"].includes(uploadEvaluation.status)) return;
    const timer = window.setInterval(() => {
      void api.getReplayEvaluation(uploadEvaluation.id).then(setUploadEvaluation).catch((failure) => {
        setMessage(failure instanceof Error ? failure.message : "Could not refresh video analysis.");
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [uploadEvaluation]);

  useEffect(() => {
    if (!uploadEvaluation || uploadEvaluation.status !== "scored" || !activeRule) return;
    if (dispatchedEvaluationId.current === uploadEvaluation.id) return;
    dispatchedEvaluationId.current = uploadEvaluation.id;
    if (uploadEvaluation.predicted_intervals.length === 0) {
      return;
    }
    void api.dispatchReplayEvaluation(uploadEvaluation.id, activeRule.id).then(() => {
      setMessage(`Analysis complete. ${uploadEvaluation.predicted_intervals.length} real match${uploadEvaluation.predicted_intervals.length === 1 ? " was" : "es were"} found and the alert action was queued.`);
      void refreshActionState(activeRule.id);
    }).catch((failure) => setMessage(failure instanceof Error ? failure.message : "Could not create the uploaded-video incident."));
  }, [activeRule, refreshActionState, uploadEvaluation]);

  const conversationMessage = uploadEvaluation?.status === "scored" && uploadEvaluation.predicted_intervals.length === 0
    ? "Analysis complete. The condition was not found in this video."
    : operating && message?.startsWith("Starting ")
      ? `AI is watching the live feed. When the condition is confirmed, Artae will ${bindingActionLabel(activeBinding).toLowerCase()}.`
    : message;

  async function ensureLocalConnector() {
    let connector = connectors.find((item) => item.connector_type === "mock" && item.scopes.includes("notifications:write"));
    if (!connector) {
      connector = await api.createConnector({ name: "This computer", connector_type: "mock", credential: "local-computer-notification", configuration: { delivery: "in_app" }, scopes: ["notifications:write"] });
      setConnectors((current) => [connector!, ...current]);
    }
    return connector;
  }

  async function resolveActionConnector() {
    if (actionDestination === "computer") return ensureLocalConnector();
    return connectors.find((connector) => connector.id === actionDestination && connector.enabled) ?? null;
  }

  async function ensureAgentAction(rule: Rule, connector: IntegrationConnector) {
    const currentBindings = await api.listRuleActions(rule.id);
    const actionType = actionTypeForConnector(connector);
    const existing = currentBindings.find((item) => item.connector_id === connector.id && item.action_type === actionType);
    if (existing) return existing;
    return api.createRuleAction(rule.id, {
      connector_id: connector.id, action_type: actionType, approval_mode: "automatic",
      rate_limit_per_minute: 6, enabled: true,
      payload_template: { title: sourceMode === "upload" ? "Uploaded video alert" : "Camera alert", summary: "{{event.summary}}", metadata: { recipient, source: "Artae Vision" } },
    });
  }

  async function runUploadedAnalysis(rule: Rule) {
    if (!uploadedVideo || !selectedCamera) throw new Error("Choose a video before starting monitoring.");
    const upload = await api.uploadReplayVideo(uploadedVideo);
    const created = await api.createReplayEvaluation({ name: uploadedVideo.name, camera_id: selectedCamera.id, source_uri: upload.source_uri, prompt: rule.original_prompt ?? submittedPrompt, duration_seconds: uploadedDuration > 0 ? uploadedDuration : 300, expected_intervals: [] });
    setUploadEvaluation(await api.runReplayEvaluation(created.id));
  }

  async function deployCompilation(result: RuleCompilation) {
    if (!result.compiled_rule || result.status === "needs_clarification") return;
    const rule = await api.acceptRuleCompilation(result.id); onRuleCreated(rule); setSelectedRuleId(rule.id);
    const connector = await resolveActionConnector();
    if (!connector) { setMessage("Connect an action destination in Settings, then deploy this agent again."); setView("settings"); return; }
    const binding = await ensureAgentAction(rule, connector);
    if (running) {
      setMessage("Updating the camera agent…");
      await onStop();
    }
    await onRuleStatusChange(rule.id, "active"); setBindings((current) => [binding, ...current.filter((item) => item.id !== binding.id)]);
    if (sourceMode === "live") {
      await onStart();
      setMessage(`Starting camera AI on ${selectedCamera?.name ?? "this camera"}. The first start can take several seconds while the vision models load.`);
    } else {
      await runUploadedAnalysis(rule); setMessage("The uploaded video is being analyzed with your rule now.");
    }
    setCompilation(null); await refreshActionState(rule.id);
  }

  async function startMonitoring() {
    if (!selectedCamera || prompt.trim().length < 8) return;
    if (sourceMode === "upload" && !uploadedVideo) { setMessage("Choose a video first, then start monitoring."); return; }
    setWorking(true); setMessage("Building your monitoring agent…"); setSubmittedPrompt(prompt.trim());
    try {
      const result = await onCompile({ camera_id: selectedCamera.id, prompt: prompt.trim() }); setCompilation(result);
      if (result.status === "needs_clarification") { setMessage("I need one detail before I can start."); return; }
      await deployCompilation(result);
    } catch (failure) { setMessage(failure instanceof Error ? failure.message : "Could not start monitoring."); }
    finally { setWorking(false); }
  }

  async function answerClarification() {
    if (!compilation || !clarification.trim()) return;
    setWorking(true);
    try {
      const result = await onClarify(compilation.id, clarification.trim()); setCompilation(result); setClarification("");
      if (result.status === "needs_clarification") setMessage("I still need a specific area. Choose the entire camera view or enter the name of a saved camera area."); else await deployCompilation(result);
    } catch (failure) { setMessage(failure instanceof Error ? failure.message : "Could not finish the monitoring rule."); }
    finally { setWorking(false); }
  }

  async function chooseEntireCameraView() {
    if (!compilation) return;
    setClarification("Full frame (automatic)");
    setWorking(true);
    try {
      const result = await onClarify(compilation.id, "Full frame (automatic)"); setCompilation(result); setClarification("");
      if (result.status === "needs_clarification") setMessage("I could not use the whole view for this request. Choose a saved camera area instead."); else await deployCompilation(result);
    } catch (failure) { setMessage(failure instanceof Error ? failure.message : "Could not use the entire camera view."); }
    finally { setWorking(false); }
  }

  async function toggleRuleAgent(rule: Rule) {
    setWorking(true); setSelectedRuleId(rule.id);
    try {
      if (rule.status === "active" && running) {
        await onStop();
        await onRuleStatusChange(rule.id, "paused");
        const anotherAgentIsActive = rules.some((item) => item.id !== rule.id && item.status === "active");
        if (anotherAgentIsActive) await onStart();
        setMessage(`${ruleTitle(rule)} is paused.`);
      } else {
        if (running) await onStop();
        if (rule.status !== "active") {
          await onRuleStatusChange(rule.id, "active");
        }
        await onStart();
        setMessage(`Starting ${ruleTitle(rule).toLowerCase()} on ${selectedCamera?.name ?? "this camera"}.`);
      }
    } catch (failure) { setMessage(failure instanceof Error ? failure.message : "Could not change the agent status."); }
    finally { setWorking(false); }
  }

  async function stopCameraAndRecording() {
    setWorking(true);
    try {
      await onStop();
      setMessage("Camera, AI analysis, and video recording stopped.");
    } catch (failure) {
      setMessage(failure instanceof Error ? failure.message : "Could not stop the camera.");
    } finally {
      setWorking(false);
    }
  }

  async function runSafeTest() {
    if (!activeRule) return; setWorking(true);
    try {
      let binding = bindings.find((item) => item.enabled);
      if (!binding) { const connector = await resolveActionConnector(); if (!connector) { setMessage("Connect an action destination first."); return; } binding = await ensureAgentAction(activeRule, connector); }
      await onSafeTest(activeRule.id, binding.connector_id); setMessage("Safe test sent. It creates a test incident without pretending the camera detected anything."); await refreshActionState(activeRule.id);
    } catch (failure) { setMessage(failure instanceof Error ? failure.message : "Could not run the safe test."); }
    finally { setWorking(false); }
  }

  async function testAgentAction(rule: Rule) {
    const binding = agentBindings[rule.id]?.find((item) => item.enabled);
    if (!binding) { setSelectedRuleId(rule.id); setMessage("This agent does not have an action yet. Open it and choose an action destination."); setView("conversation"); return; }
    setWorking(true); setSelectedRuleId(rule.id);
    try {
      await onSafeTest(rule.id, binding.connector_id);
      setMessage(`Safe test sent through ${binding.connector_name}.`);
      setView("alerts");
      await refreshActionState(rule.id);
    } catch (failure) { setMessage(failure instanceof Error ? failure.message : "Could not test this agent action."); }
    finally { setWorking(false); }
  }

  async function reviewDetection(caseId: string, status: "confirmed" | "rejected") {
    setReviewingCaseId(caseId);
    try {
      await onDecideVerification(caseId, status);
      setMessage(status === "confirmed" ? "Detection confirmed. The configured alert is being sent now." : "Detection rejected. No alert was sent.");
    } finally {
      setReviewingCaseId(null);
    }
  }

  function chooseUploadedVideo(file: File | null) {
    if (uploadedVideoUrl) URL.revokeObjectURL(uploadedVideoUrl);
    setUploadedVideo(file); setUploadedDuration(0); setUploadEvaluation(null); dispatchedEvaluationId.current = null;
    if (!file) { setUploadedVideoUrl(null); return; }
    const objectUrl = URL.createObjectURL(file); setUploadedVideoUrl(objectUrl);
    const video = document.createElement("video"); video.preload = "metadata";
    video.onloadedmetadata = () => { if (Number.isFinite(video.duration) && video.duration > 0) setUploadedDuration(video.duration); };
    video.src = objectUrl;
  }

  async function discoverTelegramChats() {
    if (telegramToken.trim().length < 8) return; setWorking(true); setTelegramSetupMessage("Looking for the chat that messaged your bot…");
    try { const chats = await api.discoverTelegramChats(telegramToken.trim()); setTelegramChats(chats); if (chats.length === 1) setTelegramChatId(chats[0].chat_id); setTelegramSetupMessage(chats.length ? "Choose where alerts should go." : "No chat found. Send /start to your bot in Telegram, then try again."); }
    catch (failure) { setTelegramSetupMessage(failure instanceof Error ? failure.message : "Could not find a Telegram chat."); }
    finally { setWorking(false); }
  }

  async function connectTelegram() {
    if (!telegramToken.trim() || !telegramChatId.trim()) return; setWorking(true);
    try {
      const connector = await api.createConnector({ name: "Safety alerts on Telegram", connector_type: "telegram", credential: telegramToken.trim(), configuration: { chat_id: telegramChatId.trim() }, scopes: ["notifications:write"] });
      setConnectors((current) => [connector, ...current]); setActionDestination(connector.id); setTelegramToken(""); setTelegramChats([]); setTelegramChatId(""); setTelegramSetupOpen(false); setMessage("Telegram is connected and will receive confirmed agent actions.");
    } catch (failure) { setTelegramSetupMessage(failure instanceof Error ? failure.message : "Could not connect Telegram."); }
    finally { setWorking(false); }
  }

  function startNewConversation() {
    setView("conversation"); setPrompt(""); setSubmittedPrompt(""); setSelectedRuleId(null); setCompilation(null); setClarification(""); setMessage(null); setUploadEvaluation(null);
  }

  function openAgent(rule: Rule) {
    setSelectedRuleId(rule.id); setSubmittedPrompt(rule.original_prompt ?? rule.name); setPrompt(rule.original_prompt ?? rule.name); setCompilation(null); setView("conversation"); setMessage(null);
  }

  const navigation: Array<{ id: WorkspaceView; label: string; icon: "spark" | "rule" | "camera" | "search" | "event" | "settings" }> = [
    { id: "conversation", label: "Build agent", icon: "spark" }, { id: "agents", label: "Agents", icon: "rule" }, { id: "footage", label: "Footage", icon: "camera" }, { id: "investigate", label: "Investigate", icon: "search" },
    { id: "alerts", label: "Alerts", icon: "event" }, { id: "settings", label: "Settings", icon: "settings" },
  ];
  const starterPrompts = [
    { label: "Fall detection", route: "Local pose AI", recipient: "Caregiver", prompt: "Alert the caregiver when a person falls to the ground." },
    { label: "Workplace safety", route: "Visual AI", recipient: "Safety manager", prompt: "Tell the safety manager when someone enters this area without a hard hat." },
    { label: "After-hours activity", route: "Local tracking", recipient: "Site manager", prompt: "Alert the site manager if a person enters this area after business hours." },
    { label: "Loading dock", route: "Local tracking", recipient: "Operations lead", prompt: "Notify operations when a delivery truck arrives at the loading dock." },
  ];

  return (
    <div className="visionChatShell">
      <aside className="visionSidebar">
        <button className="visionBrand" onClick={startNewConversation} type="button"><strong>artae<span>.</span></strong><small>VISION</small></button>
        <button className="visionNewChat" onClick={startNewConversation} type="button"><Icon name="plus" /> New conversation</button>
        <nav aria-label="Vision workspace">
          {navigation.map((item) => <button className={view === item.id ? "isActive" : ""} key={item.id} onClick={() => item.id === "conversation" ? startNewConversation() : setView(item.id)} type="button"><Icon name={item.icon} /> {item.label}{item.id === "alerts" && currentAlerts.length > 0 && <i>{currentAlerts.length}</i>}</button>)}
        </nav>
        <section className="visionConversationList">
          <header><span>CONVERSATIONS</span><button aria-label="New conversation" onClick={startNewConversation} type="button"><Icon name="plus" /></button></header>
          {rules.length > 0 ? rules.map((rule) => (
            <button className={activeRule?.id === rule.id ? "isCurrent" : ""} key={rule.id} onClick={() => openAgent(rule)} type="button">
              <span><strong>{ruleTitle(rule)}</strong><small>{rule.original_prompt ?? rule.name}</small></span>
            </button>
          )) : sessionStarted ? (
            <button className="isCurrent" onClick={() => setView("conversation")} type="button"><span><strong>{ruleTitle(activeRule)}</strong><small>{submittedPrompt || prompt}</small></span></button>
          ) : <p>Your saved monitoring conversations will appear here.</p>}
        </section>
        <div className="visionAccount">
          <span><strong>{identity?.display_name ?? identity?.email ?? "Local preview"}</strong><small>{identity ? `${identity.role} workspace` : "Development session"}</small></span>
          <button onClick={() => void onSignOut()} type="button">Sign out</button>
        </div>
        <div className="visionSidebarStatus"><i className={operating ? "isOnline" : ""} /><span><strong>{operating ? "AI is watching" : running ? "Starting camera AI" : nativeDeployment ? "Ready to start" : "Preview only"}</strong><small>{operating ? `${agent?.frame_width ?? "—"}×${agent?.frame_height ?? "—"} · ${agent?.recording_state === "recording" ? "video saving" : "video live"}` : running ? "Loading the local vision service" : nativeDeployment ? "Choose an agent and press start" : "Install the camera service for AI detection"}</small></span></div>
      </aside>

      <main className="visionMain">
        {view === "conversation" && (!sessionStarted ? (
          <section className="visionWelcome">
            <h1>What should we watch for?</h1>
            <p>Describe the moment you care about. Artae will turn it into a monitoring conversation.</p>
            <div className="visionSetupProgress" aria-label="Agent setup progress">
              <span className={selectedCamera ? "isDone" : "isCurrent"}><i>{selectedCamera ? "✓" : "1"}</i><b>Connect video</b></span>
              <span className={selectedCamera ? "isCurrent" : ""}><i>2</i><b>Describe the job</b></span>
              <span><i>3</i><b>Start the agent</b></span>
            </div>
            {!selectedCamera ? (
              <section className="visionFirstCameraSetup">
                <span><Icon name="camera" /></span>
                <div><small>STEP 1 OF 3</small><h2>{cameras.length > 0 ? "Choose the camera to use." : "Connect your first camera."}</h2><p>{cameras.length > 0 ? "Select an existing camera, then describe what it should watch for." : "Start with this computer's webcam. You can connect IP cameras later."}</p></div>
                <button disabled={busy} onClick={() => cameras.length > 0 ? setView("settings") : void onAddWebcam()} type="button">{cameras.length > 0 ? "Choose camera" : busy ? "Connecting…" : "Use my webcam"}<Icon name="chevron" /></button>
              </section>
            ) : <>
              <div className="visionConnectedSource"><span><i />{selectedCamera.name}</span><button onClick={() => setView("settings")} type="button">Change</button></div>
              <div className="visionPromptCard">
                <textarea id="monitoring-prompt" onChange={(event) => setPrompt(event.target.value)} placeholder="Ask Artae to watch for something…" rows={4} value={prompt} />
                {sourceMode === "upload" && <label className="visionUploadPicker"><Icon name="camera" /><span><strong>{uploadedVideo?.name ?? "Choose a video"}</strong><small>MP4, MOV, MKV, WEBM, or AVI · up to 512 MB</small></span><input accept="video/mp4,video/quicktime,video/webm,video/x-matroska,video/x-msvideo,.mkv,.avi" onChange={(event) => chooseUploadedVideo(event.target.files?.[0] ?? null)} type="file" /></label>}
                <div className="visionAgentBuilderRows">
                  <div><span>IF</span><p>{prompt.trim() || "Describe the event this agent should watch for"}</p></div>
                  <div><span>THEN</span><p>{actionLabel(selectedActionConnector, recipient)}</p></div>
                </div>
                <div className="visionActionPicker"><small>ACTION</small><div role="group" aria-label="Choose what the agent should do"><button className={actionDestination === "computer" ? "isActive" : ""} onClick={() => setActionDestination("computer")} type="button">In-app alert</button>{connectors.filter((connector) => connector.enabled && connector.connector_type !== "mock").map((connector) => <button className={actionDestination === connector.id ? "isActive" : ""} key={connector.id} onClick={() => setActionDestination(connector.id)} type="button">{connector.connector_type === "telegram" ? "Telegram" : connector.name}</button>)}{!telegramConnector && <button onClick={() => setTelegramSetupOpen(true)} type="button">+ Connect Telegram</button>}</div></div>
                <div className="visionPromptActions">
                  <div aria-label="Choose what to monitor" className="visionSourceChoice" role="group"><button className={sourceMode === "live" ? "isActive" : ""} onClick={() => setSourceMode("live")} type="button"><Icon name="camera" /> Live camera</button><button className={sourceMode === "upload" ? "isActive" : ""} onClick={() => setSourceMode("upload")} type="button"><Icon name="plus" /> Upload video</button></div>
                  <button className="visionStartButton" disabled={working || loading || !selectedCamera || prompt.trim().length < 8 || (sourceMode === "upload" && !uploadedVideo)} onClick={() => void startMonitoring()} type="button">{working ? "Building agent…" : "Build & deploy agent"}<Icon name="chevron" /></button>
                </div>
              </div>
              <div className="visionStarterPrompts" aria-label="Example monitoring requests">
                {starterPrompts.map((item) => <button key={item.label} onClick={() => { setPrompt(item.prompt); setRecipient(item.recipient); }} type="button"><small>{item.label}</small><span>{item.prompt}</span><em>{item.route}</em></button>)}
              </div>
            </>}
            <small className="visionPrivacy"><Icon name="shield" /> Video is processed on this computer whenever possible.</small>
          </section>
        ) : (
          <section className="visionConversation">
            <header><div><small>VIDEO AGENT</small><h1>{ruleTitle(activeRule)}</h1></div>{activeRule ? <button className={activeRuleRequested ? "isRunning" : ""} disabled={working || sourceMode === "upload"} onClick={() => void toggleRuleAgent(activeRule)} type="button"><i />{activeRuleRequested ? "Stop agent" : "Start agent"}</button> : <button disabled type="button"><i />Building agent</button>}</header>
            <div className="visionThread">
              <article className="visionAssistantMessage"><div><strong>What should we watch for?</strong><p>Describe the condition and the action you want me to take.</p></div></article>
              <article className="visionUserMessage"><p>{submittedPrompt}</p></article>
              <article className="visionAssistantMessage"><div>
                <strong>{working ? "Updating your monitoring agent…" : compilation?.status === "needs_clarification" ? "One quick question" : operating || uploadEvaluation ? "Your monitoring agent is running" : running ? agent?.observed_status === "error" ? "Camera AI could not start" : "Starting camera AI…" : "Your monitoring rule is ready"}</strong>
                {compilation?.status === "needs_clarification" ? <div className="visionClarification"><p>{compilation.clarification_question?.includes("named zones or lines") ? "Which part of the camera should I watch?" : compilation.clarification_question}</p>{compilation.clarification_question?.includes("named zones or lines") && <button className="visionEntireViewChoice" disabled={working} onClick={() => void chooseEntireCameraView()} type="button">Use the entire camera view</button>}<form onSubmit={(event) => { event.preventDefault(); void answerClarification(); }}><input aria-label="Rule clarification" onChange={(event) => setClarification(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && clarification.trim()) { event.preventDefault(); void answerClarification(); } }} placeholder="Or type the name of a saved camera area" value={clarification} /><button disabled={working || !clarification.trim()} type="submit">{working ? "Applying…" : "Continue"}</button></form></div> : <div className="visionBuildSteps" aria-label="Monitoring setup progress"><span className="isDone"><i>1</i><b>Rule described</b></span><span className={activeRule ? "isDone" : ""}><i>2</i><b>Agent built</b></span><span className={activeRule ? "isDone" : ""}><i>3</i><b>Action ready</b></span><span className={operating || uploadEvaluation ? "isDone" : ""}><i>4</i><b>{running && !operating ? "Starting AI" : running ? "Running" : "Stopped"}</b></span></div>}
                {activeRule && <div className="visionDeployedAgent"><header><span><i className={activeRuleLive ? "isOnline" : ""} />{activeRuleLive ? "AI WATCHING" : activeRuleRequested ? "AI STARTING" : activeRule.status === "active" ? "READY" : activeRule.status.toUpperCase()}</span><small>{selectedCamera?.name}</small></header><div><b>WATCH FOR</b><p>{activeRule.original_prompt ?? activeRule.name}</p></div><div><b>WHEN SEEN</b><p>{bindingActionLabel(activeBinding)}</p></div><footer><span>{activeRule.execution_plan?.strategy === "specialized_pose" ? "YOLO pose · checks every frame" : `${Math.round(activeRule.minimum_confidence * 100)}% minimum confidence`}</span><button disabled={!activeBinding || working} onClick={() => void runSafeTest()} type="button">Send test alert</button></footer></div>}
                {conversationMessage && <p className="visionStatusMessage" role="status">{conversationMessage}</p>}
              </div></article>
              {(running || uploadEvaluation || uploadedVideoUrl) && sourceMode === "upload" && <section className="visionRealPreview"><header><span><i className={uploadEvaluation?.status === "running" ? "isOnline" : ""} /><strong>{uploadedVideo?.name}</strong></span><em>{uploadEvaluation?.status?.replaceAll("_", " ") ?? "ready"}</em></header><div className="visionVideoStage">{uploadedVideoUrl && <video controls preload="metadata" src={uploadedVideoUrl} />}</div></section>}
              {running && sourceMode === "live" && selectedCamera && <MonitoringFeed agent={agent} alerts={currentAlerts} analysisLabel={activeRule?.execution_plan?.strategy === "specialized_pose" ? "YOLO pose" : activeRule?.execution_plan?.strategy === "semantic_window" ? "Visual AI" : "YOLO tracking"} busy={busy || working} camera={selectedCamera} detections={detections} events={currentEvents} nativePreviewEnabled={nativePreviewEnabled} onPreviewAvailabilityChange={setPreviewReady} onStop={stopCameraAndRecording} operating={operating} previewReady={previewReady} recordings={recordings} stream={stream} />}
            </div>
          </section>
        ))}

        {view === "agents" && <section className="visionSimplePage visionAgentsPage"><header><div><small>VIDEO AGENTS</small><h1>Your cameras have jobs.</h1><p>Each agent watches one condition and performs one connected action.</p></div><button onClick={startNewConversation} type="button"><Icon name="plus" /> Build agent</button></header>{message && <p className="visionAgentsMessage" role="status">{message}</p>}{rules.length === 0 ? <div className="visionEmptyState"><Icon name="rule" /><strong>No agents yet</strong><p>Build your first agent by describing what a camera should watch for and what it should do.</p><button onClick={startNewConversation} type="button">Build first agent</button></div> : <div className="visionAgentGrid">{rules.map((rule) => { const ruleBindings = agentBindings[rule.id] ?? []; const binding = ruleBindings.find((item) => item.enabled) ?? null; const ruleEvents = events.filter((event) => event.rule_id === rule.id); const isLive = rule.status === "active" && operating; const isRequested = rule.status === "active" && running; return <article key={rule.id}><header><span><i className={isLive ? "isOnline" : ""} />{isLive ? "AI WATCHING" : isRequested ? "STARTING" : rule.status === "active" ? "READY" : rule.status.toUpperCase()}</span><small>{selectedCamera?.name}</small></header><div className="visionAgentStatement"><span>IF</span><p>{rule.original_prompt ?? rule.name}</p></div><div className="visionAgentStatement"><span>THEN</span><p>{bindingActionLabel(binding)}</p></div><dl><div><dt>Events</dt><dd>{ruleEvents.length}</dd></div><div><dt>Confidence</dt><dd>{Math.round(rule.minimum_confidence * 100)}%</dd></div><div><dt>Model route</dt><dd>{rule.execution_plan?.strategy === "specialized_pose" ? "YOLO pose" : rule.execution_plan?.strategy === "semantic_window" ? "Visual AI" : "YOLO tracking"}</dd></div></dl><footer><button onClick={() => openAgent(rule)} type="button">Open</button><button disabled={working} onClick={() => void testAgentAction(rule)} type="button">Send test alert</button><button className={isRequested ? "isPause" : ""} disabled={working} onClick={() => void toggleRuleAgent(rule)} type="button">{isRequested ? "Stop" : "Start"}</button></footer></article>; })}</div>}</section>}

        {view === "footage" && <section className="visionSimplePage visionFootagePage"><header><div><small>SAVED FOOTAGE · TWO-HOUR ROLLING HISTORY</small><h1>Your video history.</h1><p>The newest two hours from {selectedCamera?.name ?? "your selected camera"} are private, saved to this account, and available on every device.</p></div><button disabled={working || !selectedCamera} onClick={() => void onRefreshRecordings()} type="button">Refresh</button></header>{message && <p className="visionAgentsMessage" role="status">{message}</p>}{!selectedCamera ? <div className="visionEmptyState"><Icon name="camera" /><strong>Connect a camera first</strong><p>Once a camera is connected, its retained footage will appear here.</p></div> : visibleRecordings.length === 0 ? <div className="visionEmptyState"><Icon name="camera" /><strong>No saved footage yet</strong><p>Deploy a live agent and keep recording enabled. New archived clips will appear here automatically.</p></div> : <div className="visionFootageGrid">{visibleRecordings.map((recording) => <article className="visionFootageCard" key={recording.id}>{recording.content_url ? <video controls preload="metadata" src={`${API_URL}${recording.content_url}`} /> : <div className="visionFootageUnavailable"><Icon name="camera" /><span>{recording.status === "local_only" ? "Uploading from this computer" : recording.status.replaceAll("_", " ")}</span></div>}<div><strong>{new Date(recording.started_at).toLocaleString()}</strong><span>{Math.round(recording.duration_seconds)} sec · {recording.width}×{recording.height}</span><small>Rolling history · oldest footage deletes automatically</small></div></article>)}</div>}</section>}

        {view === "investigate" && <section className="visionSimplePage"><header><small>INVESTIGATE</small><h1>Review real detections</h1><p>Only events created in this monitoring conversation appear here.</p></header>
          {currentCases.length > 0 && <div className="visionReviewQueue"><header><Icon name="spark" /><span><strong>{currentCases.length} detection{currentCases.length === 1 ? " needs" : "s need"} your review</strong><small>Confirming a match releases its configured alert.</small></span></header>{currentCases.map((item) => <article key={item.id}><div><strong>{item.proposal_summary}</strong><p>{item.camera_name} · {Math.round(item.proposer_confidence * 100)}% confidence · {formatTime(item.event.occurred_at)}</p></div><footer><button disabled={reviewingCaseId === item.id || busy} onClick={() => void reviewDetection(item.id, "rejected")} type="button">Not a match</button><button disabled={reviewingCaseId === item.id || busy} onClick={() => void reviewDetection(item.id, "confirmed")} type="button">Yes, this happened</button></footer></article>)}</div>}
          {currentEvents.length === 0 && currentCases.length === 0 ? <div className="visionEmptyState"><Icon name="search" /><strong>No evidence to investigate yet</strong><p>Start monitoring or analyze a video. Real matches will appear here automatically.</p></div> : currentEvents.length > 0 && <div className="visionRecordList">{currentEvents.map((event) => <article key={event.id}><Icon name="camera" /><div><strong>{event.details.test === true ? "Safe test incident" : event.details.uploaded_video === true ? "Uploaded video match" : "Camera condition matched"}</strong><p>{event.zone_name} · {Math.round(event.confidence * 100)}% confidence</p></div><time>{formatTime(event.occurred_at)}</time></article>)}</div>}
        </section>}

        {view === "alerts" && <section className="visionSimplePage"><header><small>ALERTS</small><h1>Alert activity</h1><p>See confirmed incidents and the real delivery status for this conversation.</p></header>{currentAlerts.length === 0 && currentExecutions.length === 0 ? <div className="visionEmptyState"><Icon name="event" /><strong>No alerts yet</strong><p>When this rule is confirmed, its incident and message status will appear here.</p></div> : <div className="visionRecordList">{currentExecutions.map((execution) => <article key={execution.id}><Icon name="event" /><div><strong>Message {execution.status.replaceAll("_", " ")}</strong><p>{execution.connector_name} · attempt {execution.attempt_count}</p></div><time>{formatTime(execution.next_attempt_at)}</time></article>)}</div>}</section>}

        {view === "settings" && <section className="visionSimplePage visionSettingsPage"><header><small>SETTINGS</small><h1>Monitoring settings</h1><p>Choose the real camera and where confirmed alerts should go.</p></header><div className="visionSettingsCard">
          <label><span>Camera</span><select value={selectedCamera?.id ?? ""} onChange={(event) => onSelectCamera(event.target.value)}>{cameras.map((camera) => <option key={camera.id} value={camera.id}>{camera.name}</option>)}</select></label>
          <label><span>Alert recipient</span><select value={recipient} onChange={(event) => setRecipient(event.target.value)}><option>Caregiver</option><option>Safety manager</option><option>Site manager</option><option>Operations lead</option></select></label>
          <label><span>Default agent action</span><select value={actionDestination} onChange={(event) => setActionDestination(event.target.value)}><option value="computer">Create an in-app alert</option>{connectors.filter((connector) => connector.enabled && connector.connector_type !== "mock").map((connector) => <option key={connector.id} value={connector.id}>{connector.connector_type === "telegram" ? "Send Telegram message" : connector.name}</option>)}</select></label>
          <div className="visionSettingAction"><span><strong>Telegram</strong><small>{telegramConnector ? `${telegramConnector.name} is connected` : "Send confirmed alerts to a Telegram chat"}</small></span><button onClick={() => setTelegramSetupOpen(true)} type="button">{telegramConnector ? "View connection" : "Connect"}</button></div>
          <div className="visionSettingAction"><span><strong>Safe test</strong><small>Verify delivery without creating fake camera evidence</small></span><button disabled={!activeRule || working} onClick={() => void runSafeTest()} type="button">Run test</button></div>
          <div className="visionSettingAction visionTechnicalTools"><span><strong>Technical tools</strong><small>Camera diagnostics and system administration</small></span><button onClick={() => onOpenAdvanced("hub")} type="button">Open</button></div>
        </div>{message && <p className="visionSettingsMessage" role="status">{message}</p>}</section>}
      </main>

      {telegramSetupOpen && <div className="automationModalBackdrop" role="presentation"><section aria-labelledby="telegram-setup-title" aria-modal="true" className="automationTelegramModal" role="dialog">
        <header><span><Icon name="activity" /></span><div><small>PHONE ALERTS</small><h2 id="telegram-setup-title">Connect Telegram</h2></div><button aria-label="Close Telegram setup" disabled={working} onClick={() => setTelegramSetupOpen(false)} type="button">×</button></header>
        {telegramConnector ? <div className="automationTelegramConnected"><Icon name="shield" /><div><strong>Telegram is connected</strong><p>{telegramConnector.name} is ready to receive confirmed alerts.</p></div><button onClick={() => setTelegramSetupOpen(false)} type="button">Done</button></div> : <>
          <ol className="automationTelegramSteps"><li><span>1</span><div><strong>Message your bot</strong><p>Open Telegram and send <code>/start</code> to the bot once.</p></div></li><li><span>2</span><div><strong>Paste the BotFather token here</strong><p>It is encrypted when saved and is not displayed again.</p></div></li></ol>
          <label className="automationTelegramField"><span>Bot token</span><input autoComplete="off" onChange={(event) => setTelegramToken(event.target.value)} placeholder="Paste the token from BotFather" type="password" value={telegramToken} /></label>
          <button className="automationTelegramFind" disabled={working || telegramToken.trim().length < 8} onClick={() => void discoverTelegramChats()} type="button">{working ? "Checking…" : "Find my Telegram chat"}</button>
          {telegramChats.length > 0 && <label className="automationTelegramField"><span>Send alerts to</span><select onChange={(event) => setTelegramChatId(event.target.value)} value={telegramChatId}><option value="">Choose a chat</option>{telegramChats.map((chat) => <option key={chat.chat_id} value={chat.chat_id}>{chat.title} · {chat.chat_type}</option>)}</select></label>}
          {telegramSetupMessage && <p className="automationTelegramMessage" role="status">{telegramSetupMessage}</p>}
          <footer><button disabled={working} onClick={() => setTelegramSetupOpen(false)} type="button">Cancel</button><button disabled={working || !telegramChatId.trim()} onClick={() => void connectTelegram()} type="button">Connect Telegram</button></footer>
        </>}
      </section></div>}
    </div>
  );
}
