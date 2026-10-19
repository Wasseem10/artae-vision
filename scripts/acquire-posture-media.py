"""Acquire and fully decode the seven locked candidate videos, without inference.

Downloads and hash verification require only stdlib. Full decoding additionally
requires av==19.0.1. All media remain local; reports are metadata only.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import platform
import subprocess
import tempfile
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("posture_source_audit", ROOT / "scripts/audit-posture-source.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
AV_VERSION = "19.0.1"


def verify_media(path, entry):
    if path.stat().st_size != entry["size"]:
        raise ValueError(f"Media size mismatch: {entry['path']}")
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(f"Media checksum mismatch: {entry['path']}")


def acquire(entry, media_root, fetch=False, opener=None):
    target = AUDIT.safe_path(media_root, entry["path"])
    if target.exists():
        verify_media(target, entry)
        return target
    if not fetch:
        raise FileNotFoundError(f"Missing locked media: {entry['path']}; use --fetch to download")
    url = (f"https://huggingface.co/datasets/{AUDIT.REPOSITORY}/resolve/{AUDIT.REVISION}/"
           + urllib.parse.quote(entry["path"]))
    request = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".part", delete=False) as output:
            temporary = pathlib.Path(output.name)
            with (opener or urllib.request.urlopen)(request, timeout=60) as response:
                size, digest = 0, hashlib.sha256()
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > entry["size"]:
                        raise ValueError(f"Oversized download: {entry['path']}")
                    digest.update(block)
                    output.write(block)
            if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                raise ValueError(f"Download integrity failure: {entry['path']}")
        # Publish complete verified bytes without overwriting a concurrent cache.
        try:
            os.link(temporary, target)
        except FileExistsError:
            verify_media(target, entry)
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def rational(value):
    return f"{value.numerator}/{value.denominator}"


def summarize_frames(frames, declared_frames, stream_start, stream_duration):
    """Inspect every decoded frame's PTS/duration; never estimate time from FPS."""
    count, first, previous, previous_end, width, height = 0, None, None, None, None, None
    gaps, overlaps = 0, 0
    missing_duration = 0
    trace = hashlib.sha256()
    for frame in frames:
        if frame.is_corrupt or frame.pts is None or frame.time_base is None:
            raise ValueError("Corrupt frame or missing presentation timestamp/time base")
        base = Fraction(frame.time_base)
        if base <= 0 or type(frame.pts) is not int:
            raise ValueError("Invalid presentation timestamp/time base")
        pts = frame.pts * base
        if previous is not None and pts <= previous:
            raise ValueError("Non-increasing decoded presentation timestamps")
        if frame.width <= 0 or frame.height <= 0:
            raise ValueError("Invalid decoded frame dimensions")
        if count and (frame.width, frame.height) != (width, height):
            raise ValueError("Decoded frame dimensions change mid-stream")
        width, height = frame.width, frame.height
        if frame.duration is None or frame.duration <= 0:
            missing_duration += 1
            end = None
        else:
            end = pts + frame.duration * base
        if previous_end is not None:
            gaps += pts > previous_end
            overlaps += pts < previous_end
        trace.update(f"{frame.pts},{rational(base)},{frame.duration},{width},{height}\n".encode())
        first = pts if first is None else first
        count, previous, previous_end = count + 1, pts, end
    if not count:
        raise ValueError("No video frames decoded")
    if declared_frames and count != declared_frames:
        raise ValueError(f"Incomplete decode: {count} frames vs {declared_frames} declared")
    duration = previous_end - first if previous_end is not None else None
    return {
        "decoded_frames": count, "declared_frames": declared_frames,
        "width": width, "height": height,
        "first_pts_seconds_exact": rational(first),
        "last_pts_seconds_exact": rational(previous),
        "last_frame_end_seconds_exact": rational(previous_end) if previous_end is not None else None,
        "decoded_span_seconds_exact": rational(duration) if duration is not None else None,
        "decoded_span_seconds": float(duration) if duration is not None else None,
        "stream_start_seconds_exact": rational(stream_start) if stream_start is not None else None,
        "stream_duration_seconds_exact": rational(stream_duration) if stream_duration is not None else None,
        "first_pts_matches_stream_start": stream_start is not None and first == stream_start,
        "decoded_span_matches_stream_duration": duration is not None and duration == stream_duration,
        "missing_frame_durations": missing_duration,
        "frame_interval_gaps": gaps, "frame_interval_overlaps": overlaps,
        "presentation_trace_sha256": trace.hexdigest(),
        "presentation_trace_format": "UTF-8 LF per decoded frame: pts,time_base_fraction,duration,width,height",
    }


def reconcile(rows, decoded):
    duration = decoded["decoded_span_seconds_exact"]
    aligned = (decoded["first_pts_matches_stream_start"]
               and decoded["decoded_span_matches_stream_duration"]
               and decoded["missing_frame_durations"] == 0
               and decoded["frame_interval_gaps"] == 0
               and decoded["frame_interval_overlaps"] == 0)
    if not aligned or duration is None:
        return {"timeline_aligned": False, "reason": "PTS origin/duration/intervals need review; label bounds not inferred"}
    end = Fraction(duration)
    return {
        "timeline_aligned": True,
        "rows_starting_at_or_after_video_end": [r["line"] for r in rows if r["start"] >= end],
        "rows_ending_at_or_after_video_end": [r["line"] for r in rows if r["end"] >= end],
        "inclusive_bin_end_exceeds_video_rows": [r["line"] for r in rows if r["end"] + 1 > end],
        "last_label_timestamp": max(r["end"] for r in rows),
        "video_end_minus_last_label_timestamp_seconds_exact": rational(end - max(r["end"] for r in rows)),
        "note": "Bounds diagnostics only. Inclusive second bins are not adjudicated activity intervals or negative exposure.",
    }


def decode_video(path, av):
    with av.open(str(path)) as container:
        if len(container.streams.video) != 1:
            raise ValueError("Expected exactly one video stream")
        stream = container.streams.video[0]
        base = Fraction(stream.time_base)
        start = stream.start_time * base if stream.start_time is not None else None
        duration = stream.duration * base if stream.duration is not None else None
        result = summarize_frames(container.decode(stream), stream.frames, start, duration)
        return {"codec": stream.codec_context.name, **result}


def git_provenance():
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    return {"code_revision": revision, "working_tree_dirty": dirty,
            "media_script_sha256": AUDIT.sha256(pathlib.Path(__file__).read_bytes()),
            "annotation_script_sha256": AUDIT.sha256((ROOT / "scripts/audit-posture-source.py").read_bytes()),
            "python": platform.python_version(), "platform": platform.platform()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-root", type=pathlib.Path, default=ROOT / "artifacts/posture-source-media")
    parser.add_argument("--fetch", action="store_true", help="Download missing locked videos; rejects corrupt existing files")
    parser.add_argument("--download-only", action="store_true", help="Verify bytes only; no decoding or duration claims")
    parser.add_argument("--output", type=pathlib.Path, required=True, help="New report path; an existing report is never overwritten")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a fresh report filename")
    lock = AUDIT.load_lock(AUDIT.LOCK)
    source = AUDIT.build_report(lock, AUDIT.FIXTURES, AUDIT.sha256(AUDIT.LOCK.read_bytes()))
    provenance = git_provenance()
    if not args.download_only and provenance["working_tree_dirty"]:
        parser.error("Commit scoped source changes before recording a full decode")
    av = None
    if not args.download_only:
        import av
        if av.__version__ != AV_VERSION:
            parser.error(f"Full decode requires av=={AV_VERSION}; found {av.__version__}")
        provenance.update(pyav=av.__version__, ffmpeg_libraries={k: list(v) for k, v in av.library_versions.items()})
    entries = [e for e in lock["videos"] if e["role"] == "candidate-evaluation"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        # Parallel acquisition is bounded to two files; every candidate is required.
        paths = list(pool.map(lambda entry: acquire(entry, args.media_root, args.fetch), entries))
    clips = []
    for entry, path in zip(entries, paths):
        clip = {**entry, "media_status": "hash-verified-not-decoded"}
        if av is not None:
            # Verify again immediately before decoding, including existing caches.
            verify_media(path, entry)
            clip["decode"] = decode_video(path, av)
            verify_media(path, entry)
            rows = AUDIT.read_rows(AUDIT.safe_path(AUDIT.FIXTURES, AUDIT.label_path(entry["path"])).read_bytes())
            clip["annotation_bounds"] = reconcile(rows, clip["decode"])
            clip["media_status"] = "hash-verified-fully-decoded"
        clips.append(clip)
        print(json.dumps({"path": entry["path"], "status": clip["media_status"],
                          "frames": clip.get("decode", {}).get("decoded_frames")}), flush=True)
    if not args.download_only:
        current = git_provenance()
        if any(current[k] != provenance[k] for k in current):
            raise ValueError("Code/provenance changed during full decode; no report published")
    report = {
        "schema_version": 1, "source_lock_sha256": source["source_lock_sha256"],
        "source": lock["source"], "provenance": provenance,
        "purpose": "source media and annotation-boundary preflight, no inference",
        "benchmark_eligible": False,
        "remaining_blockers": ["Activity/event labels and endpoint semantics need visual adjudication.",
                               "Freeze detector comparison and event-matching protocol before inference.",
                               "One subject; not a multi-person or cross-person validation source."],
        "candidate_videos": len(clips), "source_training_videos_excluded": 3,
        "media_bytes": sum(e["size"] for e in entries),
        "decoded_frames": sum(c.get("decode", {}).get("decoded_frames", 0) for c in clips),
        "clips": clips,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(report, indent=2) + "\n")
    print(f"Verified {len(clips)} videos. No model inference or accuracy/exposure score.", flush=True)


if __name__ == "__main__":
    main()
