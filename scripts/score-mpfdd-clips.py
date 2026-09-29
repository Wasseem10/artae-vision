"""Score the frozen MPFDD browser replays at clip level only.

The accessible source filenames label how many people fall, but do not provide
fall times or which visible person fell. Track-level recall cannot be scored.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "apps/web/public/vision/mpfdd/manifest.json"
LEGACY = ROOT / "artifacts/mpfdd/evaluation.json"
MULTI = ROOT / "artifacts/mpfdd/evaluation-multiperson.json"
OUTPUT = ROOT / "docs/benchmarks/mpfdd-first-look-v1.json"
DATASET_ID = "mpfdd-github-available-v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_report(path: Path, manifest: dict, schema: int, rule: str) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in manifest["cases"]}
    results = report["results"]
    provenance = report["provenance"]
    if (report["status"] != "complete" or report["schemaVersion"] != schema or
        report["sampleIntervalSeconds"] != 0.1 or
        report["dataset"]["datasetId"] != DATASET_ID or
        report["dataset"]["sourceRevision"] != manifest["sourceRevision"] or
        provenance["detector"]["rule"] != rule or
        provenance["localGitDirty"] or len(results) != 28 or
        len(cases) != 28 or set(cases) != {row["id"] for row in results} or
        provenance["localSourceHashes"]["apps/web/public/vision/mpfdd/manifest.json"] != digest(MANIFEST)):
        raise ValueError(f"Incomplete or mismatched replay: {path}")
    for row in results:
        case = cases[row["id"]]
        if (row["videoSha256"] != case["videoSha256"] or
            row["sourceGitBlobSha1"] != case["sourceGitBlobSha1"] or
            row["fallingPeopleCount"] != case["fallingPeopleCount"] or
            row["category"] != case["category"] or row.get("error") or
            row["framesAnalyzed"] <= 0):
            raise ValueError(f"Changed media, label, or failed case: {row['id']}")
        if schema == 4 and [event["atSeconds"] for event in row["multiPersonEvents"]] != row["detectedAtSeconds"]:
            raise ValueError(f"Inconsistent track alerts: {row['id']}")
    return report


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
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest["datasetId"] != DATASET_ID or len(manifest["cases"]) != 28:
        raise ValueError("Expected pinned, 28-case MPFDD manifest")
    legacy = load_report(LEGACY, manifest, 3, "BrowserPoseRule/fall-v2")
    multi = load_report(MULTI, manifest, 4, "FusedMultiPersonFallRule/fall-v1")
    if legacy["provenance"]["localGitRevision"] != multi["provenance"]["localGitRevision"]:
        raise ValueError("Runs must use the same frozen revision")
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
        "schemaVersion": 1,
        "scope": "First-look clip-level regression on 28 publicly accessible multi-person MPFDD videos; no person-level or timed fall labels",
        "sourceRevision": manifest["sourceRevision"],
        "manifestSha256": digest(MANIFEST),
        "legacyBrowserReportSha256": digest(LEGACY),
        "multiPersonBrowserReportSha256": digest(MULTI),
        "codeRevision": multi["provenance"]["localGitRevision"],
        "codeDirtyDuringReplay": False,
        "sourceHashes": multi["provenance"]["localSourceHashes"],
        "legacy": summary(legacy["results"]),
        "multiPerson": summary(multi["results"]),
        "results": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"legacy": report["legacy"], "multiPerson": report["multiPerson"]}, indent=2))


if __name__ == "__main__":
    main()
