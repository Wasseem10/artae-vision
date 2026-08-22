import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

AGENT_HEADERS = {"X-Agent-Key": "test-agent-key-123456789"}
DASHBOARD_HEADERS = {"X-Dashboard-Key": "test-dashboard-key-12345"}


def create_rule(client: TestClient) -> dict:
    camera = client.post(
        "/api/v1/cameras", json={"name": "alert-camera", "source_uri": "webcam:0"}
    ).json()
    zone = client.post(
        "/api/v1/zones",
        json={
            "camera_id": camera["id"],
            "name": "front-door",
            "points": [
                {"x": 0.1, "y": 0.1},
                {"x": 0.9, "y": 0.1},
                {"x": 0.9, "y": 0.9},
            ],
        },
    ).json()
    rule = client.post(
        "/api/v1/rules",
        json={
            "camera_id": camera["id"],
            "zone_id": zone["id"],
            "key": "door-presence",
            "name": "Person at front door",
            "duration_seconds": 2,
        },
    ).json()
    return client.patch(
        f"/api/v1/rules/{rule['id']}/status", json={"status": "active"}
    ).json()


def event_payload() -> dict:
    return {
        "schema_version": 2,
        "id": str(uuid.uuid4()),
        "event_type": "zone_presence",
        "rule_id": "door-presence",
        "camera_id": "alert-camera",
        "track_id": 12,
        "object_class": "person",
        "zone_name": "front-door",
        "entered_at_seconds": 1,
        "occurred_at_seconds": 3,
        "dwell_seconds": 2,
        "confidence": 0.94,
        "occurred_at": datetime.now(UTC).isoformat(),
        "clip_path": "artifacts/events/door.mp4",
    }


def create_channel(client: TestClient) -> dict:
    unauthorized = client.post(
        "/api/v1/alert-channels",
        headers={"X-Dashboard-Key": ""},
        json={
            "name": "operations",
            "webhook_url": "https://hooks.example.test/video",
            "signing_secret": "super-secret-signing-value",
        },
    )
    assert unauthorized.status_code == 401
    response = client.post(
        "/api/v1/alert-channels",
        headers=DASHBOARD_HEADERS,
        json={
            "name": "operations",
            "webhook_url": "https://hooks.example.test/video",
            "signing_secret": "super-secret-signing-value",
            "max_attempts": 3,
        },
    )
    assert response.status_code == 201
    assert "secret" not in response.text
    return response.json()


def test_event_atomically_creates_routed_alert_and_idempotent_delivery(
    api_client: TestClient,
) -> None:
    rule = create_rule(api_client)
    channel = create_channel(api_client)
    route = api_client.post(
        f"/api/v1/rules/{rule['id']}/alert-routes",
        headers=DASHBOARD_HEADERS,
        json={"channel_id": channel["id"], "cooldown_seconds": 60},
    )
    assert route.status_code == 201

    payload = event_payload()
    created = api_client.post(
        "/api/v1/agent/events", headers=AGENT_HEADERS, json=payload
    )
    assert created.status_code == 201
    duplicate = api_client.post(
        "/api/v1/agent/events", headers=AGENT_HEADERS, json=payload
    )
    assert duplicate.status_code == 200

    alerts = api_client.get("/api/v1/alerts", headers=DASHBOARD_HEADERS).json()
    assert len(alerts) == 1
    assert alerts[0]["status"] == "open"
    assert alerts[0]["deliveries"][0]["status"] == "queued"

    claim = api_client.post(
        "/api/v1/agent/alert-deliveries/claim",
        headers=AGENT_HEADERS,
        json={"worker_id": "alerts-1"},
    )
    assert claim.status_code == 200
    assignment = claim.json()
    assert assignment["signing_secret"] == "super-secret-signing-value"
    assert assignment["payload"]["event"]["id"] == created.json()["id"]
    result = api_client.post(
        f"/api/v1/agent/alert-deliveries/{assignment['delivery_id']}/result",
        headers=AGENT_HEADERS,
        json={"worker_id": "alerts-1", "outcome": "delivered", "status_code": 204},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "delivered"

    second = api_client.post(
        "/api/v1/agent/events", headers=AGENT_HEADERS, json=event_payload()
    )
    assert second.status_code == 201
    alerts = api_client.get("/api/v1/alerts", headers=DASHBOARD_HEADERS).json()
    assert alerts[0]["deliveries"][0]["status"] == "suppressed"


def test_acknowledging_alert_cancels_delayed_escalation(api_client: TestClient) -> None:
    rule = create_rule(api_client)
    channel = create_channel(api_client)
    api_client.post(
        f"/api/v1/rules/{rule['id']}/alert-routes",
        headers=DASHBOARD_HEADERS,
        json={"channel_id": channel["id"], "delay_seconds": 60},
    )
    api_client.post("/api/v1/agent/events", headers=AGENT_HEADERS, json=event_payload())
    alert = api_client.get("/api/v1/alerts", headers=DASHBOARD_HEADERS).json()[0]

    acknowledged = api_client.post(
        f"/api/v1/alerts/{alert['id']}/acknowledge",
        headers=DASHBOARD_HEADERS,
        json={"actor": "night-operator"},
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged"
    assert acknowledged.json()["deliveries"][0]["status"] == "suppressed"
    claim = api_client.post(
        "/api/v1/agent/alert-deliveries/claim",
        headers=AGENT_HEADERS,
        json={"worker_id": "alerts-1"},
    )
    assert claim.status_code == 204


def test_operator_can_create_safe_dashboard_only_test_alert(
    api_client: TestClient,
) -> None:
    rule = create_rule(api_client)
    channel = create_channel(api_client)
    route = api_client.post(
        f"/api/v1/rules/{rule['id']}/alert-routes",
        headers=DASHBOARD_HEADERS,
        json={"channel_id": channel["id"]},
    )
    assert route.status_code == 201

    with api_client.websocket_connect(
        f"/api/v1/ws/events?token={DASHBOARD_HEADERS['X-Dashboard-Key']}"
    ) as websocket:
        assert websocket.receive_json() == {"type": "connected"}
        created = api_client.post(
            f"/api/v1/rules/{rule['id']}/test-alert",
            headers=DASHBOARD_HEADERS,
            json={"deliver_outbound": False},
        )
        broadcast = websocket.receive_json()

    assert created.status_code == 201
    assert created.json()["status"] == "open"
    assert created.json()["event"]["details"]["test"] is True
    assert created.json()["deliveries"] == []
    assert broadcast["type"] == "event.created"
    assert broadcast["data"]["details"]["test"] is True

    claim = api_client.post(
        "/api/v1/agent/alert-deliveries/claim",
        headers=AGENT_HEADERS,
        json={"worker_id": "alerts-1"},
    )
    assert claim.status_code == 204
