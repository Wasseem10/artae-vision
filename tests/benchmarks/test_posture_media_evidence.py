"""Keep the published media evidence tied to the source roster and measured clocks."""

import hashlib
import json
import pathlib
import unittest
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[2]


class PublishedMediaEvidenceTests(unittest.TestCase):
    def test_checked_in_full_decode_has_complete_pinned_roster_and_honest_bounds(self):
        lock_path = ROOT / "docs/benchmarks/posture-source-v1.lock.json"
        lock = json.loads(lock_path.read_bytes())
        report = json.loads((ROOT / "docs/benchmarks/posture-media-v1.json").read_bytes())
        expected = {e["path"]: e for e in lock["videos"] if e["role"] == "candidate-evaluation"}
        frames = {4: 11619, 5: 7105, 6: 4290, 7: 4453, 8: 13050, 9: 3821, 10: 7025}
        self.assertEqual(report["source_lock_sha256"], hashlib.sha256(lock_path.read_bytes()).hexdigest())
        self.assertFalse(report["benchmark_eligible"])
        self.assertFalse(report["provenance"]["working_tree_dirty"])
        self.assertEqual(report["provenance"]["code_revision"], "50fa243da6213f4a0633499de9c324822185a9a6")
        self.assertEqual(report["provenance"]["pyav"], "19.0.1")
        self.assertEqual(report["candidate_videos"], 7)
        self.assertEqual(report["source_training_videos_excluded"], 3)
        self.assertEqual(report["media_bytes"], 1981798589)
        self.assertEqual(report["decoded_frames"], 51363)
        self.assertEqual({c["path"] for c in report["clips"]}, set(expected))
        self.assertEqual(len(report["clips"]), 7)
        span, overhanging = Fraction(), set()
        for clip in report["clips"]:
            source = expected[clip["path"]]
            number = int(pathlib.PurePosixPath(clip["path"]).stem.split("_")[-1])
            self.assertEqual(clip["sha256"], source["sha256"])
            self.assertEqual(clip["size"], source["size"])
            self.assertEqual(clip["media_status"], "hash-verified-fully-decoded")
            decoded = clip["decode"]
            self.assertEqual(decoded["decoded_frames"], frames[number])
            self.assertEqual(decoded["decoded_frames"], decoded["declared_frames"])
            self.assertEqual((decoded["width"], decoded["height"]), (1280, 720))
            self.assertEqual(decoded["container_start_seconds_exact"], "0/1")
            self.assertGreater(Fraction(decoded["first_pts_seconds_exact"]), 0)
            duration = Fraction(decoded["decoded_span_seconds_exact"])
            self.assertEqual(duration, Fraction(decoded["last_frame_end_seconds_exact"]) - Fraction(decoded["first_pts_seconds_exact"]))
            span += duration
            for field in ("missing_frame_durations", "frame_interval_gaps", "frame_interval_overlaps"):
                self.assertEqual(decoded[field], 0)
            self.assertEqual(len(decoded["presentation_trace_sha256"]), 64)
            bounds = clip["annotation_bounds"]
            self.assertTrue(bounds["decoded_timeline_consistent"])
            self.assertFalse(bounds["label_clock_verified"])
            self.assertEqual(bounds["rows_starting_at_or_after_video_end"], [])
            self.assertEqual(bounds["rows_ending_at_or_after_video_end"], [])
            self.assertNotIn("negative_exposure_seconds", bounds)
            if bounds["inclusive_bin_end_exceeds_video_rows"]:
                overhanging.add(number)
        self.assertEqual(span, Fraction(154092311, 90000))
        self.assertEqual(overhanging, {4, 5, 7, 9, 10})


if __name__ == "__main__":
    unittest.main()
