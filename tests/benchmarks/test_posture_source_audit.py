import copy
import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("posture_audit", ROOT / "scripts/audit-posture-source.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def rows(text):
    return AUDIT.read_rows(("start_time,end_time,action,is_fall\n" + text).encode())


class AnnotationTests(unittest.TestCase):
    def test_single_timestamp_fall_is_not_lost_as_zero_duration(self):
        result = AUDIT.audit_rows(rows("0,0,Stand-Lie,True\n1,2,Lie,True\n"))
        self.assertEqual(result["single_timestamp_rows"], 1)
        self.assertEqual(result["diagnostic_bin_counts"]["fall_label"], 3)
        # Adjacent fall rows can describe one event; don't count two events.
        self.assertEqual(result["positive_label_runs_not_adjudicated_events"], [[0, 2]])

    def test_duplicate_rows_do_not_duplicate_coverage(self):
        result = AUDIT.audit_rows(rows("0,2,Sit,False\n0,2,Sit,False\n"))
        self.assertEqual(result["duplicate_row_groups"], [[2, 3]])
        self.assertEqual(result["diagnostic_bin_counts"]["nonfall_label"], 3)

    def test_conflicting_fall_boundary_is_excluded_from_both_classes(self):
        result = AUDIT.audit_rows(rows("0,1,Stand,False\n1,2,Stand-Lie,True\n"))
        self.assertEqual(result["conflicting_bins"], [{"bin": 1, "rows": [2, 3]}])
        self.assertEqual(result["diagnostic_bin_counts"]["fall_label"], 1)
        self.assertEqual(result["diagnostic_bin_counts"]["nonfall_label"], 1)

    def test_conflicting_actions_with_same_fall_flag_are_also_excluded(self):
        result = AUDIT.audit_rows(rows("0,1,Stand,False\n1,2,None,False\n"))
        self.assertEqual(result["diagnostic_bin_counts"]["conflict"], 1)

    def test_unassigned_and_gaps_are_never_assumed_negative(self):
        result = AUDIT.audit_rows(rows("1,1,None,False\n3,3,,False\n4,4,Stand,False\n"))
        self.assertEqual(result["gap_bins"], [0, 2])
        self.assertEqual(result["unassigned_bins"], [1, 3])
        self.assertEqual(result["diagnostic_bin_counts"]["nonfall_label"], 1)

    def test_invalid_or_unbounded_intervals_fail(self):
        for interval in ("-1,1", "2,1", "0.5,1", "0,86400", "NaN,1"):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                rows(interval + ",Stand,False\n")

    def test_unknown_flags_actions_and_malformed_csv_fail(self):
        for body in ("0,1,Stand,false\n", "0,1,Walk,False\n", "0,1,Stand\n", "0,1,Stand,False,extra\n", ""):
            with self.subTest(body=body), self.assertRaises(ValueError):
                rows(body)

    def test_column_order_must_match_source(self):
        with self.assertRaises(ValueError):
            AUDIT.read_rows(b"start_time,end_time,is_fall,action\n0,1,False,Stand\n")

    def test_unsorted_rows_are_flagged_and_audited_without_silent_sort(self):
        result = AUDIT.audit_rows(rows("2,2,Sit,False\n0,0,Stand,False\n"))
        self.assertEqual(result["out_of_order_rows"], [3])
        self.assertEqual(result["gap_bins"], [1])


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.lock = AUDIT.load_lock(AUDIT.LOCK)

    def test_all_upstream_files_match_and_frozen_inventory_is_reproducible(self):
        digest = AUDIT.sha256(AUDIT.LOCK.read_bytes())
        first = AUDIT.build_report(self.lock, AUDIT.FIXTURES, digest)
        self.assertEqual(first, AUDIT.build_report(self.lock, AUDIT.FIXTURES, digest))
        archived = ROOT / "docs/benchmarks/posture-source-v1.audit.json"
        self.assertEqual(first, json.loads(archived.read_bytes()))
        self.assertEqual((json.dumps(first, indent=2) + "\n").encode(), archived.read_bytes())
        self.assertFalse(first["benchmark_eligible"])
        self.assertEqual(first["candidate_summary"], {
            "videos": 7, "source_training_videos_excluded": 3,
            "media_bytes": 1981798589, "hash_verified_videos": 0,
            "diagnostic_bin_counts_not_exposure_seconds": {
                "conflict": 6, "fall_label": 91, "gap": 2,
                "nonfall_label": 1267, "unassigned": 349},
            "duplicate_row_groups": 4, "single_timestamp_rows": 233,
        })

    def test_changed_source_bytes_are_rejected(self):
        entry = self.lock["files"][0]
        data = (AUDIT.FIXTURES / entry["path"]).read_bytes()
        AUDIT.verify_bytes(data, entry)
        for changed in (data + b"\n", data.replace(b"\n", b"\r\n")):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                AUDIT.verify_bytes(changed, entry)

    def test_lock_rejects_split_revision_inventory_or_hash_drift(self):
        mutations = [lambda x: x["source"].update(revision="main"),
                     lambda x: x["videos"][0].update(role="candidate-evaluation"),
                     lambda x: x["files"].pop(),
                     lambda x: x["videos"][0].update(sha256="not-a-hash")]
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "lock.json"
            for mutate in mutations:
                altered = copy.deepcopy(self.lock)
                mutate(altered)
                path.write_text(json.dumps(altered), encoding="utf-8")
                with self.assertRaises(ValueError):
                    AUDIT.load_lock(path)

    def test_paths_cannot_escape_cache_on_windows_or_posix(self):
        for path in ("../secret", "/absolute", "C:/secret", "a\\secret", "a//b", "./a"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                AUDIT.safe_path(AUDIT.FIXTURES, path)

    def test_failed_fetch_is_not_written_to_cache(self):
        # Bad HTTP content must never become an accepted source annotation.
        with tempfile.TemporaryDirectory() as folder, patch.object(AUDIT.urllib.request, "urlopen") as request:
            request.return_value.__enter__.return_value.read.return_value = b"bad bytes"
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                AUDIT.build_report(self.lock, pathlib.Path(folder), "unused", fetch_missing=True)
            self.assertEqual(list(pathlib.Path(folder).iterdir()), [])

    def test_media_mismatch_stops_before_scoring(self):
        with tempfile.TemporaryDirectory() as folder:
            target = AUDIT.safe_path(pathlib.Path(folder), self.lock["videos"][0]["path"])
            target.parent.mkdir(parents=True)
            target.write_bytes(b"not a real video")
            with self.assertRaisesRegex(ValueError, "Media size mismatch"):
                AUDIT.build_report(self.lock, AUDIT.FIXTURES, "unused", media_root=pathlib.Path(folder))

    def test_same_size_corrupt_media_fails_checksum_and_valid_hash_is_not_decoded(self):
        lock = copy.deepcopy(self.lock)
        lock["videos"][0].update(size=5, sha256=hashlib.sha256(b"video").hexdigest())
        with tempfile.TemporaryDirectory() as folder:
            target = AUDIT.safe_path(pathlib.Path(folder), lock["videos"][0]["path"])
            target.parent.mkdir(parents=True)
            target.write_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError, "Media checksum mismatch"):
                AUDIT.build_report(lock, AUDIT.FIXTURES, "unused", media_root=pathlib.Path(folder))
            target.write_bytes(b"video")
            result = AUDIT.build_report(lock, AUDIT.FIXTURES, "unused", media_root=pathlib.Path(folder))
            self.assertEqual(result["clips"][0]["media_status"], "hash-verified-not-decoded")
            self.assertFalse(result["benchmark_eligible"])


if __name__ == "__main__":
    unittest.main()
