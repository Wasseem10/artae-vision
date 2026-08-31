"""Build short, reproducible replay excerpts from licensed calibration footage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "artifacts" / "calibration" / "public"
DERIVED = ROOT / "artifacts" / "calibration" / "derived"


@dataclass(frozen=True, slots=True)
class Excerpt:
    source: Path
    output: Path
    start_seconds: float
    end_seconds: float


EXCERPTS = (
    Excerpt(
        PUBLIC / "pexels" / "19912008-empty-warehouse.mp4",
        DERIVED / "person-presence" / "pexels-19912008-empty-warehouse-0-12.mp4",
        0,
        12,
    ),
    Excerpt(
        PUBLIC / "pexels" / "8965389-ppe-removal.mp4",
        DERIVED / "ppe-removal" / "pexels-8965389-ppe-removal.mp4",
        0,
        11.8,
    ),
    Excerpt(
        PUBLIC / "pexels" / "7705348-spill.mp4",
        DERIVED / "spill-appears" / "pexels-7705348-spill-30-40.mp4",
        30,
        40.6,
    ),
    Excerpt(
        PUBLIC / "umafall" / "fall" / "FALL-Backwards_.mp4",
        DERIVED / "person-fall" / "umafall-backwards-8-20.mp4",
        8,
        20,
    ),
    Excerpt(
        PUBLIC / "umafall" / "fall" / "FALL-Forward_.mp4",
        DERIVED / "person-fall" / "umafall-forward-13-25.mp4",
        13,
        25,
    ),
    Excerpt(
        PUBLIC / "umafall" / "fall" / "FALL-Lateral_.mp4",
        DERIVED / "person-fall" / "umafall-lateral-13-25.mp4",
        13,
        25,
    ),
    Excerpt(
        PUBLIC / "umafall" / "adl" / "ADL-bending_.mp4",
        DERIVED / "person-fall" / "umafall-adl-bending-8-20.mp4",
        8,
        20,
    ),
    Excerpt(
        PUBLIC / "umafall" / "adl" / "ADL-sitting down (and up) on (from) a chair_.mp4",
        DERIVED / "person-fall" / "umafall-adl-sitting-8-20.mp4",
        8,
        20,
    ),
    Excerpt(
        PUBLIC / "wikimedia" / "gigaset-conveyor.webm",
        DERIVED / "equipment-stop" / "commons-gigaset-conveyor-0-12.mp4",
        0,
        12,
    ),
)


def build_excerpt(excerpt: Excerpt) -> None:
    if not excerpt.source.is_file():
        raise FileNotFoundError(excerpt.source)
    excerpt.output.parent.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(excerpt.source))
    fps = capture.get(cv2.CAP_PROP_FPS)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0 or width <= 0 or height <= 0:
        capture.release()
        raise ValueError(f"Could not read video metadata: {excerpt.source}")
    capture.set(cv2.CAP_PROP_POS_MSEC, excerpt.start_seconds * 1000)
    writer = cv2.VideoWriter(
        str(excerpt.output),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(f"Could not create excerpt: {excerpt.output}")
    written = 0
    try:
        while capture.get(cv2.CAP_PROP_POS_MSEC) / 1000 < excerpt.end_seconds:
            ok, frame = capture.read()
            if not ok:
                break
            writer.write(frame)
            written += 1
    finally:
        capture.release()
        writer.release()
    if written == 0:
        excerpt.output.unlink(missing_ok=True)
        raise RuntimeError(f"Excerpt contained no frames: {excerpt.source}")
    print(f"{excerpt.output.relative_to(ROOT)}: {written / fps:.2f}s")


if __name__ == "__main__":
    for item in EXCERPTS:
        build_excerpt(item)
