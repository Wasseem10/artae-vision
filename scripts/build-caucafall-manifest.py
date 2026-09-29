"""Join locally verified CAUCAFall v4 videos to pinned OmniFall event labels.

Install pyarrow, then run after prepare-caucafall-videos.cjs. Participant media
and the full per-clip manifest stay gitignored; commit only aggregate results.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts/caucafall"
PREPARED = ARTIFACT / "prepared-index.json"
LABELS = ARTIFACT / "omnifall-labels.parquet"
OUTPUT = ROOT / "apps/web/public/vision/caucafall/manifest.json"
LABELS_SHA256 = "a5169d3e95b26080527265516d415d068a83c3dea4cddca8d0828a8d2345fd3a"
OMNIFALL_REVISION = "83572a37b9e3081df8c06a56874b1d1f2a19386c"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if sha256(LABELS) != LABELS_SHA256:
        raise ValueError("OmniFall annotation file differs from the pinned SHA-256")
    prepared = json.loads(PREPARED.read_text(encoding="utf-8"))
    if prepared["version"] != 4 or len(prepared["cases"]) != 100:
        raise ValueError("Expected all 100 CAUCAFall v4 videos")

    rows = pq.read_table(LABELS).to_pylist()
    labels = defaultdict(list)
    for row in rows:
        if row["dataset"] == "caucafall":
            labels[Path(row["path"]).name.lower()].append(row)
    if len(labels) != 100:
        raise ValueError(f"Expected 100 OmniFall CAUCAFall video labels, found {len(labels)}")

    cases = []
    for entry in prepared["cases"]:
        stem = Path(entry["sourceFilename"]).stem.lower()
        segments = labels[stem]
        if not segments or {int(row["subject"]) for row in segments} != {entry["subject"]}:
            raise ValueError(f"Missing or mismatched event labels for {entry['id']}")
        falls = sorted((float(row["start"]), float(row["end"])) for row in segments if row["label"] == 1)
        positive = entry["id"].split("-")[2] == "fall"
        if len(falls) != int(positive):
            raise ValueError(f"Expected one fall interval only in positive clip: {entry['id']}")
        video = ROOT / "apps/web/public" / entry["videoUrl"].lstrip("/")
        if sha256(video) != entry["videoSha256"]:
            raise ValueError(f"Transcoded video changed: {entry['id']}")
        cases.append({
            "id": entry["id"],
            "name": f"Subject {entry['subject']} · {entry['activity']}",
            "category": "fall" if positive else "daily_activity",
            "partition": "holdout",
            "subjectId": f"subject-{entry['subject']}",
            "videoUrl": entry["videoUrl"],
            "videoSha256": entry["videoSha256"],
            "sourceVideoSha256": entry["sourceSha256"],
            "expectedEvents": len(falls),
            "eventRanges": [{"start": start, "end": end} for start, end in falls],
            **({"eventStartSeconds": falls[0][0]} if falls else {}),
        })
    if len({case["id"] for case in cases}) != 100:
        raise ValueError("Duplicate CAUCAFall case IDs")
    manifest = {
        "schemaVersion": 1,
        "datasetId": "caucafall-v4-omnifall-labels-v3",
        "source": "https://data.mendeley.com/datasets/7w7fccy7ky/4",
        "citation": "Eraso et al., CAUCAFall v4, doi:10.17632/7w7fccy7ky.4; Schneider et al., OmniFall, arXiv:2505.19889v3",
        "license": "CAUCAFall CC BY 4.0; OmniFall annotations CC BY-NC 4.0. Videos remain local.",
        "split": "Independent cross-source holdout: all ten CAUCAFall subjects; no CAUCAFall footage used for training or threshold selection.",
        "labelNote": "OmniFall fall intervals are action onset/end annotations. Clip outcomes and event-window outcomes are reported separately.",
        "sourceRevision": f"mendeley-v4+omnifall-{OMNIFALL_REVISION}",
        "sourceAnnotationSha256": LABELS_SHA256,
        "cases": cases,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(cases)} holdout cases: {sum(case['expectedEvents'] for case in cases)} fall events and {sum(not case['expectedEvents'] for case in cases)} daily-activity clips")


if __name__ == "__main__":
    main()
