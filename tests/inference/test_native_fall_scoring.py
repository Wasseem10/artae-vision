"""Ground-truth and temporal matching checks for native fall replay scores."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import score_native_fall as scorer


def _digest(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def _inputs(
    *,
    duration: float = 20.0,
    falls: list[tuple[float, float]] | None = None,
    detections: list[float] | None = None,
) -> tuple[dict, dict]:
    falls = falls or []
    detections = detections or []
    digest = _digest("clip")
    candidates = {
        "schema_version": 1,
        "kind": "native_fall_candidate_baseline",
        "dataset_name": "permissioned-fixture",
        "execution_path": "video_intelligence_inference.replay.run_replay:specialized_pose",
        "provenance": {"model_sha256": _digest("model")},
        "total_clips": 1,
        "total_candidates": len(detections),
        "results": [
            {
                "clip_name": "fall.mp4",
                "clip_sha256": digest,
                "duration_seconds": duration,
                "source_frame_count": 200,
                "frames_processed": 200,
                "provider_requests": 0,
                "candidate_count": len(detections),
                "candidate_times_seconds": detections,
                "candidate_intervals": [
                    {
                        "start_seconds": time - 0.1,
                        "end_seconds": time,
                        "detected_at_seconds": time,
                        "label": "event",
                    }
                    for time in detections
                ],
            }
        ],
    }
    labels = {
        "schema_version": 1,
        "kind": "native_fall_ground_truth",
        "dataset_name": "permissioned-fixture",
        "dataset_role": "held_out",
        "review_status": "independently_adjudicated",
        "clips": [
            {
                "clip_sha256": digest,
                "duration_seconds": duration,
                "reviewed_full_duration": True,
                "falls": [
                    {"start_seconds": start, "end_seconds": end} for start, end in falls
                ],
            }
        ],
    }
    return candidates, labels


def _score(candidates: dict, labels: dict, **overrides) -> dict:
    options = {
        "max_alert_delay_seconds": 2.0,
        "early_tolerance_seconds": 0.0,
        "minimum_falls": 2,
        "minimum_analyzed_hours": 1.0,
        "generated_at": "2026-09-26T00:00:00+00:00",
    }
    options.update(overrides)
    return scorer.build_report(candidates, labels, **options)


def test_matches_once_and_counts_duplicates_late_alerts_and_misses() -> None:
    candidates, labels = _inputs(falls=[(5, 6), (12, 13)], detections=[5.5, 5.8, 15.0])
    result = _score(candidates, labels)

    assert result["counts"] == {
        "labeled_falls": 2,
        "candidates": 3,
        "true_positives": 1,
        "false_alerts": 2,
        "missed_falls": 1,
    }
    assert result["recall"]["value"] == 0.5
    assert result["recall"]["status"] == "sample_size_met"
    assert result["false_alerts_per_analyzed_hour"]["status"] == "insufficient_data"
    assert result["latency_seconds"]["median"] == 0.5
    assert result["latency_seconds"]["status"] == "insufficient_data"
    assert result["clips"][0]["unmatched_candidate_indices"] == [1, 2]
    assert result["clips"][0]["unmatched_fall_indices"] == [1]


def test_matching_maximizes_event_count_when_windows_overlap() -> None:
    candidates, labels = _inputs(falls=[(10, 10.5), (11, 11.5)], detections=[10.5, 9.5])
    result = _score(candidates, labels, early_tolerance_seconds=1.0)

    assert result["counts"]["true_positives"] == 2
    assert result["counts"]["false_alerts"] == 0
    assert result["clips"][0]["matches"] == [
        {"fall_index": 0, "candidate_index": 1, "latency_seconds": -0.5},
        {"fall_index": 1, "candidate_index": 0, "latency_seconds": -0.5},
    ]


def test_no_labeled_falls_is_unmeasured_recall_with_counted_negative_exposure() -> None:
    candidates, labels = _inputs(duration=3600, detections=[])
    result = _score(candidates, labels, minimum_analyzed_hours=1.0)

    assert result["recall"]["value"] is None
    assert result["recall"]["status"] == "unmeasured"
    assert result["recall"]["confidence_interval_95"]["lower"] is None
    assert result["recall"]["confidence_interval_95"]["upper"] is None
    assert result["latency_seconds"]["status"] == "unmeasured"
    assert result["false_alerts_per_analyzed_hour"]["value"] == 0.0
    assert result["false_alerts_per_analyzed_hour"]["status"] == "sample_size_met"
    assert result["false_alerts_per_analyzed_hour"]["confidence_interval_95"] == {
        "lower": 0.0,
        "upper": 3.68888,
        "method": "poisson_exact_equal_tail",
    }
    assert result["exposure"]["negative_clip_hours"] == 1
    assert result["exposure"]["scheduled_hours"] is None


def test_small_positive_sample_is_explicitly_insufficient() -> None:
    candidates, labels = _inputs(falls=[(5, 6)], detections=[5.5])
    result = _score(candidates, labels, minimum_falls=100)

    assert result["recall"]["value"] == 1.0
    assert result["recall"]["status"] == "insufficient_data"
    assert 0 < result["recall"]["confidence_interval_95"]["lower"] < 1
    assert result["latency_seconds"]["status"] == "insufficient_data"


def test_missing_or_partially_reviewed_labels_cannot_be_scored() -> None:
    candidates, labels = _inputs()
    labels["review_status"] = "draft"
    with pytest.raises(ValueError, match="independently_adjudicated"):
        _score(candidates, labels)

    labels["review_status"] = "independently_adjudicated"
    labels["clips"][0]["reviewed_full_duration"] = False
    with pytest.raises(ValueError, match="reviewed_full_duration"):
        _score(candidates, labels)

    labels["clips"][0]["reviewed_full_duration"] = True
    labels["clips"][0]["clip_sha256"] = _digest("different clip")
    with pytest.raises(ValueError, match="Clip SHA-256 sets differ"):
        _score(candidates, labels)


def test_no_matched_falls_keeps_latency_unmeasured() -> None:
    candidates, labels = _inputs(falls=[(5, 6)], detections=[])
    result = _score(candidates, labels, minimum_falls=1)

    assert result["recall"]["value"] == 0.0
    assert result["recall"]["status"] == "sample_size_met"
    assert result["latency_seconds"]["median"] is None
    assert result["latency_seconds"]["status"] == "unmeasured"


def test_incomplete_replay_or_mismatched_duration_cannot_be_scored() -> None:
    candidates, labels = _inputs(falls=[(5, 6)])
    candidates["results"][0]["frames_processed"] = 199
    with pytest.raises(ValueError, match="every source frame"):
        _score(candidates, labels)

    candidates["results"][0]["frames_processed"] = 200
    labels["clips"][0]["duration_seconds"] = 21
    with pytest.raises(ValueError, match="durations differ"):
        _score(candidates, labels)


def test_cli_reads_separate_files_and_records_hashes(tmp_path: Path, capsys) -> None:
    candidates, labels = _inputs(falls=[(5, 6)], detections=[5.5])
    candidate_path = tmp_path / "candidates.json"
    label_path = tmp_path / "labels.json"
    candidate_path.write_text(json.dumps(candidates), encoding="utf-8")
    label_path.write_text(json.dumps(labels), encoding="utf-8")

    code = scorer.main(
        [
            "--candidates",
            str(candidate_path),
            "--labels",
            str(label_path),
            "--max-alert-delay-seconds",
            "2",
            "--minimum-falls",
            "100",
            "--minimum-analyzed-hours",
            "300",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["input_sha256"]["candidates_json"] == scorer._sha256_file(
        candidate_path
    )
    assert result["input_sha256"]["labels_json"] == scorer._sha256_file(label_path)
    assert result["recall"]["status"] == "insufficient_data"
    assert result["false_alerts_per_analyzed_hour"]["status"] == "insufficient_data"


def test_invalid_matching_window_fails_at_argument_parsing() -> None:
    with pytest.raises(SystemExit):
        scorer.parse_args(
            [
                "--candidates",
                "candidate.json",
                "--labels",
                "labels.json",
                "--max-alert-delay-seconds",
                "0",
                "--minimum-falls",
                "100",
                "--minimum-analyzed-hours",
                "300",
            ]
        )


def test_exact_intervals_cover_small_sample_extremes_and_positive_counts() -> None:
    assert scorer._clopper_pearson_95(0, 0) is None
    zero_of_one = scorer._clopper_pearson_95(0, 1)
    one_of_one = scorer._clopper_pearson_95(1, 1)
    middle = scorer._clopper_pearson_95(5, 10)

    assert zero_of_one is not None
    assert one_of_one is not None
    assert middle is not None
    assert zero_of_one[0] == 0
    assert zero_of_one[1] == pytest.approx(0.975)
    assert one_of_one[0] == pytest.approx(0.025)
    assert one_of_one[1] == 1
    assert middle == pytest.approx((0.187086, 0.812914), abs=1e-6)

    zero_per_hour = scorer._poisson_rate_95(0, 1)
    zero_per_ten_hours = scorer._poisson_rate_95(0, 10)
    three_per_two_hours = scorer._poisson_rate_95(3, 2)
    assert zero_per_hour is not None
    assert zero_per_ten_hours is not None
    assert three_per_two_hours is not None
    assert zero_per_hour == pytest.approx((0, 3.688879454), abs=1e-8)
    assert zero_per_ten_hours[1] == pytest.approx(zero_per_hour[1] / 10)
    assert three_per_two_hours == pytest.approx((0.309336061, 4.383636535), abs=1e-8)
