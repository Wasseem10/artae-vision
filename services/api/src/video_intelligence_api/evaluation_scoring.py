"""One-to-one temporal interval scoring for replay evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Any


@dataclass(frozen=True, slots=True)
class TemporalInterval:
    start_seconds: float
    end_seconds: float
    label: str = "event"
    detected_at_seconds: float | None = None
    confidence: float | None = None


def _intersection(left: TemporalInterval, right: TemporalInterval) -> float:
    return max(
        0.0,
        min(left.end_seconds, right.end_seconds) - max(left.start_seconds, right.start_seconds),
    )


def interval_iou(left: TemporalInterval, right: TemporalInterval) -> float:
    intersection = _intersection(left, right)
    union = max(left.end_seconds, right.end_seconds) - min(left.start_seconds, right.start_seconds)
    return intersection / union if union > 0 else 0.0


def _candidate_score(
    expected: TemporalInterval,
    predicted: TemporalInterval,
    *,
    minimum_iou: float,
    tolerance_seconds: float,
) -> float | None:
    if expected.label != predicted.label:
        return None
    iou = interval_iou(expected, predicted)
    if iou >= minimum_iou:
        return iou
    boundary_distance = min(
        abs(expected.start_seconds - predicted.start_seconds),
        abs(expected.end_seconds - predicted.end_seconds),
    )
    if boundary_distance <= tolerance_seconds:
        return max(0.0, 1.0 - boundary_distance / max(tolerance_seconds, 0.001)) * 0.01
    return None


def score_intervals(
    expected: list[TemporalInterval],
    predicted: list[TemporalInterval],
    *,
    minimum_iou: float = 0.1,
    tolerance_seconds: float = 1.0,
) -> dict[str, Any]:
    """Greedily match the strongest valid pairs and calculate detection metrics."""

    candidates: list[tuple[float, int, int]] = []
    for expected_index, expected_interval in enumerate(expected):
        for predicted_index, predicted_interval in enumerate(predicted):
            score = _candidate_score(
                expected_interval,
                predicted_interval,
                minimum_iou=minimum_iou,
                tolerance_seconds=tolerance_seconds,
            )
            if score is not None:
                candidates.append((score, expected_index, predicted_index))

    matched_expected: set[int] = set()
    matched_predicted: set[int] = set()
    matches: list[dict[str, Any]] = []
    latencies: list[float] = []
    for _overlap, expected_index, predicted_index in sorted(candidates, reverse=True):
        if expected_index in matched_expected or predicted_index in matched_predicted:
            continue
        matched_expected.add(expected_index)
        matched_predicted.add(predicted_index)
        expected_interval = expected[expected_index]
        predicted_interval = predicted[predicted_index]
        detected_at = (
            predicted_interval.detected_at_seconds
            if predicted_interval.detected_at_seconds is not None
            else predicted_interval.start_seconds
        )
        latency = detected_at - expected_interval.start_seconds
        latencies.append(latency)
        matches.append(
            {
                "expected_index": expected_index,
                "predicted_index": predicted_index,
                "iou": round(interval_iou(expected_interval, predicted_interval), 6),
                "latency_seconds": round(latency, 6),
            }
        )

    true_positives = len(matches)
    false_positives = len(predicted) - true_positives
    false_negatives = len(expected) - true_positives
    precision = true_positives / len(predicted) if predicted else (1.0 if not expected else 0.0)
    recall = true_positives / len(expected) if expected else (1.0 if not predicted else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "mean_latency_seconds": round(fmean(latencies), 6) if latencies else None,
        "matches": matches,
        "unmatched_expected_indices": sorted(set(range(len(expected))) - matched_expected),
        "unmatched_predicted_indices": sorted(set(range(len(predicted))) - matched_predicted),
        "minimum_iou": minimum_iou,
        "tolerance_seconds": tolerance_seconds,
    }
