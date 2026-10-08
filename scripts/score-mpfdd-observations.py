"""Summarize frame-level MPFDD pose observations without claiming person-level recall.

Run after a clean multi-person replay: python scripts/score-mpfdd-observations.py
The full browser export and source videos stay gitignored under artifacts/.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "apps/web/public/vision/mpfdd/manifest.json"
REPORT = ROOT / "artifacts/mpfdd/evaluation-multiperson.json"
OUTPUT = ROOT / "docs/benchmarks/mpfdd-observations-v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_case(case: dict, row: dict) -> dict:
    trace = row.get("observationTrace")
    if not isinstance(trace, list) or len(trace) != row["framesAnalyzed"]:
        raise ValueError(f"Missing frame trace: {case['id']}")
    nominal = int(re.search(r"-p([2-5])-", case["id"]).group(1))
    previous_ids: set[int] = set()
    all_ids: set[int] = set()
    late_new_ids = 0
    reappearances = 0
    absent_ids: set[int] = set()
    for frame in trace:
        ids = frame["trackIds"]
        raw, usable = frame["rawPoseCount"], frame["usablePoseCount"]
        if (not isinstance(ids, list) or len(ids) != len(set(ids)) or
            not all(isinstance(item, int) and item > 0 for item in ids) or
            not isinstance(raw, int) or not isinstance(usable, int) or
            not 0 <= usable <= raw <= 4 or
            not isinstance(frame["primaryPosePresent"], bool)):
            raise ValueError(f"Invalid frame observation: {case['id']}")
        now = set(ids)
        if frame["seconds"] > 1:
            late_new_ids += len(now - all_ids)
        reappearances += len(now & absent_ids)
        absent_ids |= previous_ids - now
        absent_ids -= now
        all_ids |= now
        previous_ids = now
    if len(all_ids) != row["trackIdsSeen"] or max(len(frame["trackIds"]) for frame in trace) != row["maxVisiblePeople"]:
        raise ValueError(f"Trace and result disagree: {case['id']}")
    frames = len(trace)
    return {
        "id": case["id"],
        "category": case["category"],
        "nominalPeople": nominal,
        "nominalFallers": case["fallingPeopleCount"],
        "frames": frames,
        "framesWithAnyRawPose": sum(frame["rawPoseCount"] > 0 for frame in trace),
        "framesWithNominalRawPoses": sum(frame["rawPoseCount"] >= nominal for frame in trace),
        "framesWithNominalUsablePoses": sum(frame["usablePoseCount"] >= nominal for frame in trace),
        "framesWithNominalTracks": sum(len(frame["trackIds"]) >= nominal for frame in trace),
        "framesWithPrimaryPose": sum(frame["primaryPosePresent"] for frame in trace),
        "framesWithUnassignedUsablePose": sum(frame["usablePoseCount"] > len(frame["trackIds"]) for frame in trace),
        "uniqueTrackIds": len(all_ids),
        "lateNewTrackIds": late_new_ids,
        "trackReappearances": reappearances,
        "alerted": bool(row["detectedAtSeconds"]),
    }


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in manifest["cases"]}
    rows = {row["id"]: row for row in report["results"]}
    provenance = report["provenance"]
    if (manifest["datasetId"] != "mpfdd-github-available-v1" or
        len(cases) != 28 or len(rows) != 28 or set(cases) != set(rows) or
        report["schemaVersion"] != 4 or report["status"] != "complete" or
        report["sampleIntervalSeconds"] != 0.1 or
        report["dataset"]["sourceRevision"] != manifest["sourceRevision"] or
        provenance["detector"]["rule"] != "FusedMultiPersonFallRule/fall-v1" or
        provenance["localGitDirty"] or
        provenance["localSourceHashes"]["apps/web/public/vision/mpfdd/manifest.json"] != sha256(MANIFEST)):
        raise ValueError("Expected a complete, clean, pinned 28-clip MPFDD multi-person replay")
    summaries = []
    for case in manifest["cases"]:
        row = rows[case["id"]]
        if (row.get("error") or row["videoSha256"] != case["videoSha256"] or
            row["category"] != case["category"] or
            row["fallingPeopleCount"] != case["fallingPeopleCount"]):
            raise ValueError(f"Changed media or result: {case['id']}")
        summaries.append(summarize_case(case, row))
    total_frames = sum(row["frames"] for row in summaries)
    output = {
        "schemaVersion": 1,
        "scope": "Development diagnostic on already-examined MPFDD clips; filename counts are not frame-level visible-person labels",
        "sourceRevision": manifest["sourceRevision"],
        "manifestSha256": sha256(MANIFEST),
        "browserReportSha256": sha256(REPORT),
        "codeRevision": provenance["localGitRevision"],
        "codeDirtyDuringReplay": provenance["localGitDirty"],
        "sourceHashes": provenance["localSourceHashes"],
        "summary": {
            "clips": len(summaries),
            "sampledFrames": total_frames,
            "framesWithNominalRawPoses": sum(row["framesWithNominalRawPoses"] for row in summaries),
            "framesWithNominalTracks": sum(row["framesWithNominalTracks"] for row in summaries),
            "clipsWithNoFrameAtNominalRawPoses": sum(row["framesWithNominalRawPoses"] == 0 for row in summaries),
            "clipsWithNoFrameAtNominalTracks": sum(row["framesWithNominalTracks"] == 0 for row in summaries),
            "lateNewTrackIds": sum(row["lateNewTrackIds"] for row in summaries),
            "trackReappearances": sum(row["trackReappearances"] for row in summaries),
            "fallClipsAlerted": sum(row["alerted"] for row in summaries if row["category"] == "fall"),
        },
        "results": summaries,
        "limitation": "Raw pose and session track counts cannot establish that every person or faller was detected. No person-level identity, visibility, or fall timing ground truth is available.",
    }
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], indent=2))


if __name__ == "__main__":
    main()
