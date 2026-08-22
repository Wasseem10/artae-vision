import json
from pathlib import Path

import httpx
from video_intelligence_inference.actions import (
    BackgroundEvidenceUploader,
    BackgroundWebhookDispatcher,
)
from video_intelligence_inference.events import EventRecord
from video_intelligence_inference.outbox import DurableJsonOutbox
from video_intelligence_inference.rules import RuleMatch


def make_event(tmp_path: Path) -> EventRecord:
    return EventRecord.create(
        RuleMatch(
            rule_id="person-dwell",
            track_id=7,
            object_class="person",
            zone_name="loading-zone",
            entered_at_seconds=0,
            occurred_at_seconds=5,
            dwell_seconds=5,
            confidence=0.91,
        ),
        camera_id="camera-1",
        clip_path=tmp_path / "event.mp4",
        event_id="event-1",
    )


def test_webhook_delivery_runs_through_background_dispatcher(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["X-Agent-Key"] == "agent-secret"
        return httpx.Response(202)

    with BackgroundWebhookDispatcher(
        "https://actions.test/events",
        transport=httpx.MockTransport(handler),
        headers={"X-Agent-Key": "agent-secret"},
    ) as dispatcher:
        dispatcher.submit(make_event(tmp_path))

    assert len(requests) == 1
    assert requests[0].url == "https://actions.test/events"
    payload = json.loads(requests[0].content)
    assert payload["id"] == "event-1"
    assert payload["event_type"] == "object_dwell"


def test_completed_evidence_upload_retries_until_event_exists(tmp_path: Path) -> None:
    clip = tmp_path / "event.mp4"
    clip.write_bytes(b"completed-video")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["X-Agent-Key"] == "agent-secret"
        assert request.headers["X-Evidence-Duration-Seconds"] == "2.500"
        assert request.read() == b"completed-video"
        return httpx.Response(404 if len(requests) == 1 else 200)

    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        agent_key="agent-secret",
        transport=httpx.MockTransport(handler),
        transcode_clip=False,
    ) as uploader:
        uploader.submit("event-1", clip, duration_seconds=2.5)

    assert len(requests) == 2
    assert requests[-1].url.path == "/api/v1/agent/events/event-1/clip"


def test_control_plane_events_survive_disconnect_and_sync_on_restart(
    tmp_path: Path,
) -> None:
    outbox_path = tmp_path / "offline" / "events.db"

    def unavailable(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agent/events"
        return httpx.Response(503)

    with BackgroundWebhookDispatcher(
        "https://control.test/api/v1/agent/events",
        transport=httpx.MockTransport(unavailable),
        outbox_path=outbox_path,
    ) as dispatcher:
        dispatcher.submit(make_event(tmp_path))

    outbox = DurableJsonOutbox(outbox_path)
    assert outbox.count() == 1
    assert outbox.pending()[0].attempts == 1

    delivered: list[dict] = []

    def available(request: httpx.Request) -> httpx.Response:
        delivered.append(json.loads(request.content))
        return httpx.Response(201)

    with BackgroundWebhookDispatcher(
        "https://control.test/api/v1/agent/events",
        transport=httpx.MockTransport(available),
        outbox_path=outbox_path,
    ):
        pass

    assert delivered[0]["id"] == "event-1"
    assert outbox.count() == 0
