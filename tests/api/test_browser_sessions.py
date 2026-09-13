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


def test_named_agent_persists_and_can_start_independent_runs(api_client):
    payload = {"id": str(uuid.uuid4()), "name": "Hallway safety", "job": "fall", "prompt": ""}
    path = "/api/v1/browser-sessions/jobs"
    saved = api_client.post(path, json=payload)
    assert saved.status_code == 200, saved.text
    assert api_client.post(path, json=payload).json() == saved.json()
    assert api_client.get(path).json() == [payload]
    assert api_client.get("/api/v1/browser-sessions").json() == []
    for _ in range(2):
        run = api_client.post("/api/v1/browser-sessions", json={
            "id": str(uuid.uuid4()), "name": "Hallway run", "job": "fall", "agent_id": payload["id"],
        })
        assert run.status_code == 200
        assert run.json()["agent_id"] == payload["id"]
    assert len(api_client.get("/api/v1/browser-sessions").json()) == 2
    mismatch = api_client.post("/api/v1/browser-sessions", json={
        "id": str(uuid.uuid4()), "name": "Wrong job", "job": "presence", "agent_id": payload["id"],
    })
    assert mismatch.status_code == 409


def test_saved_agents_are_private_and_cannot_execute_arbitrary_jobs(api_client):
    payload = {"id": str(uuid.uuid4()), "name": "My job", "job": "fall"}
    path = "/api/v1/browser-sessions/jobs"
    assert api_client.post(path, json=payload).status_code == 200
    assert api_client.post(path, json={**payload, "job": "open_gate"}).status_code == 422

    async def other_actor():
        return Actor(subject="other", organization_id=str(uuid.uuid4()), role=OrganizationRole.OWNER, issuer="test")

    api_client.app.dependency_overrides[get_current_actor] = other_actor
    try:
        assert api_client.get(path).json() == []
        assert api_client.post(path, json=payload).status_code == 404
        assert api_client.post("/api/v1/browser-sessions", json={
            "id": str(uuid.uuid4()), "name": "Other account", "job": "fall", "agent_id": payload["id"],
        }).status_code == 404
    finally:
        api_client.app.dependency_overrides.clear()


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


def test_caregiver_sms_fails_closed_when_provider_is_disabled(api_client):
    api_client.app.state.settings.sms_enabled = False
    response = api_client.post(
        "/api/v1/browser-sessions",
        json={
            "id": str(uuid.uuid4()),
            "name": "Senior safety",
            "job": "fall",
            "caregiver_phone": "+12065550142",
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "AWS caregiver SMS is not enabled for this deployment"


def test_browser_recordings_are_seekable_catalog_entries(api_client):
    s = create(api_client)
    observation = api_client.post(f"/api/v1/browser-sessions/{s['id']}/events", json={
        "id": str(uuid.uuid4()), "at_seconds": 2, "landmark_visibility": .8,
    }).json()
    assert observation["details"]["evidence"]["status"] == "awaiting_recording"
    assert observation["details"]["notification"]["channel"] == "in_app"
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
    saved = api_client.get(f"/api/v1/events?camera_id={s['id']}").json()[0]
    assert saved["details"]["evidence"]["status"] == "available"
    assert saved["details"]["evidence"]["recording_ids"] == [clip_id]
    # Upload retries must not erase a human's decision or duplicate evidence.
    api_client.patch(f"/api/v1/browser-sessions/{s['id']}/events/{saved['source_event_id']}/review",
                     json={"outcome": "resolved"})
    retry = api_client.put(f"{path}/{clip_id}/content", content=b"test video bytes",
                          headers={"Content-Type": "video/webm"})
    assert retry.status_code == 200
    saved = api_client.get(f"/api/v1/events?camera_id={s['id']}").json()[0]
    assert saved["details"]["review"]["status"] == "resolved"
    assert saved["details"]["evidence"]["recording_ids"] == [clip_id]
    # Events arriving after an upload get the same concrete evidence references.
    late = api_client.post(f"/api/v1/browser-sessions/{s['id']}/events", json={
        "id": str(uuid.uuid4()), "at_seconds": 3, "landmark_visibility": .8,
    }).json()
    assert late["details"]["evidence"]["recording_ids"] == [clip_id]


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


def test_incident_review_survives_reload_and_closes_existing_alert(api_client):
    s = create(api_client, "fall")
    event_id = str(uuid.uuid4())
    path = f"/api/v1/browser-sessions/{s['id']}/events"
    api_client.post(path, json={"id": event_id, "at_seconds": 6.6, "landmark_visibility": .8})
    review_path = f"{path}/{event_id}/review"
    acknowledged = api_client.patch(review_path, json={"outcome": "acknowledged"})
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["details"]["review"]["status"] == "acknowledged"
    closed = api_client.patch(review_path, json={"outcome": "false_alarm"})
    assert closed.status_code == 200, closed.text
    details = closed.json()["details"]
    assert details["review"]["status"] == "resolved"
    assert details["review"]["outcome"] == "false_alarm"
    assert details["independently_verified"] is False
    assert details["requires_human"] is True
    assert len(details["review_history"]) == 2
    # A lost response/retry does not duplicate review history or replace the operator.
    assert api_client.patch(review_path, json={"outcome": "false_alarm"}).json()["details"] == details
    assert api_client.patch(review_path, json={"outcome": "acknowledged"}).status_code == 409
    reloaded = api_client.get(f"/api/v1/events?camera_id={s['id']}").json()[0]
    assert reloaded["details"]["review"] == details["review"]
    assert api_client.get("/api/v1/alerts").json()[0]["status"] == "resolved"


def test_review_rejects_other_session_tenant_and_invalid_outcome(api_client):
    s, other_session = create(api_client), create(api_client)
    event_id = str(uuid.uuid4())
    api_client.post(f"/api/v1/browser-sessions/{s['id']}/events", json={
        "id": event_id, "at_seconds": 2, "landmark_visibility": .9,
    })
    path = f"/api/v1/browser-sessions/{s['id']}/events/{event_id}/review"
    assert api_client.patch(path, json={"outcome": "call_police"}).status_code == 422
    assert api_client.patch(path.replace(s['id'], other_session['id']), json={"outcome": "resolved"}).status_code == 404

    async def other_actor():
        return Actor(subject="other", organization_id=str(uuid.uuid4()), role=OrganizationRole.OWNER, issuer="test")

    api_client.app.dependency_overrides[get_current_actor] = other_actor
    try:
        assert api_client.patch(path, json={"outcome": "resolved"}).status_code == 404
    finally:
        api_client.app.dependency_overrides.clear()
