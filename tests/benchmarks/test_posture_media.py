import hashlib
import importlib.util
import io
import pathlib
import tempfile
import unittest
from fractions import Fraction
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("posture_media", ROOT / "scripts/acquire-posture-media.py")
MEDIA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MEDIA)


def entry(data=b"video"):
    return {"path": "valid/fall_detection_9.mp4", "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def frame(pts, duration=1, **overrides):
    values = {"pts": pts, "duration": duration, "time_base": Fraction(1, 10),
              "width": 320, "height": 240, "is_corrupt": False}
    return SimpleNamespace(**(values | overrides))


def summarize(frames, count=2, start=Fraction(0), duration=Fraction(1, 5)):
    return MEDIA.summarize_frames(frames, count, start, duration)


class AcquisitionTests(unittest.TestCase):
    def test_verified_download_is_published_atomically_and_reused_without_network(self):
        calls = []
        def opener(request, timeout):
            calls.append(request.full_url)
            self.assertEqual(timeout, 60)
            return io.BytesIO(b"video")
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            path = MEDIA.acquire(entry(), root, fetch=True, opener=opener)
            self.assertEqual(path.read_bytes(), b"video")
            self.assertEqual(list(path.parent.glob("*.part")), [])
            self.assertEqual(MEDIA.acquire(entry(), root, fetch=True, opener=opener), path)
            self.assertEqual(len(calls), 1)
            self.assertIn(MEDIA.AUDIT.REVISION, calls[0])

    def test_missing_media_without_fetch_never_calls_network(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(FileNotFoundError):
            MEDIA.acquire(entry(), pathlib.Path(folder))

    def test_corrupt_existing_cache_is_rejected_and_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            target = MEDIA.AUDIT.safe_path(root, entry()["path"])
            target.parent.mkdir(parents=True)
            target.write_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                MEDIA.acquire(entry(), root, fetch=True, opener=lambda *_: self.fail("Unexpected network"))
            self.assertEqual(target.read_bytes(), b"wrong")

    def test_truncated_oversized_or_same_size_wrong_download_never_becomes_cache(self):
        for payload in (b"short"[:3], b"too long", b"wrong"):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as folder:
                root = pathlib.Path(folder)
                with self.assertRaises(ValueError):
                    MEDIA.acquire(entry(), root, fetch=True, opener=lambda *a, **k: io.BytesIO(payload))
                self.assertFalse((root / entry()["path"]).exists())
                self.assertEqual(list(root.rglob("*.part")), [])

    def test_interrupted_transfer_cleans_partial_file(self):
        class Interrupted(io.BytesIO):
            def read(self, _size):
                if self.tell():
                    raise TimeoutError("simulated read timeout")
                return super().read(2)
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            with self.assertRaises(TimeoutError):
                MEDIA.acquire(entry(), root, fetch=True, opener=lambda *a, **k: Interrupted(b"video"))
            self.assertEqual(list(root.rglob("*.part")), [])
            self.assertFalse((root / entry()["path"]).exists())

    def test_path_traversal_cannot_fetch_or_write(self):
        bad = entry() | {"path": "../outside.mp4"}
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            MEDIA.acquire(bad, pathlib.Path(folder), fetch=True)


class TimestampTests(unittest.TestCase):
    def test_all_frames_and_exact_rational_pts_are_retained(self):
        result = summarize(iter([frame(0), frame(1)]))
        self.assertEqual(result["decoded_frames"], 2)
        self.assertEqual(result["decoded_span_seconds_exact"], "1/5")
        self.assertEqual(result["last_pts_seconds_exact"], "1/10")
        self.assertTrue(result["decoded_span_matches_stream_duration"])
        trace = b"0,1/10,1,320,240\n1,1/10,1,320,240\n"
        self.assertEqual(result["presentation_trace_sha256"], hashlib.sha256(trace).hexdigest())

    def test_variable_frame_durations_do_not_use_a_nominal_frame_rate(self):
        result = summarize([frame(0, 2), frame(2, 3)], duration=Fraction(1, 2))
        self.assertEqual(result["decoded_span_seconds_exact"], "1/2")
        self.assertEqual(result["frame_interval_gaps"], 0)
        self.assertEqual(result["frame_interval_overlaps"], 0)

    def test_empty_or_incomplete_decode_fails(self):
        for frames in ([], [frame(0)]):
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                summarize(frames)

    def test_missing_corrupt_or_nonincreasing_timestamps_fail(self):
        cases = [[frame(0), frame(1, is_corrupt=True)], [frame(0), frame(None)],
                 [frame(0), frame(1, time_base=None)], [frame(0), frame(0)],
                 [frame(1), frame(0)], [frame(0), frame(1, time_base=Fraction(0))]]
        for frames in cases:
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                summarize(frames)

    def test_dimensions_cannot_be_zero_or_change_mid_stream(self):
        for dimensions in ({"width": 0}, {"height": 0}, {"width": 640}):
            with self.subTest(dimensions=dimensions), self.assertRaises(ValueError):
                summarize([frame(0), frame(1, **dimensions)])

    def test_missing_last_frame_duration_is_not_estimated_from_fps(self):
        result = summarize([frame(0), frame(1, 0)])
        self.assertEqual(result["missing_frame_durations"], 1)
        self.assertIsNone(result["decoded_span_seconds_exact"])
        self.assertFalse(MEDIA.reconcile([{"start": 0, "end": 0, "line": 2}], result)["timeline_aligned"])

    def test_gap_overlap_or_unknown_origin_disables_bounds_inference(self):
        cases = [summarize([frame(0), frame(2)]),
                 summarize([frame(0, 2), frame(1)]),
                 summarize([frame(0), frame(1)], start=None),
                 summarize([frame(0), frame(1)], duration=Fraction(3, 10))]
        for result in cases:
            with self.subTest(result=result):
                self.assertFalse(MEDIA.reconcile([{"start": 0, "end": 0, "line": 2}], result)["timeline_aligned"])

    def test_bounds_do_not_silently_clip_labels_or_convert_them_into_exposure(self):
        result = summarize([frame(0, 10), frame(10, 10)], duration=Fraction(2))
        rows = [{"line": 2, "start": 0, "end": 0}, {"line": 3, "start": 1, "end": 1},
                {"line": 4, "start": 2, "end": 2}]
        bounds = MEDIA.reconcile(rows, result)
        self.assertEqual(bounds["rows_starting_at_or_after_video_end"], [4])
        self.assertEqual(bounds["inclusive_bin_end_exceeds_video_rows"], [4])
        self.assertEqual(rows[-1]["end"], 2)
        self.assertNotIn("negative_exposure_seconds", bounds)

    def test_partial_final_bin_is_flagged_without_rounding_up_video_end(self):
        result = summarize([frame(0), frame(1)], duration=Fraction(1, 5))
        bounds = MEDIA.reconcile([{"start": 0, "end": 0, "line": 2}], result)
        self.assertEqual(bounds["inclusive_bin_end_exceeds_video_rows"], [2])
        self.assertEqual(bounds["rows_ending_at_or_after_video_end"], [])


class RealDecoderTests(unittest.TestCase):
    def test_tiny_generated_mp4_is_fully_decoded_with_exact_duration(self):
        try:
            import av
        except ImportError:
            self.skipTest("Optional av dependency is not installed")
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "fixture.mp4"
            with av.open(str(path), "w") as output:
                stream = output.add_stream("mpeg4", rate=10)
                stream.width = stream.height = 16
                stream.pix_fmt = "yuv420p"
                for index in range(8):
                    video = av.VideoFrame(16, 16, "yuv420p")
                    for plane in video.planes:
                        plane.update(bytes(plane.buffer_size))
                    video.pts, video.time_base = index, Fraction(1, 10)
                    for packet in stream.encode(video):
                        output.mux(packet)
                for packet in stream.encode():
                    output.mux(packet)
            result = MEDIA.decode_video(path, av)
            self.assertEqual(result["decoded_frames"], 8)
            self.assertEqual(result["decoded_span_seconds_exact"], "4/5")
            self.assertTrue(result["first_pts_matches_stream_start"])
            self.assertTrue(result["decoded_span_matches_stream_duration"])


if __name__ == "__main__":
    unittest.main()
