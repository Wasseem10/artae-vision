"""Score the frozen browser replay against CAUCAFall's annotated fall intervals.

One detection may match one fall interval when it arrives between annotation
start and two seconds after annotation end. All other detections are unmatched.
The fixed grace period allows post-fall confirmation and is declared before
the holdout is run. The output contains no research video or pose trace.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/caucafall/evaluation.json"
MANIFEST = ROOT / "apps/web/public/vision/caucafall/manifest.json"
OUTPUT = ROOT / "docs/benchmarks/caucafall-independent-v1.json"
DETECTORS = {
    "liveTemporal": "detectedAtSeconds",
    "staticPosture": "postureBaselineDetectedAtSeconds",
    "poseWindowV1": "windowModelDetectedAtSeconds",
    "poseWindowV2": "windowModelV2DetectedAtSeconds",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, max(0, int(len(values) * fraction + 0.999999) - 1))], 3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report_path = args.report.resolve()
    output_path = args.output.resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (report["status"] != "complete" or
        report["dataset"]["datasetId"] != "caucafall-v4-omnifall-labels-v3" or
        len(report["results"]) != 100 or len(manifest["cases"]) != 100 or
        report["provenance"]["localSourceHashes"]["apps/web/public/vision/caucafall/manifest.json"] != sha256(MANIFEST)):
        raise ValueError("Expected complete, hash-matched CAUCAFall browser report")
    expected = {case["id"]: case for case in manifest["cases"]}
    if set(expected) != {case["id"] for case in report["results"]}:
        raise ValueError("Report cases differ from the frozen manifest")
    for filename in ["apps/web/src/lib/fall-window-model.json", "apps/web/src/lib/fall-window-model-v2.json"]:
        if report["provenance"]["localSourceHashes"][filename] != sha256(ROOT / filename):
            raise ValueError(f"Model changed since browser replay: {filename}")
    negative_hours = sum(
        result["durationSeconds"] for result in report["results"]
        if result["category"] == "daily_activity"
    ) / 3600
    if negative_hours <= 0:
        raise ValueError("No measured daily-activity exposure")

    metrics = {}
    per_clip = []
    for result in report["results"]:
        case = expected[result["id"]]
        if (result["videoSha256"] != case["videoSha256"] or
            result["eventRanges"] != case["eventRanges"]):
            raise ValueError(f"Case provenance changed: {result['id']}")
        per_clip.append({
            "id": result["id"], "subjectId": result["subjectId"],
            "category": result["category"], "eventRanges": result["eventRanges"],
            "durationSeconds": round(result["durationSeconds"], 3),
            "poseCoverage": round(result["framesWithPose"] / result["framesAnalyzed"], 4),
            "detections": {name: result[key] for name, key in DETECTORS.items()},
        })
    for name, key in DETECTORS.items():
        found = 0
        unmatched = 0
        adl_alerts = 0
        adl_clips_alerted = 0
        latencies = []
        for result in report["results"]:
            detections = result[key]
            if result["category"] == "daily_activity":
                adl_alerts += len(detections)
                adl_clips_alerted += bool(detections)
                unmatched += len(detections)
                continue
            event = result["eventRanges"][0]
            in_window = [t for t in detections if event["start"] <= t <= min(
                result["durationSeconds"], event["end"] + 2)]
            if in_window:
                found += 1
                latencies.append(in_window[0] - event["start"])
            unmatched += len(detections) - int(bool(in_window))
        metrics[name] = {
            "fallEventsDetected": found,
            "fallEventsTotal": 50,
            "eventRecall": round(found / 50, 4),
            "unmatchedAlerts": unmatched,
            "eventPrecision": round(found / (found + unmatched), 4) if found + unmatched else None,
            "dailyActivityClipsAlerted": adl_clips_alerted,
            "dailyActivityClipsTotal": 50,
            "dailyActivityAlerts": adl_alerts,
            "analyzedDailyActivityHours": round(negative_hours, 4),
            "dailyActivityAlertsPerAnalyzedHour": round(adl_alerts / negative_hours, 2),
            "medianMatchedLatencySeconds": round(statistics.median(latencies), 3) if latencies else None,
            "p95MatchedLatencySeconds": percentile(latencies, 0.95),
        }
    output = {
        "schemaVersion": 1,
        "dataset": "CAUCAFall v4; OmniFall v3 event intervals",
        "source": "https://data.mendeley.com/datasets/7w7fccy7ky/4",
        "annotationSource": "https://huggingface.co/datasets/simplexsigil2/omnifall",
        "sourceAnnotationSha256": manifest["sourceAnnotationSha256"],
        "manifestSha256": sha256(MANIFEST),
        "browserReportSha256": sha256(report_path),
        "poseModel": report["provenance"]["detector"]["model"],
        "poseModelSha256": report["provenance"]["detector"]["modelSha256"],
        "codeRevision": report["provenance"]["localGitRevision"],
        "modelSha256": {name: sha256(ROOT / filename) for name, filename in {
            "poseWindowV1": "apps/web/src/lib/fall-window-model.json",
            "poseWindowV2": "apps/web/src/lib/fall-window-model-v2.json",
        }.items()},
        "scoring": "One-to-one event match from fall onset through two seconds after fall interval end. Other alerts unmatched. False-alert exposure uses all analyzed daily-activity clip seconds only.",
        "metrics": metrics,
        "results": per_clip,
        "limitations": "100 short staged clips and less than one hour of negative footage cannot establish field fall sensitivity or operational false-alert rate.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
