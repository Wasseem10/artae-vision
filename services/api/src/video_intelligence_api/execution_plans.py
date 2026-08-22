"""Auditable model-routing plans derived from validated camera-job contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from video_intelligence_api.job_specs import CameraJobSpec
from video_intelligence_api.visual_skills import VisualSkillSelection, select_visual_skills


class ExecutionStage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    executor: str
    cadence: Literal["every_frame", "sampled_window", "on_candidate", "on_event"]
    locality: Literal["edge", "vision_provider"]
    purpose: str


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    strategy: Literal["deterministic_tracking", "semantic_window"]
    summary: str
    provider_requests: bool
    stages: list[ExecutionStage]
    visual_skills: list[VisualSkillSelection] = Field(default_factory=list)


def _stage(
    stage_id: str,
    label: str,
    executor: str,
    cadence: Literal["every_frame", "sampled_window", "on_candidate", "on_event"],
    locality: Literal["edge", "vision_provider"],
    purpose: str,
) -> ExecutionStage:
    return ExecutionStage(
        id=stage_id,
        label=label,
        executor=executor,
        cadence=cadence,
        locality=locality,
        purpose=purpose,
    )


def plan_job(spec: CameraJobSpec) -> ExecutionPlan:
    """Choose the smallest currently supported stack that can execute one job."""
    capture = _stage(
        "capture",
        "Capture",
        "OpenCV",
        "every_frame",
        "edge",
        "Read the camera while preserving timestamps for temporal reasoning.",
    )
    evidence = _stage(
        "evidence",
        "Evidence clip",
        "EvidenceRecorder",
        "on_event",
        "edge",
        "Save bounded video before and after a confirmed event.",
    )
    if spec.rule_type == "semantic_vision":
        visual_skills = list(select_visual_skills(spec.instruction))
        return ExecutionPlan(
            strategy="semantic_window",
            summary=(
                "Sample overlapping chronological frame windows and ask the configured vision "
                "model to evaluate the operator's exact condition. YOLO is not required."
            ),
            provider_requests=True,
            visual_skills=visual_skills,
            stages=[
                capture,
                _stage(
                    "window_sampling",
                    "Frame windows",
                    "OverlappingSheetSampler",
                    "sampled_window",
                    "edge",
                    "Create chronological contact sheets with overlap so actions are not split.",
                ),
                _stage(
                    "semantic_observation",
                    "Visual reasoning",
                    "Configured VLM",
                    "sampled_window",
                    "vision_provider",
                    "Evaluate open-ended objects, attributes, states, and actions.",
                ),
                _stage(
                    "temporal_confirmation",
                    "Confirmation",
                    "SemanticDecisionGate",
                    "on_candidate",
                    "edge",
                    "Apply confidence, consecutive-window confirmation, and cooldown rules.",
                ),
                evidence,
            ],
        )

    return ExecutionPlan(
        strategy="deterministic_tracking",
        summary=(
            "Detect and persistently track known objects on the edge, then evaluate geometry "
            "and time with deterministic state machines. No vision-provider request is needed."
        ),
        provider_requests=False,
        stages=[
            capture,
            _stage(
                "object_detection",
                "Object detection",
                "Ultralytics YOLO",
                "every_frame",
                "edge",
                f"Locate instances of the known '{spec.object_class}' class.",
            ),
            _stage(
                "persistent_tracking",
                "Persistent tracking",
                "ByteTrack",
                "every_frame",
                "edge",
                "Maintain stable identities between frames.",
            ),
            _stage(
                "spatial_temporal_rule",
                "Rule state machine",
                "Deterministic rule engine",
                "every_frame",
                "edge",
                f"Evaluate the {spec.rule_type.replace('_', ' ')} condition.",
            ),
            evidence,
        ],
    )
