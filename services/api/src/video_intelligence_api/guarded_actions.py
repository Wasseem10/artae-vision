"""Deterministic connector scopes, risk levels, and payload construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from video_intelligence_api.models import (
    ActionApprovalMode,
    ActionRiskLevel,
    ConnectorType,
    Event,
    Rule,
)


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    action_type: str
    label: str
    required_scope: str
    risk_level: ActionRiskLevel
    default_approval: ActionApprovalMode
    available: bool = True


ACTION_DEFINITIONS = {
    definition.action_type: definition
    for definition in (
        ActionDefinition(
            "send_notification",
            "Send notification",
            "notifications:write",
            ActionRiskLevel.LOW,
            ActionApprovalMode.AUTOMATIC,
        ),
        ActionDefinition(
            "create_ticket",
            "Create ticket",
            "tickets:write",
            ActionRiskLevel.MEDIUM,
            ActionApprovalMode.MANUAL,
        ),
        ActionDefinition(
            "invoke_webhook",
            "Invoke webhook",
            "webhooks:invoke",
            ActionRiskLevel.MEDIUM,
            ActionApprovalMode.MANUAL,
        ),
        ActionDefinition(
            "control_physical",
            "Control physical system",
            "physical:control",
            ActionRiskLevel.HIGH,
            ActionApprovalMode.MANUAL,
            available=False,
        ),
    )
}

CONNECTOR_SCOPES = {
    ConnectorType.MOCK: frozenset({"notifications:write", "tickets:write", "webhooks:invoke"}),
    ConnectorType.GENERIC_WEBHOOK: frozenset({"webhooks:invoke"}),
    ConnectorType.MESSAGING_WEBHOOK: frozenset({"notifications:write"}),
    ConnectorType.TICKET_WEBHOOK: frozenset({"tickets:write"}),
    ConnectorType.TELEGRAM: frozenset({"notifications:write"}),
}


def validate_connector_scopes(connector_type: ConnectorType, scopes: list[str]) -> list[str]:
    normalized = list(dict.fromkeys(scope.strip().casefold() for scope in scopes))
    unsupported = [scope for scope in normalized if scope not in CONNECTOR_SCOPES[connector_type]]
    if unsupported:
        raise ValueError(
            f"Connector type '{connector_type.value}' cannot grant: {', '.join(unsupported)}"
        )
    return normalized


def action_definition(action_type: str) -> ActionDefinition:
    definition = ACTION_DEFINITIONS.get(action_type)
    if definition is None:
        raise ValueError(f"Unknown action type '{action_type}'")
    return definition


def action_registry_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "actions": [
            {
                "action_type": definition.action_type,
                "label": definition.label,
                "required_scope": definition.required_scope,
                "risk_level": definition.risk_level.value,
                "default_approval": definition.default_approval.value,
                "available": definition.available,
            }
            for definition in ACTION_DEFINITIONS.values()
        ],
        "connector_types": {
            connector_type.value: sorted(scopes)
            for connector_type, scopes in CONNECTOR_SCOPES.items()
        },
    }


def build_action_payload(
    action_type: str,
    event: Event,
    rule: Rule,
    template: dict[str, Any],
) -> dict[str, Any]:
    """Build a bounded payload from trusted event fields plus a stored static template."""
    summary = (
        f"{event.object_class} matched '{rule.name}' in {event.zone_name} "
        f"at {event.occurred_at.isoformat()}"
    )
    base: dict[str, Any] = {
        "schema_version": 1,
        "action_type": action_type,
        "title": template.get("title") or f"Camera alert: {rule.name}",
        "summary": template.get("summary") or summary,
        "severity": template.get("severity") or "warning",
        "event_id": event.id,
        "rule_id": rule.id,
        "camera_id": event.camera_id,
        "object_class": event.object_class,
        "zone_name": event.zone_name,
        "confidence": event.confidence,
        "occurred_at": event.occurred_at.isoformat(),
        "is_test": event.details.get("test") is True,
    }
    metadata = template.get("metadata")
    if isinstance(metadata, dict):
        base["metadata"] = metadata
    return base
