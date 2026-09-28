"""Print pose geometry diagnostics from an exported fall benchmark run."""

import argparse
import json
from pathlib import Path


def main(path: Path) -> None:
    run = json.loads(path.read_text(encoding="utf-8"))
    print("case         y-range     max-drop/1s  min-vertical  max-aspect  detections")
    for result in run["results"]:
        points = [point for point in result["poseTrace"] if point["y"] is not None]
        if not points:
            print(result["id"], "no usable pose")
            continue
        drops = [
            later["y"] - earlier["y"]
            for earlier in points
            for later in points
            if 0.5 <= later["seconds"] - earlier["seconds"] <= 1.2
        ]
        print(
            f"{result['id']:<12} "
            f"{min(point['y'] for point in points):.2f}-{max(point['y'] for point in points):.2f}    "
            f"{max(drops, default=0):>8.2f}     "
            f"{min(point['verticality'] for point in points):>8.2f}     "
            f"{max(point['aspect'] for point in points):>8.2f}     "
            f"{result['detectedAtSeconds']}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    main(parser.parse_args().report)
