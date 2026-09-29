"""Score the deployed four-pose fall path on the previously examined CAUCAFall set.

This is a regression check, not a new independent holdout or a multi-person
identity benchmark: each source clip shows one staged participant.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/caucafall/evaluation-multiperson.json"
MANIFEST = ROOT / "apps/web/public/vision/caucafall/manifest.json"
BASELINE = ROOT / "docs/benchmarks/caucafall-independent-v1.json"
OUTPUT = ROOT / "docs/benchmarks/caucafall-multiperson-regression-v1.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))], 3)


def main() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    results = report["results"]
    cases = {case["id"]: case for case in manifest["cases"]}
    provenance = report["provenance"]
    if (report["status"] != "complete" or report["schemaVersion"] != 4 or
        report["dataset"]["datasetId"] != manifest["datasetId"] or
        provenance["detector"]["rule"] != "FusedMultiPersonFallRule/fall-v1" or
        provenance["detector"]["maxPoses"] != 4 or
        provenance["localSourceHashes"]["apps/web/public/vision/caucafall/manifest.json"] != digest(MANIFEST) or
        provenance["localSourceHashes"]["apps/web/src/lib/multi-person-fall.ts"] !=
            digest(ROOT / "apps/web/src/lib/multi-person-fall.ts") or
        len(results) != 100 or set(cases) != {row["id"] for row in results}):
        raise ValueError("Expected complete, hash-matched four-pose CAUCAFall replay")

    found = 0
    unmatched = 0
    negative_alerts = 0
    negative_clips_alerted = 0
    negative_seconds = 0.0
    delays: list[float] = []
    rows = []
    for row in results:
        case = cases[row["id"]]
        if row["videoSha256"] != case["videoSha256"] or row["eventRanges"] != case["eventRanges"]:
            raise ValueError(f"Media or labels changed: {row['id']}")
        events = row["multiPersonEvents"]
        times = row["detectedAtSeconds"]
        if [event["atSeconds"] for event in events] != times or any(
            not isinstance(event["trackId"], int) or event["trackId"] < 1 for event in events
        ):
            raise ValueError(f"Invalid track event record: {row['id']}")
        matched = False
        if row["category"] == "fall":
            interval = case["eventRanges"][0]
            in_window = [time for time in times if interval["start"] <= time <=
                         min(row["durationSeconds"], interval["end"] + 2)]
            if in_window:
                found += 1
                matched = True
                delays.append(in_window[0] - interval["start"])
            unmatched += len(times) - int(matched)
        else:
            negative_seconds += row["durationSeconds"]
            negative_alerts += len(times)
            negative_clips_alerted += bool(times)
            unmatched += len(times)
        rows.append({
            "id": row["id"], "subjectId": row["subjectId"],
            "category": row["category"], "eventRanges": row["eventRanges"],
            "durationSeconds": round(row["durationSeconds"], 3),
            "poseCoverage": round(row["framesWithPose"] / row["framesAnalyzed"], 4),
            "maxVisiblePeople": row["maxVisiblePeople"],
            "trackIdsSeen": row["trackIdsSeen"],
            "events": events, "matchedFall": matched,
            "meanInferenceMs": round(row["meanInferenceMs"], 2),
            "p95InferenceMs": round(row["p95InferenceMs"], 2),
        })

    negative_hours = negative_seconds / 3600
    metrics = {
        "fallEventsDetected": found,
        "fallEventsTotal": 50,
        "eventRecall": round(found / 50, 4),
        "unmatchedAlerts": unmatched,
        "eventPrecision": round(found / (found + unmatched), 4) if found + unmatched else None,
        "dailyActivityClipsAlerted": negative_clips_alerted,
        "dailyActivityClipsTotal": 50,
        "dailyActivityAlerts": negative_alerts,
        "analyzedDailyActivityHours": round(negative_hours, 4),
        "dailyActivityAlertsPerAnalyzedHour": round(negative_alerts / negative_hours, 2),
        "medianMatchedLatencySeconds": round(statistics.median(delays), 3) if delays else None,
        "p95MatchedLatencySeconds": percentile(delays, .95),
        "clipsWithMoreThanOnePose": sum(row["maxVisiblePeople"] > 1 for row in rows),
        "clipsWithMoreThanOneTrackId": sum(row["trackIdsSeen"] > 1 for row in rows),
        "meanClipPoseCoverage": round(statistics.mean(row["poseCoverage"] for row in rows), 4),
        "medianClipInferenceMs": round(statistics.median(row["meanInferenceMs"] for row in rows), 2),
    }
    output = {
        "schemaVersion": 1,
        "scope": "Regression on 100 previously examined, single-person CAUCAFall staged clips",
        "manifestSha256": digest(MANIFEST),
        "browserReportSha256": digest(REPORT),
        "baselineReportSha256": digest(BASELINE),
        "sourceHashes": provenance["localSourceHashes"],
        "detectorRule": provenance["detector"]["rule"],
        "codeRevision": provenance["localGitRevision"],
        "codeDirtyDuringReplay": provenance["localGitDirty"],
        "baseline": baseline["metrics"]["liveTemporal"],
        "multiPerson": metrics,
        "results": rows,
        "limitations": "This source was examined before the four-pose change and has one participant per clip. It cannot measure multi-person association, field recall, or an operational false-alert rate.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"baseline": output["baseline"], "multiPerson": metrics}, indent=2))


if __name__ == "__main__":
    main()
