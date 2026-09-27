"use client";

import { useMemo, useRef, useState } from "react";
import { BrowserPoseRule, poseFeatures, type Landmark } from "@/lib/browser-pose";
import {
  buildFallEvaluationExport,
  DEFAULT_FALL_EVALUATION_CASES,
  FALL_EVALUATION_SAMPLE_INTERVAL_SECONDS,
  isCompleteFallEvaluation,
  percentile,
  scoreFallEvaluation,
  type FallEvaluationCase,
  type FallEvaluationResult,
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
  const summary = useMemo(
    () => runStatus === "complete" && isCompleteFallEvaluation(results)
      ? scoreFallEvaluation(results)
      : null,
    [results, runStatus],
  );

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
      for (let index = 0; index < DEFAULT_FALL_EVALUATION_CASES.length; index += 1) {
        const definition = DEFAULT_FALL_EVALUATION_CASES[index];
        setCurrentCase(definition.name);
        const result = await runCase(
          definition,
          video,
          () => cancelRef.current,
          (frame, total) =>
            setProgress(
              ((index + frame / Math.max(1, total)) /
                DEFAULT_FALL_EVALUATION_CASES.length) *
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
    const payload = buildFallEvaluationExport(runStatus, results);
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
            Run the production browser pose model against three staged falls and
            two normal daily activities. This test is local and makes no AWS calls.
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

      <section className={styles.status} aria-live="polite">
        <div>
          <strong>{runStatus === "idle" ? "Ready" : currentCase}</strong>
          <span>{running ? `${Math.round(progress)}% processed` : runStatus === "complete" ? "5/5 clips processed" : runStatus === "stopped" || runStatus === "failed" ? `${results.length}/5 clips processed · incomplete run, no summary` : "5 licensed evaluation clips"}</span>
        </div>
        <div className={styles.progress} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress)}>
          <i style={{ width: `${progress}%` }} />
        </div>
      </section>

      {problem && <p className={styles.error} role="alert">{problem}</p>}

      <section className={styles.metrics} aria-label="Evaluation summary">
        <article><span>Clip accuracy</span><strong>{summary ? percent(summary.accuracy) : "—"}</strong><small>{summary ? `${summary.passedCases}/${summary.totalCases} clips correct` : "Complete all 5 clips"}</small></article>
        <article><span>Fall clip recall</span><strong>{summary ? percent(summary.recall) : "—"}</strong><small>{summary ? `${summary.truePositives} detected · ${summary.falseNegatives} missed` : "Complete all 5 clips"}</small></article>
        <article><span>Clip precision</span><strong>{summary ? percent(summary.precision) : "—"}</strong><small>{summary ? `${summary.falsePositives} negative clips alerted` : "Complete all 5 clips"}</small></article>
        <article><span>Mean candidate latency</span><strong>{summary ? seconds(summary.meanDetectionLatencySeconds) : "—"}</strong><small>{summary ? "From approximate labeled fall onset" : "Complete all 5 clips"}</small></article>
      </section>

      <section className={styles.results}>
        <header><h2>Clip results</h2><span>MediaPipe + the same temporal rule used by /live</span></header>
        <div className={styles.tableWrap}>
          <table>
            <thead><tr><th>Clip</th><th>Expected</th><th>Detected</th><th>First event</th><th>Pose coverage</th><th>Inference p95</th><th>Result</th></tr></thead>
            <tbody>
              {DEFAULT_FALL_EVALUATION_CASES.map((definition) => {
                const result = results.find((item) => item.id === definition.id);
                const expected = definition.expectedEvents > 0;
                const detected = !!result?.detectedAtSeconds.length;
                const passed = result ? expected === detected : null;
                return <tr key={definition.id}>
                  <td><strong>{definition.name}</strong><small>{definition.category === "fall" ? "Positive case" : "Negative control"}</small></td>
                  <td>{expected ? "Fall" : "No fall"}</td>
                  <td>{result ? `${result.detectedAtSeconds.length} event${result.detectedAtSeconds.length === 1 ? "" : "s"}` : "Waiting"}</td>
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
        <p>This is a reproducible engineering baseline, not clinical validation. Five staged clips cannot establish real-world safety, and approximate onset labels make the latency metric directional rather than medically precise.</p>
      </footer>
      <video className={styles.probe} ref={videoRef} muted playsInline preload="auto" aria-hidden="true" />
    </main>
  );
}
