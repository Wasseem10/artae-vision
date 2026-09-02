"""Honest support and temporal classifications for configurable visual jobs."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from video_intelligence_api.job_specs import CameraJobSpec
from video_intelligence_api.visual_skills import is_person_fall_prompt

TemporalMode = Literal["state", "transition", "sequence"]
SupportTier = Literal[
    "deterministic",
    "specialized",
    "semantic_fallback",
    "requires_context",
    "not_visually_verifiable",
]


class VisualSupportAssessment(BaseModel):
    """Operator-facing statement of what the current stack can actually verify."""

    model_config = ConfigDict(frozen=True)

    tier: SupportTier
    label: str
    deployable: bool
    reason: str
    limitations: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    validation_required: bool = True
    temporal_mode: TemporalMode = "state"


_SEQUENCE_TERMS = re.compile(r"\b(then|after|before|followed by|in sequence)\b", re.I)
_TRANSITION_TERMS = re.compile(
    r"\b(remov(?:e|es|ed|ing)|takes? off|puts? on|dons?|doffs?|turns? (?:on|off)|"
    r"shuts? (?:on|off|down)|powers? (?:on|off)|starts?|stops?|begins?|ceases?|"
    r"falls?|becomes?|changes?|appears?|disappears?|opens?|closes?|enters?|exits?|leaves?)\b",
    re.I,
)

_NON_VISUAL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b(intends?|intention|thinking|thoughts?|plans? to|about to steal|"
            r"trustworthy|dishonest|criminal|guilty)\b",
            re.I,
        ),
        "A camera cannot verify a person's thoughts, intent, honesty, or criminality.",
    ),
    (
        re.compile(
            r"\b(identify (?:the )?(?:person|face)|face recognition|recognize (?:the )?face|"
            r"what is (?:his|her|their) name|who is this person)\b",
            re.I,
        ),
        "This request depends on identifying a person, which is not a supported visual job.",
    ),
    (
        re.compile(
            r"\b(race|ethnicity|religion|sexual orientation|medical condition|diagnos(?:e|is)|"
            r"mental health|emotion|angry|sad|happy)\b",
            re.I,
        ),
        "The requested sensitive or internal human attribute is not visually verifiable.",
    ),
)

_CONTEXT_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (
        re.compile(r"\b(authori[sz]ed|unauthori[sz]ed|badge|card swipe|access control)\b", re.I),
        "query.access_control",
        "Authorization must be checked against an access-control system; "
        "pixels alone are insufficient.",
    ),
    (
        re.compile(
            r"\b(misrouted|wrong (?:package|destination|order)|expected destination|inventory|"
            r"order record|paid|payment|customer record|loyalty|crm|scheduled delivery)\b",
            re.I,
        ),
        "query.business_system",
        "The visible event must be compared with business-system data before it can be verified.",
    ),
)


def infer_temporal_mode(prompt: str) -> TemporalMode:
    """Infer whether a prompt asks for a state, a change, or an ordered sequence."""

    if _SEQUENCE_TERMS.search(prompt):
        return "sequence"
    if _TRANSITION_TERMS.search(prompt):
        return "transition"
    return "state"


def assess_visual_job(spec: CameraJobSpec, prompt: str | None = None) -> VisualSupportAssessment:
    """Classify deployability before claiming the camera can perform a request."""

    instruction = (prompt or getattr(spec, "instruction", "") or "").strip()
    temporal_mode = infer_temporal_mode(instruction)
    for pattern, reason in _NON_VISUAL_PATTERNS:
        if pattern.search(instruction):
            return VisualSupportAssessment(
                tier="not_visually_verifiable",
                label="Cannot verify visually",
                deployable=False,
                reason=reason,
                limitations=[
                    "Rewrite the job using an observable object, action, state, or change."
                ],
                validation_required=False,
                temporal_mode=temporal_mode,
            )

    required_context: list[str] = []
    context_reasons: list[str] = []
    for pattern, capability, reason in _CONTEXT_PATTERNS:
        if pattern.search(instruction):
            required_context.append(capability)
            context_reasons.append(reason)
    if required_context:
        return VisualSupportAssessment(
            tier="requires_context",
            label="Needs outside context",
            deployable=False,
            reason=" ".join(context_reasons),
            limitations=["Connect and test the required source before deployment."],
            required_context=list(dict.fromkeys(required_context)),
            temporal_mode=temporal_mode,
        )

    if spec.rule_type == "semantic_vision" and is_person_fall_prompt(instruction):
        return VisualSupportAssessment(
            tier="specialized",
            label="Continuous local fall detection",
            deployable=True,
            reason=(
                "A person-pose model and temporal state machine evaluate every frame without "
                "waiting for a vision-provider request."
            ),
            limitations=[
                "Falls hidden by furniture, poor camera angles, darkness, and track loss "
                "can be missed.",
                "This is an operational alerting aid, not a medical device.",
                "The exact camera and scenario must pass a labeled replay test before deployment.",
            ],
            temporal_mode="transition",
        )

    if spec.rule_type != "semantic_vision":
        return VisualSupportAssessment(
            tier="deterministic",
            label="Deterministic local tracking",
            deployable=True,
            reason="Known objects, geometry, and time are evaluated with local state machines.",
            limitations=[
                "Accuracy still depends on camera angle, lighting, occlusion, "
                "and detector coverage.",
                "A representative replay test is required before relying on this job.",
            ],
            temporal_mode=temporal_mode,
        )

    return VisualSupportAssessment(
        tier="semantic_fallback",
        label="General visual-AI fallback",
        deployable=True,
        reason=(
            "The condition is visibly observable but currently uses chronological "
            "vision-model windows."
        ),
        limitations=[
            "This route provides breadth, not a guaranteed accuracy level.",
            "Camera angle, resolution, lighting, occlusion, and prompt wording affect results.",
            "The exact camera and scenario must pass a replay test before deployment.",
        ],
        temporal_mode=temporal_mode,
    )
