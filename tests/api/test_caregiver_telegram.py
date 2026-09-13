import asyncio
import base64
import io
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
from PIL import Image
from video_intelligence_api.browser_vision import VisualDecision
from video_intelligence_api.routes import browser_sessions
from video_intelligence_api.telegram import send_telegram_alert


def test_message_includes_clip_and_does_not_retry_or_leak_token():
    def handler(request):
        body = json.loads(request.content)
        assert (
            body["reply_markup"]["inline_keyboard"][0][0]["url"]
            == "https://example.org/clip"
        )
        assert "parse_mode" not in body
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    receipt = asyncio.run(
        send_telegram_alert(
            "123:secret",
            "1",
            "Possible fall",
            clip_url="https://example.org/clip",
            transport=httpx.MockTransport(handler),
        )
    )
    assert receipt["status"] == "sent"
    assert "secret" not in str(receipt)

    def timeout(request):
        raise httpx.ReadTimeout("secret URL")

    failed = asyncio.run(
        send_telegram_alert(
            "123:secret", "1", "Test", transport=httpx.MockTransport(timeout)
        )
    )
    assert failed["status"] == "unknown"
    assert "secret" not in str(failed)


def test_owned_clip_delivery_is_private_and_idempotent(api_client, monkeypatch):
    connector = api_client.post(
        "/api/v1/connectors",
        json={
            "name": "Caregiver",
            "connector_type": "telegram",
            "credential": "123:secret-token",
            "configuration": {"chat_id": "123"},
            "scopes": ["notifications:write"],
        },
    )
    assert connector.status_code == 201, connector.text
    cid = connector.json()["id"]
    start = datetime.now(UTC)
    camera = api_client.post(
        "/api/v1/browser-sessions",
        json={
            "id": str(uuid.uuid4()),
            "name": "Care",
            "job": "custom",
            "prompt": "Person on floor",
            "started_at": start.isoformat(),
            "telegram_connector_id": cid,
        },
    ).json()["id"]
    api_client.app.state.settings.strands_enabled = True
    monkeypatch.setattr(
        browser_sessions,
        "inspect_frames",
        lambda *_: (
            VisualDecision(
                status="match", summary="Possible fall.", matched_frame_index=0
            ),
            {},
        ),
    )

    async def coordinate(*args, **kwargs):
        return None

    monkeypatch.setattr(browser_sessions, "coordinate_incident", coordinate)
    image = io.BytesIO()
    Image.new("RGB", (64, 64)).save(image, format="JPEG")
    eid = str(uuid.uuid4())
    analyzed = api_client.post(
        f"/api/v1/browser-sessions/{camera}/analyze",
        json={
            "id": eid,
            "frames": [
                {"at_seconds": 5, "jpeg": base64.b64encode(image.getvalue()).decode()}
            ],
        },
    )
    assert analyzed.status_code == 200, analyzed.text
    rid = str(uuid.uuid4())
    path = f"/api/v1/browser-sessions/{camera}/recordings"
    report = api_client.post(
        path,
        json={
            "segment_id": rid,
            "source_key": rid,
            "source_filename": "clip.webm",
            "started_at": start.isoformat(),
            "ended_at": (start + timedelta(seconds=12)).isoformat(),
            "duration_seconds": 12,
            "frame_count": 240,
            "fps": 20,
            "width": 640,
            "height": 360,
        },
    )
    assert report.status_code == 200, report.text
    assert (
        api_client.put(
            f"{path}/{rid}/content",
            content=b"test clip",
            headers={"Content-Type": "video/webm"},
        ).status_code
        == 200
    )
    calls = []

    async def send(token, chat, text, **kwargs):
        calls.append(text)
        return {
            "status": "sent",
            "provider": "telegram",
            "clip_url": kwargs.get("clip_url"),
        }

    monkeypatch.setattr(browser_sessions, "send_telegram_alert", send)
    route = f"/api/v1/browser-sessions/{camera}/events/{eid}/telegram"
    assert (
        api_client.post(route, json={"recording_id": str(uuid.uuid4())}).status_code
        == 409
    )
    result = api_client.post(route, json={"recording_id": rid})
    assert result.status_code == 200, result.text
    url = result.json()["clip_url"]
    assert int(parse_qs(urlparse(url).query)["expires"][0]) > time.time() + 86000
    assert api_client.get(url).content == b"test clip"
    assert api_client.get(url.replace("signature=", "signature=0")).status_code in (
        403,
        422,
    )
    assert api_client.post(route, json={"recording_id": rid}).json() == result.json()
    assert len(calls) == 1
    assert "00:00:05" in calls[0] and "24 hours" in calls[0]
    test_path = f"/api/v1/browser-sessions/telegram/{cid}/test"
    assert api_client.post(test_path).status_code == 200
    assert api_client.post(test_path).status_code == 429


def test_cannot_select_another_workspaces_connector(api_client):
    result = api_client.post(
        "/api/v1/browser-sessions",
        json={
            "id": str(uuid.uuid4()),
            "name": "No",
            "job": "fall",
            "telegram_connector_id": str(uuid.uuid4()),
        },
    )
    assert result.status_code == 404
