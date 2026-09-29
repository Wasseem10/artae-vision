"""Prepare 35 fall and 60 daily-activity clips from a pinned research source.

The source README permits academic/research use. Original and converted media
stay gitignored and are never deployed. This script requires ffmpeg with
libx264; set ARTAE_FFMPEG if ffmpeg is not on PATH.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVISION = "a895be0ed80a33b55363468c804a9e4d7af95b9c"
REPOSITORY = "adityavvvn/Fall-Detection-IMU-Video-Datase"
SOURCE_DIR = ROOT / "artifacts/imu-video-adl"
DESTINATION = ROOT / "apps/web/public/vision/imuadlfall"
TREE_URL = f"https://api.github.com/repos/{REPOSITORY}/git/trees/{REVISION}?recursive=1"


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Artae-research-benchmark"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ffmpeg_path() -> str:
    selected = os.environ.get("ARTAE_FFMPEG") or shutil.which("ffmpeg")
    if selected:
        return selected
    bundled = list((ROOT / "artifacts/pydeps/imageio_ffmpeg/binaries").glob("ffmpeg-*.exe"))
    if len(bundled) == 1:
        return str(bundled[0])
    raise RuntimeError("ffmpeg with libx264 is required; set ARTAE_FFMPEG")


def main() -> None:
    tree = json.loads(download(TREE_URL))
    if tree.get("truncated"):
        raise ValueError("Incomplete GitHub tree")
    items = sorted(
        (item for item in tree["tree"] if item.get("type") == "blob" and
         re.fullmatch(r"Daily_Activity_0[1-5]/[A-Za-z0-9_]+_video\.mp4", item["path"])),
        key=lambda item: item["path"],
    )
    if len(items) != 95 or any(item["size"] > 2_000_000 for item in items):
        raise ValueError("Expected 95 small fall and daily-activity videos")
    encoder = ffmpeg_path()
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    DESTINATION.mkdir(parents=True, exist_ok=True)
    cases = []
    counts = {"fall": 0, "adl": 0}
    for item in items:
        source_path = item["path"]
        is_fall = source_path.startswith(("Daily_Activity_04/", "Daily_Activity_05/"))
        category_id = "fall" if is_fall else "adl"
        counts[category_id] += 1
        local_source = SOURCE_DIR / source_path.replace("/", "__")
        if local_source.exists():
            raw = local_source.read_bytes()
        else:
            raw = download(f"https://raw.githubusercontent.com/{REPOSITORY}/{REVISION}/{source_path}")
            local_source.write_bytes(raw)
        if len(raw) != item["size"] or git_blob_sha1(raw) != item["sha"]:
            raise ValueError(f"Git blob mismatch: {source_path}")
        case_id = f"imu-{category_id}-{counts[category_id]:03d}"
        encoded = DESTINATION / f"{case_id}.mp4"
        subprocess.run([
            encoder, "-hide_banner", "-loglevel", "error", "-y", "-i", str(local_source),
            "-an", "-c:v", "libx264", "-threads", "1", "-preset", "veryfast", "-crf", "25",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(encoded),
        ], check=True)
        cases.append({
            "id": case_id,
            "name": source_path.replace("Daily_Activity_", "ADL ").replace("/", " · "),
            "category": "fall" if is_fall else "daily_activity",
            "partition": "holdout",
            "videoUrl": f"/vision/imuadlfall/{case_id}.mp4",
            "expectedEvents": 1 if is_fall else 0,
            "sourcePath": source_path,
            "sourceGitBlobSha1": item["sha"],
            "sourceVideoSha256": sha256(raw),
            "videoSha256": sha256(encoded.read_bytes()),
        })
    manifest = {
        "schemaVersion": 1,
        "datasetId": "imu-video-fall-adl-v1",
        "source": f"https://github.com/{REPOSITORY}/tree/{REVISION}",
        "citation": "adityavvvn, Fall Detection IMU & Video Dataset, pinned Git revision.",
        "license": "Academic/research use per source README; media local only",
        "split": "35 fall and 60 daily-activity clips from four actors; fresh-source clip-level check",
        "labelNote": "Repository clip labels: walk, sit, disturbance walk, backward fall, forward fall. Temporal fall intervals are unavailable, so fall results are clip-level only.",
        "sourceRevision": REVISION,
        "cases": cases,
    }
    (DESTINATION / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(cases)} browser-decodable clips in {DESTINATION}")


if __name__ == "__main__":
    main()
