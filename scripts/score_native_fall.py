"""Score native fall replay candidates against a separate adjudicated label manifest.

This scores finite, fully reviewed clips. It does not establish field reliability
or include camera, network, notification, and human-response failures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _nonnegative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a finite nonnegative number")
    return number


def _positive_float(value: str) -> float:
    number = _nonnegative_float(value)
    if number == 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument(
        "--output", type=Path, help="Write JSON here; default is stdout"
    )
    parser.add_argument(
        "--max-alert-delay-seconds",
        required=True,
        type=_positive_float,
        help="Predeclared latest acceptable candidate time after visible fall onset",
    )
    parser.add_argument(
        "--early-tolerance-seconds",
        type=_nonnegative_float,
        default=0.0,
        help="Predeclared allowed candidate time before visible fall onset (default: 0)",
    )
    parser.add_argument(
        "--minimum-falls",
        required=True,
        type=_positive_int,
        help="Predeclared minimum labeled falls for an adequately sized recall sample",
    )
    parser.add_argument(
        "--minimum-analyzed-hours",
        required=True,
        type=_positive_float,
        help="Predeclared minimum analyzed exposure for a false-alert-rate sample",
    )
    return parser.parse_args(argv)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{context} must be an object")
    return value


def _list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{context} must be an array")
    return value


def _number(value: Any, context: str, *, allow_zero: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{context} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0 or (not allow_zero and number == 0):
        raise ValueError(
            f"{context} must be finite and {'positive' if not allow_zero else 'nonnegative'}"
        )
    return number


def _count(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{context} must be a nonnegative integer")
    return value


def _digest(value: Any, context: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{context} must be a lowercase SHA-256 hex digest")
    return value


def _interval(value: Any, duration: float, context: str) -> tuple[float, float]:
    data = _object(value, context)
    start = _number(data.get("start_seconds"), f"{context}.start_seconds")
    end = _number(data.get("end_seconds"), f"{context}.end_seconds")
    if not start < end <= duration + 1e-6:
        raise ValueError(f"{context} must satisfy 0 <= start < end <= clip duration")
    return start, min(end, duration)


def _indexed_clips(clips: Any, source: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(_list(clips, f"{source}.clips")):
        context = f"{source}.clips[{index}]"
        clip = _object(item, context)
        digest = _digest(clip.get("clip_sha256"), f"{context}.clip_sha256")
        if digest in indexed:
            raise ValueError(f"Duplicate clip SHA-256 in {source}: {digest}")
        indexed[digest] = clip
    if not indexed:
        raise ValueError(f"{source} must contain at least one clip")
    return indexed


def _maximum_matching(
    fall_onsets: list[float],
    candidate_times: list[float],
    *,
    max_delay: float,
    early_tolerance: float,
) -> list[tuple[int, int]]:
    """Maximum-cardinality one-to-one match with deterministic nearest-first edges."""
    edges = [
        sorted(
            (
                candidate_index
                for candidate_index, detected_at in enumerate(candidate_times)
                if onset - early_tolerance - 1e-9
                <= detected_at
                <= onset + max_delay + 1e-9
            ),
            key=lambda index: (abs(candidate_times[index] - onset), index),
        )
        for onset in fall_onsets
    ]
    matched_to_fall: dict[int, int] = {}

    def augment(fall_index: int, seen: set[int]) -> bool:
        for candidate_index in edges[fall_index]:
            if candidate_index in seen:
                continue
            seen.add(candidate_index)
            previous_fall = matched_to_fall.get(candidate_index)
            if previous_fall is None or augment(previous_fall, seen):
                matched_to_fall[candidate_index] = fall_index
                return True
        return False

    for fall_index in range(len(fall_onsets)):
        augment(fall_index, set())
    return sorted(
        (
            (fall_index, candidate_index)
            for candidate_index, fall_index in matched_to_fall.items()
        ),
        key=lambda pair: pair[0],
    )


def _percentile_nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def _union_duration(intervals: list[tuple[float, float]]) -> float:
    total = 0.0
    end = 0.0
    for start, stop in sorted(intervals):
        if stop > end:
            total += stop - max(start, end)
            end = stop
    return total


def _binomial_cdf(count: int, trials: int, probability: float) -> float:
    """P(X <= count) for a binomial variable, summing from count downward."""
    if probability <= 0:
        return 1.0
    if probability >= 1:
        return 1.0 if count >= trials else 0.0
    log_term = (
        math.lgamma(trials + 1)
        - math.lgamma(count + 1)
        - math.lgamma(trials - count + 1)
        + count * math.log(probability)
        + (trials - count) * math.log1p(-probability)
    )
    term = math.exp(log_term)
    terms = [term]
    for successes in range(count, 0, -1):
        term *= successes * (1 - probability) / ((trials - successes + 1) * probability)
        terms.append(term)
    return min(1.0, math.fsum(terms))


def _poisson_cdf(count: int, mean: float) -> float:
    """P(X <= count) for a Poisson variable, summing from count downward."""
    if mean <= 0:
        return 1.0
    term = math.exp(-mean + count * math.log(mean) - math.lgamma(count + 1))
    terms = [term]
    for events in range(count, 0, -1):
        term *= events / mean
        terms.append(term)
    return min(1.0, math.fsum(terms))


def _decreasing_cdf_bracket(
    target: float, lower: float, upper: float, cdf: Callable[[float], float]
) -> tuple[float, float]:
    """Bracket the inverse; choose outer endpoints for conservative bounds."""
    for _ in range(80):
        middle = (lower + upper) / 2
        if middle == lower or middle == upper:
            break
        if cdf(middle) > target:
            lower = middle
        else:
            upper = middle
    return lower, upper


def _clopper_pearson_95(successes: int, trials: int) -> tuple[float, float] | None:
    if trials == 0:
        return None
    tail = 0.025
    lower = (
        _decreasing_cdf_bracket(
            1 - tail,
            0.0,
            1.0,
            lambda probability: _binomial_cdf(successes - 1, trials, probability),
        )[0]
        if successes
        else 0.0
    )
    upper = (
        _decreasing_cdf_bracket(
            tail,
            0.0,
            1.0,
            lambda probability: _binomial_cdf(successes, trials, probability),
        )[1]
        if successes < trials
        else 1.0
    )
    return lower, upper


def _poisson_rate_95(events: int, exposure_hours: float) -> tuple[float, float] | None:
    if exposure_hours <= 0:
        return None
    tail = 0.025
    if events:
        lower_count = _decreasing_cdf_bracket(
            1 - tail,
            0.0,
            float(events),
            lambda mean: _poisson_cdf(events - 1, mean),
        )[0]
    else:
        lower_count = 0.0
    upper_ceiling = float(events * 2 + 10)
    while _poisson_cdf(events, upper_ceiling) > tail:
        upper_ceiling *= 2
    upper_count = _decreasing_cdf_bracket(
        tail,
        0.0,
        upper_ceiling,
        lambda mean: _poisson_cdf(events, mean),
    )[1]
    return lower_count / exposure_hours, upper_count / exposure_hours


def _outward_rounded_interval(
    bounds: tuple[float, float] | None, method: str
) -> dict[str, float | str | None]:
    if bounds is None:
        return {"lower": None, "upper": None, "method": method}
    scale = 1_000_000
    return {
        "lower": math.floor(bounds[0] * scale) / scale,
        "upper": math.ceil(bounds[1] * scale) / scale,
        "method": method,
    }


def build_report(
    candidates: dict[str, Any],
    labels: dict[str, Any],
    *,
    max_alert_delay_seconds: float,
    early_tolerance_seconds: float,
    minimum_falls: int,
    minimum_analyzed_hours: float,
    candidate_sha256: str | None = None,
    label_sha256: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if (
        candidates.get("schema_version") != 1
        or candidates.get("kind") != "native_fall_candidate_baseline"
    ):
        raise ValueError(
            "Candidates must be a schema-v1 native_fall_candidate_baseline report"
        )
    if (
        labels.get("schema_version") != 1
        or labels.get("kind") != "native_fall_ground_truth"
    ):
        raise ValueError("Labels must be a schema-v1 native_fall_ground_truth manifest")
    if labels.get("review_status") != "independently_adjudicated":
        raise ValueError("Labels must have review_status=independently_adjudicated")
    role = labels.get("dataset_role")
    if role not in {"staged_regression", "held_out", "field"}:
        raise ValueError(
            "Labels need dataset_role=staged_regression, held_out, or field"
        )
    if (
        not isinstance(labels.get("dataset_name"), str)
        or not labels["dataset_name"].strip()
    ):
        raise ValueError("Labels need a nonempty dataset_name")
    if labels.get("dataset_name") != candidates.get("dataset_name"):
        raise ValueError("Candidate and label dataset_name values differ")
    if (
        candidates.get("execution_path")
        != "video_intelligence_inference.replay.run_replay:specialized_pose"
    ):
        raise ValueError(
            "Candidates must come from the native specialized_pose replay path"
        )
    model_sha256 = _digest(
        _object(candidates.get("provenance"), "candidates.provenance").get(
            "model_sha256"
        ),
        "candidates.provenance.model_sha256",
    )
    for name, value in (
        ("max_alert_delay_seconds", max_alert_delay_seconds),
        ("minimum_analyzed_hours", minimum_analyzed_hours),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if not math.isfinite(early_tolerance_seconds) or early_tolerance_seconds < 0:
        raise ValueError("early_tolerance_seconds must be finite and nonnegative")
    if (
        isinstance(minimum_falls, bool)
        or not isinstance(minimum_falls, int)
        or minimum_falls < 1
    ):
        raise ValueError("minimum_falls must be a positive integer")

    candidate_clips = _indexed_clips(candidates.get("results"), "candidates")
    label_clips = _indexed_clips(labels.get("clips"), "labels")
    if candidate_clips.keys() != label_clips.keys():
        missing = sorted(candidate_clips.keys() - label_clips.keys())
        extra = sorted(label_clips.keys() - candidate_clips.keys())
        raise ValueError(
            f"Clip SHA-256 sets differ: missing labels={missing}, extra labels={extra}"
        )
    if _count(candidates.get("total_clips"), "candidates.total_clips") != len(
        candidate_clips
    ):
        raise ValueError("Candidate total_clips does not match results")

    clip_reports: list[dict[str, Any]] = []
    total_falls = total_candidates = true_positives = 0
    total_seconds = total_nonfall_seconds = negative_clip_seconds = 0.0
    latencies: list[float] = []
    for digest, candidate_clip in candidate_clips.items():
        label_clip = label_clips[digest]
        context = f"clip {digest[:12]}"
        if label_clip.get("reviewed_full_duration") is not True:
            raise ValueError(f"{context} must have reviewed_full_duration=true")
        duration = _number(
            candidate_clip.get("duration_seconds"),
            f"{context}.duration_seconds",
            allow_zero=False,
        )
        labeled_duration = _number(
            label_clip.get("duration_seconds"),
            f"{context}.label_duration_seconds",
            allow_zero=False,
        )
        if abs(duration - labeled_duration) > 0.001:
            raise ValueError(f"{context} label and replay durations differ")
        source_frames = _count(
            candidate_clip.get("source_frame_count"), f"{context}.source_frame_count"
        )
        processed_frames = _count(
            candidate_clip.get("frames_processed"), f"{context}.frames_processed"
        )
        if source_frames == 0 or processed_frames != source_frames:
            raise ValueError(f"{context} replay did not process every source frame")
        if (
            _count(
                candidate_clip.get("provider_requests"), f"{context}.provider_requests"
            )
            != 0
        ):
            raise ValueError(f"{context} unexpectedly used provider requests")
        falls = [
            _interval(item, duration, f"{context}.falls[{index}]")
            for index, item in enumerate(
                _list(label_clip.get("falls"), f"{context}.falls")
            )
        ]
        predicted = _list(
            candidate_clip.get("candidate_intervals"), f"{context}.candidate_intervals"
        )
        candidate_times: list[float] = []
        for index, item in enumerate(predicted):
            interval = _object(item, f"{context}.candidate_intervals[{index}]")
            _interval(interval, duration, f"{context}.candidate_intervals[{index}]")
            if interval.get("label") != "event":
                raise ValueError(f"{context} candidate interval label must be event")
            detected_at = _number(
                interval.get("detected_at_seconds"),
                f"{context}.candidate_intervals[{index}].detected_at_seconds",
            )
            if detected_at > duration + 1e-6:
                raise ValueError(f"{context} candidate time exceeds clip duration")
            candidate_times.append(detected_at)
        if _count(
            candidate_clip.get("candidate_count"), f"{context}.candidate_count"
        ) != len(predicted):
            raise ValueError(f"{context} candidate_count does not match intervals")
        recorded_times = _list(
            candidate_clip.get("candidate_times_seconds"),
            f"{context}.candidate_times_seconds",
        )
        if len(recorded_times) != len(candidate_times) or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or abs(value - time) > 1e-6
            for value, time in zip(recorded_times, candidate_times)
        ):
            raise ValueError(f"{context} candidate timestamps do not match intervals")

        matches = _maximum_matching(
            [start for start, _end in falls],
            candidate_times,
            max_delay=max_alert_delay_seconds,
            early_tolerance=early_tolerance_seconds,
        )
        matched_candidates = {candidate_index for _, candidate_index in matches}
        matched_falls = {fall_index for fall_index, _ in matches}
        clip_latencies = [
            round(candidate_times[candidate_index] - falls[fall_index][0], 6)
            for fall_index, candidate_index in matches
        ]
        latencies.extend(clip_latencies)
        clip_reports.append(
            {
                "clip_sha256": digest,
                "clip_name": candidate_clip.get("clip_name"),
                "duration_seconds": round(duration, 6),
                "labeled_falls": len(falls),
                "candidates": len(candidate_times),
                "true_positives": len(matches),
                "false_alerts": len(candidate_times) - len(matches),
                "missed_falls": len(falls) - len(matches),
                "matches": [
                    {
                        "fall_index": fall_index,
                        "candidate_index": candidate_index,
                        "latency_seconds": latency,
                    }
                    for (fall_index, candidate_index), latency in zip(
                        matches, clip_latencies
                    )
                ],
                "unmatched_fall_indices": sorted(
                    set(range(len(falls))) - matched_falls
                ),
                "unmatched_candidate_indices": sorted(
                    set(range(len(candidate_times))) - matched_candidates
                ),
            }
        )
        total_seconds += duration
        total_nonfall_seconds += duration - _union_duration(falls)
        if not falls:
            negative_clip_seconds += duration
        total_falls += len(falls)
        total_candidates += len(candidate_times)
        true_positives += len(matches)

    if (
        _count(candidates.get("total_candidates"), "candidates.total_candidates")
        != total_candidates
    ):
        raise ValueError("Candidate total_candidates does not match results")
    false_alerts = total_candidates - true_positives
    missed_falls = total_falls - true_positives
    analyzed_hours = total_seconds / 3600
    recall_status = (
        "unmeasured"
        if total_falls == 0
        else "insufficient_data"
        if total_falls < minimum_falls
        else "sample_size_met"
    )
    false_alert_status = (
        "unmeasured"
        if analyzed_hours == 0
        else "insufficient_data"
        if analyzed_hours < minimum_analyzed_hours
        else "sample_size_met"
    )
    latency_status = (
        "unmeasured"
        if not latencies
        else "insufficient_data"
        if len(latencies) < minimum_falls
        else "sample_size_met"
    )
    return {
        "schema_version": 1,
        "kind": "native_fall_event_score",
        "generated_at_utc": generated_at or datetime.now(timezone.utc).isoformat(),
        "dataset_name": labels["dataset_name"],
        "dataset_role": role,
        "input_sha256": {
            "candidates_json": candidate_sha256,
            "labels_json": label_sha256,
            "model": model_sha256,
        },
        "matching": {
            "method": "maximum_cardinality_one_to_one_onset_window",
            "max_alert_delay_seconds": max_alert_delay_seconds,
            "early_tolerance_seconds": early_tolerance_seconds,
        },
        "minimum_sample": {
            "falls": minimum_falls,
            "analyzed_hours": minimum_analyzed_hours,
        },
        "exposure": {
            "clips": len(clip_reports),
            "analyzed_seconds": round(total_seconds, 6),
            "analyzed_hours": round(analyzed_hours, 6),
            "nonfall_hours": round(total_nonfall_seconds / 3600, 6),
            "negative_clip_hours": round(negative_clip_seconds / 3600, 6),
            "scheduled_hours": None,
        },
        "counts": {
            "labeled_falls": total_falls,
            "candidates": total_candidates,
            "true_positives": true_positives,
            "false_alerts": false_alerts,
            "missed_falls": missed_falls,
        },
        "recall": {
            "value": round(true_positives / total_falls, 6) if total_falls else None,
            "status": recall_status,
            "confidence_interval_95": _outward_rounded_interval(
                _clopper_pearson_95(true_positives, total_falls),
                "clopper_pearson_exact_equal_tail",
            ),
        },
        "false_alerts_per_analyzed_hour": {
            "value": round(false_alerts / analyzed_hours, 6)
            if analyzed_hours
            else None,
            "status": false_alert_status,
            "confidence_interval_95": _outward_rounded_interval(
                _poisson_rate_95(false_alerts, analyzed_hours),
                "poisson_exact_equal_tail",
            ),
        },
        "latency_seconds": {
            "median": round(statistics.median(latencies), 6) if latencies else None,
            "p95_nearest_rank": round(_percentile_nearest_rank(latencies, 0.95), 6)
            if latencies
            else None,
            "matched_events": len(latencies),
            "status": latency_status,
        },
        "clips": clip_reports,
        "limitations": [
            "Finite replay uses analyzed clip duration only; scheduled camera-hours, outages, alert delivery, and human response are unmeasured.",
            "Predeclared sample-size minima indicate exposure, not statistical confidence or representativeness.",
            "The false-alert confidence interval assumes a constant-rate Poisson count process; clustered alerts or repeated clips can make it overconfident.",
            "Staged regression footage cannot establish field performance."
            if role == "staged_regression"
            else "Held-out or field provenance and representative sampling must be audited independently.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        candidate_path = args.candidates.expanduser().resolve()
        label_path = args.labels.expanduser().resolve()
        report = build_report(
            _read_json(candidate_path),
            _read_json(label_path),
            max_alert_delay_seconds=args.max_alert_delay_seconds,
            early_tolerance_seconds=args.early_tolerance_seconds,
            minimum_falls=args.minimum_falls,
            minimum_analyzed_hours=args.minimum_analyzed_hours,
            candidate_sha256=_sha256_file(candidate_path),
            label_sha256=_sha256_file(label_path),
        )
        serialized = json.dumps(report, indent=2) + "\n"
        if args.output is None:
            sys.stdout.write(serialized)
        else:
            destination = args.output.expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(serialized, encoding="utf-8")
            print(f"Wrote {destination}", file=sys.stderr)
        return 0
    except (TypeError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
