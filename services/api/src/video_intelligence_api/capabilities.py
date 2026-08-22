"""Capability registry used to explain and validate deployability."""

from __future__ import annotations

from dataclasses import dataclass

from video_intelligence_api.config import ApiSettings
from video_intelligence_api.job_specs import SUPPORTED_JOB_TYPES, CameraJobSpec
from video_intelligence_api.visual_skills import registry_payload as visual_skill_registry


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    supported: bool
    reason: str | None = None


def configured_object_classes(settings: ApiSettings) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip().casefold() for value in settings.object_classes))


def check_job_capability(spec: CameraJobSpec, settings: ApiSettings) -> CapabilityResult:
    if spec.rule_type == "object_dwell":
        event_supported = "zone_dwell" in settings.event_types
    else:
        event_supported = spec.rule_type in settings.event_types
    if not event_supported:
        return CapabilityResult(False, f"Event type '{spec.rule_type}' is not enabled.")

    if spec.rule_type == "semantic_vision":
        return CapabilityResult(True)

    available = configured_object_classes(settings)
    if spec.object_class.casefold() not in available:
        return CapabilityResult(
            False,
            f"The configured detector cannot identify '{spec.object_class}'.",
        )
    return CapabilityResult(True)


def registry_payload(settings: ApiSettings) -> dict[str, object]:
    return {
        "schema_version": 1,
        "detector": {
            "model": settings.detector_model,
            "object_classes": list(configured_object_classes(settings)),
        },
        "event_types": list(settings.event_types),
        "platform_event_types": list(SUPPORTED_JOB_TYPES),
        "capabilities": [
            "object_detection",
            "persistent_tracking",
            "polygon_zones",
            "directional_lines",
            "temporal_confirmation",
            "semantic_vision",
        ],
        "routing_strategies": {
            "deterministic_tracking": {
                "provider_requests": False,
                "description": "YOLO, ByteTrack, geometry, and temporal state machines.",
            },
            "semantic_window": {
                "provider_requests": True,
                "description": "Overlapping frame windows evaluated by the configured VLM.",
            },
        },
        "visual_skills": visual_skill_registry(),
    }
