"""Claim evidence jobs and execute the slow Artae Labs operations off-request."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError
from video_intelligence_artae.client import ArtaeLabsClient, ArtaeLabsRequestError
from video_intelligence_artae.config import ArtaeLabsSettings

from video_intelligence_evidence.config import EvidenceWorkerSettings, get_settings

logger = logging.getLogger(__name__)


class EvidenceWorkerError(RuntimeError):
    pass


class IndexAssignment(BaseModel):
    asset_id: str
    event_id: str
    title: str
    duration_seconds: float | None


class SearchAssignment(BaseModel):
    search_id: str
    query: str
    camera_id: str | None
    limit: int = Field(ge=1, le=50)


def _claim(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    worker_id: str,
    kind: str,
    model: type[BaseModel],
) -> BaseModel | None:
    response = client.post(
        f"{base_url}/api/v1/agent/evidence/{kind}-assignments/claim",
        headers=headers,
        json={"worker_id": worker_id},
    )
    if response.status_code == 204:
        return None
    response.raise_for_status()
    return model.model_validate(response.json())


def _report(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> None:
    response = client.post(url, headers=headers, json=payload)
    response.raise_for_status()


def _is_unavailable(error: Exception) -> bool:
    return isinstance(error, ArtaeLabsRequestError) and "HTTP 501" in str(error)


def process_index(
    assignment: IndexAssignment,
    *,
    http: httpx.Client,
    labs: ArtaeLabsClient,
    labs_index_id: str,
    base_url: str,
    headers: dict[str, str],
    worker_id: str,
) -> None:
    result_url = f"{base_url}/api/v1/agent/evidence/{assignment.asset_id}/index-result"
    try:
        with tempfile.TemporaryDirectory(prefix="evidence-index-") as temporary:
            clip_path = Path(temporary) / f"{assignment.asset_id}.mp4"
            with http.stream(
                "GET",
                f"{base_url}/api/v1/evidence/{assignment.asset_id}/content",
                headers=headers,
            ) as response:
                response.raise_for_status()
                with clip_path.open("wb") as output:
                    for chunk in response.iter_bytes():
                        output.write(chunk)
            video = labs.upload_video(
                index_id=labs_index_id,
                video_path=clip_path,
                title=assignment.title,
            )
            ready = labs.wait_until_ready(video.id)
        payload = {
            "worker_id": worker_id,
            "status": "ready",
            "external_index_id": ready.index_id,
            "external_video_id": ready.id,
        }
    except Exception as error:
        logger.exception("Evidence indexing failed: asset=%s", assignment.asset_id)
        payload = {
            "worker_id": worker_id,
            "status": "unavailable" if _is_unavailable(error) else "failed",
            "error": str(error),
        }
    _report(http, result_url, headers, payload)


def process_search(
    assignment: SearchAssignment,
    *,
    http: httpx.Client,
    labs: ArtaeLabsClient,
    labs_index_id: str,
    base_url: str,
    headers: dict[str, str],
    worker_id: str,
) -> None:
    result_url = f"{base_url}/api/v1/agent/evidence/searches/{assignment.search_id}/result"
    started = time.perf_counter()
    try:
        response = labs.search(
            index_id=labs_index_id,
            query=assignment.query,
            limit=assignment.limit,
        )
        hits = [
            {
                "video_id": hit.video_id,
                "time_start": hit.time_start,
                "time_end": hit.time_end,
                "similarity": hit.similarity,
                "summary": hit.summary or hit.audio_description or hit.transcript_chunk,
            }
            for hit in response.results
        ]
        payload = {
            "worker_id": worker_id,
            "status": "completed",
            "latency_ms": response.latency_ms,
            "results": hits,
        }
    except Exception as error:
        logger.exception("Evidence search failed: search=%s", assignment.search_id)
        payload = {
            "worker_id": worker_id,
            "status": "unavailable" if _is_unavailable(error) else "failed",
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "error": str(error),
        }
    _report(http, result_url, headers, payload)


def run_worker(
    settings: EvidenceWorkerSettings,
    labs_settings: ArtaeLabsSettings,
    *,
    once: bool = False,
) -> int:
    if not labs_settings.index_id:
        raise EvidenceWorkerError("ARTAE_LABS_INDEX_ID is required")
    base_url = str(settings.control_plane_url).rstrip("/")
    worker_id = settings.worker_id or f"{socket.gethostname()}-{os.getpid()}"
    headers = {"X-Agent-Key": settings.agent_key.get_secret_value()}
    logger.info("Evidence worker ready: worker=%s index=%s", worker_id, labs_settings.index_id)
    with (
        httpx.Client(timeout=settings.request_timeout_seconds) as http,
        ArtaeLabsClient(labs_settings) as labs,
    ):
        while True:
            handled = False
            try:
                index_job = _claim(http, base_url, headers, worker_id, "index", IndexAssignment)
                if isinstance(index_job, IndexAssignment):
                    process_index(
                        index_job,
                        http=http,
                        labs=labs,
                        labs_index_id=labs_settings.index_id,
                        base_url=base_url,
                        headers=headers,
                        worker_id=worker_id,
                    )
                    handled = True
                else:
                    search_job = _claim(
                        http, base_url, headers, worker_id, "search", SearchAssignment
                    )
                    if isinstance(search_job, SearchAssignment):
                        process_search(
                            search_job,
                            http=http,
                            labs=labs,
                            labs_index_id=labs_settings.index_id,
                            base_url=base_url,
                            headers=headers,
                            worker_id=worker_id,
                        )
                        handled = True
            except httpx.HTTPError as error:
                logger.warning("Evidence control-plane request failed: %s", error)
                if once:
                    return 1
            if once:
                return 0
            if not handled:
                time.sleep(settings.poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Index and search completed evidence clips.")
    parser.add_argument("--once", action="store_true", help="Handle at most one job")
    args = parser.parse_args()
    try:
        settings = get_settings()
        labs_settings = ArtaeLabsSettings()
    except ValidationError as error:
        logging.basicConfig(level=logging.ERROR)
        logger.error("Invalid evidence-worker configuration:\n%s", error)
        return 2
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        return run_worker(settings, labs_settings, once=args.once)
    except EvidenceWorkerError as error:
        logger.error("Evidence worker configuration error: %s", error)
        return 2
    except KeyboardInterrupt:
        logger.info("Evidence worker interrupted")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
