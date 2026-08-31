import asyncio
import base64

from fastapi.testclient import TestClient
from video_intelligence_api.camera_secrets import migrate_legacy_camera_credentials
from video_intelligence_api.models import Camera, SourceType

AGENT_KEY = "test-agent-key-123456789"


def _discovered_camera(api_client: TestClient) -> tuple[dict, str, dict]:
    enrolled = api_client.post(
        "/api/v1/edge-devices",
        json={"name": "onboarding-edge", "max_concurrent_streams": 2},
    ).json()
    device = enrolled["device"]
    token = enrolled["token"]
    discovery = api_client.post(
        "/api/v1/camera-discovery-runs",
        json={"edge_device_id": device["id"], "timeout_seconds": 2},
    ).json()
    claim = api_client.post(
        "/api/v1/agent/camera-discovery-runs/claim",
        json={"worker_id": "onboarding-worker"},
        headers={"X-Device-Token": token},
    )
    assert claim.status_code == 200
    completed = api_client.post(
        f"/api/v1/agent/camera-discovery-runs/{discovery['id']}/result",
        json={
            "worker_id": "onboarding-worker",
            "devices": [
                {
                    "endpoint_reference": "urn:uuid:onboarding-camera",
                    "xaddrs": ["http://192.0.2.20/onvif/device_service"],
                    "scopes": ["onvif://www.onvif.org/name/Entrance"],
                    "remote_address": "192.0.2.20",
                }
            ],
        },
        headers={"X-Device-Token": token},
    )
    assert completed.status_code == 200
    return device, token, discovery


def test_onboarding_encrypts_credentials_and_creates_preview_verified_camera(
    api_client: TestClient,
) -> None:
    device, token, discovery = _discovered_camera(api_client)
    created = api_client.post(
        "/api/v1/camera-onboarding-runs",
        json={
            "discovery_run_id": discovery["id"],
            "endpoint_url": "http://192.0.2.20/onvif/device_service",
            "camera_name": "Entrance Camera",
            "username": "camera-admin",
            "password": "camera-secret",
            "verify_tls": True,
        },
    )
    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "queued"
    assert "username" not in run
    assert "password" not in run

    legacy = api_client.post(
        "/api/v1/agent/camera-onboarding-runs/claim",
        json={"worker_id": "legacy"},
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert legacy.status_code == 409
    claim = api_client.post(
        "/api/v1/agent/camera-onboarding-runs/claim",
        json={"worker_id": "edge-onboarding"},
        headers={"X-Device-Token": token},
    )
    assert claim.status_code == 200
    assignment = claim.json()
    assert assignment["username"] == "camera-admin"
    assert assignment["password"] == "camera-secret"

    jpeg = b"\xff\xd8verified-camera-frame\xff\xd9"
    completed = api_client.post(
        f"/api/v1/agent/camera-onboarding-runs/{run['id']}/result",
        json={
            "worker_id": "edge-onboarding",
            "profiles": [
                {
                    "token": "main",
                    "name": "Main stream",
                    "encoding": "H264",
                    "width": 1920,
                    "height": 1080,
                    "frame_rate": 30,
                    "stream_uri": "rtsp://leaked:credentials@192.0.2.20/main",
                }
            ],
            "selected_profile_token": "main",
            "stream_uri": "rtsp://leaked:credentials@192.0.2.20/main",
            "preview_jpeg_base64": base64.b64encode(jpeg).decode(),
        },
        headers={"X-Device-Token": token},
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "completed"
    assert body["profiles"][0]["stream_uri"] == "rtsp://192.0.2.20/main"

    camera = api_client.get(f"/api/v1/cameras/{body['camera_id']}").json()
    assert camera["name"] == "Entrance Camera"
    assert camera["source_uri"] == "rtsp://***:***@192.0.2.20/main"
    assert camera["edge_device_id"] == device["id"]
    assert camera["has_credentials"] is True
    preview = api_client.get(f"/api/v1/cameras/{camera['id']}/preview")
    assert preview.status_code == 200
    assert preview.content == jpeg


def test_onboarding_rejects_endpoint_not_returned_by_discovery(
    api_client: TestClient,
) -> None:
    _, _, discovery = _discovered_camera(api_client)
    response = api_client.post(
        "/api/v1/camera-onboarding-runs",
        json={
            "discovery_run_id": discovery["id"],
            "endpoint_url": "http://192.0.2.99/onvif/device_service",
            "camera_name": "Wrong Camera",
            "username": "admin",
            "password": "secret",
        },
    )
    assert response.status_code == 409


def test_legacy_rtsp_userinfo_is_migrated_to_encrypted_storage(
    api_client: TestClient,
) -> None:
    database = api_client.app.state.database
    settings = api_client.app.state.settings

    async def seed_and_migrate() -> tuple[int, str, str | None]:
        async with database.session_factory() as session:
            camera = Camera(
                organization_id=settings.development_organization_id,
                name="legacy-credential-camera",
                source_uri="rtsp://legacy-user:legacy-secret@192.0.2.30/live",
                source_type=SourceType.RTSP,
            )
            session.add(camera)
            await session.commit()
            camera_id = camera.id
        migrated = await migrate_legacy_camera_credentials(database, settings)
        async with database.session_factory() as session:
            camera = await session.get(Camera, camera_id)
            assert camera is not None
            return migrated, camera.source_uri, camera.credential_encrypted

    migrated, source_uri, encrypted = asyncio.run(seed_and_migrate())

    assert migrated == 1
    assert source_uri == "rtsp://192.0.2.30/live"
    assert encrypted is not None
    assert "legacy-user" not in encrypted
    assert "legacy-secret" not in encrypted
