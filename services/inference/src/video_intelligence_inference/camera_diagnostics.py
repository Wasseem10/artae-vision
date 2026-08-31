"""Bounded, model-free camera stream diagnostics for commissioning."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass

import cv2
import numpy as np


class CameraDiagnosticError(RuntimeError):
    """Raised when a camera stream cannot provide diagnostic frames."""


@dataclass(frozen=True, slots=True)
class CameraDiagnosticMetrics:
    frame_count: int
    read_failures: int
    width: int
    height: int
    observed_fps: float
    brightness_mean: float
    contrast_mean: float
    sharpness_mean: float
    frozen_frame_ratio: float
    black_frame_ratio: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CameraDiagnosticOutput:
    metrics: CameraDiagnosticMetrics
    preview_jpeg: bytes


def _capture_source(source_uri: str) -> str | int:
    if source_uri.lower().startswith("webcam:"):
        return int(source_uri.split(":", maxsplit=1)[1])
    return source_uri


def diagnose_camera_stream(
    *,
    source_uri: str,
    duration_seconds: float,
    maximum_frames: int,
    timeout_seconds: float = 10,
    capture_factory: Callable[[], cv2.VideoCapture] = cv2.VideoCapture,
    monotonic: Callable[[], float] = time.monotonic,
) -> CameraDiagnosticOutput:
    """Read a bounded sample and calculate basic delivery/image-quality signals."""
    capture = capture_factory()
    start = monotonic()
    frames: list[np.ndarray] = []
    brightness: list[float] = []
    contrast: list[float] = []
    sharpness: list[float] = []
    black_frames = 0
    frozen_pairs = 0
    read_failures = 0
    previous: np.ndarray | None = None
    best_frame: np.ndarray | None = None
    best_sharpness = -1.0
    width = 0
    height = 0
    try:
        capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_seconds * 1000)
        capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_seconds * 1000)
        if not capture.open(_capture_source(source_uri)):
            raise CameraDiagnosticError("Camera stream could not be opened")
        while len(frames) < maximum_frames and monotonic() - start < duration_seconds:
            ok, frame = capture.read()
            if not ok or frame is None:
                read_failures += 1
                if read_failures >= 10:
                    break
                continue
            height, width = frame.shape[:2]
            target_width = min(320, width)
            sample = cv2.resize(
                frame,
                (target_width, max(1, round(height * target_width / width))),
                interpolation=cv2.INTER_AREA,
            )
            gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
            mean = float(np.mean(gray))
            standard_deviation = float(np.std(gray))
            focus = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            brightness.append(mean)
            contrast.append(standard_deviation)
            sharpness.append(focus)
            black_frames += int(mean < 10)
            if previous is not None:
                frozen_pairs += int(float(np.mean(cv2.absdiff(previous, gray))) < 0.75)
            previous = gray
            if focus > best_sharpness:
                best_sharpness = focus
                best_frame = frame.copy()
            frames.append(gray)
    finally:
        capture.release()
    elapsed = max(0.001, monotonic() - start)
    if not frames or best_frame is None:
        raise CameraDiagnosticError("Camera stream returned no usable frames")
    if width > 960:
        best_frame = cv2.resize(
            best_frame,
            (960, max(1, round(height * 960 / width))),
            interpolation=cv2.INTER_AREA,
        )
    encoded, jpeg = cv2.imencode(".jpg", best_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not encoded:
        raise CameraDiagnosticError("Camera diagnostic preview could not be encoded")
    frame_count = len(frames)
    metrics = CameraDiagnosticMetrics(
        frame_count=frame_count,
        read_failures=read_failures,
        width=width,
        height=height,
        observed_fps=min(1000.0, frame_count / elapsed),
        brightness_mean=float(np.mean(brightness)),
        contrast_mean=float(np.mean(contrast)),
        sharpness_mean=float(np.mean(sharpness)),
        frozen_frame_ratio=frozen_pairs / max(1, frame_count - 1),
        black_frame_ratio=black_frames / frame_count,
    )
    return CameraDiagnosticOutput(metrics=metrics, preview_jpeg=jpeg.tobytes())
