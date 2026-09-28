"""Download pinned GMDCSA-24 research clips locally and build a subject-split manifest.

Videos remain gitignored. Cite Alam et al., Data in Brief 2024, and Zenodo
10.5281/zenodo.13354453. The repository supplies an MIT LICENSE; do not
redistribute participant video through this project.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps/web/public/vision/gmdcsa24"
REPOSITORY = "ekramalam/GMDCSA24-A-Dataset-for-Human-Fall-Detection-in-Videos"
REVISION = "5abac7693229900cf80f722e878fbb119211fc1c"  # v2.1
TREE_URL = f"https://api.github.com/repos/{REPOSITORY}/git/trees/{REVISION}?recursive=1"
RAW_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/{REVISION}"
USER_AGENT = "ArtaeResearchBenchmark/1.0"
FALL_ONSET = re.compile(r"Falling[^;\[]*\[\s*(\d+(?:\.\d+)?)\s+(?:to\s+)?\d", re.IGNORECASE)


def request(url: str):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=120
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha(path: Path) -> str:
    digest = hashlib.sha1()
    digest.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_blob(entry: dict, destination: Path) -> None:
    if destination.is_file() and destination.stat().st_size == entry["size"]:
        if git_blob_sha(destination) == entry["sha"]:
            return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    url = f"{RAW_URL}/{urllib.parse.quote(entry['path'])}"
    for attempt in range(3):
        try:
            with request(url) as response, partial.open("wb") as target:
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
            if partial.stat().st_size != entry["size"] or git_blob_sha(partial) != entry["sha"]:
                raise ValueError(f"Source size or Git SHA-1 mismatch: {entry['path']}")
            partial.replace(destination)
            return
        except Exception:
            partial.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def onset_by_filename(csv_path: Path) -> dict[str, float | None]:
    starts = {}
    for line in csv_path.read_text(encoding="utf-8-sig").splitlines()[1:]:
        filename = line.split(",", 1)[0].strip()
        if not filename.endswith(".mp4"):
            raise ValueError(f"Unrecognized label row: {line[:80]}")
        match = FALL_ONSET.search(line)
        if not match and "Falling" not in line:
            raise ValueError(f"Missing fall class in {csv_path}: {filename}")
        starts[filename] = float(match.group(1)) if match else None
    return starts


def prepare(subjects: list[int], workers: int) -> dict:
    with request(TREE_URL) as response:
        tree = json.load(response)
    if tree.get("truncated"):
        raise ValueError("GitHub source tree was truncated")
    entries = {entry["path"]: entry for entry in tree["tree"] if entry["type"] == "blob"}
    selected = [entry for entry in entries.values() if re.fullmatch(
        r"Subject [1-4]/(?:Fall|ADL)/(?:\d\d)\.mp4", entry["path"]
    ) and int(entry["path"].split("/")[0].split()[1]) in subjects]
    labels = [entries[f"Subject {subject}/Fall.csv"] for subject in subjects]
    if not selected:
        raise ValueError("No subject videos found in pinned source revision")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_blob, entry, OUTPUT / entry["path"]): entry
                   for entry in selected + labels}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            future.result()
            print(f"Downloaded/verified {index}/{len(futures)}: {futures[future]['path']}", flush=True)

    onsets = {subject: onset_by_filename(OUTPUT / f"Subject {subject}/Fall.csv")
              for subject in subjects}
    cases = []
    for entry in sorted(selected, key=lambda item: item["path"]):
        source_path = entry["path"]
        _, category, filename = source_path.split("/")
        subject = int(source_path.split("/")[0].split()[1])
        positive = category == "Fall"
        case_id = f"gmd-s{subject}-{category.lower()}-{Path(filename).stem}"
        video_path = OUTPUT / source_path
        case = {
            "id": case_id,
            "name": f"GMDCSA-24 subject {subject} {category.lower()} {filename}",
            "category": "fall" if positive else "daily_activity",
            "partition": "development" if subject <= 2 else "holdout",
            "subjectId": f"subject-{subject}",
            "videoUrl": f"/vision/gmdcsa24/{urllib.parse.quote(source_path)}",
            "expectedEvents": 1 if positive else 0,
            "videoSha256": sha256(video_path),
            "sourceGitBlobSha1": entry["sha"],
        }
        if positive and onsets[subject][filename] is not None:
            case["eventStartSeconds"] = onsets[subject][filename]
        cases.append(case)
    manifest = {
        "schemaVersion": 1,
        "datasetId": "gmdcsa24-v2.1",
        "source": "https://zenodo.org/records/13354453",
        "citation": "Alam E, Sufian A, Dutta P, Leo M, Hameed IA. GMDCSA24: A dataset for human fall detection in videos. Data in Brief, 2024.",
        "license": "Source repository has MIT LICENSE; participant videos remain local and are not redistributed here.",
        "split": "Subjects 1-2 are development; subjects 3-4 are locked evaluation. Separate from UR Fall.",
        "labelNote": "Clip classes and approximate fall onset are parsed from author CSV files; one fall has no onset timestamp. Event range ends may include recovery/other activities.",
        "sourceRevision": REVISION,
        "cases": cases,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subjects", nargs="+", type=int, default=[1, 2, 3, 4])
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if not set(args.subjects) <= {1, 2, 3, 4} or not 1 <= args.workers <= 12:
        parser.error("Choose subjects 1-4 and 1-12 workers")
    try:
        manifest = prepare(sorted(set(args.subjects)), args.workers)
        print(f"Manifest: {OUTPUT / 'manifest.json'} ({len(manifest['cases'])} cases)")
    except Exception as exc:
        print(f"Preparation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
