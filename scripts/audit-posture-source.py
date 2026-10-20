"""Audit a pinned public annotation source; never infer detector performance.

Only stdlib is required. Integer bins below are a diagnostic convention, NOT
measured video exposure. The upstream card does not define endpoint semantics.
"""

import argparse
import csv
import hashlib
import io
import json
import pathlib
import re
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCK = ROOT / "docs/benchmarks/posture-source-v1.lock.json"
FIXTURES = ROOT / "tests/fixtures/posture-source-v1"
REPOSITORY = "pat2echo/fall-detection-posture-classification"
REVISION = "5c075333e557e43cbcb42306fc4475201a625982"
HEADERS = ["start_time", "end_time", "action", "is_fall"]
ACTIONS = {"Stand", "Sit", "Lie", "Stand-Sit", "Stand-Lie", "Sit-Stand",
           "Sit-Lie", "Lie-Stand", "Lie-Sit", "None", ""}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verify_bytes(data, entry):
    blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    if (len(data) != entry["size"] or sha256(data) != entry["sha256"]
            or blob != entry["git_blob_sha1"]):
        raise ValueError(f"Source checksum mismatch: {entry['path']}")


def safe_path(root, relative):
    # Reject traversal/Windows drive syntax even when running this on POSIX.
    if (not relative or "\\" in relative or ":" in relative
            or any(part in ("", ".", "..") for part in relative.split("/"))):
        raise ValueError(f"Unsafe source path: {relative}")
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"Source path escapes root: {relative}")
    return target


def load_lock(path):
    lock = json.loads(path.read_bytes())
    if (lock.get("schema_version") != 1
            or lock["source"]["repository"] != REPOSITORY
            or lock["source"]["revision"] != REVISION
            or lock["source"]["license"] != "CC-BY-4.0"):
        raise ValueError("Unexpected source identity/version/license")
    expected_videos = {f"train/hr_fall_detection_{i}.mp4" for i in range(1, 4)}
    expected_videos |= {f"valid/fall_detection_{i}.mp4" for i in range(4, 11)}
    videos = lock["videos"]
    if len(videos) != 10 or {v["path"] for v in videos} != expected_videos:
        raise ValueError("Source video inventory changed")
    expected_labels = {label_path(v["path"]) for v in videos}
    entries = lock["files"]
    expected_files = expected_labels | {"README.md", "LICENSE.txt", "column_descriptions.md", "CITATION.cff"}
    if len(entries) != 14 or {e["path"] for e in entries} != expected_files:
        raise ValueError("Source metadata/label inventory changed")
    for entry in entries + videos:
        safe_path(FIXTURES, entry["path"])
        if (type(entry["size"]) is not int or entry["size"] <= 0
                or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
            raise ValueError("Invalid locked file size/hash")
    for entry in entries:
        if not re.fullmatch(r"[0-9a-f]{40}", entry["git_blob_sha1"]):
            raise ValueError("Invalid locked Git blob hash")
    for video in videos:
        split = video["path"].split("/")[0]
        role = "candidate-evaluation" if split == "valid" else "excluded-source-training"
        if video["source_split"] != split or video["role"] != role:
            raise ValueError("Source split/role changed")
    return lock


def label_path(video_path):
    path = pathlib.PurePosixPath(video_path)
    return str(path.parent / "labels" / path.with_suffix(".csv").name)


def read_rows(data):
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    if reader.fieldnames != HEADERS:
        raise ValueError("Unexpected annotation columns")
    rows = []
    for row in reader:
        line = reader.line_num
        if set(row) != set(HEADERS) or any(v is None for v in row.values()):
            raise ValueError(f"Malformed annotation row {line}")
        if not all(re.fullmatch(r"[0-9]+", row[k]) for k in HEADERS[:2]):
            raise ValueError(f"Non-integer/negative timestamp at row {line}")
        start, end = int(row["start_time"]), int(row["end_time"])
        if not 0 <= start <= end < 86400:
            raise ValueError(f"Invalid/overlong interval at row {line}")
        if row["is_fall"] not in ("True", "False") or row["action"] not in ACTIONS:
            raise ValueError(f"Unknown fall flag/action at row {line}")
        rows.append({"line": line, "start": start, "end": end,
                     "action": row["action"], "is_fall": row["is_fall"] == "True"})
    if not rows:
        raise ValueError("Empty annotation file")
    return rows


def audit_rows(rows):
    duplicates = defaultdict(list)
    bins = defaultdict(list)
    for row in rows:
        key = (row["start"], row["end"], row["action"], row["is_fall"])
        duplicates[key].append(row["line"])
        for second in range(row["start"], row["end"] + 1):
            bins[second].append(row)
    counts = Counter()
    conflicts, gaps, unassigned = [], [], []
    positive_runs, previous_positive = [], False
    for second in range(max(bins) + 1):
        owners = bins.get(second, [])
        states = {(r["action"], r["is_fall"]) for r in owners}
        if not owners:
            state = "gap"
            gaps.append(second)
        elif len(states) > 1:
            state = "conflict"
            conflicts.append({"bin": second, "rows": [r["line"] for r in owners]})
        elif next(iter(states))[0] in ("None", ""):
            state = "unassigned"
            unassigned.append(second)
        else:
            state = "fall_label" if next(iter(states))[1] else "nonfall_label"
        counts[state] += 1
        if state == "fall_label":
            if not previous_positive:
                positive_runs.append([second, second])
            else:
                positive_runs[-1][1] = second
        previous_positive = state == "fall_label"
    return {
        "rows": len(rows),
        "fall_rows": sum(r["is_fall"] for r in rows),
        "single_timestamp_rows": sum(r["start"] == r["end"] for r in rows),
        "last_label_timestamp": max(bins),
        "duplicate_row_groups": [lines for lines in duplicates.values() if len(lines) > 1],
        "out_of_order_rows": [b["line"] for a, b in zip(rows, rows[1:]) if b["start"] < a["start"]],
        "diagnostic_bin_counts": {k: counts[k] for k in ("fall_label", "nonfall_label", "unassigned", "conflict", "gap")},
        "conflicting_bins": conflicts,
        "gap_bins": gaps,
        "unassigned_bins": unassigned,
        "positive_label_runs_not_adjudicated_events": positive_runs,
    }


def build_report(lock, fixture_root, lock_digest, fetch_missing=False, media_root=None):
    for entry in lock["files"]:
        target = safe_path(fixture_root, entry["path"])
        if not target.exists() and fetch_missing:
            url = f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/"
            with urllib.request.urlopen(url + urllib.parse.quote(entry["path"]), timeout=30) as response:
                data = response.read(entry["size"] + 1)
            verify_bytes(data, entry)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        verify_bytes(target.read_bytes(), entry)
    clips = []
    for video in lock["videos"]:
        clip = {**video, "labels": label_path(video["path"])}
        clip["annotation_audit"] = audit_rows(read_rows(safe_path(fixture_root, clip["labels"]).read_bytes()))
        clip["media_status"] = "not-verified"
        if media_root is not None:
            target = safe_path(media_root, video["path"])
            if target.exists():
                if target.stat().st_size != video["size"]:
                    raise ValueError(f"Media size mismatch: {video['path']}")
                with target.open("rb") as source:
                    digest = hashlib.file_digest(source, "sha256").hexdigest()
                if digest != video["sha256"]:
                    raise ValueError(f"Media checksum mismatch: {video['path']}")
                clip["media_status"] = "hash-verified-not-decoded"
        clips.append(clip)
    candidate = [c for c in clips if c["role"] == "candidate-evaluation"]
    totals = Counter()
    for clip in candidate:
        totals.update(clip["annotation_audit"]["diagnostic_bin_counts"])
    return {
        "schema_version": 1,
        "source_lock_sha256": lock_digest,
        "source": lock["source"],
        "purpose": "source annotation quality audit, not a detector benchmark",
        "bin_convention": "Diagnostic only: integers start..end inclusive. Endpoint semantics need adjudication; bins are not measured seconds of exposure.",
        "benchmark_eligible": False,
        "blockers": [
            "Verify and decode the seven candidate videos; reconcile annotation endpoints with actual video duration.",
            "Adjudicate duplicates, conflicting boundaries, gaps, and unassigned activity against footage; preserve upstream labels.",
            "Freeze timed fall-event definitions and post-fall exclusion/recovery windows before scoring; fall rows and positive runs are not verified events.",
            "Freeze baseline/candidate, runtime, sampling, one-to-one event matching, latency tolerance, and negative exposure protocol before inference.",
            "One subject only: this source cannot validate cross-person or multi-person tracking performance.",
        ],
        "candidate_summary": {
            "videos": len(candidate),
            "source_training_videos_excluded": len(clips) - len(candidate),
            "media_bytes": sum(c["size"] for c in candidate),
            "hash_verified_videos": sum(c["media_status"] != "not-verified" for c in candidate),
            "diagnostic_bin_counts_not_exposure_seconds": dict(sorted(totals.items())),
            "duplicate_row_groups": sum(len(c["annotation_audit"]["duplicate_row_groups"]) for c in candidate),
            "single_timestamp_rows": sum(c["annotation_audit"]["single_timestamp_rows"] for c in candidate),
        },
        "clips": clips,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=pathlib.Path, default=LOCK)
    parser.add_argument("--source-dir", type=pathlib.Path, default=FIXTURES)
    parser.add_argument("--fetch-missing", action="store_true", help="Fetch only the pinned metadata and labels, never videos; verify existing files too")
    parser.add_argument("--media-root", type=pathlib.Path, help="Optionally hash local upstream videos; no inference or duration decoding")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    report = build_report(load_lock(args.lock), args.source_dir, sha256(args.lock.read_bytes()), args.fetch_missing, args.media_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report["candidate_summary"], indent=2))
    print("BLOCKED for benchmark promotion; annotation diagnostics are not accuracy or negative-exposure measurements.")


if __name__ == "__main__":
    main()
