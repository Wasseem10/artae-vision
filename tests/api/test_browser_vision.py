import base64
import io
import uuid

from PIL import Image
from video_intelligence_api.browser_vision import VisualDecision, decode_frame
from video_intelligence_api.routes import browser_sessions


def frame():
    out = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(out, format="JPEG")
    return {"at_seconds": 4, "jpeg": base64.b64encode(out.getvalue()).decode()}


def custom_session(client):
    response = client.post("/api/v1/browser-sessions", json={
        "id": str(uuid.uuid4()), "name": "Visual test", "job": "custom", "prompt": "A red box is visible",
    })
    assert response.status_code == 200, response.text
    client.app.state.settings.strands_enabled = True
    return response.json()["id"]


def test_real_model_result_creates_account_alert_with_durable_evidence_request(api_client, monkeypatch):
    camera = custom_session(api_client)
    calls = []
    def inspect(*args):
        calls.append(args)
        return VisualDecision(status="match", summary="A red box is visible."), {"inputTokens": 230}
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
    assert api_client.post(path, json={**payload, "id": str(uuid.uuid4())}).status_code == 429
    # A browser cannot bypass the visual model and invent a custom detection.
    assert api_client.post(f"/api/v1/browser-sessions/{camera}/events", json={
        "id": str(uuid.uuid4()), "at_seconds": 4, "landmark_visibility": .99,
    }).status_code == 422


def test_negative_and_unavailable_models_never_fabricate_alerts(api_client, monkeypatch):
    camera = custom_session(api_client)
    monkeypatch.setattr(browser_sessions, "inspect_frames", lambda *_: (VisualDecision(status="no_match", summary="No red box visible."), {}))
    response = api_client.post(f"/api/v1/browser-sessions/{camera}/analyze", json={"id": str(uuid.uuid4()), "frames": [frame()]})
    assert response.status_code == 200, response.text
    assert response.json()["event"] is None
    assert api_client.get("/api/v1/alerts").json() == []
    second = custom_session(api_client)
    def unavailable(*_): raise RuntimeError("provider unavailable")
    monkeypatch.setattr(browser_sessions, "inspect_frames", unavailable)
    response = api_client.post(f"/api/v1/browser-sessions/{second}/analyze", json={"id": str(uuid.uuid4()), "frames": [frame()]})
    assert response.status_code == 503
    assert api_client.get("/api/v1/alerts").json() == []


def test_invalid_frames_and_empty_jobs_rejected_before_paid_inference(api_client):
    assert api_client.post("/api/v1/browser-sessions", json={"id": str(uuid.uuid4()), "name": "Bad", "job": "custom"}).status_code == 422
    camera = custom_session(api_client)
    assert api_client.post(f"/api/v1/browser-sessions/{camera}/analyze", json={
        "id": str(uuid.uuid4()), "frames": [{"at_seconds": 0, "jpeg": "x" * 100}],
    }).status_code == 422
    assert decode_frame(frame()["jpeg"]).startswith(b"\xff\xd8")
