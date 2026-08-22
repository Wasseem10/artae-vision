import argparse
import logging
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from video_intelligence_artae.client import ArtaeLabsClient, ArtaeLabsError
from video_intelligence_artae.config import ArtaeLabsSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload a clip to Artae Labs, wait for indexing, and search it."
    )
    parser.add_argument("video", type=Path, help="Local MP4 clip to upload")
    parser.add_argument("--query", default="a person visible in the scene")
    parser.add_argument("--index-id", help="Existing Labs index; creates one when omitted")
    parser.add_argument("--index-name", default="Camera Intelligence Smoke Tests")
    parser.add_argument("--modality", default="all")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--deep-listen", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    try:
        settings = ArtaeLabsSettings()
    except ValidationError:
        logging.getLogger(__name__).error(
            "Artae Labs configuration is missing. Set ARTAE_LABS_API_KEY "
            "and, if needed, ARTAE_LABS_BASE_URL in the root .env file."
        )
        return 2

    try:
        with ArtaeLabsClient(settings) as client:
            index_id = args.index_id
            if not index_id:
                index = client.create_index(
                    args.index_name,
                    description="Short clips used to validate camera intelligence integration.",
                )
                index_id = index.id
                logging.getLogger(__name__).info("Created Labs index %s", index_id)

            video = client.upload_video(
                index_id=index_id,
                video_path=args.video,
            )
            ready_video = client.wait_until_ready(video.id)
            response = client.search(
                index_id=index_id,
                query=args.query,
                modality=cast(
                    Literal[
                        "visual",
                        "audio",
                        "transcription",
                        "ocr",
                        "semantic_event",
                        "edit_anchor",
                        "all",
                    ],
                    args.modality,
                ),
                limit=args.limit,
                deep_listen=args.deep_listen,
            )
    except (ArtaeLabsError, FileNotFoundError) as exc:
        logging.getLogger(__name__).error("Smoke test failed: %s", exc)
        return 1

    print(
        f"Indexed video {ready_video.id} with {ready_video.shot_count} shots; "
        f"query returned {response.count} result(s)."
    )
    for hit in response.results:
        print(
            f"- {hit.time_start:.2f}s-{hit.time_end:.2f}s "
            f"score={hit.similarity:.3f} {hit.summary or ''}"
        )
    return 0
