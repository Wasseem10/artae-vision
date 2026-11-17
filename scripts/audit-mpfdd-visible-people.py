"""Compare provisional frame-visible people counts with pinned pose observations.

This is a count diagnostic, never person recall, precision, or fall accuracy.
Videos and extracted frames stay local. Extraction requires OpenCV; scoring is
stdlib-only. See docs/mpfdd-visible-person-audit.md for the annotation protocol.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(labels: dict, manifest: dict, report: dict) -> dict:
    if (labels["schemaVersion"] != 1 or
        labels["reviewStatus"] != "provisional-ai-visual-review" or
        manifest["datasetId"] != "mpfdd-github-available-v1" or
        labels["sourceRevision"] != manifest["sourceRevision"] or
        report["dataset"]["sourceRevision"] != manifest["sourceRevision"] or
        report["dataset"]["datasetId"] != manifest["datasetId"] or
        report["schemaVersion"] != 4 or report["status"] != "complete" or
        report["provenance"]["localGitDirty"] or
        report["provenance"]["detector"]["rule"] != "FusedMultiPersonFallRule/fall-v1"):
        raise ValueError("Expected provisional labels and a clean pinned MPFDD observation replay")
    cases = {case["id"]: case for case in manifest["cases"]}
    replays = {row["id"]: row for row in report["results"]}
    if len(cases) != len(manifest["cases"]) or len(replays) != len(report["results"]):
        raise ValueError("Duplicate case or replay IDs")
    results, seen = [], set()
    if not labels["frames"]:
        raise ValueError("No annotated frames")
    for label in labels["frames"]:
        case_id, seconds, visible = label["caseId"], label["seconds"], label["visiblePeople"]
        if (type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0 or
            type(visible) is not int or visible < 0 or (case_id, seconds) in seen):
            raise ValueError("Invalid or duplicate frame label")
        seen.add((case_id, seconds))
        case, replay = cases[case_id], replays[case_id]
        if (label["videoSha256"] != case["videoSha256"] or
            replay["videoSha256"] != case["videoSha256"] or replay.get("error")):
            raise ValueError(f"Changed media or failed replay: {case_id}")
        matches = [frame for frame in replay["observationTrace"] if frame["seconds"] == seconds]
        if len(matches) != 1:
            raise ValueError(f"No unique observation at annotated time: {case_id} {seconds}")
        observation = matches[0]
        raw, usable, tracks = observation["rawPoseCount"], observation["usablePoseCount"], observation["trackIds"]
        if (type(raw) is not int or type(usable) is not int or not 0 <= usable <= raw <= 4 or
            not isinstance(tracks, list) or len(tracks) != len(set(tracks)) or
            any(type(track) is not int or track <= 0 for track in tracks)):
            raise ValueError("Invalid pose observation")
        results.append({
            "caseId": case_id, "seconds": seconds, "visiblePeople": visible,
            "rawPoses": raw, "usablePoses": usable, "fusedTracks": len(tracks),
            "rawCountDeficit": max(0, visible - raw),
            "rawCountExcess": max(0, raw - visible),
            "fusedCountDeficit": max(0, visible - len(tracks)),
        })
    return {
        "schemaVersion": 1,
        "scope": "Provisional visual count diagnostic on selected, already examined frames; no person matching or accuracy estimate",
        "reviewStatus": labels["reviewStatus"],
        "sourceRevision": labels["sourceRevision"],
        "replayCodeRevision": report["provenance"]["localGitRevision"],
        "summary": {
            "annotatedFrames": len(results),
            "framesWithRawCountDeficit": sum(row["rawCountDeficit"] > 0 for row in results),
            "framesWithRawCountExcess": sum(row["rawCountExcess"] > 0 for row in results),
            "framesWithFusedCountDeficit": sum(row["fusedCountDeficit"] > 0 for row in results),
        },
        "results": results,
        "limitation": "AI-assisted counts await human review. Equal counts can conceal misses and duplicates; count gaps cannot identify which person was missed, false poses, or broken track identity.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--media-root", type=Path, help="Local MPFDD folder for optional frame extraction")
    parser.add_argument("--frames-dir", type=Path, help="Local frame directory; requires --media-root")
    args = parser.parse_args()
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if (labels["manifestSha256"] != digest(args.manifest) or
        labels["browserReportSha256"] != digest(args.report) or
        report["provenance"]["localSourceHashes"]["apps/web/public/vision/mpfdd/manifest.json"] != digest(args.manifest)):
        raise ValueError("Labels or replay refer to different input hashes")
    output = compare(labels, manifest, report)
    # Tracked labels may acquire CRLF on Windows; hash their canonical JSON.
    label_hash = hashlib.sha256(json.dumps(labels, sort_keys=True, separators=(",", ":"),
                                          ensure_ascii=False).encode("utf-8")).hexdigest()
    output.update(labelsCanonicalSha256=label_hash, manifestSha256=digest(args.manifest),
                  browserReportSha256=digest(args.report))
    if bool(args.frames_dir) != bool(args.media_root):
        raise ValueError("Supply both --media-root and --frames-dir for extraction")
    if args.frames_dir:
        import cv2  # Optional OpenCV dependency; scoring uses only the stdlib.
        args.frames_dir.mkdir(parents=True, exist_ok=True)
        cases = {case["id"]: case for case in manifest["cases"]}
        media_root = args.media_root.resolve()
        for label in labels["frames"]:
            case = cases[label["caseId"]]
            video = (media_root / case["sourcePath"]).resolve()
            if not video.is_relative_to(media_root) or digest(video) != label["videoSha256"]:
                raise ValueError("Changed video or source path outside media root")
            cap = cv2.VideoCapture(str(video))
            try:
                fps = cap.get(cv2.CAP_PROP_FPS)
                if not math.isfinite(fps) or fps <= 0:
                    raise ValueError("Invalid source FPS")
                # Source clips have mixed FPS. Never assume 30 FPS for sampling.
                cap.set(cv2.CAP_PROP_POS_FRAMES, round(label["seconds"] * fps))
                ok, frame = cap.read()
                timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
                if not ok or not math.isfinite(timestamp) or abs(timestamp - label["seconds"]) > 0.001:
                    raise ValueError("Decoded frame is not at the annotated timestamp")
                if label["caseId"] != Path(label["caseId"]).name:
                    raise ValueError("Invalid case filename")
                path = args.frames_dir / f"{label['caseId']}-{label['seconds']:g}.png"
                if not cv2.imwrite(str(path), frame):
                    raise ValueError("Cannot save audit frame")
            finally:
                cap.release()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(output["summary"], indent=2))


if __name__ == "__main__":
    main()
