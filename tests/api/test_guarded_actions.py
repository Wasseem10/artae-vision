from fastapi.testclient import TestClient

AGENT_HEADERS = {"X-Agent-Key": "test-agent-key-123456789"}


def create_rule(client: TestClient, suffix: str = "one") -> dict:
    camera = client.post(
        "/api/v1/cameras",
        json={"name": f"action-camera-{suffix}", "source_uri": "0"},
    ).json()
    zone = client.post(
        "/api/v1/zones",
        json={
            "camera_id": camera["id"],
            "name": "entry",
            "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}],
        },
    ).json()
    return client.post(
        "/api/v1/rules",
        json={
            "camera_id": camera["id"],
            "zone_id": zone["id"],
            "key": f"entry-{suffix}",
            "name": "Entry alert",
            "duration_seconds": 1,
        },
    ).json()


def create_mock_connector(
    client: TestClient, suffix: str = "one", max_attempts: int = 3
) -> dict:
    response = client.post(
        "/api/v1/connectors",
        json={
            "name": f"Safe mock {suffix}",
            "connector_type": "mock",
            "credential": "encrypted-mock-secret",
            "scopes": ["notifications:write", "tickets:write", "webhooks:invoke"],
            "max_attempts": max_attempts,
        },
    )
    assert response.status_code == 201, response.text
    assert "credential" not in response.text
    return response.json()


def create_test_alert(client: TestClient, rule_id: str) -> dict:
    response = client.post(
        f"/api/v1/rules/{rule_id}/test-alert",
        json={"deliver_outbound": True},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_low_risk_action_is_idempotent_leased_and_completed(
    api_client: TestClient,
) -> None:
    rule = create_rule(api_client)
    connector = create_mock_connector(api_client)
    binding = api_client.post(
        f"/api/v1/rules/{rule['id']}/actions",
        json={
            "connector_id": connector["id"],
            "action_type": "send_notification",
            "rate_limit_per_minute": 10,
        },
    )
    assert binding.status_code == 201, binding.text
    assert binding.json()["risk_level"] == "low"
    assert binding.json()["approval_mode"] == "automatic"

    create_test_alert(api_client, rule["id"])
    executions = api_client.get("/api/v1/action-executions").json()
    assert len(executions) == 1
    assert executions[0]["status"] == "queued"

    claim = api_client.post(
        "/api/v1/agent/action-executions/claim",
        headers=AGENT_HEADERS,
        json={"worker_id": "action-worker"},
    )
    assert claim.status_code == 200, claim.text
    assignment = claim.json()
    assert assignment["connector_type"] == "mock"
    assert assignment["credential"] == "encrypted-mock-secret"
    assert assignment["idempotency_key"].startswith("action:")
    duplicate_claim = api_client.post(
        "/api/v1/agent/action-executions/claim",
        headers=AGENT_HEADERS,
        json={"worker_id": "other-worker"},
    )
    assert duplicate_claim.status_code == 204

    result = api_client.post(
        f"/api/v1/agent/action-executions/{assignment['execution_id']}/result",
        headers=AGENT_HEADERS,
        json={"worker_id": "action-worker", "outcome": "succeeded", "status_code": 204},
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "succeeded"
    assert result.json()["attempt_count"] == 1


def test_medium_risk_action_requires_approval_and_dead_letters(
    api_client: TestClient,
) -> None:
    rule = create_rule(api_client, "ticket")
    connector = create_mock_connector(api_client, "ticket", max_attempts=1)
    binding = api_client.post(
        f"/api/v1/rules/{rule['id']}/actions",
        json={"connector_id": connector["id"], "action_type": "create_ticket"},
    ).json()
    assert binding["risk_level"] == "medium"
    assert binding["approval_mode"] == "manual"

    create_test_alert(api_client, rule["id"])
    execution = api_client.get("/api/v1/action-executions").json()[0]
    assert execution["status"] == "awaiting_approval"
    assert (
        api_client.post(
            "/api/v1/agent/action-executions/claim",
            headers=AGENT_HEADERS,
            json={"worker_id": "action-worker"},
        ).status_code
        == 204
    )

    approved = api_client.post(
        f"/api/v1/action-executions/{execution['id']}/approve", json={}
    )
    assert approved.status_code == 200
    assert approved.json()["approved_by"] == "local-dashboard-operator"
    assignment = api_client.post(
        "/api/v1/agent/action-executions/claim",
        headers=AGENT_HEADERS,
        json={"worker_id": "action-worker"},
    ).json()
    dead = api_client.post(
        f"/api/v1/agent/action-executions/{execution['id']}/result",
        headers=AGENT_HEADERS,
        json={
            "worker_id": "action-worker",
            "outcome": "permanent_failure",
            "status_code": 400,
            "error": "Rejected by ticket system",
        },
    )
    assert assignment["action_type"] == "create_ticket"
    assert dead.json()["status"] == "dead_lettered"

    retried = api_client.post(f"/api/v1/action-executions/{execution['id']}/retry")
    assert retried.json()["status"] == "queued"
    assert retried.json()["attempt_count"] == 0
    assert retried.json()["manual_retry_count"] == 1

    second_alert = create_test_alert(api_client, rule["id"])
    newest = api_client.get("/api/v1/action-executions").json()[0]
    denied = api_client.post(
        f"/api/v1/action-executions/{newest['id']}/deny",
        json={"reason": "Not relevant"},
    )
    assert second_alert["id"] == newest["alert_id"]
    assert denied.json()["status"] == "denied"
    assert denied.json()["denial_reason"] == "Not relevant"


def test_rate_limit_and_alert_transition_suppress_actions(
    api_client: TestClient,
) -> None:
    rule = create_rule(api_client, "rate")
    connector = create_mock_connector(api_client, "rate")
    api_client.post(
        f"/api/v1/rules/{rule['id']}/actions",
        json={
            "connector_id": connector["id"],
            "action_type": "send_notification",
            "rate_limit_per_minute": 1,
        },
    )
    create_test_alert(api_client, rule["id"])
    first = api_client.post(
        "/api/v1/agent/action-executions/claim",
        headers=AGENT_HEADERS,
        json={"worker_id": "rate-worker"},
    ).json()
    api_client.post(
        f"/api/v1/agent/action-executions/{first['execution_id']}/result",
        headers=AGENT_HEADERS,
        json={"worker_id": "rate-worker", "outcome": "succeeded"},
    )
    second_alert = create_test_alert(api_client, rule["id"])
    limited = api_client.post(
        "/api/v1/agent/action-executions/claim",
        headers=AGENT_HEADERS,
        json={"worker_id": "rate-worker"},
    )
    assert limited.status_code == 204
    second = api_client.get("/api/v1/action-executions").json()[0]
    assert second["status"] == "retrying"
    assert "rate limit" in second["last_error"]

    acknowledged = api_client.post(
        f"/api/v1/alerts/{second_alert['id']}/acknowledge",
        json={"actor": "operator"},
    )
    assert acknowledged.status_code == 200
    assert (
        api_client.get("/api/v1/action-executions").json()[0]["status"] == "suppressed"
    )


def test_scopes_and_unavailable_physical_actions_are_enforced(
    api_client: TestClient,
) -> None:
    rule = create_rule(api_client, "scope")
    invalid_scope = api_client.post(
        "/api/v1/connectors",
        json={
            "name": "Messaging only",
            "connector_type": "messaging_webhook",
            "endpoint_url": "https://hooks.example.test/message",
            "credential": "message-secret",
            "scopes": ["tickets:write"],
        },
    )
    assert invalid_scope.status_code == 422

    connector = create_mock_connector(api_client, "scope")
    physical = api_client.post(
        f"/api/v1/rules/{rule['id']}/actions",
        json={"connector_id": connector["id"], "action_type": "control_physical"},
    )
    assert physical.status_code == 409
    assert "disabled" in physical.text


def test_telegram_connector_keeps_token_secret_and_queues_outbound_test(
    api_client: TestClient,
) -> None:
    rule = create_rule(api_client, "telegram")
    token = "123456789:telegram-bot-token-secret-value"
    created = api_client.post(
        "/api/v1/connectors",
        json={
            "name": "Security Telegram",
            "connector_type": "telegram",
            "credential": token,
            "configuration": {"chat_id": "-100123456789"},
            "scopes": ["notifications:write"],
        },
    )
    assert created.status_code == 201, created.text
    connector = created.json()
    assert connector["endpoint_url"] is None
    assert connector["configuration"] == {"chat_id": "-100123456789"}
    assert token not in created.text

    binding = api_client.post(
        f"/api/v1/rules/{rule['id']}/actions",
        json={"connector_id": connector["id"], "action_type": "send_notification"},
    )
    assert binding.status_code == 201, binding.text
    outbound_test = api_client.post(
        f"/api/v1/rules/{rule['id']}/test-alert",
        json={"deliver_outbound": True, "connector_id": connector["id"]},
    )
    assert outbound_test.status_code == 201, outbound_test.text

    claim = api_client.post(
        "/api/v1/agent/action-executions/claim",
        headers=AGENT_HEADERS,
        json={"worker_id": "telegram-worker"},
    )
    assert claim.status_code == 200, claim.text
    assignment = claim.json()
    assert assignment["connector_type"] == "telegram"
    assert assignment["credential"] == token
    assert assignment["configuration"] == {"chat_id": "-100123456789"}
    assert assignment["payload"]["is_test"] is True


def test_telegram_connector_requires_bot_token_and_chat_id(
    api_client: TestClient,
) -> None:
    missing_chat = api_client.post(
        "/api/v1/connectors",
        json={
            "name": "Broken Telegram",
            "connector_type": "telegram",
            "credential": "123456789:telegram-bot-token-secret-value",
            "scopes": ["notifications:write"],
        },
    )
    assert missing_chat.status_code == 422
    assert "chat_id" in missing_chat.text
