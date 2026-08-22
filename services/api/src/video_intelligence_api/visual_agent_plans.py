"""Compile camera jobs into explicit observe-decide-verify-act plans."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from video_intelligence_api.execution_plans import plan_job
from video_intelligence_api.job_specs import CameraJobSpec
from video_intelligence_api.visual_skills import SKILLS, select_visual_skills

SUPPORTED_CAPABILITIES = frozenset(
    {
        "camera.capture",
        "vision.object_detection",
        "vision.persistent_tracking",
        "vision.semantic_windows",
        "reasoning.spatial_temporal",
        "verification.evidence_window",
        "action.create_alert",
        *(skill.capability for skill in SKILLS),
    }
)


class VisualAgentNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: Literal["observe", "query", "decide", "verify", "act"]
    title: str
    description: str
    executor: str
    capability: str
    depends_on: list[str]
    side_effect: bool = False


class VisualAgentPlanDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    summary: str
    strategy: Literal["deterministic_tracking", "semantic_window"]
    nodes: list[VisualAgentNode]


def _node(
    node_id: str,
    kind: Literal["observe", "query", "decide", "verify", "act"],
    title: str,
    description: str,
    executor: str,
    capability: str,
    depends_on: list[str],
    *,
    side_effect: bool = False,
) -> VisualAgentNode:
    return VisualAgentNode(
        id=node_id,
        kind=kind,
        title=title,
        description=description,
        executor=executor,
        capability=capability,
        depends_on=depends_on,
        side_effect=side_effect,
    )


def compile_visual_agent_plan(spec: CameraJobSpec, prompt: str) -> VisualAgentPlanDocument:
    """Create the smallest auditable graph that can execute the accepted instruction."""
    execution = plan_job(spec)
    nodes = [
        _node(
            "capture",
            "observe",
            "Watch the camera",
            "Read timestamped frames from the selected camera.",
            "OpenCV camera capture",
            "camera.capture",
            [],
        )
    ]
    if execution.strategy == "semantic_window":
        skills = select_visual_skills(prompt)
        if skills:
            for skill in skills:
                nodes.append(
                    _node(
                        f"skill_{skill.id}",
                        "observe",
                        skill.label,
                        (
                            "Apply only this required visual capability. The temporal VLM "
                            "fallback remains active until a specialized executor passes its gate."
                        ),
                        skill.executor,
                        skill.capability,
                        ["capture"],
                    )
                )
            decision_dependencies = [f"skill_{skill.id}" for skill in skills]
        else:
            nodes.append(
                _node(
                    "understand",
                    "observe",
                    "Understand the scene",
                    "Evaluate overlapping frame windows against the operator's exact instruction.",
                    "Configured vision-language model",
                    "vision.semantic_windows",
                    ["capture"],
                )
            )
            decision_dependencies = ["understand"]
    else:
        nodes.extend(
            [
                _node(
                    "detect",
                    "observe",
                    "Find and track objects",
                    f"Detect '{spec.object_class}' and preserve its identity between frames.",
                    "YOLO + ByteTrack",
                    "vision.object_detection",
                    ["capture"],
                ),
                _node(
                    "track",
                    "observe",
                    "Keep the same identity",
                    "Maintain stable tracks so one object is not counted repeatedly.",
                    "ByteTrack",
                    "vision.persistent_tracking",
                    ["detect"],
                ),
            ]
        )
        decision_dependencies = ["track"]

    nodes.extend(
        [
            _node(
                "decide",
                "decide",
                "Check the instruction",
                "Apply the compiled spatial, temporal, confidence, and cooldown conditions.",
                "Camera rule engine",
                "reasoning.spatial_temporal",
                decision_dependencies,
            ),
            _node(
                "verify",
                "verify",
                "Confirm with evidence",
                "Preserve the bounded evidence window and confirm the candidate before acting.",
                "Evidence decision gate",
                "verification.evidence_window",
                ["decide"],
            ),
            _node(
                "alert",
                "act",
                "Create an alert",
                "Create an incident with its camera, time, confidence, and evidence clip.",
                "Alert service",
                "action.create_alert",
                ["verify"],
                side_effect=True,
            ),
        ]
    )

    lowered = prompt.casefold()
    if any(term in lowered for term in ("access control", "badge swipe", "card swipe")):
        query = _node(
            "external_context",
            "query",
            "Check access-control context",
            "Compare the visual event with an external badge or access-control record.",
            "Unconfigured access-control connector",
            "query.access_control",
            decision_dependencies,
        )
        nodes.insert(-2, query)
        nodes[-2] = nodes[-2].model_copy(update={"depends_on": ["decide", "external_context"]})
    if any(
        term in lowered
        for term in (
            "lock the door",
            "unlock the door",
            "open the gate",
            "file a ticket",
            "call my phone",
        )
    ):
        nodes.append(
            _node(
                "external_action",
                "act",
                "Operate an external system",
                "Perform the requested physical or business-system action after verification.",
                "Unconfigured external connector",
                "action.external_system",
                ["verify"],
                side_effect=True,
            )
        )

    return VisualAgentPlanDocument(
        summary=f"Watch this camera and {prompt.strip().rstrip('.').casefold()}.",
        strategy=execution.strategy,
        nodes=nodes,
    )


def required_capabilities(document: VisualAgentPlanDocument) -> list[str]:
    return list(dict.fromkeys(node.capability for node in document.nodes))


def unsupported_capabilities(document: VisualAgentPlanDocument) -> list[str]:
    return [
        value for value in required_capabilities(document) if value not in SUPPORTED_CAPABILITIES
    ]
