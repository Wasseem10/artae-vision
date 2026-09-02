"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { Icon } from "@/components/icon";
import { api } from "@/lib/api";
import { parseIntervalList } from "@/lib/evaluation";
import type {
  CalibrationReadiness,
  CalibrationScenario,
  Camera,
  ReplayEvaluation,
  ReplayScenarioVariant,
  ReplaySourceKind,
  ReplaySuite,
  ReplaySuiteRun,
} from "@/lib/types";

interface ReplayEvaluationPanelProps {
  cameras: Camera[];
  onError: (message: string) => void;
}

function percentage(value: number | undefined): string {
  return value === undefined ? "—" : `${Math.round(value * 100)}%`;
}

function gateValue(value: number | boolean): string {
  if (typeof value === "boolean") return value ? "yes" : "no";
  return Number.isInteger(value) ? String(value) : value.toFixed(4);
}

export function ReplayEvaluationPanel({ cameras, onError }: ReplayEvaluationPanelProps) {
  const [evaluations, setEvaluations] = useState<ReplayEvaluation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [name, setName] = useState("Baseline replay");
  const [cameraId, setCameraId] = useState("");
  const [sourceUri, setSourceUri] = useState("");
  const [replayFile, setReplayFile] = useState<File | null>(null);
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState("60");
  const [expectedText, setExpectedText] = useState("");
  const [scenarioKey, setScenarioKey] = useState("");
  const [scenarioVariant, setScenarioVariant] = useState<ReplayScenarioVariant>("positive");
  const [sourceKind, setSourceKind] = useState<ReplaySourceKind>("controlled");
  const [environmentTags, setEnvironmentTags] = useState("normal_light");
  const [predictedText, setPredictedText] = useState("");
  const [providerRequests, setProviderRequests] = useState("0");
  const [inputTokens, setInputTokens] = useState("0");
  const [outputTokens, setOutputTokens] = useState("0");
  const [inputPrice, setInputPrice] = useState("0");
  const [outputPrice, setOutputPrice] = useState("0");
  const [busy, setBusy] = useState(false);
  const [suites, setSuites] = useState<ReplaySuite[]>([]);
  const [selectedSuiteId, setSelectedSuiteId] = useState<string | null>(null);
  const [suiteHistory, setSuiteHistory] = useState<ReplaySuiteRun[]>([]);
  const [suiteName, setSuiteName] = useState("Core regression gate");
  const [suiteEvaluationIds, setSuiteEvaluationIds] = useState<string[]>([]);
  const [minimumF1, setMinimumF1] = useState("0.8");
  const [minimumRecall, setMinimumRecall] = useState("0.8");
  const [maximumFalsePositives, setMaximumFalsePositives] = useState("0");
  const [maximumCost, setMaximumCost] = useState("1");
  const [requirePricing, setRequirePricing] = useState(true);
  const [suiteBusy, setSuiteBusy] = useState(false);
  const [calibrationScenarios, setCalibrationScenarios] = useState<CalibrationScenario[]>([]);
  const [calibrationReadiness, setCalibrationReadiness] = useState<CalibrationReadiness | null>(null);

  const refreshCalibration = useCallback(async () => {
    try {
      const [scenarios, readiness] = await Promise.all([
        api.listCalibrationScenarios(),
        api.getCalibrationReadiness(),
      ]);
      setCalibrationScenarios(scenarios);
      setCalibrationReadiness(readiness);
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not load calibration readiness.");
    }
  }, [onError]);

  useEffect(() => {
    void Promise.all([
      api.listCalibrationScenarios(),
      api.getCalibrationReadiness(),
    ]).then(([scenarios, readiness]) => {
      setCalibrationScenarios(scenarios);
      setCalibrationReadiness(readiness);
    }).catch((failure: unknown) => {
      onError(failure instanceof Error ? failure.message : "Could not load calibration readiness.");
    });
  }, [onError]);

  useEffect(() => {
    void api
      .listReplayEvaluations()
      .then((items) => {
        setEvaluations(items);
        setSelectedId((current) => current ?? items[0]?.id ?? null);
        setSuiteEvaluationIds((current) => current.length > 0 ? current : items.map((item) => item.id));
      })
      .catch((failure: unknown) => {
        onError(failure instanceof Error ? failure.message : "Could not load replay evaluations.");
      });
  }, [onError]);

  useEffect(() => {
    void api
      .listReplaySuites()
      .then((items) => {
        setSuites(items);
        setSelectedSuiteId((current) => current ?? items[0]?.id ?? null);
      })
      .catch((failure: unknown) => {
        onError(failure instanceof Error ? failure.message : "Could not load regression suites.");
      });
  }, [onError]);

  const resolvedCameraId = cameraId || cameras[0]?.id || "";
  const selected = useMemo(
    () => evaluations.find((evaluation) => evaluation.id === selectedId) ?? null,
    [evaluations, selectedId],
  );
  const selectedSuite = useMemo(
    () => suites.find((suite) => suite.id === selectedSuiteId) ?? null,
    [selectedSuiteId, suites],
  );
  const selectedScenario = useMemo(
    () => calibrationScenarios.find((scenario) => scenario.key === scenarioKey) ?? null,
    [calibrationScenarios, scenarioKey],
  );

  useEffect(() => {
    if (!selectedSuiteId) return;
    void api
      .listReplaySuiteRuns(selectedSuiteId)
      .then(setSuiteHistory)
      .catch((failure: unknown) => {
        onError(failure instanceof Error ? failure.message : "Could not load suite history.");
      });
  }, [onError, selectedSuiteId]);

  useEffect(() => {
    const latest = selectedSuite?.latest_run;
    if (!selectedSuite || !latest || !["queued", "running"].includes(latest.status)) return;
    const timer = window.setInterval(() => {
      void api.getReplaySuite(selectedSuite.id).then((updated) => {
        setSuites((current) => current.map((suite) => suite.id === updated.id ? updated : suite));
        if (updated.latest_run) {
          setSuiteHistory((current) => [
            updated.latest_run!,
            ...current.filter((run) => run.id !== updated.latest_run?.id),
          ]);
        }
      }).catch((failure: unknown) => {
        onError(failure instanceof Error ? failure.message : "Could not refresh suite status.");
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [onError, selectedSuite]);

  useEffect(() => {
    if (!selected || !["queued", "running"].includes(selected.status)) return;
    const timer = window.setInterval(() => {
      void api
        .getReplayEvaluation(selected.id)
        .then((updated) => {
          setEvaluations((current) =>
            current.map((evaluation) =>
              evaluation.id === updated.id ? updated : evaluation,
            ),
          );
          if (["scored", "failed"].includes(updated.status)) void refreshCalibration();
        })
        .catch((failure: unknown) => {
          onError(failure instanceof Error ? failure.message : "Could not refresh replay status.");
        });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [onError, refreshCalibration, selected]);

  function chooseScenario(key: string) {
    setScenarioKey(key);
    const scenario = calibrationScenarios.find((item) => item.key === key);
    if (!scenario) return;
    setPrompt(scenario.prompt);
    setName(`${scenario.title} calibration`);
    setExpectedText("");
    setScenarioVariant("positive");
    setEnvironmentTags(scenario.recommended_environment_tags[0] ?? "normal_light");
  }

  async function createEvaluation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      const expected = parseIntervalList(expectedText);
      const uploaded = replayFile ? await api.uploadReplayVideo(replayFile) : null;
      const replaySource = uploaded?.source_uri ?? sourceUri.trim();
      if (!replaySource) throw new Error("Choose a replay video or enter a video path.");
      const created = await api.createReplayEvaluation({
        name: name.trim(),
        camera_id: resolvedCameraId,
        source_uri: replaySource,
        prompt: prompt.trim(),
        duration_seconds: Number(duration),
        expected_intervals: expected,
        scenario_key: scenarioKey || null,
        scenario_variant: scenarioKey ? scenarioVariant : "unclassified",
        source_kind: scenarioKey ? sourceKind : "unclassified",
        environment_tags: scenarioKey
          ? environmentTags.split(",").map((tag) => tag.trim()).filter(Boolean)
          : [],
      });
      setEvaluations((current) => [created, ...current]);
      setSuiteEvaluationIds((current) => [created.id, ...current]);
      setSelectedId(created.id);
      setPredictedText("");
      setReplayFile(null);
      await refreshCalibration();
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not create the evaluation.");
    } finally {
      setBusy(false);
    }
  }

  function selectReplayFile(file: File | null) {
    setReplayFile(file);
    if (!file) return;
    const objectUrl = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      if (Number.isFinite(video.duration) && video.duration > 0) {
        setDuration(video.duration.toFixed(2));
      }
      URL.revokeObjectURL(objectUrl);
    };
    video.onerror = () => URL.revokeObjectURL(objectUrl);
    video.src = objectUrl;
  }

  async function scoreEvaluation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    try {
      const predictions = parseIntervalList(predictedText).map((interval) => ({
        ...interval,
        detected_at_seconds: interval.start_seconds,
      }));
      const scored = await api.scoreReplayEvaluation(selected.id, {
        predicted_intervals: predictions,
        provider_requests: Number(providerRequests),
        input_tokens: Number(inputTokens),
        output_tokens: Number(outputTokens),
        input_price_per_million_usd: Number(inputPrice),
        output_price_per_million_usd: Number(outputPrice),
      });
      setEvaluations((current) =>
        current.map((evaluation) => (evaluation.id === scored.id ? scored : evaluation)),
      );
      await refreshCalibration();
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not score the evaluation.");
    } finally {
      setBusy(false);
    }
  }

  async function runEvaluation() {
    if (!selected) return;
    setBusy(true);
    try {
      const queued = await api.runReplayEvaluation(selected.id);
      setEvaluations((current) =>
        current.map((evaluation) => (evaluation.id === queued.id ? queued : evaluation)),
      );
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not queue the replay.");
    } finally {
      setBusy(false);
    }
  }

  function toggleSuiteEvaluation(evaluationId: string) {
    setSuiteEvaluationIds((current) =>
      current.includes(evaluationId)
        ? current.filter((id) => id !== evaluationId)
        : [...current, evaluationId],
    );
  }

  async function createSuite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (suiteEvaluationIds.length === 0) {
      onError("Select at least one replay baseline for the regression suite.");
      return;
    }
    setSuiteBusy(true);
    try {
      const created = await api.createReplaySuite({
        name: suiteName.trim(),
        evaluation_ids: suiteEvaluationIds,
        minimum_macro_f1: Number(minimumF1),
        minimum_macro_recall: Number(minimumRecall),
        maximum_false_positives: Number(maximumFalsePositives),
        maximum_estimated_cost_usd: Number(maximumCost),
        require_pricing: requirePricing,
      });
      setSuites((current) => [created, ...current]);
      setSelectedSuiteId(created.id);
      setSuiteHistory([]);
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not create regression suite.");
    } finally {
      setSuiteBusy(false);
    }
  }

  async function runSuite(suite: ReplaySuite) {
    setSuiteBusy(true);
    try {
      const run = await api.runReplaySuite(suite.id);
      setSuites((current) => current.map((item) =>
        item.id === suite.id ? { ...item, latest_run: run } : item,
      ));
      setSelectedSuiteId(suite.id);
      setSuiteHistory((current) => [run, ...current]);
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Could not run regression suite.");
    } finally {
      setSuiteBusy(false);
    }
  }

  return (
    <section className="panel evaluationPanel" id="evaluations">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Phase 16 · measurable reliability</span>
          <h2>Replay evaluation lab</h2>
          <p className="mutedText">
            Preserve the production execution route, ground-truth intervals, detected intervals,
            latency, and provider cost for a labeled video.
          </p>
        </div>
        <span className="evaluationCount">{evaluations.length} runs</span>
      </div>

      {calibrationReadiness && (
        <div className={`calibrationReadiness calibration-${calibrationReadiness.status}`}>
          <div className="calibrationSummary">
            <div>
              <span className="eyebrow">General benchmark evidence</span>
              <h3>
                {calibrationReadiness.benchmark_accuracy_claimable
                  ? "General benchmark pack ready"
                  : "General benchmark still in progress"}
              </h3>
              <p>{calibrationReadiness.message}</p>
            </div>
            <div className="calibrationTotals">
              <div><strong>{calibrationReadiness.ready_scenarios}/{calibrationReadiness.required_scenarios}</strong><small>scenarios ready</small></div>
              <div><strong>{calibrationReadiness.site_specific_ready_scenarios}/{calibrationReadiness.required_scenarios}</strong><small>site-proven scenarios</small></div>
              <div><strong>{calibrationReadiness.public_benchmark_clips}</strong><small>licensed benchmark clips</small></div>
              <div><strong>{calibrationReadiness.site_specific_clips}</strong><small>site-specific clips</small></div>
              <div><strong>{calibrationReadiness.synthetic_pipeline_checks}</strong><small>synthetic checks</small></div>
            </div>
          </div>
          <div className="calibrationScenarioGrid">
            {calibrationReadiness.scenarios.map((status) => (
              <button
                className={`calibrationScenario calibration-status-${status.status}`}
                key={status.key}
                onClick={() => chooseScenario(status.key)}
                type="button"
              >
                <span>{status.status.replace("_", " ")}</span>
                <strong>{status.title}</strong>
                <small>{status.positive_clips} positive · {status.negative_clips} negative · {status.challenging_clips} challenging</small>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="evaluationWorkspace">
        <form className="evaluationForm" onSubmit={createEvaluation}>
          <h3>Create a labeled replay</h3>
          <label>
            <span>Calibration scenario (recommended)</span>
            <select onChange={(event) => chooseScenario(event.target.value)} value={scenarioKey}>
              <option value="">Custom / unclassified replay</option>
              {calibrationScenarios.map((scenario) => (
                <option key={scenario.key} value={scenario.key}>{scenario.title}</option>
              ))}
            </select>
          </label>
          {selectedScenario && (
            <div className="calibrationProtocol">
              <strong>{selectedScenario.description}</strong>
              <span>{selectedScenario.temporal_mode} · {selectedScenario.metric_family.replace("_", " ")}</span>
              <ol>
                {selectedScenario.recording_protocol.map((instruction) => <li key={instruction}>{instruction}</li>)}
              </ol>
              {selectedScenario.automation_status === "manual_only" && (
                <small>Text correctness still requires manual value-level review.</small>
              )}
            </div>
          )}
          {selectedScenario && (
            <div className="calibrationMetadata">
              <label>
                <span>Clip result</span>
                <select
                  onChange={(event) => {
                    const variant = event.target.value as ReplayScenarioVariant;
                    setScenarioVariant(variant);
                    if (variant === "negative") setExpectedText("");
                  }}
                  value={scenarioVariant}
                >
                  <option value="positive">Positive · event occurs</option>
                  <option value="negative">Negative · event never occurs</option>
                </select>
              </label>
              <label>
                <span>Evidence source</span>
                <select onChange={(event) => setSourceKind(event.target.value as ReplaySourceKind)} value={sourceKind}>
                  <option value="controlled">Controlled camera recording</option>
                  <option value="field">Real field footage</option>
                  <option value="public_benchmark">Licensed public benchmark</option>
                  <option value="synthetic">Synthetic pipeline check</option>
                </select>
              </label>
              <label className="calibrationTags">
                <span>Environment tags</span>
                <input onChange={(event) => setEnvironmentTags(event.target.value)} placeholder="low_light, far_distance" value={environmentTags} />
              </label>
            </div>
          )}
          <label>
            <span>Evaluation name</span>
            <input onChange={(event) => setName(event.target.value)} required value={name} />
          </label>
          <label>
            <span>Camera context</span>
            <select
              onChange={(event) => setCameraId(event.target.value)}
              required
              value={resolvedCameraId}
            >
              <option value="">Select a camera</option>
              {cameras.map((camera) => (
                <option key={camera.id} value={camera.id}>{camera.name}</option>
              ))}
            </select>
          </label>
          <label className="replayUploadField">
            <span>Choose a replay video</span>
            <input
              accept="video/mp4,.mp4,.mov,.mkv,.webm,.avi"
              onChange={(event) => selectReplayFile(event.target.files?.[0] ?? null)}
              type="file"
            />
            <small>{replayFile ? `${replayFile.name} · ${(replayFile.size / 1_048_576).toFixed(1)} MB` : "MP4, MOV, MKV, WEBM, or AVI · maximum 512 MB"}</small>
          </label>
          <label>
            <span>Or use a path/URI (advanced)</span>
            <input
              onChange={(event) => setSourceUri(event.target.value)}
              placeholder="C:\\clips\\masked-entry.mp4"
              value={sourceUri}
            />
          </label>
          <label>
            <span>Natural-language job</span>
            <textarea
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Alert me when a masked person enters the store."
              readOnly={Boolean(selectedScenario)}
              required
              rows={3}
              value={prompt}
            />
          </label>
          <div className="evaluationPair">
            <label>
              <span>Duration (seconds)</span>
              <input min="0.1" onChange={(event) => setDuration(event.target.value)} step="0.1" type="number" value={duration} />
            </label>
            <label>
              <span>Expected event intervals</span>
              <input
                disabled={scenarioVariant === "negative" && Boolean(selectedScenario)}
                onChange={(event) => setExpectedText(event.target.value)}
                placeholder={selectedScenario?.metric_family === "structured_text" ? "Not used for text value scoring" : "5-10, 24-30"}
                value={expectedText}
              />
            </label>
          </div>
          <small>Intervals use video seconds. An empty list represents a negative test clip.</small>
          <button className="buttonPrimary" disabled={busy || !resolvedCameraId} type="submit">
            <Icon name="plus" /> {busy ? "Saving…" : "Create replay baseline"}
          </button>
        </form>

        <div className="evaluationRuns">
          <h3>Saved runs</h3>
          {evaluations.length === 0 ? (
            <div className="evaluationEmpty">No replay baselines yet.</div>
          ) : (
            evaluations.map((evaluation) => (
              <button
                className={evaluation.id === selectedId ? "evaluationRun selected" : "evaluationRun"}
                key={evaluation.id}
                onClick={() => setSelectedId(evaluation.id)}
                type="button"
              >
                <span>{evaluation.status}</span>
                <strong>{evaluation.name}</strong>
                <small>
                  {evaluation.execution_strategy === "semantic_window"
                    ? "VLM windows"
                    : evaluation.execution_strategy === "specialized_pose"
                      ? "Local pose"
                      : "YOLO + tracking"}
                  {evaluation.status === "scored" ? ` · F1 ${percentage(evaluation.metrics.f1)}` : " · awaiting results"}
                </small>
              </button>
            ))
          )}
        </div>
      </div>

      {selected && (
        <div className="evaluationScorecard">
          <div className="evaluationRoute">
            <span>{selected.execution_plan.provider_requests ? "Paid provider route" : "Local route"}</span>
            <strong>{selected.execution_plan.summary}</strong>
            <small>{selected.source_uri} · {selected.duration_seconds}s · {selected.expected_intervals.length} expected events</small>
            {selected.scenario_key && (
              <div className="calibrationBadges">
                <span>{selected.scenario_key.replaceAll("_", " ")}</span>
                <span>{selected.scenario_variant}</span>
                <span>{selected.source_kind}</span>
                {selected.environment_tags.map((tag) => <span key={tag}>{tag.replaceAll("_", " ")}</span>)}
              </div>
            )}
            <div className="evaluationRunControl">
              <button
                className="buttonPrimary"
                disabled={busy || ["queued", "running"].includes(selected.status)}
                onClick={() => void runEvaluation()}
                type="button"
              >
                {selected.status === "queued"
                  ? "Waiting for replay worker…"
                  : selected.status === "running"
                    ? "Running replay…"
                    : selected.status === "scored"
                      ? "Run again"
                      : "Run replay automatically"}
              </button>
              <span className={`replayStatus status-${selected.status}`}>{selected.status}</span>
            </div>
            {(["queued", "running"].includes(selected.status) || selected.progress_percent > 0) && (
              <div className="replayProgress" aria-label={`Replay ${selected.progress_percent}% complete`}>
                <div className="replayProgressHeader">
                  <span>
                    {selected.status === "queued"
                      ? "Waiting for an idle worker"
                      : selected.status === "running"
                        ? "Processing video"
                        : selected.status === "scored"
                          ? "Replay complete"
                          : "Replay stopped"}
                  </span>
                  <strong>{Math.round(selected.progress_percent)}%</strong>
                </div>
                <div className="replayProgressTrack">
                  <span style={{ width: `${selected.progress_percent}%` }} />
                </div>
                <small>{selected.processed_seconds.toFixed(1)} of {selected.duration_seconds.toFixed(1)} video seconds</small>
              </div>
            )}
            {selected.last_error && <p className="evaluationError">{selected.last_error}</p>}
          </div>
          <div className="evaluationMetrics">
            <div><small>Precision</small><strong>{percentage(selected.metrics.precision)}</strong></div>
            <div><small>Recall</small><strong>{percentage(selected.metrics.recall)}</strong></div>
            <div><small>F1</small><strong>{percentage(selected.metrics.f1)}</strong></div>
            <div><small>Mean latency</small><strong>{selected.metrics.mean_latency_seconds == null ? "—" : `${selected.metrics.mean_latency_seconds.toFixed(2)}s`}</strong></div>
            <div><small>False alarms</small><strong>{selected.metrics.false_positives ?? "—"}</strong></div>
            <div>
              <small>Estimated cost</small>
              <strong>
                {selected.metrics.pricing_configured === false
                  ? "Configure pricing"
                  : `$${selected.estimated_cost_usd.toFixed(4)}`}
              </strong>
            </div>
          </div>
          <form className="evaluationScoreForm" onSubmit={scoreEvaluation}>
            <label>
              <span>Detected event intervals</span>
              <input onChange={(event) => setPredictedText(event.target.value)} placeholder="6-9, 25-31" value={predictedText} />
            </label>
            <div className="evaluationUsageGrid">
              <label><span>Requests</span><input min="0" onChange={(event) => setProviderRequests(event.target.value)} type="number" value={providerRequests} /></label>
              <label><span>Input tokens</span><input min="0" onChange={(event) => setInputTokens(event.target.value)} type="number" value={inputTokens} /></label>
              <label><span>Output tokens</span><input min="0" onChange={(event) => setOutputTokens(event.target.value)} type="number" value={outputTokens} /></label>
              <label><span>Input $/1M</span><input min="0" onChange={(event) => setInputPrice(event.target.value)} step="0.001" type="number" value={inputPrice} /></label>
              <label><span>Output $/1M</span><input min="0" onChange={(event) => setOutputPrice(event.target.value)} step="0.001" type="number" value={outputPrice} /></label>
            </div>
            <button className="buttonSecondary" disabled={busy} type="submit">Calculate score</button>
          </form>
          <p className="evaluationNotice">
            Automatic runs are leased to an idle inference worker and never create real incidents.
            Manual result entry remains available for importing results from another model or tool.
          </p>
        </div>
      )}

      <div className="regressionLab">
        <div className="regressionHeader">
          <div>
            <span className="eyebrow">Release protection</span>
            <h3>Regression suites and promotion gates</h3>
            <p className="mutedText">
              Run several labeled videos as one test. The stored gate decides whether accuracy,
              false alarms, pricing, and cost are safe enough to promote.
            </p>
          </div>
          <span className="evaluationCount">{suites.length} suites</span>
        </div>

        <div className="regressionWorkspace">
          <form className="regressionBuilder" onSubmit={createSuite}>
            <label>
              <span>Suite name</span>
              <input onChange={(event) => setSuiteName(event.target.value)} required value={suiteName} />
            </label>
            <fieldset>
              <legend>Replay baselines</legend>
              {evaluations.length === 0 ? (
                <small>Create a labeled replay first.</small>
              ) : evaluations.map((evaluation) => (
                <label className="regressionCheckbox" key={evaluation.id}>
                  <input
                    checked={suiteEvaluationIds.includes(evaluation.id)}
                    onChange={() => toggleSuiteEvaluation(evaluation.id)}
                    type="checkbox"
                  />
                  <span>
                    <strong>{evaluation.name}</strong>
                    <small>
                      {evaluation.execution_strategy === "semantic_window"
                        ? "VLM windows"
                        : evaluation.execution_strategy === "specialized_pose"
                          ? "Local pose"
                          : "Local tracking"}
                    </small>
                  </span>
                </label>
              ))}
            </fieldset>
            <div className="regressionThresholds">
              <label>
                <span>Minimum macro F1</span>
                <input max="1" min="0" onChange={(event) => setMinimumF1(event.target.value)} step="0.01" type="number" value={minimumF1} />
              </label>
              <label>
                <span>Minimum recall</span>
                <input max="1" min="0" onChange={(event) => setMinimumRecall(event.target.value)} step="0.01" type="number" value={minimumRecall} />
              </label>
              <label>
                <span>Maximum false alarms</span>
                <input min="0" onChange={(event) => setMaximumFalsePositives(event.target.value)} type="number" value={maximumFalsePositives} />
              </label>
              <label>
                <span>Maximum run cost</span>
                <input min="0" onChange={(event) => setMaximumCost(event.target.value)} step="0.01" type="number" value={maximumCost} />
              </label>
            </div>
            <label className="regressionCheckbox compact">
              <input checked={requirePricing} onChange={(event) => setRequirePricing(event.target.checked)} type="checkbox" />
              <span>Fail paid runs when provider pricing is missing</span>
            </label>
            <button className="buttonPrimary" disabled={suiteBusy || suiteEvaluationIds.length === 0} type="submit">
              <Icon name="plus" /> {suiteBusy ? "Saving…" : "Create regression gate"}
            </button>
          </form>

          <div className="regressionSuites">
            <h4>Saved suites</h4>
            {suites.length === 0 ? (
              <div className="evaluationEmpty">No regression gates yet.</div>
            ) : suites.map((suite) => (
              <button
                className={suite.id === selectedSuiteId ? "regressionSuite selected" : "regressionSuite"}
                key={suite.id}
                onClick={() => setSelectedSuiteId(suite.id)}
                type="button"
              >
                <span className={`replayStatus status-${suite.latest_run?.status ?? "draft"}`}>
                  {suite.latest_run?.status ?? "not run"}
                </span>
                <strong>{suite.name}</strong>
                <small>{suite.evaluation_ids.length} baselines · F1 ≥ {suite.minimum_macro_f1}</small>
              </button>
            ))}
          </div>
        </div>

        {selectedSuite && (
          <div className="regressionReport">
            <div className="regressionReportHeader">
              <div>
                <span>Selected promotion gate</span>
                <strong>{selectedSuite.name}</strong>
                <small>
                  F1 ≥ {selectedSuite.minimum_macro_f1} · recall ≥ {selectedSuite.minimum_macro_recall}
                  {` · false alarms ≤ ${selectedSuite.maximum_false_positives} · cost ≤ $${selectedSuite.maximum_estimated_cost_usd.toFixed(2)}`}
                </small>
              </div>
              <button
                className="buttonPrimary"
                disabled={suiteBusy || ["queued", "running"].includes(selectedSuite.latest_run?.status ?? "")}
                onClick={() => void runSuite(selectedSuite)}
                type="button"
              >
                {selectedSuite.latest_run?.status === "queued"
                  ? "Waiting for workers…"
                  : selectedSuite.latest_run?.status === "running"
                    ? "Running suite…"
                    : "Run complete suite"}
              </button>
            </div>

            {selectedSuite.latest_run ? (
              <>
                <div className={`promotionDecision decision-${selectedSuite.latest_run.status}`}>
                  <span>Promotion decision</span>
                  <strong>
                    {selectedSuite.latest_run.status === "passed"
                      ? "PASS · configuration may advance"
                      : selectedSuite.latest_run.status === "failed"
                        ? "BLOCKED · fix regressions first"
                        : "PENDING · suite is still executing"}
                  </strong>
                  {["queued", "running"].includes(selectedSuite.latest_run.status) && (
                    <small>
                      {selectedSuite.latest_run.metrics.completed_count ?? 0} of {selectedSuite.latest_run.metrics.evaluation_count ?? selectedSuite.evaluation_ids.length} replays complete
                    </small>
                  )}
                </div>
                {selectedSuite.latest_run.gate_results.length > 0 && (
                  <div className="gateGrid">
                    {selectedSuite.latest_run.gate_results.map((gate) => (
                      <article className={gate.passed ? "gateResult passed" : "gateResult failed"} key={gate.key}>
                        <span>{gate.passed ? "✓" : "×"}</span>
                        <div>
                          <strong>{gate.label}</strong>
                          <small>{gateValue(gate.actual)} {gate.operator} {gateValue(gate.threshold)}</small>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
                {selectedSuite.latest_run.results.length > 0 && (
                  <div className="regressionResults">
                    {selectedSuite.latest_run.results.map((result) => (
                      <article key={result.evaluation_id}>
                        <span className={`replayStatus status-${result.status}`}>{result.status}</span>
                        <strong>{result.name}</strong>
                        <small>F1 {percentage(result.metrics.f1)} · false alarms {result.metrics.false_positives ?? "—"} · ${result.estimated_cost_usd.toFixed(4)}</small>
                      </article>
                    ))}
                  </div>
                )}
                {selectedSuite.latest_run.metrics.scenario_metrics && (
                  <div className="scenarioBreakdown">
                    <h4>Capability breakdown</h4>
                    {Object.entries(selectedSuite.latest_run.metrics.scenario_metrics).map(([key, metrics]) => (
                      <article key={key}>
                        <div>
                          <strong>{key.replaceAll("_", " ")}</strong>
                          <small>{metrics.evaluation_count} clips · {metrics.source_kinds.join(" + ")} · {metrics.variants.join(" + ")}</small>
                        </div>
                        <span>F1 {percentage(metrics.macro_f1)}</span>
                        <span>Recall {percentage(metrics.macro_recall)}</span>
                        <span>{metrics.false_positives} false alarms</span>
                      </article>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="evaluationNotice">This suite has not run yet. Its first result will become the promotion baseline.</p>
            )}

            {suiteHistory.length > 0 && (
              <div className="regressionHistory">
                <h4>Run history</h4>
                {suiteHistory.slice(0, 6).map((run) => (
                  <div key={run.id}>
                    <span className={`replayStatus status-${run.status}`}>{run.status}</span>
                    <time>{new Date(run.created_at).toLocaleString()}</time>
                    <strong>F1 {percentage(run.metrics.macro_f1)}</strong>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
