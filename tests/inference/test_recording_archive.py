import json
from dataclasses import asdict
from pathlib import Path

import httpx
from video_intelligence_inference.continuous_recording import SegmentManifest
from video_intelligence_inference.recording_archive import (
    BackgroundRecordingArchiveUploader,
)


def manifest() -> SegmentManifest:
    return SegmentManifest(
        segment_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        camera_id="camera-1",
        source_key="segment-0001",
        filename="segment-0001.mp4",
        started_at="2026-08-22T12:00:00+00:00",
        completed_at="2026-08-22T12:00:05+00:00",
        source_start_seconds=0,
        source_end_seconds=5,
        frame_count=150,
        fps=30,
        width=1920,
        height=1080,
    )


def test_recording_archive_spools_reports_and_uploads(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"id": manifest().segment_id})
        return httpx.Response(200, json={"size_bytes": len(b"video")})

    spool = tmp_path / "spool"
    with BackgroundRecordingArchiveUploader(
        "http://control.test/api/v1",
        enabled=True,
        headers={"X-Device-Token": "device-token"},
        spool_directory=spool,
        transport=httpx.MockTransport(handler),
    ) as uploader:
        uploader.submit(source, manifest())

    assert [request.method for request in requests] == ["POST", "PUT"]
    assert json.loads(requests[0].content)["frame_count"] == 150
    assert requests[1].content == b"video"
    assert requests[1].headers["X-Device-Token"] == "device-token"
    assert not list(spool.iterdir())


def test_recording_archive_recovers_spooled_segment_after_restart(
    tmp_path: Path,
) -> None:
    spool = tmp_path / "spool"
    spool.mkdir()
    pending = manifest()
    (spool / f"{pending.segment_id}.mp4").write_bytes(b"pending-video")
    (spool / f"{pending.segment_id}.json").write_text(json.dumps(asdict(pending)))
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200, json={"size_bytes": len(b"pending-video")})

    with BackgroundRecordingArchiveUploader(
        "http://control.test/api/v1",
        enabled=True,
        headers={},
        spool_directory=spool,
        transport=httpx.MockTransport(handler),
    ):
        pass

    assert methods == ["POST", "PUT"]
    assert not list(spool.iterdir())
