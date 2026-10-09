"""Run with python -m unittest discover -s tests/benchmarks -v (stdlib only)."""

import copy
import importlib.util
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "mpfdd_scorer", Path(__file__).resolve().parents[2] / "scripts/score-mpfdd-clips.py"
)
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


def replay():
    return {
        "id": "sample", "durationSeconds": 1.0, "framesAnalyzed": 11,
        "framesWithPose": 9,
        "poseTrace": [{"seconds": round(min(0.999, i * 0.1), 3)} for i in range(11)],
        "detectedAtSeconds": [0.8], "meanInferenceMs": 12.0, "p95InferenceMs": 20.0,
        "trackIdsSeen": 2, "maxVisiblePeople": 2,
        "multiPersonEvents": [{"atSeconds": 0.8, "trackId": 1}],
    }


class SamplingTests(unittest.TestCase):
    def test_accepts_complete_legacy_and_multi_replays(self):
        for schema in (3, 4):
            scorer.validate_sampling(replay(), schema)

    def test_accepts_simultaneous_falls_on_distinct_tracks(self):
        row = replay()
        row["detectedAtSeconds"] = [0.8, 0.8]
        row["multiPersonEvents"].append({"atSeconds": 0.8, "trackId": 2})
        scorer.validate_sampling(row, 4)

    def test_rejects_truncated_negative_before_counting_exposure(self):
        row = replay()
        row.update(detectedAtSeconds=[], multiPersonEvents=[], framesAnalyzed=10)
        row["poseTrace"].pop()
        with self.assertRaisesRegex(ValueError, "Incomplete sampling"):
            scorer.validate_sampling(row, 4)

    def test_rejects_missing_repeated_reordered_or_shifted_samples(self):
        for times in ([0.0] * 11, list(reversed(replay()["poseTrace"])),
                      [{"seconds": 0.05 + i * 0.1} for i in range(11)]):
            row = replay()
            row["poseTrace"] = [{"seconds": t} if isinstance(t, float) else t for t in times]
            with self.subTest(times=times), self.assertRaises(ValueError):
                scorer.validate_sampling(row, 3)

    def test_rejects_nonfinite_duration_coverage_and_timings(self):
        corruptions = {
            "durationSeconds": [float("nan"), float("inf"), -1, True],
            "framesAnalyzed": [True, 11.0, 1],
            "framesWithPose": [12, -1, 1.5, True],
            "meanInferenceMs": [float("nan"), -1, True],
            "p95InferenceMs": [float("inf"), -1],
        }
        for field, values in corruptions.items():
            for value in values:
                row = replay()
                row[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    scorer.validate_sampling(row, 3)

    def test_rejects_invalid_or_unsampled_alerts(self):
        for alerts in ([float("nan")], [True], [-0.1], [1.0], [0.85], [0.8, 0.7]):
            row = replay()
            row["detectedAtSeconds"] = alerts
            with self.subTest(alerts=alerts), self.assertRaises(ValueError):
                scorer.validate_sampling(row, 3)

    def test_rejects_duplicate_or_unknown_track_events(self):
        for events in ([{"atSeconds": 0.8, "trackId": 3}],
                       [{"atSeconds": 0.8, "trackId": True}],
                       [{"atSeconds": 0.8, "trackId": 1}] * 2):
            row = replay()
            row["multiPersonEvents"] = copy.deepcopy(events)
            row["detectedAtSeconds"] = [event["atSeconds"] for event in events]
            with self.subTest(events=events), self.assertRaises(ValueError):
                scorer.validate_sampling(row, 4)

    def test_non_integral_duration_matches_browser_loop(self):
        row = replay()
        row["durationSeconds"] = 1.04
        row["poseTrace"][-1]["seconds"] = 1.0
        scorer.validate_sampling(row, 3)


if __name__ == "__main__":
    unittest.main()
