import hashlib
import hmac
import json

import httpx
from video_intelligence_alerts.config import AlertWorkerSettings
from video_intelligence_alerts.worker import (
    ActionAssignment,
    AlertAssignment,
    action_headers,
    adapt_action_payload,
    canonical_body,
    classify_response,
    deliver_assignment,
    evaluate_operational_health,
    execute_action,
    run_worker,
    signed_headers,
)


def assignment() -> AlertAssignment:
    return AlertAssignment(
        delivery_id="delivery-1",
        alert_id="alert-1",
        event_id="event-1",
        webhook_url="https://receiver.test/hooks",
        signing_secret="signing-secret-value",
        timeout_seconds=5,
        payload={"z": 2, "a": {"message": "person entered"}},
    )


def test_signature_covers_timestamp_and_canonical_exact_body() -> None:
    job = assignment()
    body = canonical_body(job.payload)
    headers = signed_headers(job, body, 1_700_000_000)
    expected = hmac.new(
        b"signing-secret-value",
        b"1700000000." + body,
        hashlib.sha256,
    ).hexdigest()

    assert body == b'{"a":{"message":"person entered"},"z":2}'
    assert headers["X-Artae-Signature"] == f"v1={expected}"
    assert headers["Idempotency-Key"] == "delivery-1"


def test_delivery_sends_signed_body_and_classifies_retryable_response() -> None:
    received: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["body"] = request.content
        received["headers"] = dict(request.headers)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = deliver_assignment(assignment(), client)

    assert json.loads(received["body"]) == assignment().payload  # type: ignore[arg-type]
    assert "x-artae-signature" in received["headers"]  # type: ignore[operator]
    assert result == {
        "outcome": "retryable",
        "status_code": 503,
        "error": "Webhook returned HTTP 503",
    }
    assert classify_response(204) == "delivered"
    assert classify_response(400) == "permanent_failure"
    assert classify_response(429) == "retryable"


def action_assignment(connector_type: str = "generic_webhook") -> ActionAssignment:
    return ActionAssignment(
        execution_id="execution-1",
        connector_type=connector_type,
        endpoint_url=None
        if connector_type == "mock"
        else "https://receiver.test/actions",
        credential="connector-signing-secret",
        timeout_seconds=5,
        idempotency_key="action:execution-1",
        action_type="send_notification",
        payload={
            "summary": "Person entered",
            "event_id": "event-1",
            "confidence": 0.91,
        },
    )


def test_mock_action_has_no_network_side_effect() -> None:
    def fail_if_called(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Unexpected network request: {request.url}")

    with httpx.Client(transport=httpx.MockTransport(fail_if_called)) as client:
        result = execute_action(action_assignment("mock"), client)

    assert result == {"outcome": "succeeded", "status_code": 204, "error": None}


def test_messaging_and_ticket_adapters_use_idempotent_signed_requests() -> None:
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(201)

    messaging = action_assignment("messaging_webhook")
    ticket = action_assignment("ticket_webhook").model_copy(
        update={"action_type": "create_ticket"}
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert execute_action(messaging, client)["outcome"] == "succeeded"
        assert execute_action(ticket, client)["outcome"] == "succeeded"

    messaging_body = json.loads(received[0].content)
    ticket_body = json.loads(received[1].content)
    assert messaging_body["text"] == "Person entered"
    assert ticket_body["external_id"] == "action:execution-1"
    assert received[0].headers["Idempotency-Key"] == "action:execution-1"
    assert "X-Artae-Signature" in received[0].headers
    body = canonical_body(adapt_action_payload(messaging))
    assert action_headers(messaging, body, 1)["X-Artae-Action"] == "send_notification"


def test_telegram_adapter_sends_readable_camera_alert() -> None:
    received: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["url"] = str(request.url)
        received["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    telegram = action_assignment("telegram").model_copy(
        update={
            "endpoint_url": None,
            "credential": "123456:telegram-bot-token-value",
            "configuration": {"chat_id": "-100123456"},
            "payload": {
                "title": "Camera alert: Restricted entrance",
                "summary": "person matched 'Restricted entrance' in Front Door",
                "camera_name": "Front entrance",
                "confidence": 0.92,
                "is_test": False,
            },
        }
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute_action(telegram, client)

    assert result == {"outcome": "succeeded", "status_code": 200, "error": None}
    assert received["url"] == (
        "https://api.telegram.org/bot123456:telegram-bot-token-value/sendMessage"
    )
    assert received["body"] == {
        "chat_id": "-100123456",
        "text": (
            "Artae Vision alert\nCamera alert: Restricted entrance\n"
            "person matched 'Restricted entrance' in Front Door\n"
            "Camera: Front entrance\nConfidence: 92%"
        ),
    }


def test_telegram_transport_error_does_not_expose_bot_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("failed with secret URL", request=request)

    telegram = action_assignment("telegram").model_copy(
        update={
            "endpoint_url": None,
            "credential": "123456:do-not-leak-this-token",
            "configuration": {"chat_id": "123"},
        }
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute_action(telegram, client)

    assert result["outcome"] == "retryable"
    assert "do-not-leak-this-token" not in str(result)


def test_operational_health_evaluation_uses_internal_agent_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agent/operational-health/evaluate"
        assert request.headers["X-Agent-Key"] == "agent-secret"
        return httpx.Response(
            200,
            json={
                "evaluated_resources": 4,
                "active_incidents": 1,
                "opened_incidents": 1,
                "resolved_incidents": 0,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = evaluate_operational_health(
            client,
            "http://control.test",
            {"X-Agent-Key": "agent-secret"},
        )

    assert result == {
        "evaluated_resources": 4,
        "active_incidents": 1,
        "opened_incidents": 1,
        "resolved_incidents": 0,
    }


def test_idle_operations_worker_runs_health_watchdog_automatically() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/operational-health/evaluate"):
            return httpx.Response(
                200,
                json={
                    "evaluated_resources": 2,
                    "active_incidents": 0,
                    "opened_incidents": 0,
                    "resolved_incidents": 0,
                },
            )
        return httpx.Response(204)

    result = run_worker(
        AlertWorkerSettings(
            control_plane_url="http://control.test",
            agent_key="test-agent-key-123456",
            worker_id="operations-worker",
        ),
        once=True,
        transport=httpx.MockTransport(handler),
    )

    assert result == 0
    assert paths[0] == "/api/v1/agent/operational-health/evaluate"
