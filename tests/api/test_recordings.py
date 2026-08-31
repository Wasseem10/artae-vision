from urllib.parse import urlsplit

from fastapi.testclient import TestClient

AGENT_KEY = "test-agent-key-123456789"


def create_camera(client: TestClient) -> dict:
    return client.post(
        "/api/v1/cameras",
        json={"name": "archive-camera", "source_uri": "rtsp://camera.test/live"},
    ).json()


def report_segment(client: TestClient, camera_id: str) -> dict:
    response = client.post(
        f"/api/v1/agent/cameras/{camera_id}/recordings",
        json={
            "segment_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "source_key": "edge-segment-0001",
            "source_filename": "../../unsafe-name.mp4",
            "started_at": "2026-08-20T12:00:00Z",
            "ended_at": "2026-08-20T12:05:00Z",
            "duration_seconds": 300,
            "frame_count": 9000,
            "fps": 30,
            "width": 1920,
            "height": 1080,
        },
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert response.status_code == 200
    return response.json()


def test_edge_reports_archives_and_plays_recording_segment(
    api_client: TestClient,
) -> None:
    camera = create_camera(api_client)
    reported = report_segment(api_client, camera["id"])

    assert reported["status"] == "local_only"
    assert reported["source_filename"] == "unsafe-name.mp4"
    assert reported["content_url"] is None
    duplicate = report_segment(api_client, camera["id"])
    assert duplicate["id"] == reported["id"]

    video = b"video-segment-content"
    archived = api_client.put(
        f"/api/v1/agent/recordings/{reported['id']}/content",
        content=video,
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "video/mp4"},
    )
    assert archived.status_code == 200
    body = archived.json()
    assert body["status"] == "ready"
    assert body["size_bytes"] == len(video)
    assert len(body["sha256"]) == 64
    assert body["content_url"].startswith(
        f"/api/v1/recordings/{reported['id']}/content?"
    )

    playback_path = urlsplit(body["content_url"]).path
    playback_query = urlsplit(body["content_url"]).query
    playback = api_client.get(f"{playback_path}?{playback_query}")
    assert playback.status_code == 200
    assert playback.content == video

    listed = api_client.get(f"/api/v1/cameras/{camera['id']}/recordings").json()
    assert [item["id"] for item in listed] == [reported["id"]]


def test_legal_hold_blocks_retention_then_release_expires_content(
    api_client: TestClient,
) -> None:
    camera = create_camera(api_client)
    segment = report_segment(api_client, camera["id"])
    api_client.put(
        f"/api/v1/agent/recordings/{segment['id']}/content",
        content=b"held-video",
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "video/mp4"},
    )

    held = api_client.put(
        f"/api/v1/recordings/{segment['id']}/legal-hold",
        json={"enabled": True},
    )
    assert held.status_code == 200
    assert held.json()["legal_hold"] is True
    retained = api_client.post("/api/v1/recordings/retention/run").json()
    assert retained == {"expired_segments": 0, "deleted_bytes": 0}

    api_client.put(
        f"/api/v1/recordings/{segment['id']}/legal-hold",
        json={"enabled": False},
    )
    expired = api_client.post("/api/v1/recordings/retention/run").json()
    assert expired == {"expired_segments": 1, "deleted_bytes": len(b"held-video")}
    listed = api_client.get(f"/api/v1/cameras/{camera['id']}/recordings").json()
    assert listed[0]["status"] == "expired"
    assert listed[0]["content_url"] is None


def test_recording_upload_rejects_non_video_and_oversized_content(
    api_client: TestClient,
) -> None:
    camera = create_camera(api_client)
    segment = report_segment(api_client, camera["id"])

    wrong_type = api_client.put(
        f"/api/v1/agent/recordings/{segment['id']}/content",
        content=b"text",
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "text/plain"},
    )
    assert wrong_type.status_code == 415
    oversized = api_client.put(
        f"/api/v1/agent/recordings/{segment['id']}/content",
        content=b"x" * 1025,
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "video/mp4"},
    )
    assert oversized.status_code == 413


def test_upload_automatically_keeps_only_the_configured_camera_history(
    api_client: TestClient,
) -> None:
    camera = create_camera(api_client)
    segment_ids = [
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",
    ]
    starts = ["2026-08-20T12:00:00Z", "2026-08-20T12:30:00Z", "2026-08-20T13:00:00Z"]
    ends = ["2026-08-20T12:30:00Z", "2026-08-20T13:00:00Z", "2026-08-20T13:30:00Z"]

    for index, segment_id in enumerate(segment_ids):
        reported = api_client.post(
            f"/api/v1/agent/cameras/{camera['id']}/recordings",
            json={
                "segment_id": segment_id,
                "source_key": f"rolling-segment-{index}",
                "source_filename": f"rolling-segment-{index}.mp4",
                "started_at": starts[index],
                "ended_at": ends[index],
                "duration_seconds": 1800,
                "frame_count": 54000,
                "fps": 30,
                "width": 1280,
                "height": 720,
            },
            headers={"X-Agent-Key": AGENT_KEY},
        )
        assert reported.status_code == 200
        archived = api_client.put(
            f"/api/v1/agent/recordings/{segment_id}/content",
            content=f"video-{index}".encode(),
            headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "video/mp4"},
        )
        assert archived.status_code == 200

    listed = api_client.get(f"/api/v1/cameras/{camera['id']}/recordings?limit=250").json()
    by_id = {item["id"]: item for item in listed}
    assert by_id[segment_ids[0]]["status"] == "expired"
    assert by_id[segment_ids[0]]["content_url"] is None
    assert by_id[segment_ids[1]]["status"] == "ready"
    assert by_id[segment_ids[2]]["status"] == "ready"
    assert sum(
        item["duration_seconds"]
        for item in listed
        if item["status"] == "ready"
    ) == 3600
