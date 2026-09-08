"""Strands incident coordinator for confirmed camera events.

YOLO and the temporal rule engines remain responsible for observing video.  This
module begins after a detection is confirmed and lets a Strands agent choose and
invoke the operational tools that preserve evidence, notify a responder, or ask a
human to review an ambiguous situation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Literal

import anyio
from pydantic import BaseModel, Field

from video_intelligence_api.config import ApiSettings
from video_intelligence_api.models import Camera, Event, Rule

logger = logging.getLogger(__name__)


class IncidentSummary(BaseModel):
    """Small, auditable result returned by the incident agent."""

    summary: str = Field(min_length=1, max_length=500)
    severity: Literal["low", "medium", "high", "critical"]
    requires_human: bool


class IncidentAgentRun(BaseModel):
    """Persisted public trace without private model reasoning or credentials."""

    framework: Literal["Strands Agents SDK"] = "Strands Agents SDK"
    model_id: str
    status: Literal["completed", "fallback"]
    summary: str
    severity: Literal["low", "medium", "high", "critical"]
    requires_human: bool
    tools_invoked: list[str]
    tool_actions: list[dict[str, object]]
    cycles: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None

    def requested(self, tool_name: str) -> bool:
        """Return whether the coordinator requested an operational tool."""
        return tool_name in self.tools_invoked


@dataclass(slots=True)
class _ToolLedger:
    calls: list[dict[str, object]] = field(default_factory=list)

    def record(self, name: str, **arguments: object) -> dict[str, object]:
        call = {"tool": name, **arguments}
        self.calls.append(call)
        return {"accepted": True, **call}


def _event_prompt(event: Event, camera: Camera, rule: Rule) -> str:
    summary = event.details.get("summary")
    return (
        "Coordinate this confirmed visual incident. Use the available tools instead of only "
        "describing what should happen. Never invent people, injuries, camera observations, "
        "contact details, or evidence. A confirmed fall must preserve evidence and notify the "
        "responder. Ask for human review when the supplied facts are genuinely ambiguous.\n\n"
        f"Event ID: {event.id}\n"
        f"Camera: {camera.name}\n"
        f"Camera job: {rule.original_prompt or rule.name}\n"
        f"Detected event: {event.event_type}\n"
        f"Object: {event.object_class or 'not supplied'}\n"
        f"Confidence: {event.confidence:.3f}\n"
        f"Detector summary: {summary if isinstance(summary, str) else 'not supplied'}\n"
        f"Evidence clip reference: {event.clip_uri or 'pending'}"
    )


def _metric_number(summary: dict[str, Any], section: str, name: str) -> int:
    value = summary.get(section)
    if not isinstance(value, dict):
        return 0
    number = value.get(name, 0)
    return int(number) if isinstance(number, (int, float)) else 0


def _run_agent(event: Event, camera: Camera, rule: Rule, settings: ApiSettings) -> IncidentAgentRun:
    # Imports stay inside the enabled path so normal camera ingestion remains
    # lightweight and tests can run without AWS credentials.
    from strands import Agent, tool
    from strands.models import BedrockModel

    ledger = _ToolLedger()

    @tool
    def preserve_evidence(reason: str, seconds_before: int = 5, seconds_after: int = 10) -> dict:
        """Preserve a short incident clip around the confirmed event.

        Args:
            reason: Why this evidence matters to the responder.
            seconds_before: Seconds to retain before the event, from 0 through 30.
            seconds_after: Seconds to retain after the event, from 0 through 60.
        """
        return ledger.record(
            "preserve_evidence",
            reason=reason[:300],
            seconds_before=max(0, min(seconds_before, 30)),
            seconds_after=max(0, min(seconds_after, 60)),
        )

    @tool
    def notify_responder(message: str, priority: str) -> dict:
        """Prepare the verified incident notification for the assigned responder.

        Args:
            message: Concise factual notification grounded in the detector event.
            priority: One of low, medium, high, or critical.
        """
        normalized = priority.casefold()
        if normalized not in {"low", "medium", "high", "critical"}:
            normalized = "high"
        return ledger.record(
            "notify_responder",
            message=message[:500],
            priority=normalized,
        )

    @tool
    def request_human_review(reason: str) -> dict:
        """Place an uncertain incident in the operator review queue.

        Args:
            reason: The exact ambiguity a person should resolve.
        """
        return ledger.record("request_human_review", reason=reason[:500])

    model = BedrockModel(
        model_id=settings.strands_model_id,
        region_name=settings.strands_region,
        temperature=0,
        max_tokens=600,
    )
    agent = Agent(
        model=model,
        tools=[preserve_evidence, notify_responder, request_human_review],
        system_prompt=(
            "You are Artae's safety incident coordinator. The vision system has already supplied "
            "a confirmed event. Coordinate the smallest safe response using tools, keep every "
            "claim grounded in the supplied event, and never claim that a notification was "
            "delivered—the downstream delivery worker owns delivery."
        ),
        structured_output_model=IncidentSummary,
        callback_handler=None,
        agent_id="artae-incident-coordinator",
        name="Artae Incident Coordinator",
        description="Turns confirmed camera events into evidence and responder actions.",
        trace_attributes={
            "service.name": "artae-incident-coordinator",
            "artae.event_id": event.id,
            "artae.camera_id": camera.id,
            "artae.rule_id": rule.id,
        },
    )
    result = agent(_event_prompt(event, camera, rule))
    structured = result.structured_output
    if not isinstance(structured, IncidentSummary):
        structured = IncidentSummary(
            summary=str(result)[:500] or "Incident coordinated.",
            severity="high" if event.event_type == "person_fall" else "medium",
            requires_human=False,
        )

    # A confirmed event must never disappear because a model omitted a tool call.
    # The fallback calls are explicit in the public trace and the deterministic
    # delivery pipeline still performs the actual database transaction.
    invoked = {str(call["tool"]) for call in ledger.calls}
    if "preserve_evidence" not in invoked:
        ledger.record(
            "preserve_evidence",
            reason="Confirmed visual event",
            seconds_before=5,
            seconds_after=10,
            enforced_by="safety_policy",
        )
    if "notify_responder" not in invoked:
        ledger.record(
            "notify_responder",
            message=f"{camera.name}: {event.event_type.replace('_', ' ')} detected.",
            priority=structured.severity,
            enforced_by="safety_policy",
        )

    metric_summary = result.metrics.get_summary()
    usage = metric_summary.get("accumulated_usage", {})
    return IncidentAgentRun(
        model_id=settings.strands_model_id,
        status="completed",
        summary=structured.summary,
        severity=structured.severity,
        requires_human=structured.requires_human,
        tools_invoked=[str(call["tool"]) for call in ledger.calls],
        tool_actions=ledger.calls,
        cycles=_metric_number(metric_summary, "accumulated_metrics", "cycleCount")
        or int(metric_summary.get("total_cycles", 0) or 0),
        input_tokens=int(usage.get("inputTokens", 0) or 0),
        output_tokens=int(usage.get("outputTokens", 0) or 0),
    )


def _fallback_run(
    event: Event,
    camera: Camera,
    settings: ApiSettings,
    exc: Exception,
) -> IncidentAgentRun:
    severity: Literal["low", "medium", "high", "critical"] = (
        "critical" if event.event_type == "person_fall" else "high"
    )
    return IncidentAgentRun(
        model_id=settings.strands_model_id,
        status="fallback",
        summary="The Strands coordinator was unavailable; the safety policy continued locally.",
        severity=severity,
        requires_human=True,
        tools_invoked=["preserve_evidence", "notify_responder"],
        tool_actions=[
            {
                "tool": "preserve_evidence",
                "reason": "Confirmed visual event",
                "seconds_before": 5,
                "seconds_after": 10,
                "enforced_by": "availability_fallback",
            },
            {
                "tool": "notify_responder",
                "message": f"{camera.name}: {event.event_type.replace('_', ' ')} detected.",
                "priority": severity,
                "enforced_by": "availability_fallback",
            },
        ],
        error=type(exc).__name__,
    )


async def coordinate_incident(
    event: Event,
    camera: Camera,
    rule: Rule,
    settings: ApiSettings,
) -> IncidentAgentRun | None:
    """Run Strands outside the async event loop and fail safely on provider errors."""
    if not settings.strands_enabled:
        return None
    try:
        with anyio.fail_after(settings.strands_timeout_seconds):
            return await anyio.to_thread.run_sync(
                partial(_run_agent, event, camera, rule, settings),
                abandon_on_cancel=True,
            )
    except Exception as exc:  # provider outages must not suppress a safety alert
        logger.exception("Strands incident coordination failed for event=%s", event.id)
        return _fallback_run(event, camera, settings, exc)


__all__ = ["IncidentAgentRun", "IncidentSummary", "coordinate_incident"]
