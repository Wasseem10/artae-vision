"""Versioned visual-skill manifests and the smallest-capability prompt router."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal

_PERSON_FALL_PATTERN = re.compile(
    r"\b(?:fall|falls|fell|fallen|falling|collapse|collapses|collapsed|collapsing)\b",
    re.IGNORECASE,
)


def is_person_fall_prompt(prompt: str) -> bool:
    """Return true only for fall/collapse transitions handled by the pose skill."""
    return bool(_PERSON_FALL_PATTERN.search(prompt))


@dataclass(frozen=True, slots=True)
class VisualSkillDefinition:
    id: str
    label: str
    capability: str
    terms: tuple[str, ...]
    preferred_executor: str
    fallback_executor: str
    status: Literal["fallback_only", "specialized_ready", "planned"]
    benchmark_policy: str
    input_contract: str
    output_contract: str
    temporal_support: tuple[Literal["state", "transition", "sequence"], ...]


@dataclass(frozen=True, slots=True)
class VisualSkillSelection:
    id: str
    label: str
    capability: str
    executor: str
    execution_mode: Literal["specialized", "semantic_fallback"]
    provider_requests: bool
    benchmark_policy: str
    readiness: Literal["fallback_only", "specialized_ready"]


SKILLS: tuple[VisualSkillDefinition, ...] = (
    VisualSkillDefinition(
        id="ppe_compliance",
        label="PPE compliance",
        capability="vision.skill.ppe_compliance",
        terms=("hard hat", "helmet", "gloves", "safety vest", "ppe", "face mask", "masked"),
        preferred_executor="PPE attribute model",
        fallback_executor="Temporal VLM windows",
        status="fallback_only",
        benchmark_policy="scenario replay gate required before deployment",
        input_contract="Chronological camera-frame window plus the operator condition",
        output_contract=(
            "Visible PPE state or transition, confidence, frame span, and evidence rationale"
        ),
        temporal_support=("state", "transition", "sequence"),
    ),
    VisualSkillDefinition(
        id="ocr_text",
        label="Text and screen reading",
        capability="vision.skill.ocr_text",
        terms=("read text", "screen", "display", "label", "serial number"),
        preferred_executor="OCR model",
        fallback_executor="Temporal VLM windows",
        status="fallback_only",
        benchmark_policy="text-specific replay gate required before deployment",
        input_contract="Camera crop or chronological window containing visible text",
        output_contract="Transcribed text, confidence, location, and source-frame references",
        temporal_support=("state", "transition"),
    ),
    VisualSkillDefinition(
        id="license_plate",
        label="License-plate reading",
        capability="vision.skill.license_plate",
        terms=("license plate", "number plate", "vehicle plate"),
        preferred_executor="Plate detector + OCR",
        fallback_executor="Temporal VLM windows",
        status="fallback_only",
        benchmark_policy="camera-angle plate replay gate required before deployment",
        input_contract="Vehicle/plate crop with timestamp and camera identity",
        output_contract="Plate text, confidence, bounding region, and source-frame reference",
        temporal_support=("state", "transition"),
    ),
    VisualSkillDefinition(
        id="barcode_label",
        label="Barcode and label reading",
        capability="vision.skill.barcode_label",
        terms=("barcode", "qr code", "shipping label", "package label"),
        preferred_executor="Barcode decoder + OCR",
        fallback_executor="Temporal VLM windows",
        status="fallback_only",
        benchmark_policy="label-resolution replay gate required before deployment",
        input_contract="Package or label crop with timestamp",
        output_contract="Decoded value, symbology or text type, confidence, and source frame",
        temporal_support=("state", "transition"),
    ),
    VisualSkillDefinition(
        id="pose_action",
        label="Pose and action analysis",
        capability="vision.skill.pose_action",
        terms=(
            "fall",
            "falls",
            "fell",
            "fallen",
            "falling",
            "collapse",
            "collapses",
            "collapsed",
            "collapsing",
            "lying",
            "backflip",
            "jump",
            "gesture",
            "posture",
        ),
        preferred_executor="Pose/action model",
        fallback_executor="Temporal VLM windows",
        status="specialized_ready",
        benchmark_policy="action-duration replay gate required before deployment",
        input_contract="Chronological person-centered frame window",
        output_contract="Visible pose/action, confidence, temporal span, and evidence rationale",
        temporal_support=("state", "transition", "sequence"),
    ),
    VisualSkillDefinition(
        id="open_grounding",
        label="Open-vocabulary grounding",
        capability="vision.skill.open_grounding",
        terms=("production line", "charging station", "loading zone", "treadmill", "robot"),
        preferred_executor="Open-vocabulary detector",
        fallback_executor="Temporal VLM windows",
        status="fallback_only",
        benchmark_policy="site-scene replay gate required before deployment",
        input_contract="Camera frame/window plus open-vocabulary object description",
        output_contract="Grounded object regions, labels, confidence, and frame references",
        temporal_support=("state", "transition", "sequence"),
    ),
    VisualSkillDefinition(
        id="segmentation",
        label="Object and region segmentation",
        capability="vision.skill.segmentation",
        terms=("mask the", "segment", "outline", "boundary", "falls off", "spill", "leak"),
        preferred_executor="Segmentation model",
        fallback_executor="Temporal VLM windows",
        status="fallback_only",
        benchmark_policy="boundary-quality replay gate required before deployment",
        input_contract="Camera frame/window plus target region description",
        output_contract="Region mask or visible-region rationale, confidence, and frame reference",
        temporal_support=("state", "transition"),
    ),
    VisualSkillDefinition(
        id="change_anomaly",
        label="Change and anomaly detection",
        capability="vision.skill.change_anomaly",
        terms=(
            "shuts off",
            "powers off",
            "stopped moving",
            "stops moving",
            "missing",
            "misplaced",
            "misrouted",
            "unusual",
            "spill",
            "leak",
            "smoke",
        ),
        preferred_executor="Scene-change model",
        fallback_executor="Temporal VLM windows",
        status="fallback_only",
        benchmark_policy="normal-baseline replay gate required before deployment",
        input_contract="Chronological frame window with an established visible baseline",
        output_contract="Change type, before/after evidence, confidence, and temporal span",
        temporal_support=("transition", "sequence"),
    ),
)


def select_visual_skills(prompt: str) -> tuple[VisualSkillSelection, ...]:
    normalized = " " + " ".join(re.sub(r"[^a-z0-9]+", " ", prompt.casefold()).split()) + " "
    selected: list[VisualSkillSelection] = []
    for definition in SKILLS:
        if any(f" {term} " in normalized for term in definition.terms):
            specialized = definition.status == "specialized_ready"
            if definition.id == "pose_action":
                specialized = specialized and is_person_fall_prompt(prompt)
            selected.append(
                VisualSkillSelection(
                    id=definition.id,
                    label=definition.label,
                    capability=definition.capability,
                    executor=(
                        definition.preferred_executor
                        if specialized
                        else definition.fallback_executor
                    ),
                    execution_mode="specialized" if specialized else "semantic_fallback",
                    provider_requests=not specialized,
                    benchmark_policy=definition.benchmark_policy,
                    readiness=definition.status,
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
