import windowModel from "./fall-window-model.json";
import windowModelV2 from "./fall-window-model-v2.json";

export type FallEvaluationCase = {
  id: string;
  name: string;
  category: "fall" | "daily_activity";
  partition?: "development" | "holdout";
  videoUrl: string;
  expectedEvents: number;
  eventStartSeconds?: number;
  frameCount?: number;
  sourceZipSha256?: string;
  sourceGitBlobSha1?: string;
  subjectId?: string;
  videoSha256?: string;
  sourceVideoSha256?: string;
  sourceFilename?: string;
  sourcePath?: string;
  fallingPeopleCount?: number;
  eventRanges?: { start: number; end: number }[];
};

export type FallPoseTrace = {
  seconds: number;
  y: number | null;
  verticality: number | null;
  aspect: number | null;
  phase: string;
};

/** Per-sampled-frame observations for diagnosing multi-person coverage and track continuity. */
export type FallObservationTrace = {
  seconds: number;
  rawPoseCount: number;
  usablePoseCount: number;
  primaryPosePresent: boolean;
  trackIds: number[];
};

export type FallEvaluationResult = FallEvaluationCase & {
  durationSeconds: number;
  framesAnalyzed: number;
  framesWithPose: number;
  detectedAtSeconds: number[];
  /** Session-local pose tracks for the four-pose browser pipeline. */
  multiPersonEvents?: { atSeconds: number; trackId: number }[];
  maxVisiblePeople?: number;
  trackIdsSeen?: number;
  observationTrace?: FallObservationTrace[];
  postureBaselineDetectedAtSeconds?: number[];
  windowModelDetectedAtSeconds?: number[];
  windowModelV2DetectedAtSeconds?: number[];
  poseTrace?: FallPoseTrace[];
  meanInferenceMs: number;
  p95InferenceMs: number;
  error?: string;
};

export type FallEvaluationDataset = {
  datasetId: string;
  source: string;
  citation: string;
  license: string;
  split: string;
  labelNote: string;
  sourceRevision?: string;
  sourceAnnotationSha256?: string;
  cases: FallEvaluationCase[];
};

export function parseFallEvaluationDataset(value: unknown): FallEvaluationDataset {
  if (!value || typeof value !== "object") throw new Error("Invalid dataset manifest");
  const candidate = value as Record<string, unknown>;
  const urfall = candidate.datasetId === "urfall-rgb-cam0-v1";
  const gmdcsa24 = candidate.datasetId === "gmdcsa24-v2.1";
  const caucafall = candidate.datasetId === "caucafall-v4-omnifall-labels-v3";
  const realbiomfall = candidate.datasetId === "realbiomfall-100-v3";
  const imuVideo = candidate.datasetId === "imu-video-fall-adl-v1";
  const mpfdd = candidate.datasetId === "mpfdd-github-available-v1";
  if (candidate.schemaVersion !== 1 || (!urfall && !gmdcsa24 && !caucafall && !realbiomfall && !imuVideo && !mpfdd) ||
      !Array.isArray(candidate.cases) || candidate.cases.length === 0 ||
      candidate.cases.length > (mpfdd ? 28 : urfall ? 70 : imuVideo ? 95 : caucafall || realbiomfall ? 100 : 160)) throw new Error("Invalid fall dataset manifest");
  const cases = candidate.cases as Array<Record<string, unknown>>;
  const ids = new Set<string>();
  for (const item of cases) {
    const positive = item.category === "fall";
    const urId = typeof item.id === "string" ? /^(fall|adl)-(\d{2})$/.exec(item.id) : null;
    const gmdId = typeof item.id === "string" ? /^gmd-s([1-4])-(fall|adl)-(\d{2})$/.exec(item.id) : null;
    const caucaId = typeof item.id === "string" ? /^cauca-s(10|[1-9])-(fall|adl)-(backwards|forward|left|right|sitting|hop|kneel|pickup|sitdown|walk)$/.exec(item.id) : null;
    const realbiomId = typeof item.id === "string" ? /^realbiom-fall-(\d{3})$/.exec(item.id) : null;
    const imuId = typeof item.id === "string" ? /^imu-(adl|fall)-(\d{3})$/.exec(item.id) : null;
    const mpfddId = typeof item.id === "string" ? /^mpfdd-s([1-4])-p([2-5])-f([0-5])-(adl|fall)-(\d+)$/.exec(item.id) : null;
    const validUrCase = urfall && urId &&
      item.videoUrl === `/vision/urfall/${item.id}-cam0-rgb.mp4` &&
      item.partition === (Number(urId[2]) <= 10 ? "development" : "holdout") &&
      Number.isInteger(item.frameCount) && (item.frameCount as number) > 0 &&
      typeof item.sourceZipSha256 === "string" && /^[a-f0-9]{64}$/.test(item.sourceZipSha256);
    const validGmdCase = gmdcsa24 && gmdId &&
      item.videoUrl === `/vision/gmdcsa24/Subject%20${gmdId[1]}/${gmdId[2] === "fall" ? "Fall" : "ADL"}/${gmdId[3]}.mp4` &&
      item.partition === (Number(gmdId[1]) <= 2 ? "development" : "holdout") &&
      item.subjectId === `subject-${gmdId[1]}` &&
      typeof item.sourceGitBlobSha1 === "string" && /^[a-f0-9]{40}$/.test(item.sourceGitBlobSha1);
    const caucaStems: Record<string, string> = {
      backwards: "FallBackwards", forward: "FallForward", left: "FallLeft",
      right: "FallRight", sitting: "FallSitting", hop: "Hop", kneel: "Kneel",
      pickup: "Pickupobject", sitdown: "SitDown", walk: "Walk",
    };
    const validCaucaCase = caucafall && caucaId &&
      item.videoUrl === `/vision/caucafall/Subject.${caucaId[1]}/${caucaStems[caucaId[3]]}S${caucaId[1]}.mp4` &&
      item.partition === "holdout" && item.subjectId === `subject-${caucaId[1]}` &&
      (caucaId[2] === "fall") === ["backwards", "forward", "left", "right", "sitting"].includes(caucaId[3]) &&
      typeof item.sourceVideoSha256 === "string" && /^[a-f0-9]{64}$/.test(item.sourceVideoSha256) &&
      Array.isArray(item.eventRanges) && item.eventRanges.length === (caucaId[2] === "fall" ? 1 : 0) &&
      item.eventRanges.every((range: { start: number; end: number }) =>
        Number.isFinite(range.start) && range.start >= 0 && Number.isFinite(range.end) && range.end > range.start) &&
      (caucaId[2] === "adl" || item.eventStartSeconds === item.eventRanges[0].start);
    const validRealbiomCase = realbiomfall && realbiomId &&
      Number(realbiomId[1]) >= 1 && Number(realbiomId[1]) <= 100 &&
      item.videoUrl === `/vision/realbiomfall/${item.id}.mp4` &&
      item.partition === "holdout" && item.category === "fall" &&
      typeof item.sourceFilename === "string" && /^[A-Za-z0-9_.-]+\.mp4$/.test(item.sourceFilename) &&
      typeof item.sourceVideoSha256 === "string" && /^[a-f0-9]{64}$/.test(item.sourceVideoSha256) &&
      typeof item.sourceZipSha256 === "string" && /^[a-f0-9]{64}$/.test(item.sourceZipSha256) &&
      item.eventStartSeconds === undefined && item.eventRanges === undefined;
    const imuSource = typeof item.sourcePath === "string" ?
      /^Daily_Activity_0([1-5])\/(walk|sit|dist_walk|fall_bwd|fall_fwd)_P0[1-4]_T0[1-5]_video\.mp4$/.exec(item.sourcePath) : null;
    const validImuCase = imuVideo && imuId && imuSource &&
      Number(imuId[2]) >= 1 && Number(imuId[2]) <= (imuId[1] === "fall" ? 35 : 60) &&
      ["walk", "sit", "dist_walk", "fall_bwd", "fall_fwd"][Number(imuSource[1]) - 1] === imuSource[2] &&
      (Number(imuSource[1]) >= 4) === (imuId[1] === "fall") &&
      item.category === (imuId[1] === "fall" ? "fall" : "daily_activity") &&
      item.videoUrl === `/vision/imuadlfall/${item.id}.mp4` &&
      item.partition === "holdout" &&
      typeof item.sourceGitBlobSha1 === "string" && /^[a-f0-9]{40}$/.test(item.sourceGitBlobSha1) &&
      typeof item.sourceVideoSha256 === "string" && /^[a-f0-9]{64}$/.test(item.sourceVideoSha256) &&
      item.eventStartSeconds === undefined && item.eventRanges === undefined;
    const mpfddSource = mpfddId ? `Scene_${mpfddId[1]}/S${mpfddId[1]}-P${mpfddId[2]}-F${mpfddId[3]}-${mpfddId[4].toUpperCase()}-${mpfddId[5]}.mp4` : "";
    const validMpfddCase = mpfdd && mpfddId &&
      item.sourcePath === mpfddSource &&
      item.videoUrl === `/vision/mpfdd/${mpfddSource}` &&
      item.partition === "holdout" &&
      item.category === (Number(mpfddId[3]) ? "fall" : "daily_activity") &&
      item.fallingPeopleCount === Number(mpfddId[3]) &&
      Number(mpfddId[3]) <= Number(mpfddId[2]) &&
      typeof item.sourceGitBlobSha1 === "string" && /^[a-f0-9]{40}$/.test(item.sourceGitBlobSha1) &&
      item.eventStartSeconds === undefined && item.eventRanges === undefined;
    if (typeof item.id !== "string" || (!validUrCase && !validGmdCase && !validCaucaCase && !validRealbiomCase && !validImuCase && !validMpfddCase) ||
        ids.has(item.id) || typeof item.name !== "string" ||
        item.name.length > 100 || (item.category !== "fall" && item.category !== "daily_activity") ||
        (urfall && urId?.[1] !== (positive ? "fall" : "adl")) ||
        (gmdcsa24 && gmdId?.[2] !== (positive ? "fall" : "adl")) ||
        (caucafall && caucaId?.[2] !== (positive ? "fall" : "adl")) ||
        (realbiomfall && !positive) ||
        item.expectedEvents !== (positive ? 1 : 0) ||
        (urfall && positive && item.eventStartSeconds === undefined) ||
        (item.eventStartSeconds !== undefined &&
          (!Number.isFinite(item.eventStartSeconds) || (item.eventStartSeconds as number) < 0)) ||
        typeof item.videoSha256 !== "string" || !/^[a-f0-9]{64}$/.test(item.videoSha256)) {
      throw new Error("Invalid fall case in manifest");
    }
    ids.add(item.id);
  }
  for (const key of ["source", "citation", "license", "split", "labelNote"] as const) {
    if (typeof candidate[key] !== "string" || candidate[key].length > 1000) {
      throw new Error("Invalid UR Fall provenance");
    }
  }
  if (gmdcsa24 && candidate.sourceRevision !== "5abac7693229900cf80f722e878fbb119211fc1c") {
    throw new Error("Invalid GMDCSA-24 source revision");
  }
  if (caucafall && (candidate.sourceRevision !==
        "mendeley-v4+omnifall-83572a37b9e3081df8c06a56874b1d1f2a19386c" ||
      candidate.sourceAnnotationSha256 !== "a5169d3e95b26080527265516d415d068a83c3dea4cddca8d0828a8d2345fd3a")) {
    throw new Error("Invalid CAUCAFall annotation provenance");
  }
  if (realbiomfall && candidate.sourceRevision !== "zenodo-11636174-v3") {
    throw new Error("Invalid RealBiomFall source revision");
  }
  if (imuVideo && candidate.sourceRevision !== "a895be0ed80a33b55363468c804a9e4d7af95b9c") {
    throw new Error("Invalid IMU-video source revision");
  }
  if (mpfdd && candidate.sourceRevision !== "ec6cbcd81ed27e745ba5f6918192d7ec302d31c2") {
    throw new Error("Invalid MPFDD source revision");
  }
  return candidate as FallEvaluationDataset;
}

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
  rule: "BrowserPoseRule/fall-v2",
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

export const BUILTIN_FALL_DATASET: FallEvaluationDataset = {
  datasetId: "umafall-staged-smoke-v1",
  source: "https://figshare.com/articles/dataset/UMA_ADL_FALL_Dataset_zip/4214283",
  citation: "Casilari E, Santoyo-Ramón JA. UMAFall: Fall Detection Dataset.",
  license: "CC BY 4.0",
  split: "Five same-source staged clips; smoke test only",
  labelNote: "Fall onset times are approximate manual labels.",
  cases: DEFAULT_FALL_EVALUATION_CASES,
};

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
      (definition.frameCount === undefined ||
        Math.abs(result.durationSeconds - definition.frameCount / 30) < 0.05) &&
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
  detector: "temporal" | "posture" | "window" | "windowV2" = "temporal",
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
    const detections = detector === "temporal" ? result.detectedAtSeconds :
      detector === "posture" ? result.postureBaselineDetectedAtSeconds ?? [] :
        detector === "window" ? result.windowModelDetectedAtSeconds ?? [] :
          result.windowModelV2DetectedAtSeconds ?? [];
    const expectedPositive = result.expectedEvents > 0;
    const detected = detections.length > 0;
    if (expectedPositive && detected) truePositives += 1;
    else if (expectedPositive) falseNegatives += 1;
    else if (detected) falsePositives += 1;
    else trueNegatives += 1;

    if (!expectedPositive) {
      negativeSeconds += result.durationSeconds;
      falseAlerts += detections.length;
    }
    extraDetections += Math.max(
      0,
      detections.length - result.expectedEvents,
    );
    if (
      expectedPositive &&
      detected &&
      result.eventStartSeconds !== undefined
    ) {
      latencies.push(
        Math.max(0, detections[0] - result.eventStartSeconds),
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
    totalDetections: results.reduce((total, result) => total + (
      detector === "temporal" ? result.detectedAtSeconds.length :
        detector === "posture" ? result.postureBaselineDetectedAtSeconds?.length ?? 0 :
          detector === "window" ? result.windowModelDetectedAtSeconds?.length ?? 0 :
            result.windowModelV2DetectedAtSeconds?.length ?? 0
    ), 0),
    extraDetections,
  };
}

export function buildFallEvaluationExport(
  status: FallEvaluationRunStatus,
  results: FallEvaluationResult[],
  generatedAt: string = new Date().toISOString(),
  dataset: FallEvaluationDataset = BUILTIN_FALL_DATASET,
) {
  if (status !== "complete" || !isCompleteFallEvaluation(results, dataset.cases)) {
    throw new Error("Only a completed evaluation can be exported.");
  }
  // This value is opt-in and public at build time; no server credentials enter
  // the browser bundle. Leave it null for builds without a known Git revision.
  const codeRevision = process.env.NEXT_PUBLIC_GIT_COMMIT_SHA?.trim() || null;
  return {
    schemaVersion: 3,
    status: "complete" as const,
    scoringUnit: "clip" as const,
    generatedAt,
    sampleIntervalSeconds: FALL_EVALUATION_SAMPLE_INTERVAL_SECONDS,
    dataset: {
      datasetId: dataset.datasetId,
      source: dataset.source,
      citation: dataset.citation,
      license: dataset.license,
      split: dataset.split,
      labelNote: dataset.labelNote,
      sourceRevision: dataset.sourceRevision ?? null,
      sourceAnnotationSha256: dataset.sourceAnnotationSha256 ?? null,
    },
    provenance: {
      detector: FALL_EVALUATION_DETECTOR,
      candidate: {
        name: windowModel.name,
        source: "apps/web/src/lib/fall-window-model.json",
        threshold: windowModel.threshold,
        training: windowModel.training,
      },
      candidateV2: {
        name: windowModelV2.name,
        source: "apps/web/src/lib/fall-window-model-v2.json",
        threshold: windowModelV2.threshold,
        training: windowModelV2.training,
      },
      codeRevision,
      codeRevisionSource: codeRevision ? "NEXT_PUBLIC_GIT_COMMIT_SHA" : null,
    },
    summary: scoreFallEvaluation(results),
    postureBaselineSummary: scoreFallEvaluation(results, "posture"),
    windowModelSummary: scoreFallEvaluation(results, "window"),
    windowModelV2Summary: scoreFallEvaluation(results, "windowV2"),
    partitions: (["development", "holdout"] as const).flatMap((partition) => {
      const subset = results.filter((result) => result.partition === partition);
      return subset.length ? [{
        name: partition,
        cases: subset.length,
        summary: scoreFallEvaluation(subset),
        postureBaselineSummary: scoreFallEvaluation(subset, "posture"),
        windowModelSummary: scoreFallEvaluation(subset, "window"),
        windowModelV2Summary: scoreFallEvaluation(subset, "windowV2"),
      }] : [];
    }),
    results,
    limitation:
      "Staged research footage does not establish medical or field reliability; clip-level classification is distinct from event-level accuracy.",
  };
}

export function buildMultiPersonFallEvaluationExport(
  status: FallEvaluationRunStatus,
  results: FallEvaluationResult[],
  generatedAt: string = new Date().toISOString(),
  dataset: FallEvaluationDataset = BUILTIN_FALL_DATASET,
) {
  const base = buildFallEvaluationExport(status, results, generatedAt, dataset);
  return {
    ...base,
    schemaVersion: 4,
    provenance: {
      ...base.provenance,
      detector: {
        ...FALL_EVALUATION_DETECTOR,
        rule: "FusedMultiPersonFallRule/fall-v1",
        trackerSource: "apps/web/src/lib/multi-person-fall.ts",
        maxPoses: 4,
      },
    },
    postureBaselineSummary: null,
    windowModelSummary: null,
    windowModelV2Summary: null,
    partitions: (["development", "holdout"] as const).flatMap((partition) => {
      const subset = results.filter((result) => result.partition === partition);
      return subset.length ? [{ name: partition, cases: subset.length, summary: scoreFallEvaluation(subset) }] : [];
    }),
    limitation: "Single-person staged research clips measure detector regression, not multi-person identity accuracy or field reliability. Event tracks are session-only.",
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
