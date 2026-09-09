import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.engine import Engine
from video_intelligence_api.auth import Actor, get_current_actor
from video_intelligence_api.models import OrganizationRole


@pytest.fixture(autouse=True)
def enforce_sqlite_foreign_keys():
    def enable(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    sqlalchemy_event.listen(Engine, "connect", enable)
    yield
    sqlalchemy_event.remove(Engine, "connect", enable)


def create(client, job="presence"):
    response = client.post(
        "/api/v1/browser-sessions",
        json={
            "id": str(uuid.uuid4()),
            "name": "Browser test",
            "job": job,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_browser_session_creates_durable_alert_without_edge_service(api_client):
    s = create(api_client)
    payload = {"id": str(uuid.uuid4()), "at_seconds": 2, "landmark_visibility": 0.9}
    path = f"/api/v1/browser-sessions/{s['id']}/events"
    response = api_client.post(path, json=payload)
    assert response.status_code == 200, response.text
    event = response.json()
    assert event["details"]["independently_verified"] is False
    assert api_client.post(path, json=payload).json()["id"] == event["id"]
    assert len(api_client.get(f"/api/v1/events?camera_id={s['id']}").json()) == 1
    assert len(api_client.get("/api/v1/alerts").json()) == 1
    assert api_client.get("/api/v1/browser-sessions").json()[0]["id"] == s["id"]


def test_browser_session_keeps_recording_time_origin_across_devices(api_client):
    started = datetime.now(UTC) - timedelta(minutes=2)
    response = api_client.post(
        "/api/v1/browser-sessions",
        json={
            "id": str(uuid.uuid4()),
            "name": "Time origin",
            "job": "fall",
            "started_at": started.isoformat(),
        },
    )
    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["created_at"]) == started
    listed = api_client.get("/api/v1/browser-sessions").json()[0]
    assert datetime.fromisoformat(listed["created_at"]) == started


def test_browser_recordings_are_seekable_catalog_entries(api_client):
    s = create(api_client)
    start = datetime.now(UTC)
    clip_id = str(uuid.uuid4())
    path = f"/api/v1/browser-sessions/{s['id']}/recordings"
    response = api_client.post(
        path,
        json={
            "segment_id": clip_id,
            "source_key": clip_id,
            "source_filename": "clip.webm",
            "started_at": start.isoformat(),
            "ended_at": (start + timedelta(seconds=5)).isoformat(),
            "duration_seconds": 5,
            "frame_count": 100,
            "fps": 20,
            "width": 640,
            "height": 480,
        },
    )
    assert response.status_code == 200, response.text
    response = api_client.put(
        f"{path}/{clip_id}/content",
        content=b"test video bytes",
        headers={"Content-Type": "video/webm"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["content_url"]
    assert len(api_client.get(f"/api/v1/cameras/{s['id']}/recordings").json()) == 1


def test_browser_observations_cannot_use_an_edge_camera(api_client):
    camera = api_client.post(
        "/api/v1/cameras", json={"name": "Edge", "source_uri": "webcam:0"}
    ).json()
    response = api_client.post(
        f"/api/v1/browser-sessions/{camera['id']}/events",
        json={
            "id": str(uuid.uuid4()),
            "at_seconds": 2,
            "landmark_visibility": 0.9,
        },
    )
    assert response.status_code == 404


def test_browser_sessions_are_tenant_scoped(api_client):
    s = create(api_client)

    async def other_actor():
        return Actor(
            subject="other",
            organization_id=str(uuid.uuid4()),
            role=OrganizationRole.OWNER,
            issuer="test",
        )

    api_client.app.dependency_overrides[get_current_actor] = other_actor
    try:
        assert api_client.get("/api/v1/browser-sessions").json() == []
        response = api_client.post(
            f"/api/v1/browser-sessions/{s['id']}/events",
            json={
                "id": str(uuid.uuid4()),
                "at_seconds": 1,
                "landmark_visibility": 0.9,
            },
        )
        assert response.status_code == 404
    finally:
        api_client.app.dependency_overrides.clear()
