"""Compare two browser replays on identical, hash-verified CAUCAFall clips."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "apps/web/public/vision/caucafall/manifest.json"


def matched(result: dict) -> bool:
    event = result["eventRanges"][0]
    return any(event["start"] <= timestamp <= min(result["durationSeconds"], event["end"] + 2)
               for timestamp in result["detectedAtSeconds"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in (args.baseline, args.candidate)]
    expected = {item["id"]: item for item in manifest["cases"]}
    if len(expected) != 100:
        raise ValueError("Expected the full 100-clip CAUCAFall manifest")
    by_report = []
    for report in reports:
        if report["status"] != "complete" or report["dataset"]["datasetId"] != manifest["datasetId"]:
            raise ValueError("Incomplete or incorrect dataset")
        results = {item["id"]: item for item in report["results"]}
        if len(results) != 100 or set(results) != set(expected):
            raise ValueError("Report cases differ from the manifest")
        for case_id, result in results.items():
            definition = expected[case_id]
            if (result["videoSha256"] != definition["videoSha256"] or
                result["eventRanges"] != definition["eventRanges"] or
                result["framesAnalyzed"] < 1):
                raise ValueError(f"Unmatched case provenance: {case_id}")
        by_report.append(results)
    baseline, candidate = by_report
    gains = [case_id for case_id, result in baseline.items() if result["category"] == "fall"
             and not matched(result) and matched(candidate[case_id])]
    losses = [case_id for case_id, result in baseline.items() if result["category"] == "fall"
              and matched(result) and not matched(candidate[case_id])]
    false_alerts = [case_id for case_id, result in candidate.items()
                    if result["category"] == "daily_activity" and result["detectedAtSeconds"]]
    negative_hours = sum(result["durationSeconds"] for result in candidate.values()
                         if result["category"] == "daily_activity") / 3600
    output = {
        "baselineModel": reports[0]["provenance"]["detector"]["model"],
        "candidateModel": reports[1]["provenance"]["detector"]["model"],
        "baselineMatchedFalls": sum(matched(result) for result in baseline.values() if result["category"] == "fall"),
        "candidateMatchedFalls": sum(matched(result) for result in candidate.values() if result["category"] == "fall"),
        "gainedFallIds": gains,
        "lostFallIds": losses,
        "candidateDailyActivityClipsAlerted": false_alerts,
        "candidateDailyActivityAlertsPerAnalyzedHour": round(sum(
            len(result["detectedAtSeconds"]) for result in candidate.values()
            if result["category"] == "daily_activity") / negative_hours, 2),
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
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
