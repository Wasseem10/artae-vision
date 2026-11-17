"""Provisional count-audit tests; no model inference or video downloads."""

import copy
import importlib.util
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "audit", Path(__file__).resolve().parents[2] / "scripts/audit-mpfdd-visible-people.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def inputs():
    labels = {
        "schemaVersion": 1, "reviewStatus": "provisional-ai-visual-review",
        "sourceRevision": "source", "frames": [
            {"caseId": "clip", "seconds": 2, "visiblePeople": 1, "videoSha256": "video"},
            {"caseId": "clip", "seconds": 5, "visiblePeople": 2, "videoSha256": "video"},
        ],
    }
    manifest = {
        "datasetId": "mpfdd-github-available-v1", "sourceRevision": "source",
        "cases": [{"id": "clip", "videoSha256": "video"}],
    }
    report = {
        "schemaVersion": 4, "status": "complete", "dataset": {
            "datasetId": "mpfdd-github-available-v1", "sourceRevision": "source",
        },
        "provenance": {"localGitDirty": False, "localGitRevision": "replay",
                       "detector": {"rule": "FusedMultiPersonFallRule/fall-v1"}},
        "results": [{"id": "clip", "videoSha256": "video", "observationTrace": [
            {"seconds": 2, "rawPoseCount": 2, "usablePoseCount": 2, "trackIds": [1]},
            {"seconds": 5, "rawPoseCount": 1, "usablePoseCount": 1, "trackIds": [1]},
        ]}],
    }
    return labels, manifest, report


class VisiblePersonTests(unittest.TestCase):
    def test_reports_deficits_and_excess_without_accuracy_metrics(self):
        result = audit.compare(*inputs())
        self.assertEqual(result["summary"], {
            "annotatedFrames": 2, "framesWithRawCountDeficit": 1,
            "framesWithRawCountExcess": 1, "framesWithFusedCountDeficit": 1,
        })
        self.assertEqual(result["reviewStatus"], "provisional-ai-visual-review")
        self.assertNotIn("recall", result)
        self.assertNotIn("precision", result)

    def test_rejects_changed_video(self):
        labels, manifest, report = inputs()
        labels["frames"][0]["videoSha256"] = "other"
        with self.assertRaises(ValueError):
            audit.compare(labels, manifest, report)

    def test_rejects_invalid_or_duplicate_labels(self):
        for value in (-1, True, 1.5):
            labels, manifest, report = inputs()
            labels["frames"][0]["visiblePeople"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                audit.compare(labels, manifest, report)
        labels, manifest, report = inputs()
        labels["frames"].append(copy.deepcopy(labels["frames"][0]))
        with self.assertRaises(ValueError):
            audit.compare(labels, manifest, report)

    def test_rejects_unsampled_time(self):
        labels, manifest, report = inputs()
        labels["frames"][0]["seconds"] = 2.05
        with self.assertRaises(ValueError):
            audit.compare(labels, manifest, report)

    def test_rejects_missing_or_duplicate_observation(self):
        for duplicate in (False, True):
            labels, manifest, report = inputs()
            trace = report["results"][0]["observationTrace"]
            if duplicate:
                trace.append(copy.deepcopy(trace[0]))
            else:
                trace.pop(0)
            with self.subTest(duplicate=duplicate), self.assertRaises(ValueError):
                audit.compare(labels, manifest, report)

    def test_rejects_changed_revision_dirty_or_failed_replay(self):
        for field in ("revision", "dirty", "error", "duplicate"):
            labels, manifest, report = inputs()
            if field == "revision":
                report["dataset"]["sourceRevision"] = "other"
            elif field == "dirty":
                report["provenance"]["localGitDirty"] = True
            elif field == "error":
                report["results"][0]["error"] = "inference failure"
            else:
                report["results"].append(copy.deepcopy(report["results"][0]))
            with self.subTest(field=field), self.assertRaises(ValueError):
                audit.compare(labels, manifest, report)

    def test_rejects_invalid_pose_counts_and_track_ids(self):
        for field, value in (("rawPoseCount", True), ("usablePoseCount", 3),
                             ("trackIds", [1, 1]), ("trackIds", [True])):
            labels, manifest, report = inputs()
            report["results"][0]["observationTrace"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                audit.compare(labels, manifest, report)


if __name__ == "__main__":
    unittest.main()
