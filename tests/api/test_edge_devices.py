import asyncio

from fastapi.testclient import TestClient
from video_intelligence_api.device_credentials import generate_device_credential
from video_intelligence_api.models import EdgeDevice, Organization

ORG_B = "20000000-0000-0000-0000-000000000002"


def create_running_camera(client: TestClient, index: int) -> dict:
    camera = client.post(
        "/api/v1/cameras",
        json={"name": f"edge-camera-{index}", "source_uri": f"demo-{index}.mp4"},
    ).json()
    zone = client.post(
        "/api/v1/zones",
        json={
            "camera_id": camera["id"],
            "name": "full-frame",
            "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}],
        },
    ).json()
    rule = client.post(
        "/api/v1/rules",
        json={
            "camera_id": camera["id"],
            "zone_id": zone["id"],
            "key": "person-present",
            "name": "Person present",
            "duration_seconds": 1,
        },
    ).json()
    client.patch(f"/api/v1/rules/{rule['id']}/status", json={"status": "active"})
    started = client.put(
        f"/api/v1/cameras/{camera['id']}/agent",
        json={"desired_status": "running"},
    )
    assert started.status_code == 200
    return camera


def test_device_credential_capacity_rotation_and_revocation(
    api_client: TestClient,
) -> None:
    cameras = [create_running_camera(api_client, index) for index in range(3)]
    enrolled = api_client.post(
        "/api/v1/edge-devices",
        json={"name": "loading-dock-edge", "max_concurrent_streams": 2},
    )
    assert enrolled.status_code == 201
    token = enrolled.json()["token"]
    device = enrolled.json()["device"]
    assert token.startswith(f"vid1.{device['id']}.")

    headers = {"X-Device-Token": token}
    first = api_client.post(
        "/api/v1/agent/assignments/claim",
        json={"worker_id": "edge-host-1"},
        headers=headers,
    )
    second = api_client.post(
        "/api/v1/agent/assignments/claim",
        json={"worker_id": "edge-host-1"},
        headers=headers,
    )
    full = api_client.post(
        "/api/v1/agent/assignments/claim",
        json={"worker_id": "edge-host-1"},
        headers=headers,
    )
    assert {first.json()["camera_id"], second.json()["camera_id"]} <= {
        camera["id"] for camera in cameras
    }
    assert full.status_code == 204
    assigned = api_client.get(
        f"/api/v1/cameras/{first.json()['camera_id']}/agent"
    ).json()
    assert assigned["edge_device_id"] == device["id"]

    rotated = api_client.post(f"/api/v1/edge-devices/{device['id']}/rotate-credential")
    assert rotated.status_code == 200
    replacement = rotated.json()["token"]
    assert replacement != token
    assert (
        api_client.post(
            "/api/v1/agent/assignments/claim",
            json={"worker_id": "edge-host-1"},
            headers=headers,
        ).status_code
        == 401
    )
    assert (
        api_client.post(
            "/api/v1/agent/assignments/claim",
            json={"worker_id": "edge-host-1"},
            headers={"X-Device-Token": replacement},
        ).status_code
        == 200
    )

    revoked = api_client.post(f"/api/v1/edge-devices/{device['id']}/revoke")
    assert revoked.json()["status"] == "revoked"
    assert (
        api_client.post(
            "/api/v1/agent/assignments/claim",
            json={"worker_id": "edge-host-1"},
            headers={"X-Device-Token": replacement},
        ).status_code
        == 401
    )

    async def credential_is_hashed() -> None:
        async with api_client.app.state.database.session_factory() as session:
            stored = await session.get(EdgeDevice, device["id"])
            assert stored is not None
            assert stored.credential_hash != token
            assert stored.credential_hash != replacement

    asyncio.run(credential_is_hashed())


def test_device_cannot_read_another_organizations_camera(
    api_client: TestClient,
) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "tenant-a-camera", "source_uri": "tenant-a.mp4"},
    ).json()

    async def seed_other_tenant_device() -> str:
        database = api_client.app.state.database
        async with database.session_factory() as session:
            session.add(
                Organization(id=ORG_B, slug="tenant-b-edge", name="Tenant B Edge")
            )
            credential = generate_device_credential(
                "20000000-0000-0000-0000-000000000099"
            )
            session.add(
                EdgeDevice(
                    id="20000000-0000-0000-0000-000000000099",
                    organization_id=ORG_B,
                    name="tenant-b-device",
                    credential_hash=credential.token_hash,
                    credential_fingerprint=credential.fingerprint,
                )
            )
            await session.commit()
            return credential.token

    token = asyncio.run(seed_other_tenant_device())
    response = api_client.get(
        f"/api/v1/agent/config?camera_ref={camera['id']}",
        headers={"X-Device-Token": token},
    )
    assert response.status_code == 404


def test_operator_mutations_create_tenant_audit_records(api_client: TestClient) -> None:
    created = api_client.post(
        "/api/v1/cameras",
        json={"name": "audited-camera", "source_uri": "audit.mp4"},
    )
    request_id = created.headers["X-Request-ID"]

    audit = api_client.get("/api/v1/audit-logs").json()
    matching = next(record for record in audit if record["request_id"] == request_id)
    assert matching["action"] == "POST /api/v1/cameras"
    assert matching["resource_type"] == "cameras"
    assert matching["actor_subject"] == "local-dashboard-operator"
    assert matching["status_code"] == 201
    assert matching["details"] == {"query_keys": []}
