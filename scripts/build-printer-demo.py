"""Build the short, deterministic printer-failure demo from attributed dataset frames."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sequence", type=Path, help="GreenSkullEarly masks directory")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    images = sorted(args.sequence.glob("*_frame.jpg"))
    if len(images) != 10:
        raise SystemExit(f"Expected 10 source frames, found {len(images)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    width, height, fps = 960, 540, 24
    writer = cv2.VideoWriter(
        str(args.output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )
    if not writer.isOpened():
        raise SystemExit("OpenCV could not create the MP4")

    # The first six observations establish a normal baseline. Later observations
    # linger so a five-second demo interval reliably sees the developing failure.
    durations = [1, 1, 1, 1, 1, 1, 3, 3, 3, 8]
    try:
        for path, seconds in zip(images, durations, strict=True):
            frame = cv2.imread(str(path))
            if frame is None:
                raise SystemExit(f"Could not read {path}")
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            for _ in range(seconds * fps):
                writer.write(frame)
    finally:
        writer.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
