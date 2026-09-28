"""Fit a small causal pose-window classifier; keep GMDCSA subjects 3-4 unseen.

Requires numpy. Uses all previously examined UR Fall clips plus GMDCSA subject 1
for training; subject 2 chooses one fixed threshold. The exported weights are
for research evaluation, not a validated safety product.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
FEATURE_NAMES = [
    "y", "verticality", "aspect", "drop_0.3s", "drop_0.7s",
    "tilt_0.3s", "tilt_0.7s", "aspect_rise_0.3s",
    "aspect_rise_0.7s", "drop_from_recent_min", "pose_coverage_1s",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frame_features(history: list[dict], current: dict) -> list[float] | None:
    if current["y"] is None or current["verticality"] is None or current["aspect"] is None:
        return None
    t = current["seconds"]
    recent = [frame for frame in history if t - frame["seconds"] <= 1.0]
    valid = [frame for frame in recent if frame["y"] is not None and
             frame["verticality"] is not None and frame["aspect"] is not None]
    if not valid:
        return None

    def prior(lag: float) -> dict:
        earlier = [frame for frame in valid if frame["seconds"] <= t - lag + 1e-6]
        return earlier[-1] if earlier else valid[0]

    p03, p07 = prior(0.3), prior(0.7)
    aspect = min(float(current["aspect"]), 3.0)
    return [
        float(current["y"]), float(current["verticality"]), aspect,
        float(current["y"] - p03["y"]), float(current["y"] - p07["y"]),
        float(p03["verticality"] - current["verticality"]),
        float(p07["verticality"] - current["verticality"]),
        float(aspect - min(p03["aspect"], 3.0)),
        float(aspect - min(p07["aspect"], 3.0)),
        float(current["y"] - min(frame["y"] for frame in valid)),
        len(valid) / max(1, len(recent)),
    ]


def features_for_trace(trace: list[dict]) -> list[list[float] | None]:
    history: list[dict] = []
    output = []
    previous_time = -math.inf
    missing_since = None
    for frame in trace:
        t = frame["seconds"]
        if t <= previous_time or t - previous_time > 1:
            history = []
            missing_since = None
        if frame["y"] is None:
            if missing_since is None:
                missing_since = t
        elif missing_since is not None:
            if t - missing_since > 0.3:
                history = []
            missing_since = None
        history = [entry for entry in history if t - entry["seconds"] <= 1.0]
        history.append(frame)
        output.append(frame_features(history, frame))
        previous_time = t
    return output


def motion_seen(features: list[float]) -> bool:
    return (max(features[3], features[4]) > 0.07 or
            max(features[5], features[6]) > 0.15 or
            max(features[7], features[8]) > 0.2)


def predict_clip(result: dict, model: dict, threshold: float) -> list[float]:
    mean = np.array(model["mean"])
    scale = np.array(model["scale"])
    weights = np.array(model["weights"])
    detections = []
    consecutive = 0
    previous_time = -math.inf
    last_alert = -math.inf
    for frame, features in zip(result["poseTrace"], features_for_trace(result["poseTrace"])):
        t = frame["seconds"]
        if t <= previous_time or t - previous_time > 1:
            consecutive = 0
        previous_time = t
        if features is None or not motion_seen(features):
            consecutive = 0
            continue
        z = np.dot((np.array(features) - mean) / scale, weights) + model["bias"]
        probability = 1 / (1 + math.exp(-float(np.clip(z, -30, 30))))
        consecutive = consecutive + 1 if probability >= threshold else 0
        if consecutive >= 2 and t - last_alert > 10:
            detections.append(t)
            last_alert = t
            consecutive = 0
    return detections


def clip_summary(results: list[dict], model: dict, threshold: float) -> dict:
    tp = fp = tn = fn = 0
    for result in results:
        detected = bool(predict_clip(result, model, threshold))
        positive = result["category"] == "fall"
        if positive and detected:
            tp += 1
        elif positive:
            fn += 1
        elif detected:
            fp += 1
        else:
            tn += 1
    return {"fallsDetected": tp, "fallsMissed": fn,
            "activitiesAlerted": fp, "activitiesSilent": tn}


def train(ur_path: Path, gmd_path: Path) -> dict:
    ur_report = json.loads(ur_path.read_text(encoding="utf-8"))
    gmd_report = json.loads(gmd_path.read_text(encoding="utf-8"))
    if ur_report["status"] != "complete" or len(ur_report["results"]) != 70:
        raise ValueError("Expected the complete, previously examined UR Fall report")
    if gmd_report["status"] != "complete" or len(gmd_report["results"]) != 80 or any(
        result.get("partition") != "development" for result in gmd_report["results"]
    ):
        raise ValueError("GMDCSA training input must contain subjects 1-2 only")
    training = ur_report["results"] + [result for result in gmd_report["results"]
                                           if result.get("subjectId") == "subject-1"]
    validation = [result for result in gmd_report["results"]
                  if result.get("subjectId") == "subject-2"]
    rows, labels = [], []
    for result in training:
        onset = result.get("eventStartSeconds")
        for frame, features in zip(result["poseTrace"], features_for_trace(result["poseTrace"])):
            if features is None:
                continue
            t = frame["seconds"]
            if result["category"] == "fall":
                if onset is None or onset - 0.15 <= t < onset + 0.1 or t > onset + 1.8:
                    continue
                label = int(t >= onset + 0.1)
            else:
                label = 0
            rows.append(features)
            labels.append(label)
    x = np.array(rows, dtype=np.float64)
    y = np.array(labels, dtype=np.float64)
    if np.count_nonzero(y) < 100 or np.count_nonzero(1 - y) < 100:
        raise ValueError("Insufficient training windows")
    mean = x.mean(axis=0)
    scale = np.maximum(x.std(axis=0), 0.05)
    x = (x - mean) / scale
    sample_weights = np.where(y == 1, 0.5 / y.sum(), 0.5 / (1 - y).sum())
    weights = np.zeros(x.shape[1], dtype=np.float64)
    bias = 0.0
    # Deterministic full-batch logistic regression with L2 shrinkage.
    for epoch in range(1600):
        z = np.clip(x @ weights + bias, -30, 30)
        probability = 1 / (1 + np.exp(-z))
        residual = sample_weights * (probability - y)
        rate = 0.8 / (1 + epoch / 400)
        weights -= rate * (x.T @ residual + 0.025 * weights)
        bias -= rate * residual.sum()
    model = {
        "schemaVersion": 1,
        "name": "PoseWindowLogistic/v1",
        "sampleIntervalSeconds": 0.1,
        "featureNames": FEATURE_NAMES,
        "mean": mean.round(8).tolist(),
        "scale": scale.round(8).tolist(),
        "weights": weights.round(8).tolist(),
        "bias": round(float(bias), 8),
        "minConsecutiveSamples": 2,
        "motionGate": {"drop": 0.07, "tilt": 0.15, "aspectRise": 0.2},
        "training": {
            "sources": ["UR Fall all 70, previously examined", "GMDCSA-24 subject 1"],
            "validation": "GMDCSA-24 subject 2",
            "reserved": "GMDCSA-24 subjects 3-4, no detector outputs examined before freeze",
            "urReportSha256": sha256(ur_path),
            "gmdDevelopmentReportSha256": sha256(gmd_path),
            "trainingWindows": len(y),
            "positiveTrainingWindows": int(y.sum()),
        },
    }
    candidates = []
    for threshold in ([index / 100 for index in range(10, 91, 5)] +
                      [0.92, 0.94, 0.96, 0.97, 0.98, 0.99, 0.995]):
        summary = clip_summary(validation, model, threshold)
        candidates.append((threshold, summary))
    # Fixed selection rule: allow at most 10% of subject-2 ADL clips to alert,
    # then maximize detected fall clips, breaking ties toward higher threshold.
    negative_count = sum(result["category"] != "fall" for result in validation)
    allowed_fp = math.floor(negative_count * 0.1)
    eligible = [item for item in candidates if item[1]["activitiesAlerted"] <= allowed_fp]
    if eligible:
        selected = max(eligible, key=lambda item: (item[1]["fallsDetected"], item[0]))
    else:
        selected = min(candidates, key=lambda item: (item[1]["activitiesAlerted"],
                                                      -item[1]["fallsDetected"], -item[0]))
    model["threshold"] = selected[0]
    model["training"]["validationSummary"] = selected[1]
    model["training"]["validationThresholdCandidates"] = [
        {"threshold": threshold, **summary} for threshold, summary in candidates
    ]
    model["training"]["trainingClipSummary"] = clip_summary(training, model, selected[0])
    return model


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ur-report", type=Path, default=ROOT / "artifacts/urfall/evaluation.json")
    parser.add_argument("--gmd-report", type=Path, default=ROOT / "artifacts/gmdcsa24/evaluation.json")
    parser.add_argument("--output", type=Path, default=ROOT / "apps/web/src/lib/fall-window-model.json")
    parser.add_argument("--predictions-output", type=Path,
                        default=ROOT / "artifacts/gmdcsa24/pose-window-dev-predictions.json")
    args = parser.parse_args()
    model = train(args.ur_report, args.gmd_report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    development = json.loads(args.gmd_report.read_text(encoding="utf-8"))["results"]
    args.predictions_output.parent.mkdir(parents=True, exist_ok=True)
    args.predictions_output.write_text(json.dumps({
        result["id"]: predict_clip(result, model, model["threshold"])
        for result in development
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "threshold": model["threshold"],
                      "train": model["training"]["trainingClipSummary"],
                      "validation": model["training"]["validationSummary"]}, indent=2))
