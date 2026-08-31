"""Versioned, model-independent camera-job contracts.

The control plane stores these documents as JSON so adding a new job type does
not require adding another group of rule-specific database columns.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class StrictJobModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LegacyObjectDwellJob(StrictJobModel):
    """Milestone 8/9 contract retained for already-created jobs."""

    schema_version: Literal[1] = 1
    rule_type: Literal["object_dwell"] = "object_dwell"
    object_class: str = Field(min_length=1, max_length=80)
    zone_id: str = Field(min_length=1, max_length=36)
    zone_name: str = Field(min_length=1, max_length=120)
    duration_seconds: float = Field(gt=0, le=86400)
    minimum_confidence: float = Field(default=0.4, ge=0, le=1)
    absence_grace_seconds: float = Field(default=1.0, ge=0, le=60)


class JobV2Base(StrictJobModel):
    schema_version: Literal[2] = 2
    object_class: str = Field(min_length=1, max_length=80)
    minimum_confidence: float = Field(default=0.4, ge=0, le=1)
    absence_grace_seconds: float = Field(default=1.0, ge=0, le=60)


class ZoneJobBase(JobV2Base):
    zone_id: str = Field(min_length=1, max_length=36)
    zone_name: str = Field(min_length=1, max_length=120)


class ZoneDwellJob(ZoneJobBase):
    rule_type: Literal["zone_dwell"] = "zone_dwell"
    duration_seconds: float = Field(gt=0, le=86400)


class ZonePresenceJob(ZoneJobBase):
    rule_type: Literal["zone_presence"] = "zone_presence"
    confirmation_seconds: float = Field(default=0, ge=0, le=86400)


class ZoneEntryJob(ZoneJobBase):
    rule_type: Literal["zone_entry"] = "zone_entry"


class ZoneExitJob(ZoneJobBase):
    rule_type: Literal["zone_exit"] = "zone_exit"


class CountThresholdJob(ZoneJobBase):
    rule_type: Literal["count_threshold"] = "count_threshold"
    comparison: Literal["at_least", "at_most"]
    threshold: int = Field(ge=0, le=10000)
    confirmation_seconds: float = Field(default=0, ge=0, le=86400)


class LineCrossingJob(JobV2Base):
    rule_type: Literal["line_crossing"] = "line_crossing"
    line_id: str = Field(min_length=1, max_length=36)
    line_name: str = Field(min_length=1, max_length=120)
    direction: Literal["any", "forward", "reverse"] = "any"


class SemanticVisionJob(StrictJobModel):
    """Open-ended visual event evaluated from chronological frame windows."""

    schema_version: Literal[3] = 3
    rule_type: Literal["semantic_vision"] = "semantic_vision"
    instruction: str = Field(min_length=5, max_length=2000)
    object_class: str = Field(default="visual_event", min_length=1, max_length=80)
    zone_id: str = Field(min_length=1, max_length=36)
    zone_name: str = Field(min_length=1, max_length=120)
    minimum_confidence: float = Field(default=0.7, ge=0, le=1)
    absence_grace_seconds: float = Field(default=1.0, ge=0, le=60)
    confirmation_windows: int = Field(default=1, ge=1, le=10)
    cooldown_seconds: float = Field(default=60.0, ge=0, le=86400)
    temporal_mode: Literal["state", "transition", "sequence"] = "state"
    baseline_windows: int = Field(default=0, ge=0, le=10)


CameraJobSpec = Annotated[
    LegacyObjectDwellJob
    | ZoneDwellJob
    | ZonePresenceJob
    | ZoneEntryJob
    | ZoneExitJob
    | CountThresholdJob
    | LineCrossingJob
    | SemanticVisionJob,
    Field(discriminator="rule_type"),
]
camera_job_adapter: TypeAdapter[CameraJobSpec] = TypeAdapter(CameraJobSpec)

SUPPORTED_JOB_TYPES: tuple[str, ...] = (
    "zone_dwell",
    "zone_presence",
    "zone_entry",
    "zone_exit",
    "count_threshold",
    "line_crossing",
    "semantic_vision",
)


def validate_job_spec(value: object) -> CameraJobSpec:
    return camera_job_adapter.validate_python(value)


def spatial_id(spec: CameraJobSpec) -> str:
    return spec.line_id if isinstance(spec, LineCrossingJob) else spec.zone_id


def spatial_name(spec: CameraJobSpec) -> str:
    return spec.line_name if isinstance(spec, LineCrossingJob) else spec.zone_name


def duration_for_legacy_column(spec: CameraJobSpec) -> float:
    if isinstance(spec, (LegacyObjectDwellJob, ZoneDwellJob)):
        return spec.duration_seconds
    if isinstance(spec, (ZonePresenceJob, CountThresholdJob)):
        return max(spec.confirmation_seconds, 0.0)
    return 0.0


def legacy_job_spec(
    *,
    object_class: str,
    zone_id: str,
    zone_name: str,
    duration_seconds: float,
    minimum_confidence: float,
    absence_grace_seconds: float,
) -> LegacyObjectDwellJob:
    return LegacyObjectDwellJob(
        object_class=object_class,
        zone_id=zone_id,
        zone_name=zone_name,
        duration_seconds=duration_seconds,
        minimum_confidence=minimum_confidence,
        absence_grace_seconds=absence_grace_seconds,
    )
