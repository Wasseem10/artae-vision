export type FallEvaluationCase = {
  id: string;
  name: string;
  category: "fall" | "daily_activity";
  videoUrl: string;
  expectedEvents: number;
  eventStartSeconds?: number;
};

export type FallEvaluationResult = FallEvaluationCase & {
  durationSeconds: number;
  framesAnalyzed: number;
  framesWithPose: number;
  detectedAtSeconds: number[];
  meanInferenceMs: number;
  p95InferenceMs: number;
  error?: string;
};

export type FallEvaluationRunStatus =
  | "idle"
  | "running"
  | "complete"
  | "stopped"
  | "failed";

/** TP/FP/TN/FN count clips, not individually time-matched fall events. */
export type FallEvaluationSummary = {
  totalCases: number;
  passedCases: number;
  truePositives: number;
  falsePositives: number;
  trueNegatives: number;
  falseNegatives: number;
  precision: number | null;
  recall: number | null;
  accuracy: number;
  falseAlertsPerHour: number | null;
  meanDetectionLatencySeconds: number | null;
  totalDetections: number;
  extraDetections: number;
};

export const FALL_EVALUATION_SAMPLE_INTERVAL_SECONDS = 0.1;

// Keep these identifiers in sync with browser-pose.ts, pose-worker.js,
// package.json, and the model digest checked by scripts/prepare-vision.mjs.
export const FALL_EVALUATION_DETECTOR = {
  rule: "BrowserPoseRule/fall-v1",
  ruleSource: "apps/web/src/lib/browser-pose.ts",
  runtime: "@mediapipe/tasks-vision@0.10.32",
  worker: "/vision/pose-worker.js",
  model: "MediaPipe Pose Landmarker Lite float16/1",
  modelSha256: "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a",
} as const;

export const DEFAULT_FALL_EVALUATION_CASES: FallEvaluationCase[] = [
  {
    id: "fall-lateral",
    name: "Staged lateral fall",
    category: "fall",
    videoUrl: "/vision/samples/fall-lateral.mp4",
    expectedEvents: 1,
    eventStartSeconds: 5,
  },
  {
    id: "fall-forward",
    name: "Staged forward fall",
    category: "fall",
    videoUrl: "/vision/samples/fall-forward.mp4",
    expectedEvents: 1,
    eventStartSeconds: 6,
  },
  {
    id: "fall-backwards",
    name: "Staged backward fall",
    category: "fall",
    videoUrl: "/vision/samples/fall-backwards.mp4",
    expectedEvents: 1,
    eventStartSeconds: 6,
  },
  {
    id: "sitting",
    name: "Sitting down and standing up",
    category: "daily_activity",
    videoUrl: "/vision/samples/sitting.mp4",
    expectedEvents: 0,
  },
  {
    id: "bending",
    name: "Bending down and standing up",
    category: "daily_activity",
    videoUrl: "/vision/samples/bending.mp4",
    expectedEvents: 0,
  },
];

export function isCompleteFallEvaluation(
  results: FallEvaluationResult[],
  cases: FallEvaluationCase[] = DEFAULT_FALL_EVALUATION_CASES,
): boolean {
  if (results.length !== cases.length || cases.length === 0) return false;
  const byId = new Map(results.map((result) => [result.id, result]));
  return byId.size === cases.length && cases.every((definition) => {
    const result = byId.get(definition.id);
    return !!result && !result.error &&
      result.category === definition.category &&
      result.expectedEvents === definition.expectedEvents &&
      Number.isFinite(result.durationSeconds) && result.durationSeconds > 0 &&
      result.framesAnalyzed > 0;
  });
}

function ratio(numerator: number, denominator: number): number | null {
  return denominator > 0 ? numerator / denominator : null;
}

function mean(values: number[]): number | null {
  return values.length
    ? values.reduce((total, value) => total + value, 0) / values.length
    : null;
}

export function scoreFallEvaluation(
  results: FallEvaluationResult[],
): FallEvaluationSummary {
  let truePositives = 0;
  let falsePositives = 0;
  let trueNegatives = 0;
  let falseNegatives = 0;
  let negativeSeconds = 0;
  let falseAlerts = 0;
  let extraDetections = 0;
  const latencies: number[] = [];

  for (const result of results) {
    const expectedPositive = result.expectedEvents > 0;
    const detected = result.detectedAtSeconds.length > 0;
    if (expectedPositive && detected) truePositives += 1;
    else if (expectedPositive) falseNegatives += 1;
    else if (detected) falsePositives += 1;
    else trueNegatives += 1;

    if (!expectedPositive) {
      negativeSeconds += result.durationSeconds;
      falseAlerts += result.detectedAtSeconds.length;
    }
    extraDetections += Math.max(
      0,
      result.detectedAtSeconds.length - result.expectedEvents,
    );
    if (
      expectedPositive &&
      detected &&
      result.eventStartSeconds !== undefined
    ) {
      latencies.push(
        Math.max(0, result.detectedAtSeconds[0] - result.eventStartSeconds),
      );
    }
  }

  return {
    totalCases: results.length,
    passedCases: truePositives + trueNegatives,
    truePositives,
    falsePositives,
    trueNegatives,
    falseNegatives,
    precision: ratio(truePositives, truePositives + falsePositives),
    recall: ratio(truePositives, truePositives + falseNegatives),
    accuracy: ratio(
      truePositives + trueNegatives,
      Math.max(1, results.length),
    )!,
    falseAlertsPerHour:
      negativeSeconds > 0 ? falseAlerts / (negativeSeconds / 3600) : null,
    meanDetectionLatencySeconds: mean(latencies),
    totalDetections: results.reduce(
      (total, result) => total + result.detectedAtSeconds.length,
      0,
    ),
    extraDetections,
  };
}

export function buildFallEvaluationExport(
  status: FallEvaluationRunStatus,
  results: FallEvaluationResult[],
  generatedAt: string = new Date().toISOString(),
) {
  if (status !== "complete" || !isCompleteFallEvaluation(results)) {
    throw new Error("Only a completed five-clip evaluation can be exported.");
  }
  // This value is opt-in and public at build time; no server credentials enter
  // the browser bundle. Leave it null for builds without a known Git revision.
  const codeRevision = process.env.NEXT_PUBLIC_GIT_COMMIT_SHA?.trim() || null;
  return {
    schemaVersion: 1,
    status: "complete" as const,
    scoringUnit: "clip" as const,
    generatedAt,
    sampleIntervalSeconds: FALL_EVALUATION_SAMPLE_INTERVAL_SECONDS,
    provenance: {
      detector: FALL_EVALUATION_DETECTOR,
      codeRevision,
      codeRevisionSource: codeRevision ? "NEXT_PUBLIC_GIT_COMMIT_SHA" : null,
    },
    summary: scoreFallEvaluation(results),
    results,
    limitation:
      "Small staged benchmark; results do not establish medical or field reliability.",
  };
}

export function percentile(values: number[], percentileValue: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(
    sorted.length - 1,
    Math.max(0, Math.ceil((percentileValue / 100) * sorted.length) - 1),
  );
  return sorted[index];
}
