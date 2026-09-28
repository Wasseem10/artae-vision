"""Exploratory slice audit of the already examined GMDCSA-24 subjects 3-4.

Requires the ignored local evaluation report and author CSV files prepared by
prepare-gmdcsa24-benchmark.py, plus numpy. This is development analysis now:
subjects 3-4 cannot validate a new detector or threshold again.
"""

from __future__ import annotations

import csv
import json
import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/gmdcsa24/evaluation.json"
MEDIA = ROOT / "apps/web/public/vision/gmdcsa24"
MODEL = ROOT / "apps/web/src/lib/fall-window-model.json"
predict_clip = runpy.run_path(str(ROOT / "scripts/train-pose-window-fall.py"))["predict_clip"]


def description(result: dict) -> str:
    subject = result["subjectId"].split("-")[-1]
    csv_path = MEDIA / f"Subject {subject}" / "Fall.csv"
    filename = result["name"].split()[-1]
    with csv_path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if row["File Name"].strip() == filename:
                return row["Description"].strip()
    raise ValueError(f"No author description for {result['id']}")


def count(results: list[dict], key: str) -> int:
    return sum(bool(result[key]) for result in results)


def percent_pose(results: list[dict]) -> float:
    return round(sum(result["framesWithPose"] / result["framesAnalyzed"] for result in results) / len(results) * 100, 1)


def main() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    if report["status"] != "complete" or len(report["results"]) != 80:
        raise ValueError("Expected the complete, previously examined subject-3/4 report")
    falls = [result for result in report["results"] if result["category"] == "fall"]
    activities = [result for result in report["results"] if result["category"] != "fall"]
    bed = [result for result in falls if "bed" in description(result).lower()]
    other = [result for result in falls if result not in bed]
    misses = [result for result in falls if not result["windowModelDetectedAtSeconds"]]
    replay_mismatches = [
        result["id"] for result in report["results"]
        if bool(predict_clip(result, model, model["threshold"])) !=
        bool(result["windowModelDetectedAtSeconds"])
    ]
    output = {
        "note": "Exploratory audit of an examined holdout; cannot be reused for independent validation.",
        "traceReplayNote": "The exported pose trace rounds each feature to four decimals. Browser detections in the original report are authoritative; threshold sweeps over rounded traces are approximate.",
        "frozenThresholdReplayMismatches": replay_mismatches,
        "slices": {
            name: {
                "clips": len(group),
                "liveRuleDetected": count(group, "detectedAtSeconds"),
                "windowCandidateDetected": count(group, "windowModelDetectedAtSeconds"),
                "meanPoseCoveragePercent": percent_pose(group),
            }
            for name, group in [("allFalls", falls), ("bedMentioned", bed), ("otherFalls", other)]
        },
        "missedBedClips": [result["id"] for result in misses if result in bed],
        "missesWithAtLeast70PercentPoseCoverage": sum(
            result["framesWithPose"] / result["framesAnalyzed"] >= 0.7 for result in misses
        ),
        "thresholdExploration": [],
    }
    for threshold in [0.7, 0.85, 0.9, 0.94, 0.96, 0.98]:
        output["thresholdExploration"].append({
            "threshold": threshold,
            "bedFallsDetected": sum(bool(predict_clip(result, model, threshold)) for result in bed),
            "otherFallsDetected": sum(bool(predict_clip(result, model, threshold)) for result in other),
            "activitiesAlerted": sum(bool(predict_clip(result, model, threshold)) for result in activities),
        })
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
