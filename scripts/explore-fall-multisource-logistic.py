"""Exploratory leave-one-source-out pose fit; all inputs were already examined.

Requires numpy. Outputs are development diagnostics, not a promotion gate or
fresh-source accuracy estimate. No model weights are exported for live use.
"""

import json
import math
import runpy
from pathlib import Path

import numpy as np

root = Path(__file__).resolve().parents[1]
legacy = runpy.run_path(str(root / "scripts/train-pose-window-fall.py"))
features_for_trace = legacy["features_for_trace"]
predict_clip = legacy["predict_clip"]
sources = {
    "ur": [root / "artifacts/urfall/evaluation.json"],
    "gmd": [root / "artifacts/gmdcsa24/development-subjects-1-2.json", root / "artifacts/gmdcsa24/evaluation.json"],
    "cauca": [root / "artifacts/caucafall/evaluation.json"],
}
data = {name: sum((json.loads(path.read_text())["results"] for path in paths), []) for name, paths in sources.items()}


def rows_for(names):
    x, y, weights = [], [], []
    for name in names:
        clips = data[name]
        for clip in clips:
            windows = []
            onset = clip.get("eventStartSeconds")
            ranges = clip.get("eventRanges") or []
            end = min(clip["durationSeconds"], ranges[0]["end"] + 1 if ranges else (onset or 0) + 1.8)
            for frame, features in zip(clip["poseTrace"], features_for_trace(clip["poseTrace"])):
                if features is None:
                    continue
                t = frame["seconds"]
                if clip["category"] == "fall":
                    if onset is None or onset - .15 <= t < onset + .1 or t > end:
                        continue
                    label = int(t >= onset + .1)
                else:
                    label = 0
                windows.append((features, label))
            if not windows:
                continue
            positives = sum(label for _, label in windows)
            negatives = len(windows) - positives
            for features, label in windows:
                x.append(features)
                y.append(label)
                contribution = (1 / len(names)) * (1 / len(clips))
                if positives:
                    contribution *= .5 / positives if label else .5 / negatives
                else:
                    contribution /= negatives
                weights.append(contribution)
    x, y, weights = np.asarray(x), np.asarray(y), np.asarray(weights)
    for label in (0, 1):
        mask = y == label
        weights[mask] *= .5 / weights[mask].sum()
    return x, y, weights


def fit(names):
    x, y, weights = rows_for(names)
    mean = x.mean(axis=0)
    scale = np.maximum(x.std(axis=0), .05)
    x = (x - mean) / scale
    coefficients = np.zeros(x.shape[1])
    bias = 0.0
    for epoch in range(1200):
        scores = np.clip(x @ coefficients + bias, -30, 30)
        residual = weights * (1 / (1 + np.exp(-scores)) - y)
        rate = .8 / (1 + epoch / 400)
        coefficients -= rate * (x.T @ residual + .025 * coefficients)
        bias -= rate * residual.sum()
    return {"mean": mean.tolist(), "scale": scale.tolist(), "weights": coefficients.tolist(), "bias": bias}


def score(clips, model, threshold):
    fall_hit = fall_count = adl_hit = adl_count = 0
    for clip in clips:
        detected = predict_clip(clip, model, threshold)
        if clip["category"] == "fall":
            fall_count += 1
            start = clip.get("eventStartSeconds")
            ranges = clip.get("eventRanges") or []
            end = min(clip["durationSeconds"], ranges[0]["end"] + 2) if ranges else clip["durationSeconds"]
            fall_hit += any((start or 0) <= t <= end for t in detected)
        else:
            adl_count += 1
            adl_hit += bool(detected)
    return f"{fall_hit}/{fall_count} falls; {adl_hit}/{adl_count} ADL clips"


for held in data:
    train = [name for name in data if name != held]
    model = fit(train)
    print("HELD", held, "TRAIN", train, flush=True)
    for threshold in (.8, .9, .95, .98, .995):
        print(threshold, "held", score(data[held], model, threshold),
              "train", score(sum((data[name] for name in train), []), model, threshold), flush=True)

model = fit(list(data))
print("ALL SOURCE FIT", flush=True)
for threshold in (.8, .9, .95, .98, .995):
    print(threshold, *(f"{name}: {score(clips, model, threshold)}" for name, clips in data.items()), flush=True)
