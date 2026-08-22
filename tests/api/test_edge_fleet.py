from datetime import UTC, datetime

from fastapi.testclient import TestClient


def enroll(client: TestClient) -> tuple[dict, dict[str, str]]:
    response = client.post(
        "/api/v1/edge-devices",
        json={"name": "offline-station", "max_concurrent_streams": 3},
    )
    assert response.status_code == 201
    body = response.json()
    return body["device"], {"X-Device-Token": body["token"]}


def test_profile_signed_configuration_and_update_rollback_lifecycle(
    api_client: TestClient,
) -> None:
    device, edge_headers = enroll(api_client)
    reported = api_client.post(
        "/api/v1/agent/fleet/profile",
        headers=edge_headers,
        json={
            "hostname": "edge-orlando-01",
            "os_name": "Linux",
            "architecture": "x86_64",
            "cpu_count": 12,
            "memory_mb": 32768,
            "accelerator": "NVIDIA RTX",
            "storage_available_mb": 200000,
            "worker_version": "1.4.0",
            "health_status": "healthy",
            "offline_queue_depth": 2,
            "last_sync_at": datetime.now(UTC).isoformat(),
            "details": {"cuda": "13.0"},
        },
    )
    assert reported.status_code == 200, reported.text
    assert reported.json()["offline_queue_depth"] == 2

    configuration = {
        "offline_rules": ["person-dwell"],
        "provider_requests_allowed": False,
        "storage_retention_hours": 48,
    }
    revision = api_client.post(
        f"/api/v1/edge-devices/{device['id']}/config-revisions",
        json={"configuration": configuration},
    )
    assert revision.status_code == 201, revision.text
    body = revision.json()
    assert body["revision"] == 1
    assert len(body["content_sha256"]) == 64
    assert len(body["signature"]) == 64

    fetched = api_client.get("/api/v1/agent/fleet/config", headers=edge_headers)
    assert fetched.status_code == 200
    assert fetched.json()["configuration"] == configuration
    assert fetched.headers["etag"] == f'"{body["content_sha256"]}"'
    assert fetched.headers["x-config-signature"] == body["signature"]

    update = api_client.post(
        f"/api/v1/edge-devices/{device['id']}/updates",
        json={"target_version": "1.5.0"},
    )
    assert update.status_code == 201
    update_id = update.json()["id"]
    assert update.json()["rollback_version"] == "1.4.0"
    for update_status in ("downloading", "applying", "failed", "rolled_back"):
        result = api_client.post(
            f"/api/v1/agent/fleet/updates/{update_id}",
            headers=edge_headers,
            json={
                "status": update_status,
                "error": "health check failed" if update_status == "failed" else None,
            },
        )
        assert result.status_code == 200, result.text
    assert result.json()["status"] == "rolled_back"
    assert result.json()["completed_at"] is not None

    fleet = api_client.get("/api/v1/edge-devices/fleet").json()
    assert fleet[0]["device"]["id"] == device["id"]
    assert fleet[0]["profile"]["accelerator"] == "NVIDIA RTX"
    assert fleet[0]["config"]["revision"] == 1
    assert fleet[0]["update"]["status"] == "rolled_back"


def test_legacy_shared_key_cannot_impersonate_an_enrolled_station(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/v1/agent/fleet/profile",
        headers={"X-Agent-Key": "test-agent-key-123456789"},
        json={
            "hostname": "unknown",
            "os_name": "Windows",
            "architecture": "x86_64",
            "cpu_count": 4,
            "memory_mb": 8000,
            "storage_available_mb": 1000,
            "worker_version": "0.1.0",
            "health_status": "healthy",
        },
    )
    assert response.status_code == 409
    assert "enrolled edge-device token" in response.json()["detail"]
