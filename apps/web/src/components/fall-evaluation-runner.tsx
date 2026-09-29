"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { BrowserPoseRule, PostureOnlyFallRule, poseFeatures, type Landmark } from "@/lib/browser-pose";
import { PoseWindowFallRule, type PoseWindowModel } from "@/lib/pose-window-fall";
import windowModel from "@/lib/fall-window-model.json";
import windowModelV2 from "@/lib/fall-window-model-v2.json";
import {
  BUILTIN_FALL_DATASET,
  buildFallEvaluationExport,
  FALL_EVALUATION_SAMPLE_INTERVAL_SECONDS,
  isCompleteFallEvaluation,
  parseFallEvaluationDataset,
  percentile,
  scoreFallEvaluation,
  type FallEvaluationCase,
  type FallEvaluationDataset,
  type FallEvaluationResult,
  type FallPoseTrace,
  type FallEvaluationRunStatus,
} from "@/lib/fall-evaluation";
import styles from "./fall-evaluation-runner.module.css";

type WorkerReply = {
  type: "ready" | "result" | "error";
  landmarks?: Landmark[];
  inferenceMs?: number;
  message?: string;
};

function waitForWorker(
  worker: Worker,
  send: () => void,
  expected: WorkerReply["type"],
): Promise<WorkerReply> {
  return new Promise((resolve, reject) => {
    const receive = ({ data }: MessageEvent<WorkerReply>) => {
      if (data.type === "error") {
        cleanup();
        reject(new Error(data.message || "Pose worker failed"));
      } else if (data.type === expected) {
        cleanup();
        resolve(data);
      }
    };
    const fail = () => {
      cleanup();
      reject(new Error("Pose worker stopped unexpectedly"));
    };
    const cleanup = () => {
      worker.removeEventListener("message", receive);
      worker.removeEventListener("error", fail);
    };
    worker.addEventListener("message", receive);
    worker.addEventListener("error", fail);
    send();
  });
}

function loadVideo(video: HTMLVideoElement, source: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const ready = () => {
      cleanup();
      resolve();
    };
    const fail = () => {
      cleanup();
      reject(new Error(`Could not decode ${source}`));
    };
    const cleanup = () => {
      video.removeEventListener("loadeddata", ready);
      video.removeEventListener("error", fail);
    };
    video.addEventListener("loadeddata", ready);
    video.addEventListener("error", fail);
    video.src = source;
    video.load();
  });
}

function seek(video: HTMLVideoElement, seconds: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const done = () => {
      cleanup();
      resolve();
    };
    const fail = () => {
      cleanup();
      reject(new Error("Video seek failed"));
    };
    const cleanup = () => {
      video.removeEventListener("seeked", done);
      video.removeEventListener("error", fail);
    };
    video.addEventListener("seeked", done);
    video.addEventListener("error", fail);
    video.currentTime = Math.min(
      Math.max(0, seconds),
      Math.max(0, video.duration - 0.001),
    );
    if (!video.seeking) queueMicrotask(done);
  });
}

async function runCase(
  definition: FallEvaluationCase,
  video: HTMLVideoElement,
  cancelled: () => boolean,
  onProgress: (frame: number, total: number) => void,
): Promise<FallEvaluationResult> {
  const worker = new Worker("/vision/pose-worker.js");
  const inferenceTimes: number[] = [];
  const detectedAtSeconds: number[] = [];
  const postureBaselineDetectedAtSeconds: number[] = [];
  const windowModelDetectedAtSeconds: number[] = [];
  const windowModelV2DetectedAtSeconds: number[] = [];
  const poseTrace: FallPoseTrace[] = [];
  let framesAnalyzed = 0;
  let framesWithPose = 0;
  try {
    await waitForWorker(
      worker,
      () => worker.postMessage({ type: "init" }),
      "ready",
    );
    await loadVideo(video, definition.videoUrl);
    const durationSeconds = video.duration;
    if (!Number.isFinite(durationSeconds) || durationSeconds <= 0) {
      throw new Error("Video duration is unavailable");
    }
    const totalFrames = Math.max(
      1,
      Math.floor(durationSeconds / FALL_EVALUATION_SAMPLE_INTERVAL_SECONDS),
    );
    const rule = new BrowserPoseRule("fall");
    const postureBaseline = new PostureOnlyFallRule();
    const windowCandidate = new PoseWindowFallRule(windowModel as PoseWindowModel);
    const windowCandidateV2 = new PoseWindowFallRule(windowModelV2 as PoseWindowModel);
    for (let frame = 0; frame <= totalFrames; frame += 1) {
      if (cancelled()) throw new Error("Evaluation cancelled");
      const seconds = Math.min(
        durationSeconds - 0.001,
        frame * FALL_EVALUATION_SAMPLE_INTERVAL_SECONDS,
      );
      await seek(video, seconds);
      const bitmap = await createImageBitmap(video);
      const response = await waitForWorker(
        worker,
        () =>
          worker.postMessage(
            { type: "frame", bitmap, timestamp: Math.round(seconds * 1000) },
            [bitmap],
          ),
        "result",
      );
      const landmarks = response.landmarks ?? [];
      const features = poseFeatures(
        landmarks,
        video.videoWidth,
        video.videoHeight,
      );
      framesAnalyzed += 1;
      if (features) framesWithPose += 1;
      if (rule.update(features, seconds)) {
        detectedAtSeconds.push(Number(seconds.toFixed(3)));
      }
      if (postureBaseline.update(features, seconds)) {
        postureBaselineDetectedAtSeconds.push(Number(seconds.toFixed(3)));
      }
      if (windowCandidate.update(features, seconds)) {
        windowModelDetectedAtSeconds.push(Number(seconds.toFixed(3)));
      }
      if (windowCandidateV2.update(features, seconds)) {
        windowModelV2DetectedAtSeconds.push(Number(seconds.toFixed(3)));
      }
      poseTrace.push({
        seconds: Number(seconds.toFixed(3)),
        y: features ? Number(features.y.toFixed(4)) : null,
        verticality: features ? Number(features.verticality.toFixed(4)) : null,
        aspect: features ? Number(features.aspect.toFixed(4)) : null,
        phase: rule.status,
      });
      inferenceTimes.push(response.inferenceMs ?? 0);
      if (frame % 5 === 0 || frame === totalFrames) {
        onProgress(frame, totalFrames);
      }
    }
    return {
      ...definition,
      durationSeconds,
      framesAnalyzed,
      framesWithPose,
      detectedAtSeconds,
      postureBaselineDetectedAtSeconds,
      windowModelDetectedAtSeconds,
      windowModelV2DetectedAtSeconds,
      poseTrace,
      meanInferenceMs:
        inferenceTimes.reduce((total, value) => total + value, 0) /
        Math.max(1, inferenceTimes.length),
      p95InferenceMs: percentile(inferenceTimes, 95),
    };
  } finally {
    worker.terminate();
    video.removeAttribute("src");
    video.load();
  }
}

function percent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function seconds(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(2)} s`;
}

export function FallEvaluationRunner() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const cancelRef = useRef(false);
  const [running, setRunning] = useState(false);
  const [runStatus, setRunStatus] = useState<FallEvaluationRunStatus>("idle");
  const [results, setResults] = useState<FallEvaluationResult[]>([]);
  const [currentCase, setCurrentCase] = useState("");
  const [progress, setProgress] = useState(0);
  const [problem, setProblem] = useState<string | null>(null);
  const [externalDatasets, setExternalDatasets] = useState<Partial<Record<"urfall" | "gmdcsa24" | "caucafall", FallEvaluationDataset>>>({});
  const [datasetMode, setDatasetMode] = useState<"builtin" | "urfall" | "gmdcsa24" | "caucafall">("builtin");
  const dataset = datasetMode !== "builtin" && externalDatasets[datasetMode]
    ? externalDatasets[datasetMode] : BUILTIN_FALL_DATASET;
  const cases = dataset.cases;

  useEffect(() => {
    let active = true;
    const sources = ["urfall", "gmdcsa24", "caucafall"] as const;
    void Promise.all(sources.map(async (source) => {
      try {
        const response = await fetch(`/vision/${source}/manifest.json`, { cache: "no-store" });
        if (!response.ok) return null;
        return [source, parseFallEvaluationDataset(await response.json())] as const;
      } catch { return null; }
    })).then((loaded) => {
      if (!active) return;
      const available = Object.fromEntries(loaded.filter((item) => item !== null)) as
        Partial<Record<"urfall" | "gmdcsa24" | "caucafall", FallEvaluationDataset>>;
      setExternalDatasets(available);
      const requested = new URLSearchParams(window.location.search).get("dataset");
      if ((requested === "urfall" || requested === "gmdcsa24" || requested === "caucafall") && available[requested]) {
        setDatasetMode(requested);
      }
    });
    return () => { active = false; };
  }, []);

  function selectDataset(mode: "builtin" | "urfall" | "gmdcsa24" | "caucafall") {
    if (running) return;
    setDatasetMode(mode);
    setRunStatus("idle");
    setResults([]);
    setProblem(null);
    setProgress(0);
    setCurrentCase("");
  }
  const summary = useMemo(
    () => runStatus === "complete" && isCompleteFallEvaluation(results, cases)
      ? scoreFallEvaluation(results)
      : null,
    [results, runStatus, cases],
  );
  const postureSummary = summary ? scoreFallEvaluation(results, "posture") : null;
  const windowSummary = summary ? scoreFallEvaluation(results, "window") : null;
  const windowV2Summary = summary ? scoreFallEvaluation(results, "windowV2") : null;
  const splitSummaries = summary ? (["development", "holdout"] as const).flatMap((partition) => {
    const subset = results.filter((result) => result.partition === partition);
    return subset.length ? [{
      partition,
      cases: subset.length,
      temporal: scoreFallEvaluation(subset),
      posture: scoreFallEvaluation(subset, "posture"),
      window: scoreFallEvaluation(subset, "window"),
      windowV2: scoreFallEvaluation(subset, "windowV2"),
    }] : [];
  }) : [];

  async function run() {
    const video = videoRef.current;
    if (!video || running) return;
    cancelRef.current = false;
    setRunning(true);
    setRunStatus("running");
    setResults([]);
    setProblem(null);
    setProgress(0);
    setCurrentCase("");
    const completed: FallEvaluationResult[] = [];
    try {
      for (let index = 0; index < cases.length; index += 1) {
        const definition = cases[index];
        setCurrentCase(definition.name);
        const result = await runCase(
          definition,
          video,
          () => cancelRef.current,
          (frame, total) =>
            setProgress(
              ((index + frame / Math.max(1, total)) /
                cases.length) *
                100,
            ),
        );
        completed.push(result);
        setResults([...completed]);
      }
      if (cancelRef.current) throw new Error("Evaluation cancelled");
      setProgress(100);
      setCurrentCase("Evaluation complete");
      setRunStatus("complete");
    } catch (error) {
      if (!cancelRef.current) {
        setProblem(
          error instanceof Error ? error.message : "Evaluation could not finish",
        );
      }
      setCurrentCase(cancelRef.current ? "Evaluation stopped" : "Evaluation failed");
      setRunStatus(cancelRef.current ? "stopped" : "failed");
    } finally {
      setRunning(false);
    }
  }

  function download() {
    if (runStatus !== "complete" || !summary) return;
    const payload = buildFallEvaluationExport(runStatus, results, new Date().toISOString(), dataset);
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `artae-fall-evaluation-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <span>ARTAE ENGINEERING</span>
          <h1>Fall detector evaluation</h1>
          <p>
            Run the production browser pose model on staged footage. Compare its
            temporal rule with a sustained-posture baseline and a research pose-window
            candidate on the same frames.
            This local evaluation makes no AWS calls.
          </p>
        </div>
        <div className={styles.actions}>
          {summary && !running && (
            <button type="button" onClick={download}>Download JSON</button>
          )}
          <button
            className={styles.primary}
            type="button"
            onClick={running ? () => { cancelRef.current = true; } : () => void run()}
          >
            {running ? "Stop evaluation" : runStatus !== "idle" ? "Run again" : "Run evaluation"}
          </button>
        </div>
      </header>

      <nav className={styles.datasetChoice} aria-label="Evaluation dataset">
        <button type="button" aria-pressed={datasetMode === "builtin"} disabled={running}
          onClick={() => selectDataset("builtin")}>Five-clip smoke test</button>
        {externalDatasets.urfall && <button type="button" aria-pressed={datasetMode === "urfall"} disabled={running}
          onClick={() => selectDataset("urfall")}>UR Fall research set ({externalDatasets.urfall.cases.length})</button>}
        {externalDatasets.gmdcsa24 && <button type="button" aria-pressed={datasetMode === "gmdcsa24"} disabled={running}
          onClick={() => selectDataset("gmdcsa24")}>GMDCSA-24 subject split ({externalDatasets.gmdcsa24.cases.length})</button>}
        {externalDatasets.caucafall && <button type="button" aria-pressed={datasetMode === "caucafall"} disabled={running}
          onClick={() => selectDataset("caucafall")}>CAUCAFall independent source ({externalDatasets.caucafall.cases.length})</button>}
        <span>{dataset.split}</span>
      </nav>

      <section className={styles.status} aria-live="polite">
        <div>
          <strong>{runStatus === "idle" ? "Ready" : currentCase}</strong>
          <span>{running ? `${Math.round(progress)}% processed` : runStatus === "complete" ? `${cases.length}/${cases.length} clips processed` : runStatus === "stopped" || runStatus === "failed" ? `${results.length}/${cases.length} clips processed · incomplete run, no summary` : `${cases.length} licensed evaluation clips`}</span>
        </div>
        <div className={styles.progress} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress)}>
          <i style={{ width: `${progress}%` }} />
        </div>
      </section>

      {problem && <p className={styles.error} role="alert">{problem}</p>}

      <section className={styles.metrics} aria-label="Evaluation summary">
        <article><span>Clip accuracy</span><strong>{summary ? percent(summary.accuracy) : "—"}</strong><small>{summary ? `${summary.passedCases}/${summary.totalCases} clips correct` : `Complete all ${cases.length} clips`}</small></article>
        <article><span>Fall clip recall</span><strong>{summary ? percent(summary.recall) : "—"}</strong><small>{summary ? `${summary.truePositives} detected · ${summary.falseNegatives} missed` : `Complete all ${cases.length} clips`}</small></article>
        <article><span>Clip precision</span><strong>{summary ? percent(summary.precision) : "—"}</strong><small>{summary ? `${summary.falsePositives} negative clips alerted` : `Complete all ${cases.length} clips`}</small></article>
        <article><span>Mean candidate latency</span><strong>{summary ? seconds(summary.meanDetectionLatencySeconds) : "—"}</strong><small>{summary ? "From approximate labeled fall onset" : `Complete all ${cases.length} clips`}</small></article>
      </section>

      {summary && postureSummary && windowSummary && windowV2Summary && <section className={styles.comparison} aria-label="Detector comparison">
        <h2>Same frames, four methods</h2>
        <table><thead><tr><th>Rule</th><th>Fall recall</th><th>Clip precision</th><th>False alerts / negative hour</th><th>Candidate delay</th></tr></thead>
          <tbody>
            <tr><th>Temporal descent + floor</th><td>{percent(summary.recall)}</td><td>{percent(summary.precision)}</td><td>{summary.falseAlertsPerHour?.toFixed(1) ?? "—"}</td><td>{seconds(summary.meanDetectionLatencySeconds)}</td></tr>
            <tr><th>Sustained posture only</th><td>{percent(postureSummary.recall)}</td><td>{percent(postureSummary.precision)}</td><td>{postureSummary.falseAlertsPerHour?.toFixed(1) ?? "—"}</td><td>{seconds(postureSummary.meanDetectionLatencySeconds)}</td></tr>
            <tr><th>Trained pose window · research candidate</th><td>{percent(windowSummary.recall)}</td><td>{percent(windowSummary.precision)}</td><td>{windowSummary.falseAlertsPerHour?.toFixed(1) ?? "—"}</td><td>{seconds(windowSummary.meanDetectionLatencySeconds)}</td></tr>
            <tr><th>Expanded training pose window · research candidate</th><td>{percent(windowV2Summary.recall)}</td><td>{percent(windowV2Summary.precision)}</td><td>{windowV2Summary.falseAlertsPerHour?.toFixed(1) ?? "—"}</td><td>{seconds(windowV2Summary.meanDetectionLatencySeconds)}</td></tr>
          </tbody></table>
      </section>}

      {splitSummaries.length > 0 && <section className={styles.comparison} aria-label="Dataset partitions">
        <h2>Development and reserved sequences</h2>
        <table><thead><tr><th>Partition</th><th>Clips</th><th>Rule</th><th>Fall clips detected</th><th>Daily activity alerts</th></tr></thead>
          <tbody>{splitSummaries.flatMap((group) => [
            <tr key={`${group.partition}-temporal`}><th rowSpan={4}>{group.partition}</th><td rowSpan={4}>{group.cases}</td><td>Temporal</td><td>{group.temporal.truePositives}/{group.temporal.truePositives + group.temporal.falseNegatives}</td><td>{group.temporal.falsePositives}</td></tr>,
            <tr key={`${group.partition}-posture`}><td>Posture</td><td>{group.posture.truePositives}/{group.posture.truePositives + group.posture.falseNegatives}</td><td>{group.posture.falsePositives}</td></tr>,
            <tr key={`${group.partition}-window`}><td>Pose window candidate</td><td>{group.window.truePositives}/{group.window.truePositives + group.window.falseNegatives}</td><td>{group.window.falsePositives}</td></tr>,
            <tr key={`${group.partition}-window-v2`}><td>Expanded pose window</td><td>{group.windowV2.truePositives}/{group.windowV2.truePositives + group.windowV2.falseNegatives}</td><td>{group.windowV2.falsePositives}</td></tr>,
          ])}</tbody></table>
      </section>}

      <section className={styles.results}>
        <header><h2>Clip results</h2><span>MediaPipe + the same temporal rule used by /live</span></header>
        <div className={styles.tableWrap}>
          <table>
            <thead><tr><th>Clip</th><th>Expected</th><th>Live rule</th><th>Candidate v1</th><th>Candidate v2</th><th>First live event</th><th>Pose coverage</th><th>Inference p95</th><th>Live result</th></tr></thead>
            <tbody>
              {cases.map((definition) => {
                const result = results.find((item) => item.id === definition.id);
                const expected = definition.expectedEvents > 0;
                const detected = !!result?.detectedAtSeconds.length;
                const passed = result ? expected === detected : null;
                return <tr key={definition.id}>
                  <td><strong>{definition.name}</strong><small>{definition.category === "fall" ? "Positive case" : "Negative control"}</small></td>
                  <td>{expected ? "Fall" : "No fall"}</td>
                  <td>{result ? `${result.detectedAtSeconds.length} event${result.detectedAtSeconds.length === 1 ? "" : "s"}` : "Waiting"}</td>
                  <td>{result ? `${result.windowModelDetectedAtSeconds?.length ?? 0} event${result.windowModelDetectedAtSeconds?.length === 1 ? "" : "s"}` : "Waiting"}</td>
                  <td>{result ? `${result.windowModelV2DetectedAtSeconds?.length ?? 0} event${result.windowModelV2DetectedAtSeconds?.length === 1 ? "" : "s"}` : "Waiting"}</td>
                  <td>{result?.detectedAtSeconds.length ? `${result.detectedAtSeconds[0].toFixed(1)} s` : "—"}</td>
                  <td>{result ? percent(result.framesWithPose / Math.max(1, result.framesAnalyzed)) : "—"}</td>
                  <td>{result ? `${result.p95InferenceMs.toFixed(1)} ms` : "—"}</td>
                  <td><span className={passed === null ? styles.pending : passed ? styles.pass : styles.fail}>{passed === null ? "Pending" : passed ? "Pass" : "Fail"}</span></td>
                </tr>;
              })}
            </tbody>
          </table>
        </div>
      </section>

      <footer className={styles.disclosure}>
        <strong>What this proves</strong>
        <p>This is a reproducible engineering benchmark on staged research footage, not clinical validation. The dataset does not represent real accidental falls or older adults. Candidate delay uses approximate onset labels; dataset license and provenance appear in the downloaded JSON.</p>
      </footer>
      <video className={styles.probe} ref={videoRef} muted playsInline preload="auto" aria-hidden="true" />
    </main>
  );
}
