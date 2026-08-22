from datetime import UTC, datetime

from fastapi.testclient import TestClient

AGENT_HEADERS = {"X-Agent-Key": "test-agent-key-123456789"}


def create_rule(client: TestClient, suffix: str) -> dict:
    camera = client.post(
        "/api/v1/cameras",
        json={"name": f"context-camera-{suffix}", "source_uri": "0"},
    ).json()
    zone = client.post(
        "/api/v1/zones",
        json={
            "camera_id": camera["id"],
            "name": "entrance",
            "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}],
        },
    ).json()
    return client.post(
        "/api/v1/rules",
        json={
            "camera_id": camera["id"],
            "zone_id": zone["id"],
            "key": f"tailgating-{suffix}",
            "name": "Tailgating correlation",
            "duration_seconds": 1,
        },
    ).json()


def create_source(client: TestClient, suffix: str) -> dict:
    response = client.post(
        "/api/v1/context-sources",
        json={
            "name": f"Simulated badge reader {suffix}",
            "source_type": "simulated_access_control",
        },
    )
    assert response.status_code == 201, response.text
    assert "credential" not in response.text
    return response.json()


def create_policy(client: TestClient, rule: dict, source: dict) -> dict:
    response = client.post(
        f"/api/v1/rules/{rule['id']}/correlation-policies",
        json={
            "source_id": source["id"],
            "window_before_seconds": 5,
            "window_after_seconds": 0,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_tailgating_correlation_creates_alert_and_guarded_action(
    api_client: TestClient,
) -> None:
    rule = create_rule(api_client, "matched")
    source = create_source(api_client, "matched")
    policy = create_policy(api_client, rule, source)
    connector = api_client.post(
        "/api/v1/connectors",
        json={
            "name": "Safe correlated notification",
            "connector_type": "mock",
            "scopes": ["notifications:write"],
        },
    ).json()
    api_client.post(
        f"/api/v1/rules/{rule['id']}/actions",
        json={"connector_id": connector["id"], "action_type": "send_notification"},
    )

    demo = api_client.post(
        f"/api/v1/rules/{rule['id']}/correlation-demo",
        json={"visual_people": 2, "authorized_entries": 1},
    )
    assert demo.status_code == 201, demo.text
    assert api_client.get("/api/v1/alerts").json() == []

    processed = api_client.post(
        "/api/v1/agent/correlation-evaluations/process-next",
        headers=AGENT_HEADERS,
    )
    assert processed.status_code == 200, processed.text
    assert processed.json()["status"] == "matched"
    assert processed.json()["visual_count"] == 2
    assert processed.json()["observation_count"] == 1
    assert processed.json()["policy_id"] == policy["id"]
    assert "Camera count 2 > authorized 1" in processed.json()["explanation"]
    assert len(api_client.get("/api/v1/alerts").json()) == 1
    executions = api_client.get("/api/v1/action-executions").json()
    assert len(executions) == 1
    assert executions[0]["status"] == "queued"


def test_equal_visual_and_authorized_counts_are_clear(api_client: TestClient) -> None:
    rule = create_rule(api_client, "clear")
    source = create_source(api_client, "clear")
    create_policy(api_client, rule, source)
    api_client.post(
        f"/api/v1/rules/{rule['id']}/correlation-demo",
        json={"visual_people": 1, "authorized_entries": 1},
    )
    processed = api_client.post(
        "/api/v1/agent/correlation-evaluations/process-next",
        headers=AGENT_HEADERS,
    )
    assert processed.status_code == 200
    assert processed.json()["status"] == "clear"
    assert api_client.get("/api/v1/alerts").json() == []


def test_normalized_observation_ingest_is_idempotent(api_client: TestClient) -> None:
    source = create_source(api_client, "idempotent")
    payload = {
        "source_event_id": "badge-reader-event-1",
        "observation_type": "access_granted",
        "occurred_at": datetime.now(UTC).isoformat(),
        "entity_key": "anonymous-card-1",
        "attributes": {"reader": "lobby"},
    }
    first = api_client.post(
        f"/api/v1/context-sources/{source['id']}/observations", json=payload
    )
    second = api_client.post(
        f"/api/v1/context-sources/{source['id']}/observations", json=payload
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert len(api_client.get("/api/v1/context-observations").json()) == 1
