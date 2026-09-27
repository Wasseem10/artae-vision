import asyncio
import errno
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio
from fastapi.testclient import TestClient
from test_control_plane import AGENT_KEY, create_active_rule, event_payload
from video_intelligence_api.models import EvidenceReviewSample, ReviewSampleKind
from video_intelligence_api.routes import evidence as evidence_routes


def _upload(client: TestClient, clip: bytes = b"incident-clip") -> tuple[dict, dict, dict, dict]:
    camera, _, rule = create_active_rule(client)
    payload = event_payload()
    event_response = client.post(
        "/api/v1/agent/events", json=payload, headers={"X-Agent-Key": AGENT_KEY}
    )
    assert event_response.status_code == 201
    upload = client.put(
        f"/api/v1/agent/events/{payload['id']}/clip",
        content=clip,
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "video/mp4"},
    )
    assert upload.status_code == 200
    return camera, rule, event_response.json(), upload.json()


def _unavailable(client: TestClient, asset_id: str) -> None:
    claimed = client.post(
        "/api/v1/agent/evidence/index-assignments/claim",
        json={"worker_id": "retention-test"},
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert claimed.status_code == 200
    assert claimed.json()["asset_id"] == asset_id
    finished = client.post(
        f"/api/v1/agent/evidence/{asset_id}/index-result",
        json={
            "worker_id": "retention-test",
            "status": "unavailable",
            "error": "optional index provider unavailable",
        },
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert finished.status_code == 200


def _resolve(client: TestClient) -> None:
    alerts = client.get("/api/v1/alerts").json()
    assert len(alerts) == 1
    resolved = client.post(f"/api/v1/alerts/{alerts[0]['id']}/resolve")
    assert resolved.status_code == 200


def _advance_clock(monkeypatch) -> None:
    later = datetime.now(UTC) + timedelta(hours=2)
    monkeypatch.setattr(evidence_routes, "utc_now", lambda: later)


def test_retention_is_off_by_default(api_client: TestClient) -> None:
    _, _, _, asset = _upload(api_client)
    status = api_client.get("/api/v1/evidence/retention/status")
    assert status.status_code == 200
    assert status.json()["policy_approved"] is False
    assert status.json()["retention_hours"] is None
    assert status.json()["awaiting_review"] == 1
    refused = api_client.post("/api/v1/evidence/retention/run?dry_run=false")
    assert refused.status_code == 409
    assert api_client.get(asset["content_url"]).status_code == 200


def test_full_storage_rejects_new_clip_without_marking_it_ready(
    api_client: TestClient, tmp_path: Path
) -> None:
    api_client.app.state.settings.evidence_storage_max_bytes = 4
    create_active_rule(api_client)
    payload = event_payload()
    created = api_client.post(
        "/api/v1/agent/events", json=payload, headers={"X-Agent-Key": AGENT_KEY}
    )
    assert created.status_code == 201
    url = f"/api/v1/agent/events/{payload['id']}/clip"
    full = api_client.put(
        url,
        content=b"12345",
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "video/mp4"},
    )
    assert full.status_code == 507
    asset = api_client.get("/api/v1/evidence").json()[0]
    assert asset["status"] == "awaiting_upload"
    assert asset["content_url"] is None
    assert not list((tmp_path / "evidence").glob("*.part"))
    api_client.app.state.settings.evidence_storage_max_bytes = 1024
    retry = api_client.put(
        url,
        content=b"12345",
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "video/mp4"},
    )
    assert retry.status_code == 200
    # A lost ACK retry remains idempotent even if the local volume later fills.
    api_client.app.state.settings.evidence_storage_max_bytes = 1
    duplicate = api_client.put(
        url,
        content=b"12345",
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "video/mp4"},
    )
    assert duplicate.status_code == 200


def test_duplicate_upload_refuses_to_ack_a_missing_api_clip(
    api_client: TestClient, tmp_path: Path
) -> None:
    _, _, _, asset = _upload(api_client)
    (tmp_path / "evidence" / f"{asset['id']}.mp4").unlink()
    source_event_id = event_payload_id(asset, api_client)
    duplicate = api_client.put(
        f"/api/v1/agent/events/{source_event_id}/clip",
        content=b"incident-clip",
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "video/mp4"},
    )
    assert duplicate.status_code == 503
    assert api_client.get("/api/v1/evidence").json()[0]["status"] == "queued"


def test_review_hold_alert_and_tombstone_gate_retention(
    api_client: TestClient, monkeypatch, tmp_path: Path
) -> None:
    settings = api_client.app.state.settings
    settings.retention_policy_configured = True
    settings.evidence_retention_hours = 1
    clip = b"private-incident-clip"
    camera, _, _, asset = _upload(api_client, clip)
    old_url = asset["content_url"]
    search = api_client.post(
        "/api/v1/evidence/searches",
        json={"query": "person loading zone", "camera_id": camera["id"]},
    )
    assert search.status_code == 201
    assert search.json()["results"]
    _advance_clock(monkeypatch)
    # Time alone cannot delete pending, unreviewed incident evidence.
    assert api_client.post("/api/v1/evidence/retention/run?dry_run=false").json()[
        "expired_assets"
    ] == 0
    reviewed = api_client.post(f"/api/v1/evidence/{asset['id']}/review")
    assert reviewed.status_code == 200
    _resolve(api_client)
    # Queued evidence is still needed by the optional index worker.
    assert api_client.post("/api/v1/evidence/retention/run?dry_run=false").json()[
        "expired_assets"
    ] == 0
    _unavailable(api_client, asset["id"])
    held = api_client.put(
        f"/api/v1/evidence/{asset['id']}/legal-hold", json={"enabled": True}
    )
    assert held.status_code == 200
    assert api_client.post("/api/v1/evidence/retention/run?dry_run=false").json()[
        "expired_assets"
    ] == 0
    released = api_client.put(
        f"/api/v1/evidence/{asset['id']}/legal-hold", json={"enabled": False}
    )
    assert released.status_code == 200
    expired = api_client.post("/api/v1/evidence/retention/run?dry_run=false")
    assert expired.status_code == 200
    assert expired.json()["expired_assets"] == 1
    assert api_client.get(old_url).status_code == 404
    assert not list((tmp_path / "evidence").glob("*.mp4"))
    catalog = api_client.get("/api/v1/evidence").json()[0]
    assert catalog["status"] == "expired"
    assert catalog["content_url"] is None
    hold_after_expiry = api_client.put(
        f"/api/v1/evidence/{asset['id']}/legal-hold", json={"enabled": True}
    )
    assert hold_after_expiry.status_code == 409
    cached = api_client.get(f"/api/v1/evidence/searches/{search.json()['id']}")
    assert cached.status_code == 200
    assert cached.json()["results"] == []
    # Repeated bytes acknowledge a lost upload response without restoring the clip.
    retry_url = f"/api/v1/agent/events/{event_payload_id(asset, api_client)}/clip"
    same = api_client.put(
        retry_url,
        content=clip,
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "video/mp4"},
    )
    assert same.status_code == 200
    assert same.json()["status"] == "expired"
    assert same.json()["content_url"] is None
    different = api_client.put(
        retry_url,
        content=b"different",
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "video/mp4"},
    )
    assert different.status_code == 409
    assert not list((tmp_path / "evidence").glob("*.mp4"))


def event_payload_id(asset: dict, client: TestClient) -> str:
    events = client.get("/api/v1/events").json()
    return next(event["source_event_id"] for event in events if event["id"] == asset["event_id"])


def test_review_sample_prevents_expiry(api_client: TestClient, monkeypatch) -> None:
    settings = api_client.app.state.settings
    settings.retention_policy_configured = True
    settings.evidence_retention_hours = 1
    camera, rule, event, asset = _upload(api_client)
    api_client.post(f"/api/v1/evidence/{asset['id']}/review")
    _resolve(api_client)
    _unavailable(api_client, asset["id"])

    async def add_review_sample() -> None:
        async with api_client.app.state.database.session_factory() as session:
            session.add(
                EvidenceReviewSample(
                    organization_id=camera["organization_id"],
                    camera_id=camera["id"],
                    rule_id=rule["id"],
                    event_id=event["id"],
                    kind=ReviewSampleKind.CANDIDATE,
                    priority=1.0,
                    dedup_key="retention-review-sample",
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
            await session.commit()

    asyncio.run(add_review_sample())
    _advance_clock(monkeypatch)
    result = api_client.post("/api/v1/evidence/retention/run?dry_run=false")
    assert result.status_code == 200
    assert result.json()["expired_assets"] == 0
    assert api_client.get(asset["content_url"]).status_code == 200


def test_failed_unlink_keeps_a_retryable_tombstone(
    api_client: TestClient, monkeypatch, tmp_path: Path
) -> None:
    settings = api_client.app.state.settings
    settings.retention_policy_configured = True
    settings.evidence_retention_hours = 1
    _, _, _, asset = _upload(api_client)
    api_client.post(f"/api/v1/evidence/{asset['id']}/review")
    _resolve(api_client)
    _unavailable(api_client, asset["id"])
    _advance_clock(monkeypatch)
    original_unlink = Path.unlink
    evidence_path = tmp_path / "evidence" / f"{asset['id']}.mp4"

    def blocked_unlink(path: Path, *args, **kwargs):
        if path == evidence_path:
            raise OSError(errno.EACCES, "simulated storage failure")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, "unlink", blocked_unlink)
        failed = api_client.post("/api/v1/evidence/retention/run?dry_run=false")
    assert failed.status_code == 200
    assert failed.json()["cleanup_errors"] == 1
    assert api_client.get("/api/v1/evidence").json()[0]["status"] == "expired"
    assert api_client.get(asset["content_url"]).status_code == 404
    assert evidence_path.is_file()
    repaired = api_client.post("/api/v1/evidence/retention/run?dry_run=false")
    assert repaired.status_code == 200
    assert repaired.json()["expired_assets"] == 1
    assert not evidence_path.exists()


def test_concurrent_hold_prevents_sqlite_retention_race(
    api_client: TestClient, monkeypatch
) -> None:
    settings = api_client.app.state.settings
    settings.retention_policy_configured = True
    settings.evidence_retention_hours = 1
    _, _, _, asset = _upload(api_client)
    api_client.post(f"/api/v1/evidence/{asset['id']}/review")
    _resolve(api_client)
    _unavailable(api_client, asset["id"])
    _advance_clock(monkeypatch)
    selected = threading.Event()
    release = threading.Event()
    original_protected = evidence_routes._retention_protected

    async def pause_after_candidate_read(session, candidate):
        result = await original_protected(session, candidate)
        selected.set()
        await anyio.to_thread.run_sync(lambda: release.wait(10))
        return result

    monkeypatch.setattr(evidence_routes, "_retention_protected", pause_after_candidate_read)
    with ThreadPoolExecutor(max_workers=1) as pool:
        sweep = pool.submit(
            api_client.post, "/api/v1/evidence/retention/run?dry_run=false"
        )
        assert selected.wait(10)
        held = api_client.put(
            f"/api/v1/evidence/{asset['id']}/legal-hold", json={"enabled": True}
        )
        assert held.status_code == 200
        release.set()
        result = sweep.result(timeout=10)
    assert result.status_code == 200
    assert result.json()["expired_assets"] == 0
    assert api_client.get("/api/v1/evidence").json()[0]["legal_hold"] is True
    assert api_client.get(asset["content_url"]).status_code == 200
