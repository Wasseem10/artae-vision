"""Train a second causal pose-window candidate before opening CAUCAFall results.

UR Fall and GMDCSA-24 subjects 1-3 are training data; already examined
GMDCSA subject 4 selects one threshold. CAUCAFall is entirely untouched here.
The model is research-only and does not change the live alert rule.
"""

from __future__ import annotations

import hashlib
import json
import math
import runpy
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
UR = ROOT / "artifacts/urfall/evaluation.json"
GMD_DEV = ROOT / "artifacts/gmdcsa24/development-subjects-1-2.json"
GMD_EXAMINED = ROOT / "artifacts/gmdcsa24/evaluation.json"
OUTPUT = ROOT / "apps/web/src/lib/fall-window-model-v2.json"
PREDICTIONS = ROOT / "artifacts/gmdcsa24/pose-window-v2-dev-predictions.json"
legacy = runpy.run_path(str(ROOT / "scripts/train-pose-window-fall.py"))
FEATURE_NAMES = legacy["FEATURE_NAMES"]
features_for_trace = legacy["features_for_trace"]
clip_summary = legacy["clip_summary"]
predict_clip = legacy["predict_clip"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ur = json.loads(UR.read_text(encoding="utf-8"))
    dev = json.loads(GMD_DEV.read_text(encoding="utf-8"))
    examined = json.loads(GMD_EXAMINED.read_text(encoding="utf-8"))
    if (ur["status"] != "complete" or len(ur["results"]) != 70 or
        dev["status"] != "complete" or len(dev["results"]) != 80 or
        examined["status"] != "complete" or len(examined["results"]) != 80):
        raise ValueError("Expected complete UR and GMDCSA benchmark reports")
    training = ur["results"] + dev["results"] + [
        result for result in examined["results"] if result["subjectId"] == "subject-3"
    ]
    validation = [result for result in examined["results"] if result["subjectId"] == "subject-4"]
    if (len(training) != 193 or len(validation) != 37 or
        {result["subjectId"] for result in validation} != {"subject-4"}):
        raise ValueError("Unexpected development split")
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
    x = np.asarray(rows, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    if np.count_nonzero(y) < 100 or np.count_nonzero(1 - y) < 100:
        raise ValueError("Insufficient training windows")
    mean = x.mean(axis=0)
    scale = np.maximum(x.std(axis=0), 0.05)
    x = (x - mean) / scale
    sample_weights = np.where(y == 1, 0.5 / y.sum(), 0.5 / (1 - y).sum())
    weights = np.zeros(x.shape[1], dtype=np.float64)
    bias = 0.0
    for epoch in range(1600):
        z = np.clip(x @ weights + bias, -30, 30)
        probability = 1 / (1 + np.exp(-z))
        residual = sample_weights * (probability - y)
        rate = 0.8 / (1 + epoch / 400)
        weights -= rate * (x.T @ residual + 0.025 * weights)
        bias -= rate * residual.sum()
    model = {
        "schemaVersion": 1,
        "name": "PoseWindowLogistic/v2-more-subjects",
        "sampleIntervalSeconds": 0.1,
        "featureNames": FEATURE_NAMES,
        "mean": mean.round(8).tolist(),
        "scale": scale.round(8).tolist(),
        "weights": weights.round(8).tolist(),
        "bias": round(float(bias), 8),
        "minConsecutiveSamples": 2,
        "motionGate": {"drop": 0.07, "tilt": 0.15, "aspectRise": 0.2},
        "training": {
            "sources": ["UR Fall all 70", "GMDCSA-24 subjects 1-3"],
            "validation": "GMDCSA-24 subject 4, previously examined",
            "reserved": "CAUCAFall v4 all ten subjects; no detector outputs examined before freeze",
            "urReportSha256": sha256(UR),
            "gmdDevelopmentReportSha256": sha256(GMD_DEV),
            "gmdExaminedReportSha256": sha256(GMD_EXAMINED),
            "trainingClips": len(training),
            "trainingWindows": len(y),
            "positiveTrainingWindows": int(y.sum()),
        },
    }
    candidates = []
    for threshold in ([index / 100 for index in range(10, 91, 5)] +
                      [0.92, 0.94, 0.96, 0.97, 0.98, 0.99, 0.995]):
        candidates.append((threshold, clip_summary(validation, model, threshold)))
    allowed_fp = math.floor(sum(result["category"] != "fall" for result in validation) * 0.1)
    eligible = [item for item in candidates if item[1]["activitiesAlerted"] <= allowed_fp]
    if eligible:
        selected = max(eligible, key=lambda item: (item[1]["fallsDetected"], item[0]))
    else:
        selected = min(candidates, key=lambda item: (
            item[1]["activitiesAlerted"], -item[1]["fallsDetected"], -item[0]))
    model["threshold"] = selected[0]
    model["training"]["validationSummary"] = selected[1]
    model["training"]["validationThresholdCandidates"] = [
        {"threshold": threshold, **summary} for threshold, summary in candidates
    ]
    model["training"]["trainingClipSummary"] = clip_summary(training, model, selected[0])
    OUTPUT.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    PREDICTIONS.write_text(json.dumps({
        result["id"]: predict_clip(result, model, model["threshold"])
        for result in dev["results"] + examined["results"]
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "threshold": model["threshold"],
                      "train": model["training"]["trainingClipSummary"],
                      "validation": selected[1]}, indent=2))


if __name__ == "__main__":
    main()
