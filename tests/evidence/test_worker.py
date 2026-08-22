import json
from pathlib import Path
from types import SimpleNamespace

import httpx
from video_intelligence_artae.client import ArtaeLabsRequestError
from video_intelligence_evidence.worker import (
    IndexAssignment,
    SearchAssignment,
    process_index,
    process_search,
)


class SuccessfulLabs:
    uploaded: bytes | None = None

    def upload_video(self, *, index_id: str, video_path: Path, title: str):
        assert index_id == "idx-1"
        assert title == "Camera - person"
        self.uploaded = video_path.read_bytes()
        return SimpleNamespace(id="video-1")

    def wait_until_ready(self, video_id: str):
        assert video_id == "video-1"
        return SimpleNamespace(id="video-1", index_id="idx-1")

    def search(self, *, index_id: str, query: str, limit: int):
        assert (index_id, query, limit) == ("idx-1", "person near door", 5)
        hit = SimpleNamespace(
            video_id="video-1",
            time_start=1.0,
            time_end=3.5,
            similarity=0.92,
            summary="Person near the door",
            audio_description=None,
            transcript_chunk=None,
        )
        return SimpleNamespace(latency_ms=14, results=[hit])


def test_index_job_downloads_clip_and_reports_provider_ids() -> None:
    reports: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=b"video-bytes")
        reports.append(json.loads(request.content))
        return httpx.Response(200, json={})

    labs = SuccessfulLabs()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        process_index(
            IndexAssignment(
                asset_id="asset-1",
                event_id="event-1",
                title="Camera - person",
                duration_seconds=4,
            ),
            http=client,
            labs=labs,  # type: ignore[arg-type]
            labs_index_id="idx-1",
            base_url="https://control.test",
            headers={"X-Agent-Key": "secret"},
            worker_id="worker-1",
        )

    assert labs.uploaded == b"video-bytes"
    assert reports == [
        {
            "worker_id": "worker-1",
            "status": "ready",
            "external_index_id": "idx-1",
            "external_video_id": "video-1",
        }
    ]


def test_http_501_is_reported_as_unavailable() -> None:
    reports: list[dict] = []

    class UnavailableLabs(SuccessfulLabs):
        def upload_video(self, **kwargs):
            raise ArtaeLabsRequestError("Artae Labs returned HTTP 501: internal only")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=b"video-bytes")
        reports.append(json.loads(request.content))
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        process_index(
            IndexAssignment(
                asset_id="asset-1",
                event_id="event-1",
                title="Camera - person",
                duration_seconds=4,
            ),
            http=client,
            labs=UnavailableLabs(),  # type: ignore[arg-type]
            labs_index_id="idx-1",
            base_url="https://control.test",
            headers={},
            worker_id="worker-1",
        )

    assert reports[0]["status"] == "unavailable"
    assert "501" in reports[0]["error"]


def test_search_job_reports_timecoded_hits() -> None:
    reports: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        reports.append(json.loads(request.content))
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        process_search(
            SearchAssignment(
                search_id="search-1",
                query="person near door",
                camera_id=None,
                limit=5,
            ),
            http=client,
            labs=SuccessfulLabs(),  # type: ignore[arg-type]
            labs_index_id="idx-1",
            base_url="https://control.test",
            headers={},
            worker_id="worker-1",
        )

    assert reports[0]["status"] == "completed"
    assert reports[0]["results"][0]["time_start"] == 1.0
    assert reports[0]["results"][0]["similarity"] == 0.92
