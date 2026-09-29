"""Audit the frozen browser fall rules across already-examined sources.

This is a development diagnostic, not an independent validation run. The input
reports contain locally held pose traces; stdout contains only aggregates and
case identifiers, with no video or landmark traces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "urfall": ["artifacts/urfall/evaluation.json"],
    "gmdcsa24": [
        "artifacts/gmdcsa24/development-subjects-1-2.json",
        "artifacts/gmdcsa24/evaluation.json",
    ],
    "caucafall": ["artifacts/caucafall/evaluation.json"],
    "imu_video": ["artifacts/imuadlfall/evaluation.json"],
    "realbiomfall": ["artifacts/realbiomfall/evaluation.json"],
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def event_interval(clip: dict) -> tuple[float, float]:
    """Use annotated onset when available; otherwise score at clip level."""
    duration = float(clip["durationSeconds"])
    ranges = clip.get("eventRanges") or []
    if ranges:
        return float(ranges[0]["start"]), min(duration, float(ranges[0]["end"]) + 2)
    onset = clip.get("eventStartSeconds")
    return (float(onset) if onset is not None else 0), duration


def hit(times: list[float], interval: tuple[float, float]) -> bool:
    return any(interval[0] <= t <= interval[1] for t in times)


def pose_signals(clip: dict) -> dict[str, bool | float]:
    trace = clip.get("poseTrace") or []
    valid = [f for f in trace if all(f.get(key) is not None for key in ("y", "verticality", "aspect"))]
    interval = event_interval(clip)
    relevant = [f for f in valid if interval[0] <= f["seconds"] <= interval[1]]
    # Descriptive signals only. They are not ground-truth movement labels.
    upright = any(f["verticality"] > .75 and f["aspect"] < 1.05 for f in valid)
    horizontal = any(f["verticality"] < .55 and f["aspect"] > .9 for f in relevant)
    descent = any(
        later["y"] - earlier["y"] > .15
        for i, later in enumerate(relevant)
        for earlier in relevant[:i]
        if 0 < later["seconds"] - earlier["seconds"] <= 1.5
    )
    return {
        "poseCoverage": len(valid) / len(trace) if trace else 0,
        "uprightObserved": upright,
        "horizontalObserved": horizontal,
        "descentObserved": descent,
    }


def audit(paths: list[Path]) -> dict:
    clips = []
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("status") != "complete":
            raise ValueError(f"Incomplete browser report: {path}")
        clips.extend(report["results"])
    ids = [clip["id"] for clip in clips]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case identifiers in one source")
    falls = [clip for clip in clips if clip["category"] == "fall"]
    activities = [clip for clip in clips if clip["category"] == "daily_activity"]
    if len(falls) + len(activities) != len(clips):
        raise ValueError("Unexpected case category")
    misses = []
    temporal_hits = window_hits = activity_temporal = activity_window = 0
    window_falls = window_activities = 0
    for clip in falls:
        interval = event_interval(clip)
        temporal = hit(clip["detectedAtSeconds"], interval)
        has_window_result = "windowModelDetectedAtSeconds" in clip
        window = hit(clip["windowModelDetectedAtSeconds"], interval) if has_window_result else None
        temporal_hits += temporal
        window_falls += has_window_result
        window_hits += bool(window)
        if not temporal:
            misses.append({"id": clip["id"], "windowHit": window, **pose_signals(clip)})
    for clip in activities:
        activity_temporal += bool(clip["detectedAtSeconds"])
        has_window_result = "windowModelDetectedAtSeconds" in clip
        window_activities += has_window_result
        activity_window += bool(clip["windowModelDetectedAtSeconds"]) if has_window_result else 0
    return {
        "clips": len(clips),
        "falls": len(falls),
        "activities": len(activities),
        "activityHours": round(sum(clip["durationSeconds"] for clip in activities) / 3600, 4),
        "temporalFallHits": temporal_hits,
        "poseWindowFallHits": window_hits if window_falls else None,
        "poseWindowFallClipsScored": window_falls,
        "temporalActivityClipsAlerted": activity_temporal,
        "poseWindowActivityClipsAlerted": activity_window if window_activities else None,
        "poseWindowActivityClipsScored": window_activities,
        "temporalMissesWithAtLeast70PercentPose": sum(item["poseCoverage"] >= .7 for item in misses),
        "temporalMissesWithAllThreePoseSignals": sum(
            item["uprightObserved"] and item["horizontalObserved"] and item["descentObserved"]
            for item in misses
        ),
        "misses": misses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write a JSON report instead of stdout")
    args = parser.parse_args()
    output = {"purpose": "already-examined-source development audit", "sources": {}}
    for name, relative_paths in SOURCES.items():
        paths = [ROOT / item for item in relative_paths]
        output["sources"][name] = {
            "reportSha256": {str(path.relative_to(ROOT)): digest(path) for path in paths},
            **audit(paths),
        }
    encoded = json.dumps(output, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
