"""Score the frozen MPFDD browser replays at clip level only.

The accessible source filenames label how many people fall, but do not provide
fall times or which visible person fell. Track-level recall cannot be scored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "apps/web/public/vision/mpfdd/manifest.json"
LEGACY = ROOT / "artifacts/mpfdd/evaluation.json"
MULTI = ROOT / "artifacts/mpfdd/evaluation-multiperson.json"
OUTPUT = ROOT / "docs/benchmarks/mpfdd-first-look-v1.json"
DATASET_ID = "mpfdd-github-available-v1"
PRESENTED_PROTOCOL = {
    "method": "presented-frame-v1",
    "seekOffsetSeconds": 0.001,
    "maxFrameLagSeconds": 0.05,
    "maxFrameLeadSeconds": 0.002,
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def validate_sampling(row: dict, schema: int) -> None:
    """Reject partial replays before counting a clip's duration as exposure."""
    if schema in (3, 4) and row.get("presentedFrameTrace") is not None:
        raise ValueError("Presented trace mislabeled as a seek-only schema")
    case_id = row["id"]
    duration = row.get("durationSeconds")
    if not finite_number(duration) or duration <= 0.001:
        raise ValueError(f"Invalid duration: {case_id}")
    # Match runCase's inclusive 0.1-second loop, including its end clamp.
    expected_frames = max(1, math.floor(duration / 0.1)) + 1
    frames = row.get("framesAnalyzed")
    coverage = row.get("framesWithPose")
    trace = row.get("poseTrace")
    if (type(frames) is not int or frames != expected_frames or
        type(coverage) is not int or not 0 <= coverage <= frames or
        not isinstance(trace, list) or len(trace) != frames):
        raise ValueError(f"Incomplete sampling or invalid coverage: {case_id}")
    for index, frame in enumerate(trace):
        seconds = frame.get("seconds") if isinstance(frame, dict) else None
        expected = min(duration - 0.001, index * 0.1)
        if not finite_number(seconds) or abs(seconds - expected) > 0.00051:
            raise ValueError(f"Missing, reordered, or changed sample: {case_id}")
    alerts = row.get("detectedAtSeconds")
    if (not isinstance(alerts, list) or
        any(not finite_number(time) or not 0 <= time < duration for time in alerts) or
        alerts != sorted(alerts)):
        raise ValueError(f"Invalid alert timeline: {case_id}")
    sample_times = {frame["seconds"] for frame in trace}
    if any(time not in sample_times for time in alerts):
        raise ValueError(f"Alert outside sampled timeline: {case_id}")
    for metric in ("meanInferenceMs", "p95InferenceMs"):
        if not finite_number(row.get(metric)) or row[metric] < 0:
            raise ValueError(f"Invalid inference timing: {case_id}")
    if schema in (5, 6):
        validate_presented_sampling(row)
    if schema in (4, 6):
        events = row.get("multiPersonEvents")
        track_count = row.get("trackIdsSeen")
        visible = row.get("maxVisiblePeople")
        if (type(track_count) is not int or track_count < 0 or
            type(visible) is not int or not 0 <= visible <= track_count or
            not isinstance(events, list) or
            any(not isinstance(event, dict) or type(event.get("trackId")) is not int or
                event["trackId"] <= 0 or
                not finite_number(event.get("atSeconds")) for event in events) or
            [event.get("atSeconds") for event in events] != alerts or
            len({event["trackId"] for event in events}) > track_count or
            len({(event["atSeconds"], event["trackId"]) for event in events}) != len(events)):
            raise ValueError(f"Inconsistent track alerts: {case_id}")


def validate_presented_sampling(row: dict) -> None:
    """Mirror presented-frame-v1's explicit contract, not exact frame identity."""
    trace = row.get("presentedFrameTrace")
    if not isinstance(trace, list) or len(trace) != row["framesAnalyzed"]:
        raise ValueError(f"Missing or truncated presented trace: {row['id']}")
    previous_counter, previous_time = 0, -1.0
    for index, sample in enumerate(trace):
        if not isinstance(sample, dict):
            raise ValueError("Invalid presented frame")
        requested, decoded, counter = (sample.get(key) for key in
                                       ("requestedSeconds", "decodedSeconds", "presentedFrames"))
        expected = min(row["durationSeconds"] - 0.001, index * 0.1)
        if (not finite_number(requested) or abs(requested - expected) > 1e-6 or
            not finite_number(decoded) or decoded < 0 or
            requested - decoded > PRESENTED_PROTOCOL["maxFrameLagSeconds"] + 1e-6 or
            decoded - requested > PRESENTED_PROTOCOL["maxFrameLeadSeconds"] + 1e-6 or
            type(counter) is not int or counter <= previous_counter or
            decoded < previous_time):
            raise ValueError(f"Invalid presented timeline: {row['id']}")
        previous_counter, previous_time = counter, decoded


def validate_protocol(provenance: dict, schema: int) -> None:
    if schema not in (3, 4, 5, 6):
        raise ValueError("Unsupported replay schema")
    protocol = provenance.get("frameSampling")
    if schema in (5, 6):
        if not isinstance(protocol, dict) or set(protocol) != set(PRESENTED_PROTOCOL):
            raise ValueError("Missing presented-frame-v1 protocol")
        if (protocol["method"] != PRESENTED_PROTOCOL["method"] or
            any(not finite_number(protocol[key]) or protocol[key] != expected
                for key, expected in PRESENTED_PROTOCOL.items() if key != "method")):
            raise ValueError("Changed presented-frame-v1 protocol")
    elif protocol is not None:
        raise ValueError("Presented provenance mislabeled as a seek-only schema")


def load_report(path: Path, manifest: dict, schema: int, rule: str,
                manifest_path: Path | None = None) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in manifest["cases"]}
    results = report["results"]
    provenance = report["provenance"]
    validate_protocol(provenance, schema)
    if (report["status"] != "complete" or report["scoringUnit"] != "clip" or report["schemaVersion"] != schema or
        report["sampleIntervalSeconds"] != 0.1 or
        report["dataset"]["datasetId"] != DATASET_ID or
        report["dataset"]["sourceRevision"] != manifest["sourceRevision"] or
        provenance["detector"]["rule"] != rule or
        provenance["localGitDirty"] is not False or len(results) != 28 or
        len(cases) != 28 or set(cases) != {row["id"] for row in results} or
        provenance["localSourceHashes"]["apps/web/public/vision/mpfdd/manifest.json"] != digest(manifest_path or MANIFEST)):
        raise ValueError(f"Incomplete or mismatched replay: {path}")
    for row in results:
        case = cases[row["id"]]
        if (row["videoSha256"] != case["videoSha256"] or
            row["sourceGitBlobSha1"] != case["sourceGitBlobSha1"] or
            row["fallingPeopleCount"] != case["fallingPeopleCount"] or
            row["category"] != case["category"] or row.get("error") or
            row["framesAnalyzed"] <= 0):
            raise ValueError(f"Changed media, label, or failed case: {row['id']}")
        validate_sampling(row, schema)
    return report


def validate_pair(legacy: dict, multi: dict) -> None:
    if (legacy["schemaVersion"], multi["schemaVersion"]) not in ((3, 4), (5, 6)):
        raise ValueError("Cannot mix seek-only and presented-frame replays")
    if legacy["provenance"]["localGitRevision"] != multi["provenance"]["localGitRevision"]:
        raise ValueError("Runs must use the same frozen revision")
    if legacy["provenance"]["localSourceHashes"] != multi["provenance"]["localSourceHashes"]:
        raise ValueError("Runs must use identical frozen source hashes")
    for key in ("runtime", "model", "modelSha256", "worker"):
        before, after = (report["provenance"]["detector"].get(key) for report in (legacy, multi))
        if not isinstance(before, str) or not before or before != after:
            raise ValueError(f"Mismatched detector provenance: {key}")


def summary(results: list[dict]) -> dict:
    falls = [row for row in results if row["category"] == "fall"]
    negatives = [row for row in results if row["category"] == "daily_activity"]
    assert len(falls) == 22 and len(negatives) == 6
    negative_hours = sum(row["durationSeconds"] for row in negatives) / 3600
    groups: dict[int, list[dict]] = defaultdict(list)
    for row in falls:
        groups[row["fallingPeopleCount"]].append(row)
    return {
        "fallClipsAlerted": sum(bool(row["detectedAtSeconds"]) for row in falls),
        "fallClipsTotal": len(falls),
        "dailyActivityClipsAlerted": sum(bool(row["detectedAtSeconds"]) for row in negatives),
        "dailyActivityClipsTotal": len(negatives),
        "dailyActivityAlerts": sum(len(row["detectedAtSeconds"]) for row in negatives),
        "analyzedDailyActivityHours": round(negative_hours, 4),
        "fallClipsByNominalFallerCount": {
            str(count): {
                "alerted": sum(bool(row["detectedAtSeconds"]) for row in group),
                "total": len(group),
            } for count, group in sorted(groups.items())
        },
        "medianClipInferenceMs": round(statistics.median(row["meanInferenceMs"] for row in results), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sampling", choices=("seeked", "presented"), default="seeked")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--legacy-report", type=Path)
    parser.add_argument("--multi-report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    presented = args.sampling == "presented"
    suffix = "-presented-v1" if presented else ""
    legacy_path = args.legacy_report or LEGACY.with_name(f"evaluation{suffix}.json")
    multi_path = args.multi_report or MULTI.with_name(f"evaluation-multiperson{suffix}.json")
    output_path = args.output or (ROOT / "artifacts/mpfdd/presented-comparison.json" if presented else OUTPUT)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest["datasetId"] != DATASET_ID or len(manifest["cases"]) != 28:
        raise ValueError("Expected pinned, 28-case MPFDD manifest")
    legacy = load_report(legacy_path, manifest, 5 if presented else 3,
                         "BrowserPoseRule/fall-v2", args.manifest)
    multi = load_report(multi_path, manifest, 6 if presented else 4,
                        "FusedMultiPersonFallRule/fall-v1", args.manifest)
    validate_pair(legacy, multi)
    legacy_rows = {row["id"]: row for row in legacy["results"]}
    multi_rows = {row["id"]: row for row in multi["results"]}
    rows = []
    for case in manifest["cases"]:
        before = legacy_rows[case["id"]]
        after = multi_rows[case["id"]]
        if abs(before["durationSeconds"] - after["durationSeconds"]) > 0.01:
            raise ValueError(f"Different clip duration: {case['id']}")
        rows.append({
            "id": case["id"], "sourcePath": case["sourcePath"],
            "scene": int(case["id"].split("-")[1][1:]),
            "peopleCount": int(case["id"].split("-")[2][1:]),
            "nominalFallerCount": case["fallingPeopleCount"],
            "category": case["category"],
            "durationSeconds": round(after["durationSeconds"], 3),
            "legacyAlertTimes": before["detectedAtSeconds"],
            "multiPersonAlerts": after["multiPersonEvents"],
            "maxTrackedPeople": after["maxVisiblePeople"],
            "trackIdsSeen": after["trackIdsSeen"],
            "poseCoverage": round(after["framesWithPose"] / after["framesAnalyzed"], 4),
            "meanInferenceMs": round(after["meanInferenceMs"], 2),
        })
    report = {
        "schemaVersion": 2 if presented else 1,
        "scope": ("Development clip-level regression on examined MPFDD footage with presented-frame-v1; no person-level or timed fall labels"
                  if presented else "First-look clip-level regression on 28 publicly accessible multi-person MPFDD videos; no person-level or timed fall labels"),
        "sourceRevision": manifest["sourceRevision"],
        "manifestSha256": digest(args.manifest),
        "legacyBrowserReportSha256": digest(legacy_path),
        "multiPersonBrowserReportSha256": digest(multi_path),
        "codeRevision": multi["provenance"]["localGitRevision"],
        "codeDirtyDuringReplay": False,
        "sourceHashes": multi["provenance"]["localSourceHashes"],
        "legacy": summary(legacy["results"]),
        "multiPerson": summary(multi["results"]),
        "results": rows,
    }
    if presented:
        report["frameSampling"] = PRESENTED_PROTOCOL
        report["inputReportSchemas"] = [5, 6]
        report["verifiedPresentationSamples"] = {
            "legacy": sum(row["framesAnalyzed"] for row in legacy["results"]),
            "multiPerson": sum(row["framesAnalyzed"] for row in multi["results"]),
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"legacy": report["legacy"], "multiPerson": report["multiPerson"]}, indent=2))


if __name__ == "__main__":
    main()
