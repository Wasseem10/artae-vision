"""Build the short, deterministic printer-failure demo from attributed dataset frames."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import cv2
import imageio_ffmpeg


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
    with tempfile.TemporaryDirectory() as temp_dir:
        intermediate = Path(temp_dir) / "printer-demo.mp4"
        writer = cv2.VideoWriter(
            str(intermediate), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
        )
        if not writer.isOpened():
            raise SystemExit("OpenCV could not create the intermediate MP4")

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

        # OpenCV's mp4v output is not supported by every browser. Transcode to
        # H.264/yuv420p and move metadata to the front for dependable web playback.
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-y",
                "-i",
                str(intermediate),
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(args.output),
            ],
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
