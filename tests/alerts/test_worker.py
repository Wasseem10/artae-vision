import hashlib
import hmac
import json

import httpx
from video_intelligence_alerts.worker import (
    ActionAssignment,
    AlertAssignment,
    action_headers,
    adapt_action_payload,
    canonical_body,
    classify_response,
    deliver_assignment,
    execute_action,
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
