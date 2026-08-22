import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from video_intelligence_artae.client import (
    ArtaeLabsClient,
    ArtaeLabsIndexingError,
)
from video_intelligence_artae.config import ArtaeLabsSettings


def make_settings() -> ArtaeLabsSettings:
    return ArtaeLabsSettings(
        api_key=SecretStr("test-secret"),
        base_url="https://labs.test/api/v1/labs",
        poll_interval_seconds=0.01,
        indexing_timeout_seconds=1,
    )


def test_empty_api_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ArtaeLabsSettings(api_key="")


def test_upload_and_search_follow_checked_in_labs_contract(tmp_path: Path) -> None:
    video_bytes = b"small-video-payload"
    video_path = tmp_path / "camera.mp4"
    video_path.write_bytes(video_bytes)
    api_requests: list[httpx.Request] = []
    upload_requests: list[httpx.Request] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        api_requests.append(request)
        assert request.headers["X-API-Key"] == "test-secret"
        route = request.url.path
        if route.endswith("/indexes"):
            return httpx.Response(
                201,
                json={"id": "idx-1", "name": "Camera clips", "description": None},
            )
        if route.endswith("/indexes/idx-1/upload-init"):
            body = json.loads(request.content)
            assert body == {
                "filename": "camera.mp4",
                "content_type": "video/mp4",
                "size_bytes": len(video_bytes),
            }
            return httpx.Response(
                200,
                json={
                    "upload_url": "https://uploads.test/presigned/video",
                    "upload_key": "labs/idx-1/camera.mp4",
                    "expires_in_seconds": 900,
                },
            )
        if route.endswith("/indexes/idx-1/upload-complete"):
            return httpx.Response(
                202,
                json={"id": "vid-1", "index_id": "idx-1", "status": "pending"},
            )
        if route.endswith("/search"):
            body = json.loads(request.content)
            assert body["query"] == "person by a loading door"
            return httpx.Response(
                200,
                json={
                    "query": body["query"],
                    "count": 1,
                    "latency_ms": 12,
                    "results": [
                        {
                            "shot_id": "shot-1",
                            "video_id": "vid-1",
                            "shot_index": 0,
                            "time_start": 1.0,
                            "time_end": 4.0,
                            "duration_s": 3.0,
                            "similarity": 0.91,
                            "semantic_events": None,
                        }
                    ],
                },
            )
        raise AssertionError(f"Unexpected API request: {request.method} {route}")

    def upload_handler(request: httpx.Request) -> httpx.Response:
        upload_requests.append(request)
        assert "X-API-Key" not in request.headers
        assert request.read() == video_bytes
        return httpx.Response(200)

    with ArtaeLabsClient(
        make_settings(),
        api_transport=httpx.MockTransport(api_handler),
        upload_transport=httpx.MockTransport(upload_handler),
    ) as client:
        index = client.create_index("Camera clips")
        video = client.upload_video(index_id=index.id, video_path=video_path)
        results = client.search(index_id=index.id, query="person by a loading door")

    assert index.id == "idx-1"
    assert video.id == "vid-1"
    assert results.results[0].time_start == 1.0
    assert len(api_requests) == 4
    assert len(upload_requests) == 1


def test_wait_until_ready_polls_until_completed() -> None:
    statuses = iter(
        [
            {
                "id": "vid-1",
                "index_id": "idx-1",
                "status": "processing",
                "status_progress": 30,
            },
            {
                "id": "vid-1",
                "index_id": "idx-1",
                "status": "completed",
                "status_progress": 100,
            },
        ]
    )

    def api_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/videos/vid-1")
        return httpx.Response(200, json=next(statuses))

    with ArtaeLabsClient(
        make_settings(),
        api_transport=httpx.MockTransport(api_handler),
    ) as client:
        video = client.wait_until_ready("vid-1", poll_interval_seconds=0)

    assert video.status == "completed"


def test_wait_until_ready_surfaces_indexing_failure() -> None:
    def api_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "vid-1",
                "index_id": "idx-1",
                "status": "failed",
                "error_message": "decoder failed",
            },
        )

    with (
        ArtaeLabsClient(
            make_settings(),
            api_transport=httpx.MockTransport(api_handler),
        ) as client,
        pytest.raises(ArtaeLabsIndexingError, match="decoder failed"),
    ):
        client.wait_until_ready("vid-1", poll_interval_seconds=0)
