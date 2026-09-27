import json
import sqlite3
import subprocess
import threading
import time
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


def test_durable_evidence_upload_survives_outage_and_restart(tmp_path: Path) -> None:
    clip = tmp_path / "event.mp4"
    clip.write_bytes(b"completed-video")
    outbox_path = tmp_path / "offline" / "evidence.db"
    failed = threading.Event()

    def unavailable(request: httpx.Request) -> httpx.Response:
        assert request.read() == b"completed-video"
        failed.set()
        return httpx.Response(503)

    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        transport=httpx.MockTransport(unavailable),
        transcode_clip=False,
        outbox_path=outbox_path,
        retry_interval_seconds=0.05,
    ) as uploader:
        uploader.submit("event-1", clip, duration_seconds=2.5)
        assert DurableJsonOutbox(outbox_path).count() == 1
        assert failed.wait(timeout=1)

    outbox = DurableJsonOutbox(outbox_path)
    assert outbox.count() == 1
    assert outbox.pending()[0].attempts == 1
    assert clip.read_bytes() == b"completed-video"
    uploaded = threading.Event()
    requests: list[bytes] = []

    def available(request: httpx.Request) -> httpx.Response:
        requests.append(request.read())
        uploaded.set()
        return httpx.Response(201)

    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        transport=httpx.MockTransport(available),
        transcode_clip=False,
        outbox_path=outbox_path,
        retry_interval_seconds=0.05,
    ):
        assert uploaded.wait(timeout=1)

    assert requests == [b"completed-video"]
    assert outbox.count() == 0
    assert clip.read_bytes() == b"completed-video"


def test_successful_evidence_upload_records_restart_safe_retention_receipt(
    tmp_path: Path,
) -> None:
    clips = tmp_path / "clips"
    clips.mkdir()
    clip = clips / "event-1.mp4"
    clip.write_bytes(b"accepted-video")
    outbox_path = tmp_path / "offline" / "evidence.db"
    uploaded = threading.Event()

    def available(request: httpx.Request) -> httpx.Response:
        assert request.read() == b"accepted-video"
        uploaded.set()
        return httpx.Response(201)

    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        transport=httpx.MockTransport(available),
        transcode_clip=False,
        outbox_path=outbox_path,
        retry_interval_seconds=0.02,
    ) as uploader:
        uploader.submit("event-1", clip, duration_seconds=2.5)
        assert uploaded.wait(timeout=1)

    restarted = DurableJsonOutbox(outbox_path)
    assert restarted.count() == 0
    with sqlite3.connect(outbox_path) as connection:
        connection.execute(
            "UPDATE acknowledged_evidence SET acknowledged_at = ?",
            (time.time() - 7200,),
        )
    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        transcode_clip=False,
        outbox_path=outbox_path,
        clips_directory=clips,
        retention_hours=1,
        retry_interval_seconds=0.02,
    ):
        deadline = time.monotonic() + 1
        while clip.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
    assert not clip.exists()


def test_accepted_upload_with_disappearing_local_source_does_not_retry_forever(
    tmp_path: Path, monkeypatch
) -> None:
    clip = tmp_path / "event-1.mp4"
    clip.write_bytes(b"accepted-video")
    outbox_path = tmp_path / "evidence.db"
    accepted = threading.Event()

    def accept_and_remove(_self, _event_id: str, path: Path, _duration: float) -> None:
        path.unlink()
        accepted.set()

    monkeypatch.setattr(BackgroundEvidenceUploader, "_put_clip", accept_and_remove)
    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        transcode_clip=False,
        outbox_path=outbox_path,
        retry_interval_seconds=0.02,
    ) as uploader:
        uploader.submit("event-1", clip, duration_seconds=2.5)
        assert accepted.wait(timeout=1)

    assert DurableJsonOutbox(outbox_path).count() == 0
    with sqlite3.connect(outbox_path) as connection:
        receipt_count = connection.execute(
            "SELECT COUNT(*) FROM acknowledged_evidence"
        ).fetchone()[0]
    assert receipt_count == 0


def test_durable_evidence_waits_for_event_after_repeated_404s(tmp_path: Path) -> None:
    clip = tmp_path / "event.mp4"
    clip.write_bytes(b"completed-video")
    outbox_path = tmp_path / "offline" / "evidence.db"
    event_available = threading.Event()
    repeated_404s = threading.Event()
    uploaded = threading.Event()
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        assert request.url.path == "/api/v1/agent/events/event-1/clip"
        attempts += 1
        if not event_available.is_set():
            if attempts >= 3:
                repeated_404s.set()
            return httpx.Response(404)
        uploaded.set()
        return httpx.Response(200)

    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        transport=httpx.MockTransport(handler),
        transcode_clip=False,
        outbox_path=outbox_path,
        retry_interval_seconds=0.02,
        retry_max_seconds=0.05,
    ) as uploader:
        uploader.submit("event-1", clip, duration_seconds=2.5)
        assert repeated_404s.wait(timeout=1)
        assert DurableJsonOutbox(outbox_path).count() == 1
        assert clip.exists()
        event_available.set()
        assert uploaded.wait(timeout=1)

    assert DurableJsonOutbox(outbox_path).count() == 0
    assert attempts >= 4


def test_durable_evidence_reuses_transcode_between_retries(
    tmp_path: Path, monkeypatch
) -> None:
    clip = tmp_path / "event.mp4"
    clip.write_bytes(b"source-video")
    outbox_path = tmp_path / "offline" / "evidence.db"
    transcodes: list[Path] = []
    uploaded = threading.Event()
    requests = 0

    def fake_transcode(source: Path) -> Path:
        transcodes.append(source)
        target = tmp_path / "temporary.mp4"
        target.write_bytes(b"transcoded-video")
        return target

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        assert request.read() == b"transcoded-video"
        if requests == 1:
            return httpx.Response(503)
        uploaded.set()
        return httpx.Response(201)

    monkeypatch.setattr(
        "video_intelligence_inference.actions._transcode_h264", fake_transcode
    )
    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        transport=httpx.MockTransport(handler),
        outbox_path=outbox_path,
        retry_interval_seconds=0.02,
    ) as uploader:
        uploader.submit("event-1", clip, duration_seconds=2.5)
        assert uploaded.wait(timeout=1)

    assert requests == 2
    assert transcodes == [clip]
    assert not (tmp_path / "event.upload.mp4").exists()
    assert clip.read_bytes() == b"source-video"


def test_missing_evidence_source_stays_queued(tmp_path: Path) -> None:
    clip = tmp_path / "missing.mp4"
    outbox_path = tmp_path / "offline" / "evidence.db"
    outbox = DurableJsonOutbox(outbox_path)
    requests = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200)

    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        transport=httpx.MockTransport(handler),
        transcode_clip=False,
        outbox_path=outbox_path,
        retry_interval_seconds=0.05,
    ) as uploader:
        uploader.submit("event-1", clip, duration_seconds=2.5)
        deadline = time.monotonic() + 1
        while outbox.pending()[0].attempts == 0 and time.monotonic() < deadline:
            time.sleep(0.01)

    assert outbox.count() == 1
    assert outbox.pending()[0].attempts >= 1
    assert requests == 0
    assert not clip.exists()


def test_evidence_restart_reuses_cached_transcode(tmp_path: Path, monkeypatch) -> None:
    clip = tmp_path / "event.mp4"
    clip.write_bytes(b"source-video")
    outbox_path = tmp_path / "offline" / "evidence.db"
    transcodes: list[Path] = []
    first_attempt = threading.Event()
    second_attempt = threading.Event()

    def fake_transcode(source: Path) -> Path:
        transcodes.append(source)
        target = tmp_path / "temporary.mp4"
        target.write_bytes(b"transcoded-video")
        return target

    monkeypatch.setattr(
        "video_intelligence_inference.actions._transcode_h264", fake_transcode
    )

    def unavailable(request: httpx.Request) -> httpx.Response:
        assert request.read() == b"transcoded-video"
        first_attempt.set()
        return httpx.Response(503)

    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        transport=httpx.MockTransport(unavailable),
        outbox_path=outbox_path,
        retry_interval_seconds=0.05,
    ) as uploader:
        uploader.submit("event-1", clip, duration_seconds=2.5)
        assert first_attempt.wait(timeout=1)

    cache = tmp_path / "event.upload.mp4"
    assert cache.read_bytes() == b"transcoded-video"
    assert DurableJsonOutbox(outbox_path).count() == 1

    def available(request: httpx.Request) -> httpx.Response:
        assert request.read() == b"transcoded-video"
        second_attempt.set()
        return httpx.Response(200)

    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        transport=httpx.MockTransport(available),
        outbox_path=outbox_path,
        retry_interval_seconds=0.05,
    ):
        assert second_attempt.wait(timeout=1)

    assert transcodes == [clip]
    assert DurableJsonOutbox(outbox_path).count() == 0
    assert not cache.exists()
    assert clip.read_bytes() == b"source-video"
    with sqlite3.connect(outbox_path) as connection:
        recorded_cache = connection.execute(
            "SELECT cache_path FROM acknowledged_evidence WHERE record_id = ?", ("event-1",)
        ).fetchone()[0]
    assert recorded_cache == str(cache.resolve())


def test_lost_success_response_retries_identical_evidence_bytes(tmp_path: Path) -> None:
    clip = tmp_path / "event.mp4"
    clip.write_bytes(b"completed-video")
    outbox_path = tmp_path / "offline" / "evidence.db"
    outbox = DurableJsonOutbox(outbox_path)
    accepted: list[bytes] = []
    first_attempt = threading.Event()

    def response_lost(request: httpx.Request) -> httpx.Response:
        accepted.append(request.read())
        first_attempt.set()
        raise httpx.ReadError("response lost after server acceptance", request=request)

    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        transport=httpx.MockTransport(response_lost),
        transcode_clip=False,
        outbox_path=outbox_path,
        retry_interval_seconds=0.05,
    ) as uploader:
        uploader.submit("event-1", clip, duration_seconds=2.5)
        assert first_attempt.wait(timeout=1)

    assert outbox.count() == 1
    recovered = threading.Event()

    def available(request: httpx.Request) -> httpx.Response:
        accepted.append(request.read())
        recovered.set()
        return httpx.Response(200)

    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        transport=httpx.MockTransport(available),
        transcode_clip=False,
        outbox_path=outbox_path,
        retry_interval_seconds=0.05,
    ):
        assert recovered.wait(timeout=1)

    assert accepted == [b"completed-video", b"completed-video"]
    assert outbox.count() == 0


def test_ffmpeg_transcode_timeout_is_bounded_and_keeps_durable_job(
    tmp_path: Path, monkeypatch
) -> None:
    clip = tmp_path / "event.mp4"
    clip.write_bytes(b"source-video")
    outbox_path = tmp_path / "offline" / "evidence.db"
    outbox = DurableJsonOutbox(outbox_path)
    timeouts: list[int] = []

    def timed_out(_command, *, check, capture_output, timeout):
        assert check and capture_output
        timeouts.append(timeout)
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout)

    monkeypatch.setattr(
        "video_intelligence_inference.actions.subprocess.run", timed_out
    )
    monkeypatch.setattr(
        "video_intelligence_inference.actions.imageio_ffmpeg.get_ffmpeg_exe",
        lambda: "ffmpeg",
    )
    with BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        outbox_path=outbox_path,
        retry_interval_seconds=0.05,
    ) as uploader:
        uploader.submit("event-1", clip, duration_seconds=2.5)
        deadline = time.monotonic() + 1
        while outbox.pending()[0].attempts == 0 and time.monotonic() < deadline:
            time.sleep(0.01)

    assert timeouts and all(timeout == 600 for timeout in timeouts)
    assert outbox.count() == 1
    assert outbox.pending()[0].attempts >= 1
    assert clip.read_bytes() == b"source-video"
    assert not list(tmp_path.glob("event-browser-*.mp4"))


def test_control_plane_events_survive_disconnect_and_sync_on_restart(
    tmp_path: Path,
) -> None:
    outbox_path = tmp_path / "offline" / "events.db"
    disconnected_attempt = threading.Event()

    def unavailable(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agent/events"
        disconnected_attempt.set()
        return httpx.Response(503)

    with BackgroundWebhookDispatcher(
        "https://control.test/api/v1/agent/events",
        transport=httpx.MockTransport(unavailable),
        outbox_path=outbox_path,
        retry_interval_seconds=0.05,
    ) as dispatcher:
        dispatcher.submit(make_event(tmp_path))
        assert disconnected_attempt.wait(timeout=1)

    outbox = DurableJsonOutbox(outbox_path)
    assert outbox.count() == 1
    assert outbox.pending()[0].attempts == 1

    delivered: list[dict] = []
    synchronized = threading.Event()

    def available(request: httpx.Request) -> httpx.Response:
        delivered.append(json.loads(request.content))
        synchronized.set()
        return httpx.Response(201)

    with BackgroundWebhookDispatcher(
        "https://control.test/api/v1/agent/events",
        transport=httpx.MockTransport(available),
        outbox_path=outbox_path,
        retry_interval_seconds=0.05,
    ):
        assert synchronized.wait(timeout=1)

    assert delivered[0]["id"] == "event-1"
    assert outbox.count() == 0


def test_control_plane_event_retries_after_recovery_without_another_event(
    tmp_path: Path,
) -> None:
    outbox_path = tmp_path / "offline" / "events.db"
    outbox = DurableJsonOutbox(outbox_path)
    disconnected_attempt = threading.Event()
    network_recovered = threading.Event()
    delivered = threading.Event()
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        event_id = json.loads(request.content)["id"]
        requests.append(event_id)
        if not network_recovered.is_set():
            disconnected_attempt.set()
            return httpx.Response(503)
        delivered.set()
        return httpx.Response(201)

    with BackgroundWebhookDispatcher(
        "https://control.test/api/v1/agent/events",
        transport=httpx.MockTransport(handler),
        outbox_path=outbox_path,
        retry_interval_seconds=0.05,
    ) as dispatcher:
        dispatcher.submit(make_event(tmp_path))
        assert disconnected_attempt.wait(timeout=1)
        assert outbox.count() == 1

        network_recovered.set()
        assert delivered.wait(timeout=1), "The quiet camera must retry the queued event"
        deadline = time.monotonic() + 1
        while outbox.count() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert outbox.count() == 0

        attempts_after_delivery = len(requests)
        time.sleep(0.15)
        assert len(requests) == attempts_after_delivery

    assert requests == ["event-1"] * attempts_after_delivery
    assert attempts_after_delivery >= 2


def test_closing_idle_outbox_does_not_retry_queued_event(tmp_path: Path) -> None:
    outbox_path = tmp_path / "offline" / "events.db"
    attempted = threading.Event()
    requests = 0

    def unavailable(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        attempted.set()
        return httpx.Response(503)

    with BackgroundWebhookDispatcher(
        "https://control.test/api/v1/agent/events",
        transport=httpx.MockTransport(unavailable),
        outbox_path=outbox_path,
        retry_interval_seconds=60,
    ) as dispatcher:
        dispatcher.submit(make_event(tmp_path))
        assert attempted.wait(timeout=1)

    assert requests == 1
    assert DurableJsonOutbox(outbox_path).count() == 1


def test_outbox_without_webhook_does_not_start_retry_loop(tmp_path: Path) -> None:
    with BackgroundWebhookDispatcher(
        None,
        outbox_path=tmp_path / "offline" / "events.db",
    ) as dispatcher:
        assert dispatcher._futures == []


def test_two_dispatchers_do_not_deliver_the_same_queued_event(tmp_path: Path) -> None:
    outbox_path = tmp_path / "offline" / "events.db"
    outbox = DurableJsonOutbox(outbox_path)
    outbox.put("event-1", make_event(tmp_path).to_dict())
    first_request_started = threading.Event()
    finish_request = threading.Event()
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content)["id"])
        first_request_started.set()
        assert finish_request.wait(timeout=2)
        return httpx.Response(201)

    first = BackgroundWebhookDispatcher(
        "https://control.test/api/v1/agent/events",
        transport=httpx.MockTransport(handler),
        outbox_path=outbox_path,
        retry_interval_seconds=0.02,
    )
    second: BackgroundWebhookDispatcher | None = None
    try:
        assert first_request_started.wait(timeout=1)
        second = BackgroundWebhookDispatcher(
            "https://control.test/api/v1/agent/events",
            transport=httpx.MockTransport(handler),
            outbox_path=outbox_path,
            retry_interval_seconds=0.02,
        )
        time.sleep(0.1)
        assert requests == ["event-1"]
    finally:
        finish_request.set()
        first.close()
        if second is not None:
            second.close()

    assert outbox.count() == 0
    assert requests == ["event-1"]


def test_two_evidence_uploaders_keep_one_long_upload_claimed(tmp_path: Path) -> None:
    clip = tmp_path / "event.mp4"
    clip.write_bytes(b"completed-video")
    outbox_path = tmp_path / "offline" / "evidence.db"
    outbox = DurableJsonOutbox(outbox_path)
    outbox.put(
        "event-1",
        {"event_id": "event-1", "path": str(clip), "duration_seconds": 2.5},
    )
    first_request_started = threading.Event()
    finish_request = threading.Event()
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        first_request_started.set()
        assert finish_request.wait(timeout=2)
        return httpx.Response(201)

    first = BackgroundEvidenceUploader(
        "https://control.test/api/v1",
        transport=httpx.MockTransport(handler),
        transcode_clip=False,
        outbox_path=outbox_path,
        retry_interval_seconds=0.02,
        claim_lease_seconds=0.12,
    )
    second: BackgroundEvidenceUploader | None = None
    try:
        assert first_request_started.wait(timeout=1)
        second = BackgroundEvidenceUploader(
            "https://control.test/api/v1",
            transport=httpx.MockTransport(handler),
            transcode_clip=False,
            outbox_path=outbox_path,
            retry_interval_seconds=0.02,
            claim_lease_seconds=0.12,
        )
        time.sleep(0.4)
        assert requests == ["/api/v1/agent/events/event-1/clip"]
    finally:
        finish_request.set()
        first.close()
        if second is not None:
            second.close()

    assert outbox.count() == 0
    assert requests == ["/api/v1/agent/events/event-1/clip"]
