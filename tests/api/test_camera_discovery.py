from fastapi.testclient import TestClient

AGENT_KEY = "test-agent-key-123456789"


def test_discovery_runs_are_leased_to_the_selected_edge_device(
    api_client: TestClient,
) -> None:
    enrolled = api_client.post(
        "/api/v1/edge-devices",
        json={"name": "camera-lan-edge", "max_concurrent_streams": 2},
    ).json()
    device = enrolled["device"]
    token = enrolled["token"]
    created = api_client.post(
        "/api/v1/camera-discovery-runs",
        json={"edge_device_id": device["id"], "timeout_seconds": 2},
    )
    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "queued"

    legacy_claim = api_client.post(
        "/api/v1/agent/camera-discovery-runs/claim",
        json={"worker_id": "legacy-worker"},
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert legacy_claim.status_code == 409
    claim = api_client.post(
        "/api/v1/agent/camera-discovery-runs/claim",
        json={"worker_id": "edge-worker-1"},
        headers={"X-Device-Token": token},
    )
    assert claim.status_code == 200
    assert claim.json()["discovery_id"] == run["id"]

    wrong_worker = api_client.post(
        f"/api/v1/agent/camera-discovery-runs/{run['id']}/result",
        json={"worker_id": "wrong-worker", "devices": []},
        headers={"X-Device-Token": token},
    )
    assert wrong_worker.status_code == 409
    completed = api_client.post(
        f"/api/v1/agent/camera-discovery-runs/{run['id']}/result",
        json={
            "worker_id": "edge-worker-1",
            "devices": [
                {
                    "endpoint_reference": "urn:uuid:camera-one",
                    "xaddrs": ["http://192.0.2.10/onvif/device_service"],
                    "scopes": ["onvif://www.onvif.org/name/LoadingDock"],
                    "remote_address": "192.0.2.10",
                }
            ],
        },
        headers={"X-Device-Token": token},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["devices"][0]["remote_address"] == "192.0.2.10"
    assert completed.json()["worker_id"] is None

    history = api_client.get("/api/v1/camera-discovery-runs").json()
    assert [item["id"] for item in history] == [run["id"]]


def test_discovery_requires_an_active_tenant_device(api_client: TestClient) -> None:
    missing = api_client.post(
        "/api/v1/camera-discovery-runs",
        json={
            "edge_device_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "timeout_seconds": 3,
        },
    )
    assert missing.status_code == 404
