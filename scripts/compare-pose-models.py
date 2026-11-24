"""Compare browser reports against a CAUCAFall manifest, with explicit exposure."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "apps/web/public/vision/caucafall/manifest.json"


def matched(result: dict) -> bool:
    event = result["eventRanges"][0]
    return any(event["start"] <= timestamp <= min(result["durationSeconds"], event["end"] + 2)
               for timestamp in result["detectedAtSeconds"])


def unique_cases(rows: list[dict], source: str) -> dict[str, dict]:
    if not isinstance(rows, list) or len(rows) != 100:
        raise ValueError(f"Expected exactly 100 {source} cases")
    ids = [row["id"] for row in rows]
    if any(not isinstance(case_id, str) or not case_id for case_id in ids) or len(set(ids)) != len(ids):
        raise ValueError(f"Invalid or duplicate {source} case IDs")
    return dict(zip(ids, rows))


def finite_number(value: object, minimum: float = 0) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= minimum


def activity_exposure(results: dict[str, dict]) -> dict:
    activities = [row for row in results.values() if row["category"] == "daily_activity"]
    seconds = sum(row["durationSeconds"] for row in activities)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Invalid total activity video duration")
    alerts = sum(len(row["detectedAtSeconds"]) for row in activities)
    return {
        "clips": len(activities),
        "clipsAlerted": sum(bool(row["detectedAtSeconds"]) for row in activities),
        "alertCount": alerts,
        "reportedVideoSeconds": seconds,
        "alertsPerReportedVideoHour": round(alerts / seconds * 3600, 2),
        "analyzedExposureVerified": False,
    }


def clip_outcome(result: dict) -> dict:
    return {
        "reportedVideoSeconds": result["durationSeconds"],
        "alertTimestampsSeconds": list(result["detectedAtSeconds"]),
        # An activity clip has no annotated fall to match; null is not a miss.
        "matchedFall": matched(result) if result["category"] == "fall" else None,
    }


def compare_reports(manifest: dict, reports: list[dict]) -> dict:
    if len(reports) != 2:
        raise ValueError("Expected baseline and candidate reports")
    expected = unique_cases(manifest["cases"], "manifest")
    for case_id, definition in expected.items():
        category, ranges = definition["category"], definition["eventRanges"]
        if category not in ("fall", "daily_activity") or not isinstance(ranges, list) or len(ranges) != int(category == "fall"):
            raise ValueError(f"Invalid manifest label: {case_id}")
        for event in ranges:
            if not finite_number(event["start"]) or not finite_number(event["end"]) or event["start"] > event["end"]:
                raise ValueError(f"Invalid manifest event interval: {case_id}")
    if not any(item["category"] == "daily_activity" for item in expected.values()):
        raise ValueError("Activity footage is required for negative exposure")
    by_report = []
    for report in reports:
        if report["status"] != "complete" or report["dataset"]["datasetId"] != manifest["datasetId"]:
            raise ValueError("Incomplete or incorrect dataset")
        results = unique_cases(report["results"], "report")
        if set(results) != set(expected):
            raise ValueError("Report cases differ from the manifest")
        for case_id, result in results.items():
            definition = expected[case_id]
            if (result["videoSha256"] != definition["videoSha256"] or
                result["category"] != definition["category"] or
                result["eventRanges"] != definition["eventRanges"]):
                raise ValueError(f"Unmatched case provenance: {case_id}")
            frames, poses = result["framesAnalyzed"], result["framesWithPose"]
            duration, alerts = result["durationSeconds"], result["detectedAtSeconds"]
            if (type(frames) is not int or frames < 1 or type(poses) is not int or not 0 <= poses <= frames or
                not finite_number(duration) or duration == 0 or not finite_number(result["meanInferenceMs"])):
                raise ValueError(f"Invalid observation metrics: {case_id}")
            if (not isinstance(alerts, list) or
                any(not finite_number(t) or t > duration for t in alerts)):
                raise ValueError(f"Invalid alert timestamp: {case_id}")
        by_report.append(results)
    baseline, candidate = by_report
    gains = [case_id for case_id, result in baseline.items() if result["category"] == "fall"
             and not matched(result) and matched(candidate[case_id])]
    losses = [case_id for case_id, result in baseline.items() if result["category"] == "fall"
              and matched(result) and not matched(candidate[case_id])]
    false_alerts = [case_id for case_id, result in candidate.items()
                    if result["category"] == "daily_activity" and result["detectedAtSeconds"]]
    output = {
        "schemaVersion": 2,
        "limitations": [
            "Activity rates use reported video duration, not verified analyzed exposure or field monitoring hours.",
            "Manifest consistency does not establish annotation correctness, complete inference replay or independent validation.",
            "A matched fall has an alert within the annotated interval plus the existing two-second allowance; it does not prove person identity.",
        ],
        "baselineModel": reports[0]["provenance"]["detector"]["model"],
        "candidateModel": reports[1]["provenance"]["detector"]["model"],
        "baselineMatchedFalls": sum(matched(result) for result in baseline.values() if result["category"] == "fall"),
        "candidateMatchedFalls": sum(matched(result) for result in candidate.values() if result["category"] == "fall"),
        "gainedFallIds": gains,
        "lostFallIds": losses,
        "candidateDailyActivityClipsAlerted": false_alerts,
        "dailyActivityExposure": {
            "baseline": activity_exposure(baseline),
            "candidate": activity_exposure(candidate),
        },
        "perClip": [{
            "id": case_id, "category": definition["category"],
            "eventRanges": [dict(event) for event in definition["eventRanges"]],
            "baseline": clip_outcome(baseline[case_id]),
            "candidate": clip_outcome(candidate[case_id]),
        } for case_id, definition in expected.items()],
        "meanPoseCoverage": {
            "baseline": round(statistics.mean(result["framesWithPose"] / result["framesAnalyzed"]
                                              for result in baseline.values()), 4),
            "candidate": round(statistics.mean(result["framesWithPose"] / result["framesAnalyzed"]
                                               for result in candidate.values()), 4),
        },
        "meanInferenceMs": {
            "baseline": round(statistics.mean(result["meanInferenceMs"] for result in baseline.values()), 2),
            "candidate": round(statistics.mean(result["meanInferenceMs"] for result in candidate.values()), 2),
        },
    }
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--manifest", type=Path, default=MANIFEST,
                        help="Local CAUCAFall manifest (defaults to the prepared browser dataset)")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in (args.baseline, args.candidate)]
    output = compare_reports(manifest, reports)
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
