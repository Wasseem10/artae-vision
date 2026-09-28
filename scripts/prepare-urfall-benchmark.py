"""Prepare the authors' UR Fall RGB sequences for a local, reproducible browser benchmark.

The dataset is CC BY-NC-SA 4.0 for non-commercial academic use. Media stays
gitignored; only source URLs, hashes, labels, and aggregate results may be shared.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://fenix.ur.edu.pl/~mkepski/ds/data"
DATASET_PAGE = "https://fenix.ur.edu.pl/~mkepski/ds/uf.html"
OUTPUT = ROOT / "apps/web/public/vision/urfall"
CACHE = ROOT / "artifacts/urfall/raw"
FPS = 30


def download(url: str, destination: Path) -> None:
    if destination.is_file() and destination.stat().st_size > 0:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "ArtaeResearchBenchmark/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as target:
            shutil.copyfileobj(response, target)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def onset_labels(path: Path) -> dict[str, float]:
    onset: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as source:
        for row in csv.reader(source):
            if len(row) < 3:
                raise ValueError(f"Malformed author label row in {path.name}")
            sequence, frame_text, label_text = row[:3]
            if label_text == "0" and sequence not in onset:
                onset[sequence] = (int(frame_text) - 1) / FPS
    return onset


def ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        executable = shutil.which("ffmpeg")
        if executable:
            return executable
        raise RuntimeError("Install imageio-ffmpeg or put ffmpeg on PATH") from None


def convert(sequence: str, archive: Path, video: Path, ffmpeg: str) -> int:
    with zipfile.ZipFile(archive) as source:
        if source.testzip() is not None:
            raise ValueError(f"Corrupt zip archive: {archive}")
        frames = sorted(
            name for name in source.namelist()
            if name.startswith(sequence + "/") and name.lower().endswith(".png")
        )
        if not frames:
            raise ValueError(f"No RGB PNG frames in {archive}")
        numbers = [int(Path(name).stem.rsplit("-", 1)[-1]) for name in frames]
        if numbers != list(range(1, len(frames) + 1)):
            raise ValueError(f"Missing or reordered frames in {archive}")
        temporary = video.with_suffix(".part.mp4")
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "image2pipe", "-framerate", str(FPS), "-vcodec", "png",
            "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "25", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(temporary),
        ]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            assert process.stdin is not None
            for name in frames:
                process.stdin.write(source.read(name))
            process.stdin.close()
            assert process.stderr is not None
            error = process.stderr.read().decode("utf-8", errors="replace")
            if process.wait() != 0:
                raise RuntimeError(f"ffmpeg failed for {sequence}: {error[-1000:]}")
            temporary.replace(video)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            temporary.unlink(missing_ok=True)
    return len(frames)


def prepare(max_falls: int, max_adls: int) -> dict:
    if not (0 <= max_falls <= 30 and 0 <= max_adls <= 40 and max_falls + max_adls > 0):
        raise ValueError("Choose 0–30 falls and 0–40 daily activity sequences")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    labels = CACHE / "urfall-cam0-falls.csv"
    download(f"{SOURCE}/{labels.name}", labels)
    starts = onset_labels(labels)
    ffmpeg = ffmpeg_executable()
    cases = []
    for category, maximum in (("fall", max_falls), ("adl", max_adls)):
        for number in range(1, maximum + 1):
            sequence = f"{category}-{number:02d}-cam0-rgb"
            archive = CACHE / f"{sequence}.zip"
            video = OUTPUT / f"{sequence}.mp4"
            download(f"{SOURCE}/{archive.name}", archive)
            if not video.is_file() or video.stat().st_size == 0:
                frame_count = convert(sequence, archive, video, ffmpeg)
            else:
                with zipfile.ZipFile(archive) as source:
                    frame_count = sum(name.lower().endswith(".png") for name in source.namelist())
            source_id = f"{category}-{number:02d}"
            if category == "fall" and source_id not in starts:
                raise ValueError(f"No transition label for {source_id}")
            cases.append({
                "id": source_id,
                "name": f"UR Fall {source_id}",
                "category": "fall" if category == "fall" else "daily_activity",
                "partition": "development" if number <= 10 else "holdout",
                "videoUrl": f"/vision/urfall/{sequence}.mp4",
                "expectedEvents": 1 if category == "fall" else 0,
                "eventStartSeconds": starts.get(source_id),
                "frameCount": frame_count,
                "sourceZipSha256": sha256(archive),
                "videoSha256": sha256(video),
            })
            print(f"Prepared {source_id}: {frame_count} frames", flush=True)
    manifest = {
        "schemaVersion": 1,
        "datasetId": "urfall-rgb-cam0-v1",
        "source": DATASET_PAGE,
        "citation": "Kwolek B, Kepski M. Human fall detection on embedded platform using depth maps and wireless accelerometer. Computer Methods and Programs in Biomedicine 117(3), 2014.",
        "license": "CC BY-NC-SA 4.0; non-commercial academic use",
        "split": "Sequences 01-10 of each class are development cases; the remaining 20 falls and 30 daily activities are a locked holdout. Subject IDs are unavailable, so this is not a person-independent split.",
        "labelNote": "Clip class is supplied by the authors. Approximate onset is the first depth-label transition frame (0) at 30 FPS; RGB and depth streams are not perfectly synchronized.",
        "cases": cases,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--falls", type=int, default=30)
    parser.add_argument("--adls", type=int, default=40)
    args = parser.parse_args()
    try:
        result = prepare(args.falls, args.adls)
        print(f"Manifest: {OUTPUT / 'manifest.json'} ({len(result['cases'])} cases)")
    except Exception as exc:
        print(f"Preparation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
