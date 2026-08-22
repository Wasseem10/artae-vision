"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Icon } from "@/components/icon";
import { StatusPill } from "@/components/status-pill";
import { api } from "@/lib/api";
import type {
  ActionExecution,
  AlertIncident,
  Camera,
  CameraAgent,
  ConnectorType,
  ContextSource,
  CorrelationEvaluation,
  IntegrationConnector,
  InvestigationResult,
  ReplaySuite,
  Rule,
  RuleCompilation,
  RuleActionBinding,
  RuleCorrelationPolicy,
  SceneChange,
  SceneMemoryItem,
  Site,
  SiteMap,
  VisualAgentPlan,
  VisualAgentSimulation,
} from "@/lib/types";

interface GuidedAgentWorkspaceProps {
  cameras: Camera[];
  selectedCamera: Camera | null;
  agent: CameraAgent | null;
  alerts: AlertIncident[];
  busy: boolean;
  onSelectCamera: (cameraId: string) => void;
  onCompile: (input: { camera_id: string; prompt: string }) => Promise<RuleCompilation>;
  onClarify: (compilationId: string, answer: string) => Promise<RuleCompilation>;
  onRuleCreated: (rule: Rule) => void;
  onStart: () => void;
  onStop: () => void;
  onOpenAdvanced: () => void;
  onError: (message: string) => void;
}

const examples = [
  "Alert me when a person enters without a hard hat.",
  "Notify me if someone tailgates through the entrance.",
  "Tell me when a product falls off the production line.",
];

export function GuidedAgentWorkspace({
  cameras,
  selectedCamera,
  agent,
  alerts,
  busy,
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
    ? alerts.filter((alert) => alert.event.camera_id === selectedCamera.id).slice(0, 3)
    : [];
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
      const plan = await api.createAgentPlan(rule.id);
      setPlans((current) => [plan, ...current]);
      setCompilation(null);
      setPrompt("");
      setSimulation(null);
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
    if (!currentPlan || !connectorName.trim() || !connectorUrl.trim() || !connectorCredential.trim()) return;
    setWorking(true);
    try {
      const definition = {
        messaging_webhook: { scope: "notifications:write", action: "send_notification" as const },
        ticket_webhook: { scope: "tickets:write", action: "create_ticket" as const },
        generic_webhook: { scope: "webhooks:invoke", action: "invoke_webhook" as const },
      }[connectorType];
      const connector = await api.createConnector({
        name: connectorName.trim(),
        connector_type: connectorType,
        endpoint_url: connectorUrl.trim(),
        credential: connectorCredential.trim(),
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
      await refreshActions();
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not connect the external tool.");
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
        <h2>Connect your first camera</h2>
        <p>Add a webcam, video file, or RTSP camera before giving it a job.</p>
        <button className="buttonPrimary" onClick={onOpenAdvanced} type="button">Add a camera</button>
      </section>
    );
  }

  return (
    <div className="guidedWorkspace">
      <section className="guidedHero">
        <div className="guidedHeroTop">
          <div>
            <span className="eyebrow">Camera automation</span>
            <h1>What should this camera watch for?</h1>
            <p>Describe the event in plain English. You will review and test the plan before anything goes live.</p>
          </div>
          <label className="cameraPicker">
            <span>Camera</span>
            <select value={selectedCamera.id} onChange={(event) => onSelectCamera(event.target.value)}>
              {cameras.map((camera) => <option key={camera.id} value={camera.id}>{camera.name}</option>)}
            </select>
            <StatusPill status={selectedCamera.status} />
          </label>
        </div>

        <div className="instructionComposer">
          <textarea
            aria-label="Camera instruction"
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Example: Alert me when a person enters without a hard hat."
            rows={3}
            value={prompt}
          />
          <div className="composerFooter">
            <span>{prompt.length}/2000</span>
            <button className="buttonPrimary" disabled={busy || working || prompt.trim().length < 5} onClick={() => void compile()} type="button">
              Build the plan
            </button>
          </div>
        </div>
        <div className="exampleRow">
          <span>Try an example:</span>
          {examples.map((example) => <button key={example} onClick={() => setPrompt(example)} type="button">{example}</button>)}
        </div>
      </section>

      {compilation && (
        <section className="reviewCard">
          <div className="reviewHeader">
            <span className="stepNumber">1</span>
            <div><small>Review</small><h2>{compilation.status === "needs_clarification" ? "One detail is missing" : "Here is how the camera will do it"}</h2></div>
          </div>
          {compilation.status === "needs_clarification" ? (
            <div className="clarificationBox">
              <p>{compilation.clarification_question}</p>
              <div><input value={clarification} onChange={(event) => setClarification(event.target.value)} placeholder="Type your answer" /><button className="buttonPrimary" disabled={!clarification.trim() || working} onClick={() => void answerClarification()} type="button">Continue</button></div>
            </div>
          ) : (
            <>
              <p className="planExplanation">{compilation.explanation}</p>
              <div className="miniPlan">
                {compilation.execution_plan?.stages.map((stage, index) => (
                  <article key={stage.id}><span>{index + 1}</span><div><strong>{stage.label}</strong><p>{stage.purpose}</p></div></article>
                ))}
              </div>
              <button className="buttonPrimary" disabled={working} onClick={() => void createPlan()} type="button">Save this plan</button>
            </>
          )}
        </section>
      )}

      {currentPlan ? (
        <section className="planBoard">
          <div className="planBoardHeader">
            <div><span className="eyebrow">Current plan · version {currentPlan.revision}</span><h2>{currentPlan.prompt}</h2><p>{currentPlan.plan.summary}</p></div>
            <span className={`deploymentBadge deployment-${currentPlan.status}`}>{currentPlan.status}</span>
          </div>
          <div className="planFlow">
            {currentPlan.plan.nodes.map((node, index) => (
              <article className={node.side_effect ? "planNode actionNode" : "planNode"} key={node.id}>
                <span>{index + 1}</span><small>{node.kind}</small><strong>{node.title}</strong><p>{node.description}</p>
              </article>
            ))}
          </div>
          {currentPlan.unsupported_capabilities.length > 0 && (
            <div className="capabilityWarning"><Icon name="shield" /><div><strong>This plan needs a connection before it can go live</strong><p>{currentPlan.unsupported_capabilities.join(", ")}</p></div></div>
          )}
          <div className="releaseSteps">
            <article className="releaseStep"><span className={simulation ? "done" : ""}>{simulation ? "✓" : "1"}</span><div><strong>Safe simulation</strong><p>Checks every step without sending alerts or operating another system.</p></div><button className="buttonSecondary" disabled={working} onClick={() => void simulate()} type="button">{simulation ? "Run again" : "Run simulation"}</button></article>
            <article className="releaseStep"><span className={passedRun ? "done" : ""}>{passedRun ? "✓" : "2"}</span><div><strong>Replay safety test</strong><p>{passedRun ? `Passed: ${passedRun.metrics.macro_f1 ?? 0} F1 score` : "No passed regression test yet. Open Advanced tools to create one."}</p></div>{!passedRun && <button className="buttonSecondary" onClick={onOpenAdvanced} type="button">Open tests</button>}</article>
            <article className="releaseStep"><span className={deployed ? "done" : ""}>{deployed ? "✓" : "3"}</span><div><strong>Deploy</strong><p>{deployed ? "This version is approved and its rule is active." : "Makes the tested version the active camera job."}</p></div>{!deployed && <button className="buttonPrimary" disabled={working || !simulation || !passedRun || currentPlan.unsupported_capabilities.length > 0} onClick={() => void deploy()} type="button">Deploy plan</button>}</article>
          </div>
          {simulation && <p className="simulationSummary"><Icon name="shield" /> {simulation.summary}</p>}
        </section>
      ) : (
        <section className="firstPlanHint"><span>1</span><div><strong>Describe a job above</strong><p>Your readable plan, safe simulation, test gate, and deploy control will appear here.</p></div></section>
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
        {sceneChanges.length > 0 && <p className="sceneChangeSummary"><Icon name="event" /> {sceneChanges.length} recorded scene {sceneChanges.length === 1 ? "change" : "changes"}; latest state: {sceneChanges[0].new_state}.</p>}
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
        {running ? <button className="buttonSecondary" disabled={busy} onClick={onStop} type="button">Stop analysis</button> : <button className="buttonPrimary" disabled={busy || !deployed} onClick={onStart} type="button">Start analysis</button>}
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
                <label><span>Tool type</span><select value={connectorType} onChange={(event) => setConnectorType(event.target.value as Exclude<ConnectorType, "mock">)}><option value="messaging_webhook">Messaging webhook</option><option value="ticket_webhook">Ticket webhook</option><option value="generic_webhook">Generic webhook</option></select></label>
                <label><span>Name</span><input value={connectorName} onChange={(event) => setConnectorName(event.target.value)} placeholder="Operations Slack" /></label>
                <label className="connectorWide"><span>HTTPS endpoint</span><input value={connectorUrl} onChange={(event) => setConnectorUrl(event.target.value)} placeholder="https://…" /></label>
                <label className="connectorWide"><span>Signing credential</span><input type="password" value={connectorCredential} onChange={(event) => setConnectorCredential(event.target.value)} placeholder="Stored encrypted; never shown again" /></label>
                <button className="buttonPrimary" disabled={working || !connectorName.trim() || !connectorUrl.trim() || connectorCredential.trim().length < 8} onClick={() => void connectRealTool()} type="button">Connect and attach</button>
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
        <div className="simpleSectionHeader"><div><span className="eyebrow">Results</span><h2>Latest alerts</h2></div><button className="buttonGhost" onClick={onOpenAdvanced} type="button">View all activity</button></div>
        {cameraAlerts.length ? cameraAlerts.map((alert) => <article key={alert.id}><span className="alertMarker"><Icon name="event" /></span><div><strong>{alert.event.object_class} · {alert.event.event_type.replaceAll("_", " ")}</strong><p>{alert.event.zone_name} · {Math.round(alert.event.confidence * 100)}% confidence</p></div><time>{new Date(alert.created_at).toLocaleString()}</time></article>) : <p className="emptyCopy">No alerts yet. Confirmed events will appear here with their evidence.</p>}
      </section>
    </div>
  );
}
