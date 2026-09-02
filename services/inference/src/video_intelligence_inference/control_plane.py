"""Authenticated control-plane client for heterogeneous camera jobs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from video_intelligence_inference.pose_action import is_person_fall_instruction
from video_intelligence_inference.zones import Line, Point, Zone


class ControlPlaneConfigError(RuntimeError):
    """Raised when agent configuration cannot be loaded or selected safely."""


class _PointPayload(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class _GeometryPayload(BaseModel):
    id: str
    name: str
    geometry_type: Literal["polygon", "line"] = "polygon"
    points: list[_PointPayload] = Field(min_length=2)

    @model_validator(mode="after")
    def valid_points(self) -> _GeometryPayload:
        if self.geometry_type == "polygon" and len(self.points) < 3:
            raise ValueError("Polygon geometry requires at least three points")
        if self.geometry_type == "line" and len(self.points) != 2:
            raise ValueError("Line geometry requires exactly two points")
        return self


class _JobSpecPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1, 2, 3]
    rule_type: Literal[
        "object_dwell",
        "zone_dwell",
        "zone_presence",
        "zone_entry",
        "zone_exit",
        "count_threshold",
        "line_crossing",
        "semantic_vision",
    ]
    object_class: str
    zone_id: str | None = None
    zone_name: str | None = None
    line_id: str | None = None
    line_name: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    confirmation_seconds: float | None = Field(default=None, ge=0)
    minimum_confidence: float = Field(ge=0, le=1)
    absence_grace_seconds: float = Field(ge=0)
    comparison: Literal["at_least", "at_most"] | None = None
    threshold: int | None = Field(default=None, ge=0)
    direction: Literal["any", "forward", "reverse"] | None = None
    instruction: str | None = Field(default=None, min_length=5, max_length=2000)
    confirmation_windows: int = Field(default=1, ge=1, le=10)
    cooldown_seconds: float = Field(default=60, ge=0, le=86400)
    temporal_mode: Literal["state", "transition", "sequence"] = "state"
    baseline_windows: int = Field(default=0, ge=0, le=10)


class _ExecutionPlanPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    schema_version: Literal[1] = 1
    strategy: Literal["deterministic_tracking", "semantic_window", "specialized_pose"]
    provider_requests: bool


class _RulePayload(BaseModel):
    id: str
    key: str
    rule_type: str
    object_class: str
    duration_seconds: float = Field(ge=0)
    minimum_confidence: float = Field(ge=0, le=1)
    absence_grace_seconds: float = Field(ge=0)
    zone: _GeometryPayload
    spec: _JobSpecPayload | None = None
    execution_plan: _ExecutionPlanPayload | None = None


class _CameraPayload(BaseModel):
    camera_id: str
    camera_name: str
    source_uri: str
    rules: list[_RulePayload]


@dataclass(frozen=True, slots=True)
class ResolvedRuleConfig:
    rule_id: str
    rule_type: str
    object_class: str
    minimum_confidence: float
    absence_grace_seconds: float
    geometry: Zone | Line
    duration_seconds: float = 0.0
    confirmation_seconds: float = 0.0
    comparison: Literal["at_least", "at_most"] | None = None
    threshold: int | None = None
    direction: Literal["any", "forward", "reverse"] = "any"
    instruction: str | None = None
    confirmation_windows: int = 1
    cooldown_seconds: float = 60.0
    temporal_mode: Literal["state", "transition", "sequence"] = "state"
    baseline_windows: int = 0
    execution_strategy: (
        Literal["deterministic_tracking", "semantic_window", "specialized_pose"] | None
    ) = None

    @property
    def zone(self) -> Zone:
        if not isinstance(self.geometry, Zone):
            raise ValueError("This job uses a line, not a polygon zone.")
        return self.geometry


@dataclass(frozen=True, slots=True)
class ResolvedAgentConfig:
    camera_id: str
    source_uri: str
    rules: tuple[ResolvedRuleConfig, ...]


def _resolved_rule(rule: _RulePayload) -> ResolvedRuleConfig:
    spec = rule.spec or _JobSpecPayload(
        schema_version=1,
        rule_type="object_dwell",
        object_class=rule.object_class,
        zone_id=rule.zone.id,
        zone_name=rule.zone.name,
        duration_seconds=rule.duration_seconds,
        minimum_confidence=rule.minimum_confidence,
        absence_grace_seconds=rule.absence_grace_seconds,
    )
    points = tuple(Point(point.x, point.y) for point in rule.zone.points)
    wants_line = spec.rule_type == "line_crossing"
    if wants_line:
        if rule.zone.geometry_type != "line" or len(points) != 2:
            raise ValueError("Line-crossing job did not include valid line geometry")
        geometry: Zone | Line = Line(rule.zone.name, points[0], points[1])
    else:
        if rule.zone.geometry_type != "polygon":
            raise ValueError(f"{spec.rule_type} requires polygon geometry")
        geometry = Zone(rule.zone.name, points)

    if spec.rule_type in {"object_dwell", "zone_dwell"} and not spec.duration_seconds:
        raise ValueError("Dwell jobs require a positive duration")
    if spec.rule_type == "count_threshold" and (spec.comparison is None or spec.threshold is None):
        raise ValueError("Count jobs require a comparison and threshold")
    if spec.rule_type == "semantic_vision" and not spec.instruction:
        raise ValueError("Semantic vision jobs require an instruction")
    inferred_strategy: Literal["deterministic_tracking", "semantic_window", "specialized_pose"]
    if spec.rule_type == "semantic_vision" and is_person_fall_instruction(spec.instruction):
        inferred_strategy = "specialized_pose"
    elif spec.rule_type == "semantic_vision":
        inferred_strategy = "semantic_window"
    else:
        inferred_strategy = "deterministic_tracking"
    if rule.execution_plan is not None and rule.execution_plan.strategy != inferred_strategy:
        raise ValueError(
            f"Execution plan '{rule.execution_plan.strategy}' conflicts with {spec.rule_type}"
        )
    return ResolvedRuleConfig(
        rule_id=rule.id,
        rule_type=spec.rule_type,
        object_class=spec.object_class,
        duration_seconds=spec.duration_seconds or 0,
        confirmation_seconds=spec.confirmation_seconds or 0,
        minimum_confidence=spec.minimum_confidence,
        absence_grace_seconds=spec.absence_grace_seconds,
        comparison=spec.comparison,
        threshold=spec.threshold,
        direction=spec.direction or "any",
        instruction=spec.instruction,
        confirmation_windows=spec.confirmation_windows,
        cooldown_seconds=spec.cooldown_seconds,
        temporal_mode=spec.temporal_mode,
        baseline_windows=spec.baseline_windows,
        execution_strategy=(
            rule.execution_plan.strategy if rule.execution_plan is not None else inferred_strategy
        ),
        geometry=geometry,
    )


def resolve_rule_config(payload: dict[str, object]) -> ResolvedRuleConfig:
    """Validate one assignment job and convert it to runtime geometry/configuration."""
    return _resolved_rule(_RulePayload.model_validate(payload))


def fetch_agent_config(
    base_url: str,
    *,
    agent_key: str | None = None,
    headers: Mapping[str, str] | None = None,
    camera_ref: str,
    rule_ref: str | None = None,
    timeout_seconds: float = 10.0,
    transport: httpx.BaseTransport | None = None,
) -> ResolvedAgentConfig:
    """Fetch one camera and all supported active jobs."""
    auth_headers = dict(headers or {})
    if agent_key is not None:
        auth_headers.setdefault("X-Agent-Key", agent_key)
    if not auth_headers:
        raise ControlPlaneConfigError("Control-plane credentials are required")
    try:
        with httpx.Client(timeout=timeout_seconds, transport=transport) as client:
            response = client.get(
                base_url.rstrip("/") + "/api/v1/agent/config",
                params={"camera_ref": camera_ref},
                headers=auth_headers,
            )
            response.raise_for_status()
        payload = _CameraPayload.model_validate(response.json())
        candidates = payload.rules
        if rule_ref is not None:
            candidates = [
                rule for rule in candidates if rule.id == rule_ref or rule.key == rule_ref
            ]
        resolved = tuple(_resolved_rule(rule) for rule in candidates)
    except (httpx.HTTPError, ValidationError, ValueError) as exc:
        raise ControlPlaneConfigError(f"Could not load control-plane configuration: {exc}") from exc

    if not resolved:
        detail = f" matching {rule_ref!r}" if rule_ref else ""
        raise ControlPlaneConfigError(f"No active supported camera job{detail} was found.")
    return ResolvedAgentConfig(payload.camera_id, payload.source_uri, resolved)
