from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import socket
import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, HttpUrl, ValidationError

from video_intelligence_alerts.config import AlertWorkerSettings, get_settings

logger = logging.getLogger(__name__)


class AlertAssignment(BaseModel):
    delivery_id: str
    alert_id: str
    event_id: str
    webhook_url: HttpUrl
    signing_secret: str
    timeout_seconds: float = Field(gt=0, le=60)
    payload: dict[str, Any]


class ActionAssignment(BaseModel):
    execution_id: str
    connector_type: Literal[
        "mock", "generic_webhook", "messaging_webhook", "ticket_webhook", "telegram"
    ]
    endpoint_url: HttpUrl | None = None
    credential: str
    configuration: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = Field(gt=0, le=60)
    idempotency_key: str
    action_type: str
    payload: dict[str, Any]


def canonical_body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def signed_headers(assignment: AlertAssignment, body: bytes, timestamp: int) -> dict[str, str]:
    message = str(timestamp).encode() + b"." + body
    signature = hmac.new(assignment.signing_secret.encode(), message, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "Idempotency-Key": assignment.delivery_id,
        "X-Artae-Event": "video.alert.created",
        "X-Artae-Timestamp": str(timestamp),
        "X-Artae-Signature": f"v1={signature}",
    }


def action_headers(assignment: ActionAssignment, body: bytes, timestamp: int) -> dict[str, str]:
    message = str(timestamp).encode() + b"." + body
    signature = hmac.new(assignment.credential.encode(), message, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "Idempotency-Key": assignment.idempotency_key,
        "X-Artae-Action": assignment.action_type,
        "X-Artae-Timestamp": str(timestamp),
        "X-Artae-Signature": f"v1={signature}",
    }


def adapt_action_payload(assignment: ActionAssignment) -> dict[str, Any]:
    if assignment.connector_type == "messaging_webhook":
        return {
            "text": assignment.payload.get("summary", "Camera alert"),
            "metadata": {
                "event_id": assignment.payload.get("event_id"),
                "camera": assignment.payload.get("camera_name"),
                "confidence": assignment.payload.get("confidence"),
            },
        }
    if assignment.connector_type == "ticket_webhook":
        return {
            "title": assignment.payload.get("title", "Camera incident"),
            "description": assignment.payload.get("summary", "Camera incident"),
            "external_id": assignment.idempotency_key,
            "severity": assignment.payload.get("severity", "warning"),
            "metadata": assignment.payload,
        }
    return assignment.payload


def telegram_message_text(assignment: ActionAssignment) -> str:
    payload = assignment.payload
    heading = "Artae Vision test" if payload.get("is_test") is True else "Artae Vision alert"
    lines = [
        heading,
        str(payload.get("title", "Camera alert")),
        str(payload.get("summary", "A camera event was confirmed.")),
    ]
    if camera := payload.get("camera_name"):
        lines.append(f"Camera: {camera}")
    confidence = payload.get("confidence")
    if isinstance(confidence, (int, float)):
        lines.append(f"Confidence: {round(float(confidence) * 100)}%")
    return "\n".join(lines)[:4096]


def execute_telegram_action(assignment: ActionAssignment, client: httpx.Client) -> dict[str, Any]:
    chat_id = assignment.configuration.get("chat_id")
    if not isinstance(chat_id, (str, int)) or not str(chat_id).strip():
        return {"outcome": "permanent_failure", "error": "Telegram chat ID is missing"}
    token = assignment.credential.strip()
    if not token or ":" not in token:
        return {"outcome": "permanent_failure", "error": "Telegram bot token is invalid"}
    try:
        response = client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": str(chat_id), "text": telegram_message_text(assignment)},
            timeout=assignment.timeout_seconds,
        )
        classification = classify_response(response.status_code)
        try:
            telegram_result = response.json()
        except ValueError:
            telegram_result = {}
        if classification == "delivered" and telegram_result.get("ok") is not True:
            classification = "permanent_failure"
        outcome = {
            "delivered": "succeeded",
            "retryable": "retryable",
            "permanent_failure": "permanent_failure",
        }[classification]
        description = telegram_result.get("description")
        error = None if outcome == "succeeded" else str(description or "Telegram rejected message")
        return {"outcome": outcome, "status_code": response.status_code, "error": error}
    except httpx.HTTPError as exc:
        # Telegram requires the secret token in the URL. Never serialize the exception,
        # because httpx includes that URL in some error messages.
        return {
            "outcome": "retryable",
            "error": f"Telegram request failed ({type(exc).__name__})",
        }


def classify_response(status_code: int) -> Literal["delivered", "retryable", "permanent_failure"]:
    if 200 <= status_code < 300:
        return "delivered"
    if status_code in {408, 425, 429} or status_code >= 500:
        return "retryable"
    return "permanent_failure"


def claim_assignment(
    client: httpx.Client, base_url: str, headers: dict[str, str], worker_id: str
) -> AlertAssignment | None:
    response = client.post(
        f"{base_url}/api/v1/agent/alert-deliveries/claim",
        headers=headers,
        json={"worker_id": worker_id},
    )
    if response.status_code == 204:
        return None
    response.raise_for_status()
    return AlertAssignment.model_validate(response.json())


def deliver_assignment(assignment: AlertAssignment, client: httpx.Client) -> dict[str, Any]:
    body = canonical_body(assignment.payload)
    headers = signed_headers(assignment, body, int(time.time()))
    try:
        response = client.post(
            str(assignment.webhook_url),
            content=body,
            headers=headers,
            timeout=assignment.timeout_seconds,
        )
        outcome = classify_response(response.status_code)
        error = None if outcome == "delivered" else f"Webhook returned HTTP {response.status_code}"
        return {"outcome": outcome, "status_code": response.status_code, "error": error}
    except httpx.HTTPError as exc:
        return {"outcome": "retryable", "error": str(exc)}


def claim_action(
    client: httpx.Client, base_url: str, headers: dict[str, str], worker_id: str
) -> ActionAssignment | None:
    response = client.post(
        f"{base_url}/api/v1/agent/action-executions/claim",
        headers=headers,
        json={"worker_id": worker_id},
    )
    if response.status_code == 204:
        return None
    response.raise_for_status()
    return ActionAssignment.model_validate(response.json())


def execute_action(assignment: ActionAssignment, client: httpx.Client) -> dict[str, Any]:
    if assignment.connector_type == "mock":
        return {"outcome": "succeeded", "status_code": 204, "error": None}
    if assignment.connector_type == "telegram":
        return execute_telegram_action(assignment, client)
    if assignment.endpoint_url is None:
        return {
            "outcome": "permanent_failure",
            "error": "Remote connector assignment has no endpoint URL",
        }
    body = canonical_body(adapt_action_payload(assignment))
    headers = action_headers(assignment, body, int(time.time()))
    try:
        response = client.post(
            str(assignment.endpoint_url),
            content=body,
            headers=headers,
            timeout=assignment.timeout_seconds,
        )
        classification = classify_response(response.status_code)
        outcome = {
            "delivered": "succeeded",
            "retryable": "retryable",
            "permanent_failure": "permanent_failure",
        }[classification]
        error = (
            None if outcome == "succeeded" else f"Connector returned HTTP {response.status_code}"
        )
        return {"outcome": outcome, "status_code": response.status_code, "error": error}
    except httpx.HTTPError as exc:
        return {"outcome": "retryable", "error": str(exc)}


def report_action_result(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    worker_id: str,
    assignment: ActionAssignment,
    result: dict[str, Any],
) -> None:
    response = client.post(
        f"{base_url}/api/v1/agent/action-executions/{assignment.execution_id}/result",
        headers=headers,
        json={"worker_id": worker_id, **result},
    )
    response.raise_for_status()


def report_result(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    worker_id: str,
    assignment: AlertAssignment,
    result: dict[str, Any],
) -> None:
    response = client.post(
        f"{base_url}/api/v1/agent/alert-deliveries/{assignment.delivery_id}/result",
        headers=headers,
        json={"worker_id": worker_id, **result},
    )
    response.raise_for_status()


def process_correlation(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
) -> dict[str, Any] | None:
    response = client.post(
        f"{base_url}/api/v1/agent/correlation-evaluations/process-next",
        headers=headers,
    )
    if response.status_code == 204:
        return None
    response.raise_for_status()
    return response.json()


def evaluate_operational_health(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
) -> dict[str, int]:
    response = client.post(
        f"{base_url}/api/v1/agent/operational-health/evaluate",
        headers=headers,
    )
    response.raise_for_status()
    result = response.json()
    return {
        "evaluated_resources": int(result["evaluated_resources"]),
        "active_incidents": int(result["active_incidents"]),
        "opened_incidents": int(result["opened_incidents"]),
        "resolved_incidents": int(result["resolved_incidents"]),
    }


def reconcile_active_learning(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
) -> dict[str, int]:
    response = client.post(
        f"{base_url}/api/v1/active-learning/agent/reconcile",
        headers=headers,
    )
    response.raise_for_status()
    return {key: int(value) for key, value in response.json().items()}


def run_worker(
    settings: AlertWorkerSettings,
    *,
    once: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> int:
    base_url = str(settings.control_plane_url).rstrip("/")
    worker_id = settings.worker_id or f"{socket.gethostname()}-{os.getpid()}"
    control_headers = {"X-Agent-Key": settings.agent_key.get_secret_value()}
    logger.info("Alert worker ready: worker=%s", worker_id)
    next_health_evaluation = 0.0
    next_evidence_sampling = 0.0
    with httpx.Client(
        timeout=settings.control_plane_timeout_seconds,
        transport=transport,
    ) as client:
        while True:
            handled = False
            current_time = time.monotonic()
            if current_time >= next_health_evaluation:
                try:
                    health = evaluate_operational_health(client, base_url, control_headers)
                    if health["opened_incidents"] or health["resolved_incidents"]:
                        logger.info(
                            "Operational health changed: active=%d opened=%d resolved=%d",
                            health["active_incidents"],
                            health["opened_incidents"],
                            health["resolved_incidents"],
                        )
                except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                    logger.warning("Operational health evaluation failed: %s", exc)
                    if once:
                        return 1
                next_health_evaluation = current_time + settings.health_evaluation_seconds
            if current_time >= next_evidence_sampling:
                try:
                    sampling = reconcile_active_learning(client, base_url, control_headers)
                    created = (
                        sampling["candidate_samples_created"] + sampling["normal_samples_created"]
                    )
                    if (
                        created
                        or sampling["labels_synchronized"]
                        or sampling["expired_samples_skipped"]
                    ):
                        logger.info(
                            "Active evidence reconciled: created=%d synchronized=%d expired=%d",
                            created,
                            sampling["labels_synchronized"],
                            sampling["expired_samples_skipped"],
                        )
                except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                    logger.warning("Active evidence reconciliation failed: %s", exc)
                next_evidence_sampling = current_time + settings.evidence_sampling_seconds
            try:
                assignment = claim_assignment(client, base_url, control_headers, worker_id)
                if assignment is not None:
                    result = deliver_assignment(assignment, client)
                    report_result(client, base_url, control_headers, worker_id, assignment, result)
                    logger.info(
                        "Alert delivery completed: delivery=%s outcome=%s",
                        assignment.delivery_id,
                        result["outcome"],
                    )
                    handled = True
                else:
                    action = claim_action(client, base_url, control_headers, worker_id)
                    if action is not None:
                        result = execute_action(action, client)
                        report_action_result(
                            client,
                            base_url,
                            control_headers,
                            worker_id,
                            action,
                            result,
                        )
                        logger.info(
                            "Guarded action completed: execution=%s outcome=%s",
                            action.execution_id,
                            result["outcome"],
                        )
                        handled = True
                    else:
                        correlation = process_correlation(
                            client,
                            base_url,
                            control_headers,
                        )
                        if correlation is not None:
                            logger.info(
                                "Temporal correlation completed: evaluation=%s status=%s",
                                correlation["id"],
                                correlation["status"],
                            )
                            handled = True
            except httpx.HTTPError as exc:
                logger.warning("Alert control-plane request failed: %s", exc)
                if once:
                    return 1
            if once:
                return 0
            if not handled:
                time.sleep(settings.poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deliver durable signed alert webhooks.")
    parser.add_argument("--once", action="store_true", help="Handle at most one delivery")
    args = parser.parse_args()
    try:
        settings = get_settings()
    except ValidationError as exc:
        logging.basicConfig(level=logging.ERROR)
        logger.error("Invalid alert-worker configuration:\n%s", exc)
        return 2
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # Telegram authenticates with a bot token embedded in the request path. Prevent
    # the HTTP client's informational request log from exposing that secret.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        return run_worker(settings, once=args.once)
    except KeyboardInterrupt:
        logger.info("Alert worker interrupted")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
