"""Prepare the local RealBiomFall 100-video clip-level holdout.

Download the two ZIPs from https://zenodo.org/records/11636174 into
artifacts/realbiomfall/videos.zip and labels.zip first. Research media and the
generated manifest stay ignored and are never part of the deployed website.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/realbiomfall"
DESTINATION = ROOT / "apps/web/public/vision/realbiomfall"
EXTRACTED = SOURCE / "source-videos"
VIDEO_ZIP_MD5 = "1168284537004b7937ec552015461719"
LABEL_ZIP_MD5 = "01c05eda9a4188dc8ae6601c4a5c1874"
MAX_VIDEO_BYTES = 20_000_000


def digest(data: bytes, algorithm: str) -> str:
    return hashlib.new(algorithm, data).hexdigest()


def ffmpeg_path() -> str:
    selected = os.environ.get("ARTAE_FFMPEG") or shutil.which("ffmpeg")
    if selected:
        return selected
    bundled = list((ROOT / "artifacts/pydeps/imageio_ffmpeg/binaries").glob("ffmpeg-*.exe"))
    if len(bundled) == 1:
        return str(bundled[0])
    raise RuntimeError("ffmpeg with libx264 is required; set ARTAE_FFMPEG")


def main() -> None:
    videos_zip = (SOURCE / "videos.zip").read_bytes()
    labels_zip = (SOURCE / "labels.zip").read_bytes()
    if digest(videos_zip, "md5") != VIDEO_ZIP_MD5 or digest(labels_zip, "md5") != LABEL_ZIP_MD5:
        raise ValueError("Zenodo archive checksum mismatch")
    with zipfile.ZipFile(SOURCE / "labels.zip") as archive:
        label_names = {item.filename for item in archive.infolist()}
        if "labels-100/labels_temporal_coarse.pkl" not in label_names:
            raise ValueError("Expected temporal annotation archive")
    cases = []
    video_zip_sha256 = digest(videos_zip, "sha256")
    DESTINATION.mkdir(parents=True, exist_ok=True)
    EXTRACTED.mkdir(parents=True, exist_ok=True)
    encoder = ffmpeg_path()
    with zipfile.ZipFile(SOURCE / "videos.zip") as archive:
        entries = sorted(
            (item for item in archive.infolist() if item.filename.endswith(".mp4")),
            key=lambda item: item.filename,
        )
        if len(entries) != 100:
            raise ValueError(f"Expected 100 videos, got {len(entries)}")
        for number, item in enumerate(entries, start=1):
            filename = Path(item.filename).name
            if (
                item.is_dir() or
                not re.fullmatch(r"[A-Za-z0-9_.-]+\.mp4", filename) or
                item.file_size > MAX_VIDEO_BYTES or
                item.filename != f"video_clips-trimmed_cropped_padded_resized-100/{filename}"
            ):
                raise ValueError(f"Invalid archive entry: {item.filename}")
            data = archive.read(item)
            if len(data) != item.file_size:
                raise ValueError(f"Archive entry size mismatch: {filename}")
            case_id = f"realbiom-fall-{number:03d}"
            source_video = EXTRACTED / f"{case_id}.mp4"
            encoded = DESTINATION / f"{case_id}.mp4"
            source_video.write_bytes(data)
            subprocess.run([
                encoder, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source_video),
                "-an", "-c:v", "libx264", "-threads", "1", "-preset", "veryfast", "-crf", "25",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(encoded),
            ], check=True)
            cases.append({
                "id": case_id,
                "name": f"RealBiomFall clip {number:03d}",
                "category": "fall",
                "partition": "holdout",
                "videoUrl": f"/vision/realbiomfall/{case_id}.mp4",
                "expectedEvents": 1,
                "sourceFilename": filename,
                "sourceVideoSha256": digest(data, "sha256"),
                "sourceZipSha256": video_zip_sha256,
                "videoSha256": digest(encoded.read_bytes(), "sha256"),
            })
    manifest = {
        "schemaVersion": 1,
        "datasetId": "realbiomfall-100-v3",
        "source": "https://zenodo.org/records/11636174",
        "citation": "RealBiomFall: A Fine-grained Realistic Fall Dataset from the Perspective of Biomechanics. Zenodo 11636174.",
        "license": "CC BY 4.0",
        "split": "100 previously unseen positive clips; clip-level check only",
        "labelNote": "All clips are from the released fall set. Temporal label semantics have not been mapped to alert windows; this measures any alert per clip, not event-time recall. There are no negative clips.",
        "sourceRevision": "zenodo-11636174-v3",
        "sourceAnnotationSha256": digest(labels_zip, "sha256"),
        "cases": cases,
    }
    (DESTINATION / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(cases)} clips in {DESTINATION}")


if __name__ == "__main__":
    main()
