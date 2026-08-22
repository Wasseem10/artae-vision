"""Versioned visual-skill manifests and the smallest-capability prompt router."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class VisualSkillDefinition:
    id: str
    label: str
    capability: str
    terms: tuple[str, ...]
    preferred_executor: str
    fallback_executor: str
    status: Literal["available", "planned"]
    benchmark_policy: str


@dataclass(frozen=True, slots=True)
class VisualSkillSelection:
    id: str
    label: str
    capability: str
    executor: str
    execution_mode: Literal["specialized", "semantic_fallback"]
    provider_requests: bool
    benchmark_policy: str


SKILLS: tuple[VisualSkillDefinition, ...] = (
    VisualSkillDefinition(
        id="ppe_compliance",
        label="PPE compliance",
        capability="vision.skill.ppe_compliance",
        terms=("hard hat", "helmet", "gloves", "safety vest", "ppe", "face mask", "masked"),
        preferred_executor="PPE attribute model",
        fallback_executor="Temporal VLM windows",
        status="available",
        benchmark_policy="scenario replay gate required before deployment",
    ),
    VisualSkillDefinition(
        id="ocr_text",
        label="Text and screen reading",
        capability="vision.skill.ocr_text",
        terms=("read text", "screen", "display", "label", "serial number"),
        preferred_executor="OCR model",
        fallback_executor="Temporal VLM windows",
        status="available",
        benchmark_policy="text-specific replay gate required before deployment",
    ),
    VisualSkillDefinition(
        id="license_plate",
        label="License-plate reading",
        capability="vision.skill.license_plate",
        terms=("license plate", "number plate", "vehicle plate"),
        preferred_executor="Plate detector + OCR",
        fallback_executor="Temporal VLM windows",
        status="available",
        benchmark_policy="camera-angle plate replay gate required before deployment",
    ),
    VisualSkillDefinition(
        id="barcode_label",
        label="Barcode and label reading",
        capability="vision.skill.barcode_label",
        terms=("barcode", "qr code", "shipping label", "package label"),
        preferred_executor="Barcode decoder + OCR",
        fallback_executor="Temporal VLM windows",
        status="available",
        benchmark_policy="label-resolution replay gate required before deployment",
    ),
    VisualSkillDefinition(
        id="pose_action",
        label="Pose and action analysis",
        capability="vision.skill.pose_action",
        terms=("fall", "fallen", "lying", "backflip", "jump", "gesture", "posture"),
        preferred_executor="Pose/action model",
        fallback_executor="Temporal VLM windows",
        status="available",
        benchmark_policy="action-duration replay gate required before deployment",
    ),
    VisualSkillDefinition(
        id="open_grounding",
        label="Open-vocabulary grounding",
        capability="vision.skill.open_grounding",
        terms=("production line", "charging station", "loading zone", "treadmill", "robot"),
        preferred_executor="Open-vocabulary detector",
        fallback_executor="Temporal VLM windows",
        status="available",
        benchmark_policy="site-scene replay gate required before deployment",
    ),
    VisualSkillDefinition(
        id="segmentation",
        label="Object and region segmentation",
        capability="vision.skill.segmentation",
        terms=("mask the", "segment", "outline", "boundary", "falls off"),
        preferred_executor="Segmentation model",
        fallback_executor="Temporal VLM windows",
        status="available",
        benchmark_policy="boundary-quality replay gate required before deployment",
    ),
    VisualSkillDefinition(
        id="change_anomaly",
        label="Change and anomaly detection",
        capability="vision.skill.change_anomaly",
        terms=("shuts off", "powers off", "stopped moving", "missing", "misplaced", "unusual"),
        preferred_executor="Scene-change model",
        fallback_executor="Temporal VLM windows",
        status="available",
        benchmark_policy="normal-baseline replay gate required before deployment",
    ),
)


def select_visual_skills(prompt: str) -> tuple[VisualSkillSelection, ...]:
    lowered = prompt.casefold()
    selected: list[VisualSkillSelection] = []
    for definition in SKILLS:
        if any(term in lowered for term in definition.terms):
            selected.append(
                VisualSkillSelection(
                    id=definition.id,
                    label=definition.label,
                    capability=definition.capability,
                    executor=definition.fallback_executor,
                    execution_mode="semantic_fallback",
                    provider_requests=True,
                    benchmark_policy=definition.benchmark_policy,
                )
            )
    return tuple(selected)


def registry_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "routing_policy": (
            "Select only prompt-required skills; use temporal VLM windows until a "
            "specialized executor passes the scenario replay gate."
        ),
        "skills": [asdict(skill) for skill in SKILLS],
    }
