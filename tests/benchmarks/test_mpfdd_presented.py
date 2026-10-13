"""Sampling contract fixtures, not model inference or benchmark results."""
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "scorer", Path(__file__).resolve().parents[2] / "scripts/score-mpfdd-clips.py")
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


def row():
    return {
        "id": "synthetic", "durationSeconds": 0.2, "framesAnalyzed": 3,
        "framesWithPose": 1, "meanInferenceMs": 1, "p95InferenceMs": 1,
        "poseTrace": [{"seconds": s} for s in (0, 0.1, 0.199)],
        "presentedFrameTrace": [{"requestedSeconds": s, "decodedSeconds": s,
                                 "presentedFrames": i + 1} for i, s in enumerate((0, 0.1, 0.199))],
        "detectedAtSeconds": [0.1], "multiPersonEvents": [{"atSeconds": 0.1, "trackId": 2}],
        "trackIdsSeen": 1, "maxVisiblePeople": 1,
    }


def report(schema):
    return {"schemaVersion": schema, "provenance": {
        "localGitRevision": "frozen", "localSourceHashes": {"source": "hash"},
        "detector": {"runtime": "test", "model": "test", "modelSha256": "hash", "worker": "test"},
    }}


class PresentedTests(unittest.TestCase):
    def test_presented_cli_writes_a_separate_verified_summary_from_fixtures(self):
        # Synthetic protocol fixtures only: no inference or accuracy evidence.
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            cases = [{"id": f"mpfdd-s1-p2-f{int(i < 22)}-{'fall' if i < 22 else 'adl'}-{i+1}",
                      "category": "fall" if i < 22 else "daily_activity",
                      "fallingPeopleCount": int(i < 22), "videoSha256": "a" * 64,
                      "sourceGitBlobSha1": "b" * 40, "sourcePath": "fixture.mp4"}
                     for i in range(28)]
            manifest = {"datasetId": scorer.DATASET_ID, "sourceRevision": "synthetic", "cases": cases}
            manifest_path = folder / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            for schema, name, rule in ((5, "legacy.json", "BrowserPoseRule/fall-v2"),
                                       (6, "multi.json", "FusedMultiPersonFallRule/fall-v1")):
                data = report(schema)
                data.update(status="complete", scoringUnit="clip", sampleIntervalSeconds=0.1,
                            dataset={"datasetId": scorer.DATASET_ID, "sourceRevision": "synthetic"})
                data["provenance"].update(localGitDirty=False, frameSampling=scorer.PRESENTED_PROTOCOL)
                data["provenance"]["detector"]["rule"] = rule
                data["provenance"]["localSourceHashes"]["apps/web/public/vision/mpfdd/manifest.json"] = manifest_hash
                data["results"] = []
                for case in cases:
                    result = row()
                    result.update(case)
                    if case["category"] == "daily_activity":
                        result.update(detectedAtSeconds=[], multiPersonEvents=[])
                    data["results"].append(result)
                (folder / name).write_text(json.dumps(data), encoding="utf-8")
            output = folder / "comparison.json"
            command = [sys.executable, str(Path(scorer.__file__)), "--sampling", "presented",
                       "--manifest", str(manifest_path), "--legacy-report", str(folder / "legacy.json"),
                       "--multi-report", str(folder / "multi.json"), "--output", str(output)]
            completed = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["inputReportSchemas"], [5, 6])
            self.assertEqual(result["verifiedPresentationSamples"], {"legacy": 84, "multiPerson": 84})
            self.assertIn("Development", result["scope"])
            # The same files are refused when callers select the old protocol.
            command[command.index("presented")] = "seeked"
            completed = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(completed.returncode, 0)

    def test_accepts_legacy_and_fused_presented_contracts(self):
        for schema in (5, 6):
            scorer.validate_sampling(row(), schema)
            scorer.validate_protocol({"frameSampling": scorer.PRESENTED_PROTOCOL}, schema)

    def test_rejects_missing_partial_and_reordered_trace(self):
        for kind in ("missing", "partial", "reordered"):
            result = row()
            if kind == "missing": del result["presentedFrameTrace"]
            elif kind == "partial": result["presentedFrameTrace"].pop()
            else: result["presentedFrameTrace"].reverse()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                scorer.validate_sampling(result, 6)

    def test_rejects_stale_future_nonfinite_and_boolean_times(self):
        for value in (0, 0.2, float("nan"), float("inf"), True):
            result = row()
            result["presentedFrameTrace"][1]["decodedSeconds"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                scorer.validate_sampling(result, 6)

    def test_allows_declared_quantization_and_rejects_wider_bounds(self):
        result = row()
        result["presentedFrameTrace"][1]["decodedSeconds"] = 0.05
        scorer.validate_sampling(result, 6)
        result["presentedFrameTrace"][1]["decodedSeconds"] = 0.049
        with self.assertRaises(ValueError): scorer.validate_sampling(result, 6)

    def test_rejects_repeated_fractional_and_boolean_counters(self):
        for counter in (1, 2.5, True):
            result = row()
            result["presentedFrameTrace"][1]["presentedFrames"] = counter
            with self.subTest(counter=counter), self.assertRaises(ValueError):
                scorer.validate_sampling(result, 5)

    def test_rejects_backward_decoded_time(self):
        result = row()
        result["presentedFrameTrace"][-1]["decodedSeconds"] = 0.08
        with self.assertRaises(ValueError): scorer.validate_sampling(result, 5)

    def test_rejects_missing_changed_or_downgraded_protocol(self):
        with self.assertRaises(ValueError): scorer.validate_protocol({}, 6)
        for key, value in (("maxFrameLagSeconds", 0.1), ("seekOffsetSeconds", True),
                           ("method", "seeked")):
            protocol = copy.deepcopy(scorer.PRESENTED_PROTOCOL)
            protocol[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                scorer.validate_protocol({"frameSampling": protocol}, 6)
        with self.assertRaises(ValueError):
            scorer.validate_protocol({"frameSampling": scorer.PRESENTED_PROTOCOL}, 4)
        with self.assertRaises(ValueError):
            scorer.validate_sampling(row(), 4)

    def test_rejects_mixed_methods_revisions_models_and_source_hashes(self):
        scorer.validate_pair(report(3), report(4))
        scorer.validate_pair(report(5), report(6))
        for kind in ("mixed", "revision", "model", "source"):
            before, after = report(5), report(6)
            if kind == "mixed": before["schemaVersion"] = 3
            elif kind == "revision": after["provenance"]["localGitRevision"] = "other"
            elif kind == "model": after["provenance"]["detector"]["modelSha256"] = "other"
            else: after["provenance"]["localSourceHashes"]["source"] = "other"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                scorer.validate_pair(before, after)


if __name__ == "__main__": unittest.main()
