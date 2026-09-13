import base64
import io
import uuid
from datetime import datetime, timedelta, timezone

from PIL import Image
from video_intelligence_api.browser_vision import VisualDecision, decode_frame
from video_intelligence_api.routes import browser_sessions


def frame():
    out = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(out, format="JPEG")
    return {"at_seconds": 4, "jpeg": base64.b64encode(out.getvalue()).decode()}


def custom_session(client):
    response = client.post(
        "/api/v1/browser-sessions",
        json={
            "id": str(uuid.uuid4()),
            "name": "Visual test",
            "job": "custom",
            "prompt": "A red box is visible",
        },
    )
    assert response.status_code == 200, response.text
    client.app.state.settings.strands_enabled = True
    return response.json()["id"]


def test_real_model_result_creates_account_alert_with_durable_evidence_request(
    api_client, monkeypatch
):
    camera = custom_session(api_client)
    calls = []

    def inspect(*args):
        calls.append(args)
        return VisualDecision(status="match", summary="A red box is visible."), {
            "inputTokens": 230
        }

    async def no_coordinator(*args, **kwargs):
        return None

    monkeypatch.setattr(browser_sessions, "inspect_frames", inspect)
    monkeypatch.setattr(browser_sessions, "coordinate_incident", no_coordinator)
    payload = {"id": str(uuid.uuid4()), "frames": [frame()]}
    path = f"/api/v1/browser-sessions/{camera}/analyze"
    response = api_client.post(path, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["event"]["details"]["source"] == "bedrock_vision"
    assert body["event"]["details"]["evidence"]["status"] == "awaiting_recording"
    assert body["event"]["details"]["requires_human"] is True
    assert "jpeg" not in str(body)
    assert api_client.post(path, json=payload).json() == body
    assert len(calls) == 1
    assert len(api_client.get("/api/v1/alerts").json()) == 1
    history = api_client.get(f"/api/v1/browser-sessions/{camera}/events")
    assert history.status_code == 200
    assert history.json()[0]["source_event_id"] == body["event"]["source_event_id"]
    assert history.json()[0]["verification_status"] == "uncertain"
    # Keep the general confirmed feed's safety boundary unchanged.
    assert api_client.get(f"/api/v1/events?camera_id={camera}").json() == []
    from video_intelligence_api.auth import Actor, get_current_actor
    from video_intelligence_api.models import OrganizationRole

    async def other_actor():
        return Actor(
            subject="other",
            organization_id=str(uuid.uuid4()),
            role=OrganizationRole.OWNER,
            issuer="test",
        )

    api_client.app.dependency_overrides[get_current_actor] = other_actor
    try:
        assert (
            api_client.get(f"/api/v1/browser-sessions/{camera}/events").status_code
            == 404
        )
    finally:
        api_client.app.dependency_overrides.clear()
    assert (
        api_client.post(path, json={**payload, "id": str(uuid.uuid4())}).status_code
        == 429
    )
    # A browser cannot bypass the visual model and invent a custom detection.
    assert (
        api_client.post(
            f"/api/v1/browser-sessions/{camera}/events",
            json={
                "id": str(uuid.uuid4()),
                "at_seconds": 4,
                "landmark_visibility": 0.99,
            },
        ).status_code
        == 422
    )


def test_negative_and_unavailable_models_never_fabricate_alerts(
    api_client, monkeypatch
):
    camera = custom_session(api_client)
    monkeypatch.setattr(
        browser_sessions,
        "inspect_frames",
        lambda *_: (
            VisualDecision(status="no_match", summary="No red box visible."),
            {},
        ),
    )
    response = api_client.post(
        f"/api/v1/browser-sessions/{camera}/analyze",
        json={"id": str(uuid.uuid4()), "frames": [frame()]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["event"] is None
    assert api_client.get("/api/v1/alerts").json() == []
    second = custom_session(api_client)

    def unavailable(*_):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(browser_sessions, "inspect_frames", unavailable)
    response = api_client.post(
        f"/api/v1/browser-sessions/{second}/analyze",
        json={"id": str(uuid.uuid4()), "frames": [frame()]},
    )
    assert response.status_code == 503
    assert api_client.get("/api/v1/alerts").json() == []


def test_invalid_frames_and_empty_jobs_rejected_before_paid_inference(api_client):
    assert (
        api_client.post(
            "/api/v1/browser-sessions",
            json={"id": str(uuid.uuid4()), "name": "Bad", "job": "custom"},
        ).status_code
        == 422
    )
    camera = custom_session(api_client)
    assert (
        api_client.post(
            f"/api/v1/browser-sessions/{camera}/analyze",
            json={
                "id": str(uuid.uuid4()),
                "frames": [{"at_seconds": 0, "jpeg": "x" * 100}],
            },
        ).status_code
        == 422
    )
    assert decode_frame(frame()["jpeg"]).startswith(b"\xff\xd8")


def test_custom_job_waits_for_configured_matching_checks(api_client, monkeypatch):
    response = api_client.post(
        "/api/v1/browser-sessions",
        json={
            "id": str(uuid.uuid4()),
            "name": "Printer watch",
            "job": "custom",
            "prompt": "Visible stringing around the print",
            "check_interval_seconds": 5,
            "confirmation_count": 2,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["confirmation_count"] == 2
    camera = response.json()["id"]
    api_client.app.state.settings.strands_enabled = True
    monkeypatch.setattr(
        browser_sessions,
        "inspect_frames",
        lambda *_: (
            VisualDecision(status="match", summary="Stringing is visible."),
            {},
        ),
    )

    async def no_coordinator(*args, **kwargs):
        return None

    monkeypatch.setattr(browser_sessions, "coordinate_incident", no_coordinator)
    moment = datetime(2026, 9, 12, tzinfo=timezone.utc)

    def advancing_now():
        nonlocal moment
        moment += timedelta(seconds=4)
        return moment

    monkeypatch.setattr(browser_sessions, "utc_now", advancing_now)
    path = f"/api/v1/browser-sessions/{camera}/analyze"
    first = api_client.post(path, json={"id": str(uuid.uuid4()), "frames": [frame()]})
    assert first.status_code == 200, first.text
    assert first.json()["match_streak"] == 1
    assert first.json()["confirmed"] is False
    assert first.json()["event"] is None
    second_frame = {**frame(), "at_seconds": 9}
    second = api_client.post(
        path, json={"id": str(uuid.uuid4()), "frames": [second_frame]}
    )
    assert second.status_code == 200, second.text
    assert second.json()["confirmed"] is True
    assert second.json()["event"] is not None
    assert len(api_client.get("/api/v1/alerts").json()) == 1


def test_public_demo_analyzes_storyboard_without_account_storage(
    api_client, monkeypatch
):
    api_client.app.state.settings.strands_enabled = True
    browser_sessions._public_demo_starts.clear()
    browser_sessions._public_demo_checks.clear()
    monkeypatch.setattr(
        browser_sessions,
        "inspect_frames",
        lambda *_: (
            VisualDecision(
                status="match",
                summary="Loose filament is visible around the print.",
                matched_frame_index=1,
            ),
            {"inputTokens": 300},
        ),
    )

    class DemoRun:
        def model_dump(self, **_kwargs):
            return {
                "status": "completed",
                "summary": "Evidence and notification prepared.",
                "tools_invoked": ["preserve_evidence", "notify_responder"],
            }

    async def coordinator(*_args, **_kwargs):
        return DemoRun()

    monkeypatch.setattr(browser_sessions, "coordinate_incident", coordinator)
    started = api_client.post(
        "/api/v1/browser-sessions/public-demo",
        json={
            "prompt": "Alert me when the 3D print has loose filament",
        },
    )
    assert started.status_code == 200, started.text
    token = started.json()["token"]
    early = {**frame(), "at_seconds": 2}
    late = {**frame(), "at_seconds": 42}
    result = api_client.post(
        "/api/v1/browser-sessions/public-demo/analyze",
        json={
            "token": token,
            "frames": [early, late],
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "match"
    assert result.json()["matched_frame_index"] == 1
    assert result.json()["event"]["details"]["strands_agent"]["status"] == "completed"
    assert result.json()["checks_remaining"] == 3
    assert api_client.get("/api/v1/alerts").json() == []
    rejected = api_client.post(
        "/api/v1/browser-sessions/public-demo/analyze",
        json={
            "token": token + "tampered",
            "frames": [early],
        },
    )
    assert rejected.status_code == 401
