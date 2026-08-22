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
    connector_type: Literal["mock", "generic_webhook", "messaging_webhook", "ticket_webhook"]
    endpoint_url: HttpUrl | None = None
    credential: str
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


def run_worker(settings: AlertWorkerSettings, *, once: bool = False) -> int:
    base_url = str(settings.control_plane_url).rstrip("/")
    worker_id = settings.worker_id or f"{socket.gethostname()}-{os.getpid()}"
    control_headers = {"X-Agent-Key": settings.agent_key.get_secret_value()}
    logger.info("Alert worker ready: worker=%s", worker_id)
    with httpx.Client(timeout=settings.control_plane_timeout_seconds) as client:
        while True:
            handled = False
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
    try:
        return run_worker(settings, once=args.once)
    except KeyboardInterrupt:
        logger.info("Alert worker interrupted")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
