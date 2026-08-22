"""Record a short, finite webcam clip for ingestion smoke tests."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from video_intelligence_inference.camera import CameraError, WebcamCamera
from video_intelligence_inference.config import Settings, get_settings
from video_intelligence_inference.logging_config import configure_logging

logger = logging.getLogger(__name__)


class RecordingError(RuntimeError):
    """Raised when OpenCV cannot create the requested video file."""


class FrameWriter(Protocol):
    def isOpened(self) -> bool: ...

    def write(self, frame: np.ndarray) -> None: ...

    def release(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RecordingSummary:
    output_path: Path
    frame_count: int
    width: int
    height: int
    fps: int


def record_clip(
    camera: WebcamCamera,
    *,
    output_path: Path,
    duration_seconds: float,
    fps: int,
) -> RecordingSummary:
    """Capture a fixed number of frames and always release camera and writer."""
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be greater than zero.")
    if fps <= 0:
        raise ValueError("fps must be greater than zero.")

    destination = output_path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    target_frames = max(1, round(duration_seconds * fps))
    writer: FrameWriter | None = None

    with camera:
        first_frame = camera.read()
        height, width = first_frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            str(destination),
            fourcc,
            float(fps),
            (width, height),
        )
        try:
            if not writer.isOpened():
                raise RecordingError(
                    f"Could not create MP4 file at {destination}. "
                    "Check the path and OpenCV codec support."
                )

            writer.write(first_frame)
            for _ in range(target_frames - 1):
                writer.write(camera.read())
        finally:
            writer.release()

    logger.info(
        "Recorded webcam clip: path=%s frames=%d resolution=%dx%d fps=%d",
        destination,
        target_frames,
        width,
        height,
        fps,
    )
    return RecordingSummary(destination, target_frames, width, height, fps)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record a finite webcam MP4 for Artae Labs ingestion testing."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/webcam-smoke.mp4"),
        help="Destination MP4 path (default: artifacts/webcam-smoke.mp4)",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=15.0,
        help="Clip duration in seconds (default: 15)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings: Settings = get_settings()
    configure_logging(settings.log_level)
    camera = WebcamCamera(
        index=settings.camera_index,
        width=settings.camera_width,
        height=settings.camera_height,
        fps=settings.camera_fps,
    )

    try:
        summary = record_clip(
            camera,
            output_path=args.output,
            duration_seconds=args.seconds,
            fps=settings.camera_fps,
        )
    except (CameraError, ValueError, RecordingError) as exc:
        logger.error("Recording failed: %s", exc)
        return 1

    print(f"Recorded {summary.frame_count} frames to {summary.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
