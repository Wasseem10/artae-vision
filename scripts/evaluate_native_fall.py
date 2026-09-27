"""Run the native YOLO pose fall replay on finite local video clips.

This is a candidate-generation baseline. It has no ground-truth labels and
therefore cannot establish fall recall, precision, or field reliability.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INFERENCE_SOURCE = (
    ROOT / "services" / "inference" / "src" / "video_intelligence_inference"
)
RELEVANT_SOURCE_FILES = (
    "replay.py",
    "detector.py",
    "pose_action.py",
    "source.py",
    "control_plane.py",
    "config.py",
    "zones.py",
    "rules.py",
)


@dataclass(frozen=True)
class VideoMetadata:
    duration_seconds: float
    frame_count: int
    fps: float


def _fraction(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("must be a finite number between 0 and 1")
    return number


def _nonnegative(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a finite nonnegative number")
    return number


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", type=Path, required=True, help="Local YOLO pose .pt model"
    )
    parser.add_argument(
        "--clip",
        type=Path,
        action="append",
        required=True,
        help="Finite local video file; repeat for multiple clips",
    )
    parser.add_argument(
        "--output", type=Path, help="Write JSON here; default is stdout"
    )
    parser.add_argument(
        "--dataset-name", default="unspecified", help="Dataset/source label"
    )
    parser.add_argument("--confidence", type=_fraction, default=0.5)
    parser.add_argument("--iou", type=_fraction, default=0.45)
    parser.add_argument("--cooldown-seconds", type=_nonnegative, default=60.0)
    parser.add_argument("--absence-grace-seconds", type=_nonnegative, default=1.0)
    parser.add_argument("--device", help="Ultralytics device, e.g. cpu or 0")
    return parser.parse_args(argv)


def validate_inputs(args: argparse.Namespace) -> tuple[Path, tuple[Path, ...]]:
    model = args.model.expanduser().resolve()
    if not model.is_file():
        raise ValueError(
            f"Pose model file is missing: {model}. Pass --model with a local .pt file."
        )
    if model.suffix.lower() != ".pt":
        raise ValueError(f"Pose model must be a local .pt file: {model}")
    clips = tuple(clip.expanduser().resolve() for clip in args.clip)
    for clip in clips:
        if not clip.is_file():
            raise ValueError(
                f"Video clip is missing: {clip}. Pass --clip with a local video file."
            )
        if clip.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
            raise ValueError(f"Unsupported video extension: {clip}")
    if len(set(clips)) != len(clips):
        raise ValueError("Each --clip path must be unique.")
    return model, clips


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_video(path: Path) -> VideoMetadata:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is unavailable. Install services/inference dependencies in the active Python environment."
        ) from exc
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"Could not open video clip: {path}")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not math.isfinite(fps) or fps <= 0 or frame_count <= 0:
            raise ValueError(
                f"Video clip has no usable FPS/frame-count metadata: {path}"
            )
        decoded, _frame = capture.read()
        if not decoded:
            raise ValueError(f"Video clip contains no decodable frames: {path}")
        return VideoMetadata(frame_count / fps, frame_count, fps)
    finally:
        capture.release()


def _load_runtime() -> tuple[type, Callable[..., Any], Callable[..., Any]]:
    try:
        from video_intelligence_inference.config import Settings
        from video_intelligence_inference.control_plane import resolve_rule_config
        from video_intelligence_inference.replay import run_replay
    except ImportError as exc:
        raise RuntimeError(
            "Native inference dependencies are unavailable. Install services/inference "
            "with its Python dependencies and include services/inference/src on PYTHONPATH."
        ) from exc
    for name in RELEVANT_SOURCE_FILES:
        module = importlib.import_module(
            f"video_intelligence_inference.{Path(name).stem}"
        )
        loaded_from = getattr(module, "__file__", None)
        expected = (INFERENCE_SOURCE / name).resolve()
        if loaded_from is None or Path(loaded_from).resolve() != expected:
            raise RuntimeError(
                f"Native inference module {name} was imported from "
                f"{loaded_from or '<unknown>'}, not this checkout ({expected}). "
                "Set PYTHONPATH to this checkout's services/inference/src before running."
            )
    return Settings, resolve_rule_config, run_replay


def _fall_rule(
    resolve_rule_config: Callable[..., Any], args: argparse.Namespace
) -> Any:
    zone = {
        "id": "native-fall-full-frame",
        "name": "Full frame",
        "geometry_type": "polygon",
        "points": [
            {"x": 0, "y": 0},
            {"x": 1, "y": 0},
            {"x": 1, "y": 1},
            {"x": 0, "y": 1},
        ],
    }
    return resolve_rule_config(
        {
            "id": "native-fall-baseline",
            "key": "native-fall-baseline",
            "rule_type": "semantic_vision",
            "object_class": "person",
            "duration_seconds": 0,
            "minimum_confidence": args.confidence,
            "absence_grace_seconds": args.absence_grace_seconds,
            "zone": zone,
            "spec": {
                "schema_version": 3,
                "rule_type": "semantic_vision",
                "object_class": "person",
                "zone_id": zone["id"],
                "zone_name": zone["name"],
                "instruction": "Alert me if a person falls to the ground.",
                "minimum_confidence": args.confidence,
                "absence_grace_seconds": args.absence_grace_seconds,
                "cooldown_seconds": args.cooldown_seconds,
            },
            "execution_plan": {
                "schema_version": 1,
                "strategy": "specialized_pose",
                "provider_requests": False,
            },
        }
    )


def build_report(
    args: argparse.Namespace,
    *,
    runtime_loader: Callable[
        [], tuple[type, Callable[..., Any], Callable[..., Any]]
    ] = _load_runtime,
    video_probe: Callable[[Path], VideoMetadata] = probe_video,
    generated_at: str | None = None,
) -> dict[str, Any]:
    model, clips = validate_inputs(args)
    Settings, resolve_rule_config, run_replay = runtime_loader()
    settings = Settings(
        _env_file=None,
        pose_model_name=str(model),
        confidence_threshold=args.confidence,
        iou_threshold=args.iou,
        device=args.device,
        camera_width=1280,
        camera_height=720,
        camera_fps=30,
    )
    rule = _fall_rule(resolve_rule_config, args)
    if rule.execution_strategy != "specialized_pose":
        raise RuntimeError(
            "Fall rule did not resolve to the native specialized_pose path."
        )
    results: list[dict[str, Any]] = []
    for index, clip in enumerate(clips, start=1):
        metadata = video_probe(clip)
        if (
            not math.isfinite(metadata.duration_seconds)
            or metadata.duration_seconds <= 0
        ):
            raise ValueError(f"Video clip has invalid duration: {clip}")
        frames_processed = 0
        last_processed_seconds: float | None = None

        def record_progress(timestamp_seconds: float) -> None:
            nonlocal frames_processed, last_processed_seconds
            frames_processed += 1
            last_processed_seconds = timestamp_seconds

        print(f"[{index}/{len(clips)}] Analyzing {clip.name}", file=sys.stderr)
        output = run_replay(
            settings,
            source_uri=str(clip),
            duration_seconds=metadata.duration_seconds,
            rule=rule,
            on_progress=record_progress,
        )
        if frames_processed != metadata.frame_count:
            raise RuntimeError(
                f"Incomplete replay of {clip.name}: processed {frames_processed} of "
                f"{metadata.frame_count} frames reported by the video."
            )
        if output.provider_requests:
            raise RuntimeError(
                "Native pose replay unexpectedly made provider requests; refusing baseline output."
            )
        intervals = [interval.to_dict() for interval in output.intervals]
        results.append(
            {
                "clip_name": clip.name,
                "clip_sha256": sha256_file(clip),
                "duration_seconds": round(metadata.duration_seconds, 6),
                "source_fps": round(metadata.fps, 6),
                "source_frame_count": metadata.frame_count,
                "frames_processed": frames_processed,
                "last_processed_seconds": round(last_processed_seconds, 6)
                if last_processed_seconds is not None
                else None,
                "candidate_times_seconds": [
                    interval.get("detected_at_seconds", interval["end_seconds"])
                    for interval in intervals
                ],
                "candidate_intervals": intervals,
                "candidate_count": len(intervals),
                "provider_requests": output.provider_requests,
            }
        )
    source_hashes = {
        name: sha256_file(INFERENCE_SOURCE / name) for name in RELEVANT_SOURCE_FILES
    }
    source_hashes["scripts/evaluate_native_fall.py"] = sha256_file(Path(__file__))
    return {
        "schema_version": 1,
        "kind": "native_fall_candidate_baseline",
        "generated_at_utc": generated_at or datetime.now(timezone.utc).isoformat(),
        "dataset_name": args.dataset_name,
        "execution_path": "video_intelligence_inference.replay.run_replay:specialized_pose",
        "provenance": {
            "model_name": model.name,
            "model_sha256": sha256_file(model),
            "source_sha256": source_hashes,
            "configuration": {
                "pose_model": model.name,
                "minimum_confidence": rule.minimum_confidence,
                "iou_threshold": settings.iou_threshold,
                "cooldown_seconds": rule.cooldown_seconds,
                "absence_grace_seconds": rule.absence_grace_seconds,
                "device": settings.device,
                "zone": "full_frame",
                "rule_id": rule.rule_id,
                "camera_width": settings.camera_width,
                "camera_height": settings.camera_height,
                "camera_fps": settings.camera_fps,
            },
        },
        "total_clips": len(results),
        "total_candidates": sum(result["candidate_count"] for result in results),
        "results": results,
        "limitation": (
            "Unlabeled local-clip candidate baseline. No precision, recall, false-alert rate, "
            "or field reliability claim can be calculated from this output."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_report(args)
        serialized = json.dumps(report, indent=2) + "\n"
        if args.output is None:
            sys.stdout.write(serialized)
        else:
            destination = args.output.expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(serialized, encoding="utf-8")
            print(f"Wrote {destination}", file=sys.stderr)
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        detail = str(exc)
        if (
            "WinError 4551" in detail
            or "Application Control policy has blocked" in detail
        ):
            detail = (
                "Windows Application Control blocked a native inference library "
                "(WinError 4551). Run this baseline on an approved host where the "
                "PyTorch/torchvision native extensions are permitted."
            )
        elif "torchvision::nms does not exist" in detail:
            detail = (
                "Native YOLO pose inference cannot start because this Python environment "
                "cannot load the torchvision::nms operator. Check whether torchvision's "
                "native extension is blocked or failed to load, then rerun in a working "
                "inference environment."
            )
        print(f"error: {detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
