"""Synthetic scoring-integrity cases; these do not measure a detector."""
import copy
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/compare-pose-models.py"
compare = runpy.run_path(str(SCRIPT))["compare_reports"]


def fixture():
    cases = [{"id": f"clip-{i}", "category": "fall" if i < 50 else "daily_activity",
              "eventRanges": [{"start": 2, "end": 3}] if i < 50 else [],
              "videoSha256": f"{i:064x}"} for i in range(100)]
    manifest = {"datasetId": "synthetic-cauca", "cases": cases}
    report = {"status": "complete", "dataset": {"datasetId": manifest["datasetId"]},
              "provenance": {"detector": {"model": "synthetic"}},
              "results": [{**copy.deepcopy(case), "framesAnalyzed": 50, "framesWithPose": 25,
                           "durationSeconds": 10, "detectedAtSeconds": [], "meanInferenceMs": 5}
                          for case in cases]}
    return manifest, [report, copy.deepcopy(report)]


class PoseComparisonTests(unittest.TestCase):
    def test_valid_comparison_preserves_gains_losses_and_negative_exposure(self):
        manifest, reports = fixture()
        reports[0]["results"][0]["detectedAtSeconds"] = [2]
        reports[1]["results"][1]["detectedAtSeconds"] = [5]  # Inclusive two-second allowance.
        reports[1]["results"][50]["detectedAtSeconds"] = [0, 10]
        original = copy.deepcopy((manifest, reports))
        result = compare(manifest, reports)
        self.assertEqual(result["baselineMatchedFalls"], 1)
        self.assertEqual(result["candidateMatchedFalls"], 1)
        self.assertEqual(result["gainedFallIds"], ["clip-1"])
        self.assertEqual(result["lostFallIds"], ["clip-0"])
        self.assertEqual(result["candidateDailyActivityClipsAlerted"], ["clip-50"])
        self.assertEqual(result["schemaVersion"], 2)
        self.assertNotIn("candidateDailyActivityAlertsPerAnalyzedHour", result)
        self.assertEqual(result["dailyActivityExposure"]["candidate"], {
            "clips": 50, "clipsAlerted": 1, "alertCount": 2,
            "reportedVideoSeconds": 500, "alertsPerReportedVideoHour": 14.4,
            "analyzedExposureVerified": False,
        })
        self.assertEqual(result["meanPoseCoverage"], {"baseline": .5, "candidate": .5})
        self.assertEqual((manifest, reports), original)

    def test_paired_rows_reconcile_with_scores_and_keep_activity_distinct_from_misses(self):
        manifest, reports = fixture()
        reports[0]["results"][0]["detectedAtSeconds"] = [1, 2]
        reports[1]["results"][1]["detectedAtSeconds"] = [5]
        reports[0]["results"][50]["detectedAtSeconds"] = [1, 3]
        reports[1]["results"][51]["detectedAtSeconds"] = [2]
        reports[1]["results"].reverse()
        result = compare(manifest, reports)
        rows = result["perClip"]
        self.assertEqual([row["id"] for row in rows], [case["id"] for case in manifest["cases"]])
        self.assertEqual(rows[0]["baseline"]["alertTimestampsSeconds"], [1, 2])
        self.assertTrue(rows[0]["baseline"]["matchedFall"])
        self.assertFalse(rows[0]["candidate"]["matchedFall"])
        for side in ("baseline", "candidate"):
            self.assertEqual(sum(row[side]["matchedFall"] is True for row in rows), result[f"{side}MatchedFalls"])
            activities = [row for row in rows if row["category"] == "daily_activity"]
            self.assertTrue(all(row[side]["matchedFall"] is None for row in activities))
            self.assertEqual(sum(len(row[side]["alertTimestampsSeconds"]) for row in activities),
                             result["dailyActivityExposure"][side]["alertCount"])
        rows[0]["baseline"]["alertTimestampsSeconds"].append(99)
        rows[0]["eventRanges"][0]["start"] = 99
        self.assertEqual(reports[0]["results"][0]["detectedAtSeconds"], [1, 2])
        self.assertEqual(manifest["cases"][0]["eventRanges"][0]["start"], 2)

    def test_each_side_uses_its_own_reported_exposure_without_claiming_analyzed_hours(self):
        manifest, reports = fixture()
        for report in reports:
            report["results"][50]["detectedAtSeconds"] = [1]
        for row in reports[1]["results"][50:]:
            row["durationSeconds"] = 20
        result = compare(manifest, reports)
        exposure = result["dailyActivityExposure"]
        self.assertEqual(exposure["baseline"]["reportedVideoSeconds"], 500)
        self.assertEqual(exposure["candidate"]["reportedVideoSeconds"], 1000)
        self.assertEqual(exposure["baseline"]["alertsPerReportedVideoHour"], 7.2)
        self.assertEqual(exposure["candidate"]["alertsPerReportedVideoHour"], 3.6)
        self.assertFalse(exposure["baseline"]["analyzedExposureVerified"])
        self.assertFalse(exposure["candidate"]["analyzedExposureVerified"])
        self.assertIn("not verified analyzed exposure", result["limitations"][0])

    def test_overflowing_exposure_is_rejected(self):
        manifest, reports = fixture()
        for row in reports[1]["results"][50:]:
            row["durationSeconds"] = 1e308
        with self.assertRaisesRegex(ValueError, "total activity video duration"):
            compare(manifest, reports)

    def test_duplicates_are_rejected_before_dictionary_conversion(self):
        for target in ("manifest", "baseline", "candidate"):
            for append in (True, False):
                with self.subTest(target=target, append=append):
                    manifest, reports = fixture()
                    rows = manifest["cases"] if target == "manifest" else reports[target == "candidate"]["results"]
                    if append:
                        rows.append(copy.deepcopy(rows[0]))
                    else:
                        rows[-1] = copy.deepcopy(rows[0])
                    with self.assertRaises(ValueError):
                        compare(manifest, reports)

    def test_each_report_must_match_manifest_labels_media_and_intervals(self):
        for report_index in (0, 1):
            for key, value in (("category", "daily_activity"), ("videoSha256", "changed"),
                               ("eventRanges", [{"start": 0, "end": 9}]), ("id", "unknown")):
                with self.subTest(report=report_index, key=key):
                    manifest, reports = fixture()
                    reports[report_index]["results"][0][key] = value
                    with self.assertRaises(ValueError):
                        compare(manifest, reports)

    def test_invalid_metrics_cannot_inflate_coverage_or_negative_exposure(self):
        for key, values in {
            "durationSeconds": [0, -1, float("nan"), float("inf"), True, "10"],
            "framesAnalyzed": [0, -1, 1.5, True],
            "framesWithPose": [-1, 51, float("nan"), True],
            "meanInferenceMs": [-1, float("nan"), float("inf"), True],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    manifest, reports = fixture()
                    reports[1]["results"][50][key] = value
                    with self.assertRaises(ValueError):
                        compare(manifest, reports)

    def test_invalid_alert_times_are_not_counted(self):
        for alerts in ([float("nan")], [float("inf")], [-.1], [10.01], [True], "2", None):
            with self.subTest(alerts=alerts):
                manifest, reports = fixture()
                reports[1]["results"][0]["detectedAtSeconds"] = alerts
                with self.assertRaises(ValueError):
                    compare(manifest, reports)

    def test_incomplete_or_wrong_dataset_reports_are_rejected(self):
        for key, value in (("status", "running"), ("dataset", {"datasetId": "other"})):
            manifest, reports = fixture()
            reports[0][key] = value
            with self.assertRaises(ValueError):
                compare(manifest, reports)
        manifest, reports = fixture()
        with self.assertRaises(ValueError):
            compare(manifest, reports[:1])

    def test_invalid_manifest_labels_intervals_and_missing_negatives_are_rejected(self):
        for key, value in (("category", "unknown"), ("eventRanges", []),
                           ("eventRanges", [{"start": 3, "end": 2}]),
                           ("eventRanges", [{"start": 0, "end": float("inf")}])):
            manifest, reports = fixture()
            manifest["cases"][0][key] = value
            with self.assertRaises(ValueError):
                compare(manifest, reports)
        manifest, reports = fixture()
        for case in manifest["cases"]:
            case.update(category="fall", eventRanges=[{"start": 2, "end": 3}])
        with self.assertRaisesRegex(ValueError, "negative exposure"):
            compare(manifest, reports)

    def test_cli_explicit_manifest_and_invalid_report_produce_no_score(self):
        manifest, reports = fixture()
        with tempfile.TemporaryDirectory(prefix="artae-pose-comparison-") as folder:
            paths = [Path(folder) / name for name in ("manifest.json", "baseline.json", "candidate.json")]
            for path, value in zip(paths, [manifest, *reports]):
                path.write_text(json.dumps(value), encoding="utf-8")
            command = [sys.executable, str(SCRIPT), str(paths[1]), str(paths[2]), "--manifest", str(paths[0])]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), compare(manifest, reports))
            reports[1]["results"].append(copy.deepcopy(reports[1]["results"][0]))
            paths[2].write_text(json.dumps(reports[1]), encoding="utf-8")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
