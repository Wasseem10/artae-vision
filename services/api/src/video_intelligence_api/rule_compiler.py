"""Natural-language compiler for versioned, industry-neutral camera jobs."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from video_intelligence_api.capabilities import check_job_capability
from video_intelligence_api.config import ApiSettings
from video_intelligence_api.job_specs import (
    CameraJobSpec,
    CountThresholdJob,
    LineCrossingJob,
    SemanticVisionJob,
    ZoneDwellJob,
    ZoneEntryJob,
    ZoneExitJob,
    ZonePresenceJob,
)
from video_intelligence_api.models import GeometryType, Zone
from video_intelligence_api.visual_intelligence import infer_temporal_mode
from video_intelligence_api.visual_skills import is_person_fall_prompt

logger = logging.getLogger(__name__)
COMPILER_VERSION = "camera-job/3"
FULL_FRAME_ZONE_NAME = "Full frame (automatic)"


class RuleCompilerProviderError(RuntimeError):
    """Raised when a requested external compiler cannot return a valid candidate."""


class ProviderRuleCandidate(BaseModel):
    """Provider-neutral candidate; saved geometry IDs are resolved server-side."""

    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["compiled", "needs_clarification"]
    rule_type: (
        Literal[
            "zone_dwell",
            "zone_presence",
            "zone_entry",
            "zone_exit",
            "count_threshold",
            "line_crossing",
            "semantic_vision",
        ]
        | None
    ) = None
    object_class: str | None = Field(default=None, max_length=80)
    zone_name: str | None = Field(default=None, max_length=120)
    duration_seconds: float | None = Field(default=None, ge=0, le=86400)
    minimum_confidence: float = Field(default=0.4, ge=0, le=1)
    absence_grace_seconds: float = Field(default=1.0, ge=0, le=60)
    comparison: Literal["at_least", "at_most"] | None = None
    threshold: int | None = Field(default=None, ge=0, le=10000)
    direction: Literal["any", "forward", "reverse"] | None = None
    instruction: str | None = Field(default=None, min_length=5, max_length=2000)
    explanation: str = Field(min_length=1, max_length=1500)
    clarification_question: str | None = Field(default=None, max_length=1000)


class CandidateProvider(Protocol):
    name: str
    model: str | None

    async def compile(self, prompt: str, geometries: list[Zone]) -> ProviderRuleCandidate: ...


@dataclass(frozen=True)
class CompilationResult:
    provider: str
    provider_model: str | None
    candidate: ProviderRuleCandidate
    compiled_rule: CameraJobSpec | None
    warnings: list[str] = field(default_factory=list)


def _normalized(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _matching_geometries(prompt: str, geometries: list[Zone]) -> list[Zone]:
    normalized_prompt = f" {_normalized(prompt)} "
    matches: list[Zone] = []
    for geometry in geometries:
        full_name = _normalized(geometry.name)
        aliases = {full_name}
        without_suffix = re.sub(r"\b(zone|line)\b", "", full_name).strip()
        if without_suffix:
            aliases.add(without_suffix)
        if any(f" {alias} " in normalized_prompt for alias in aliases):
            matches.append(geometry)
    return matches


OBJECT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("person", ("person", "people", "pedestrian", "pedestrians", "worker", "workers")),
    ("motorcycle", ("motorcycle", "motorcycles", "motorbike", "motorbikes")),
    ("bicycle", ("bicycle", "bicycles", "bike", "bikes", "cyclist", "cyclists")),
    ("truck", ("truck", "trucks", "lorry", "lorries")),
    ("car", ("car", "cars", "vehicle", "vehicles", "automobile", "automobiles")),
    ("bus", ("bus", "buses")),
    ("dog", ("dog", "dogs")),
    ("cat", ("cat", "cats")),
)


def _matching_objects(prompt: str) -> list[str]:
    normalized_prompt = f" {_normalized(prompt)} "
    return [
        object_class
        for object_class, aliases in OBJECT_ALIASES
        if any(f" {alias} " in normalized_prompt for alias in aliases)
    ]


_DURATION_PATTERN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)\b",
    re.IGNORECASE,
)


def _durations(prompt: str) -> list[float]:
    multipliers = {
        "s": 1,
        "sec": 1,
        "secs": 1,
        "second": 1,
        "seconds": 1,
        "m": 60,
        "min": 60,
        "mins": 60,
        "minute": 60,
        "minutes": 60,
        "h": 3600,
        "hr": 3600,
        "hrs": 3600,
        "hour": 3600,
        "hours": 3600,
    }
    return [
        float(match.group("value")) * multipliers[match.group("unit").casefold()]
        for match in _DURATION_PATTERN.finditer(prompt)
    ]


def _minimum_confidence(prompt: str) -> float:
    match = re.search(
        r"(?:minimum\s+)?confidence(?:\s+(?:of|at|above))?\s+(\d+(?:\.\d+)?)\s*%",
        prompt,
        re.IGNORECASE,
    )
    return float(match.group(1)) / 100 if match else 0.4


def _job_type(prompt: str, durations: list[float]) -> str | None:
    text = f" {_normalized(prompt)} "
    if any(word in text for word in (" cross ", " crosses ", " crossed ")):
        return "line_crossing"
    if any(
        word in text
        for word in (
            " remain ",
            " remains ",
            " stay ",
            " stays ",
            " longer ",
        )
    ):
        return "zone_dwell"
    if any(
        phrase in text
        for phrase in (
            " how many ",
            " count ",
            " at least ",
            " at most ",
            " more than ",
            " fewer than ",
            " less than ",
        )
    ):
        return "count_threshold"
    if any(word in text for word in (" exit ", " exits ", " leave ", " leaves ")):
        return "zone_exit"
    if any(word in text for word in (" enter ", " enters ", " arrive ", " arrives ")):
        return "zone_entry"
    if any(word in text for word in (" inside ", " present ", " appears ", " detect ")):
        return "zone_presence"
    return None


def _count_condition(prompt: str) -> tuple[str, int] | None:
    patterns = (
        (r"\bat\s+least\s+(\d+)\b", "at_least", 0),
        (r"\b(?:more|greater)\s+than\s+(\d+)\b", "at_least", 1),
        (r"\bat\s+most\s+(\d+)\b", "at_most", 0),
        (r"\b(?:fewer|less)\s+than\s+(\d+)\b", "at_most", -1),
    )
    for pattern, comparison, offset in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return comparison, max(0, int(match.group(1)) + offset)
    return None


_SEMANTIC_VISUAL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:not\s+)?wearing\b",
        r"\b(?:hard\s*hat|helmet|gloves?|masked?|face\s+covering)\b",
        r"\btailgat(?:e|es|ed|ing)\b",
        r"\b(?:fall|falls|fell|fallen|lying\s+on\s+the\s+ground)\b",
        r"\b(?:backflip|somersault|cartwheel)\b",
        r"\b(?:screen|display|indicator\s+light)\s+(?:shuts?|turns?|goes?)\s+off\b",
        r"\b(?:powers?|shuts?)\s+(?:down|off)\b",
        r"\b(?:stops?|stopped)\s+(?:moving|working|operating)\b",
        r"\b(?:recharg(?:e|es|ed|ing)|charging\s+station)\b",
        r"\b(?:falls?|fell)\s+(?:off|from)\b",
        r"\b(?:read|scan|recognize)\b.*\b(?:text|label|serial\s+number|barcode|qr\s+code)\b",
        r"\b(?:spill|leak|smoke|misrouted|misplaced)\b",
        r"\b(?:authori[sz]ed|unauthori[sz]ed|badge|access\s+control)\b",
        r"\b(?:intends?|intention|thinking|trustworthy|criminal|about\s+to\s+steal)\b",
    )
)


def _requires_semantic_reasoning(prompt: str) -> bool:
    """Identify visible attributes, states, and actions not represented by spatial IR."""
    return any(pattern.search(prompt) for pattern in _SEMANTIC_VISUAL_PATTERNS)


def _clarification_question(missing: list[str], ambiguous: list[str]) -> str:
    parts: list[str] = []
    if missing:
        parts.append(f"Please specify {', '.join(missing)}")
    if ambiguous:
        parts.append(f"please choose one {', '.join(ambiguous)}")
    return "; ".join(parts) + "."


class DeterministicRuleProvider:
    name = "deterministic"
    model = None

    async def compile(self, prompt: str, geometries: list[Zone]) -> ProviderRuleCandidate:
        clarification = (
            prompt.rsplit("Clarification answer:", maxsplit=1)[1]
            if "Clarification answer:" in prompt
            else ""
        )
        geometry_matches = _matching_geometries(clarification, geometries) or _matching_geometries(
            prompt, geometries
        )
        # A newly connected camera always has one automatic full-frame zone. Requiring the
        # operator to know and type that internal zone name makes ordinary requests appear
        # stuck. When it is the camera's only usable area, treat the whole view as the safe
        # default and let custom saved zones remain explicit choices once they exist.
        if not geometry_matches:
            polygon_geometries = [
                geometry for geometry in geometries if geometry.geometry_type != GeometryType.LINE
            ]
            if (
                len(polygon_geometries) == 1
                and polygon_geometries[0].name == FULL_FRAME_ZONE_NAME
            ):
                geometry_matches = polygon_geometries
        object_matches = _matching_objects(clarification) or _matching_objects(prompt)
        duration_matches = _durations(clarification) or _durations(prompt)
        rule_type = _job_type(prompt, duration_matches)
        count_condition = _count_condition(clarification) or _count_condition(prompt)
        requires_semantic = _requires_semantic_reasoning(prompt)
        if requires_semantic or not rule_type:
            full_frame = next(
                (geometry for geometry in geometries if geometry.name == FULL_FRAME_ZONE_NAME),
                None,
            )
            semantic_geometry = geometry_matches[0] if len(geometry_matches) == 1 else full_frame
            if semantic_geometry is not None:
                return ProviderRuleCandidate(
                    status="compiled",
                    rule_type="semantic_vision",
                    object_class="visual_event",
                    zone_name=semantic_geometry.name,
                    instruction=prompt,
                    minimum_confidence=max(_minimum_confidence(prompt), 0.7),
                    explanation=(
                        "Use chronological visual reasoning for an attribute, state, or action "
                        "that is not safely reducible to object boxes and coordinates."
                    ),
                )
        missing: list[str] = []
        ambiguous: list[str] = []

        if not object_matches:
            missing.append("the object to watch for")
        elif len(object_matches) > 1:
            ambiguous.append("object type")
        if not geometry_matches:
            missing.append("one of the camera's named zones or lines")
        elif len(geometry_matches) > 1:
            ambiguous.append("scene geometry")
        if rule_type == "zone_dwell" and not duration_matches:
            missing.append("a dwell duration such as '30 seconds'")
        if rule_type == "count_threshold" and count_condition is None:
            missing.append("a count threshold such as 'at least 5'")

        if missing or ambiguous:
            return ProviderRuleCandidate(
                status="needs_clarification",
                explanation="The job is not precise enough to create a safe draft yet.",
                clarification_question=_clarification_question(missing, ambiguous),
            )

        geometry = geometry_matches[0]
        object_class = object_matches[0]
        duration = duration_matches[0] if duration_matches else 0.0
        behavior = {
            "zone_dwell": f"after it remains there for {duration:g} seconds",
            "zone_presence": "when it is present",
            "zone_entry": "when it enters",
            "zone_exit": "when it exits",
            "count_threshold": "when the configured count threshold is met",
            "line_crossing": "when it crosses the line",
        }
        return ProviderRuleCandidate(
            status="compiled",
            rule_type=rule_type,
            object_class=object_class,
            zone_name=geometry.name,
            duration_seconds=duration,
            minimum_confidence=_minimum_confidence(prompt),
            comparison=count_condition[0] if count_condition else None,
            threshold=count_condition[1] if count_condition else None,
            direction="any" if rule_type == "line_crossing" else None,
            explanation=(
                f"Watch for {object_class} at '{geometry.name}' and create one event "
                f"{behavior[rule_type]}, using persistent track identity."
            ),
        )


class OpenAIRuleProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def compile(self, prompt: str, geometries: list[Zone]) -> ProviderRuleCandidate:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuleCompilerProviderError(
                "The OpenAI compiler is not installed. Reinstall the API dependencies."
            ) from exc

        allowed = [
            {"name": geometry.name, "type": geometry.geometry_type.value} for geometry in geometries
        ]
        instructions = (
            "Compile one camera job into the strict schema. Supported types are zone_dwell, "
            "zone_presence, zone_entry, zone_exit, count_threshold, line_crossing, and "
            "semantic_vision. Use semantic_vision for visually observable conditions that do "
            "not map cleanly to the deterministic spatial types, preserving the operator's "
            "request in instruction. "
            "Use polygon geometry for zone jobs and line geometry for crossing. Use exactly one "
            "provided geometry name. Never invent geometry or capabilities. Ask one concise "
            "clarification when required fields are missing. Do not activate anything."
        )
        try:
            client = AsyncOpenAI(api_key=self.api_key)
            response = await client.responses.parse(
                model=self.model,
                instructions=instructions,
                input=json.dumps({"operator_request": prompt, "allowed_geometry": allowed}),
                text_format=ProviderRuleCandidate,
            )
            if response.output_parsed is None:
                raise RuleCompilerProviderError(
                    "The OpenAI response did not contain a parsed camera job."
                )
            return response.output_parsed
        except RuleCompilerProviderError:
            raise
        except Exception as exc:
            logger.exception("OpenAI rule compilation failed: model=%s", self.model)
            raise RuleCompilerProviderError("The OpenAI rule compiler is unavailable.") from exc


def _needs_clarification(message: str, question: str) -> tuple[ProviderRuleCandidate, None]:
    return (
        ProviderRuleCandidate(
            status="needs_clarification",
            explanation=message,
            clarification_question=question,
        ),
        None,
    )


def _resolve_candidate(
    candidate: ProviderRuleCandidate,
    geometries: list[Zone],
) -> tuple[ProviderRuleCandidate, CameraJobSpec | None]:
    if candidate.status == "needs_clarification":
        return candidate, None
    if candidate.rule_type == "semantic_vision":
        if not candidate.instruction or not candidate.zone_name:
            return _needs_clarification(
                "The compiler omitted the semantic instruction.",
                "What visible condition should this camera watch for?",
            )
        matches = [geometry for geometry in geometries if geometry.name == candidate.zone_name]
        if len(matches) != 1:
            return _needs_clarification(
                "The automatic full-frame geometry is unavailable.",
                "Please try compiling the visual condition again.",
            )
        geometry = matches[0]
        temporal_mode = infer_temporal_mode(candidate.instruction)
        return candidate, SemanticVisionJob(
            instruction=candidate.instruction,
            object_class=candidate.object_class or "visual_event",
            zone_id=geometry.id,
            zone_name=geometry.name,
            minimum_confidence=max(
                candidate.minimum_confidence,
                0.5 if is_person_fall_prompt(candidate.instruction) else 0.7,
            ),
            temporal_mode=temporal_mode,
            baseline_windows=1 if temporal_mode == "transition" else 0,
        )
    if not candidate.rule_type or not candidate.object_class or not candidate.zone_name:
        return _needs_clarification(
            "The compiler omitted a required job field.",
            "Which event type, object, and named zone or line should be used?",
        )
    matches = [
        geometry
        for geometry in geometries
        if _normalized(geometry.name) == _normalized(candidate.zone_name)
    ]
    if len(matches) != 1:
        safe_names = ", ".join(f"'{geometry.name}'" for geometry in geometries) or "none"
        return _needs_clarification(
            "The requested scene geometry could not be resolved safely.",
            f"Which saved zone or line should be used? Available geometry: {safe_names}.",
        )
    geometry = matches[0]
    wants_line = candidate.rule_type == "line_crossing"
    if wants_line != (geometry.geometry_type == GeometryType.LINE):
        expected = "line" if wants_line else "polygon zone"
        return _needs_clarification(
            f"The selected geometry cannot run a {candidate.rule_type} job.",
            f"Which saved {expected} should be used?",
        )

    common = {
        "object_class": _normalized(candidate.object_class),
        "minimum_confidence": candidate.minimum_confidence,
        "absence_grace_seconds": candidate.absence_grace_seconds,
    }
    if candidate.rule_type == "line_crossing":
        compiled: CameraJobSpec = LineCrossingJob(
            **common,
            line_id=geometry.id,
            line_name=geometry.name,
            direction=candidate.direction or "any",
        )
    else:
        zone = {"zone_id": geometry.id, "zone_name": geometry.name}
        if candidate.rule_type == "zone_dwell":
            if not candidate.duration_seconds:
                return _needs_clarification(
                    "A dwell duration is required.", "How long should the object remain?"
                )
            compiled = ZoneDwellJob(**common, **zone, duration_seconds=candidate.duration_seconds)
        elif candidate.rule_type == "zone_presence":
            compiled = ZonePresenceJob(
                **common, **zone, confirmation_seconds=candidate.duration_seconds or 0
            )
        elif candidate.rule_type == "zone_entry":
            compiled = ZoneEntryJob(**common, **zone)
        elif candidate.rule_type == "zone_exit":
            compiled = ZoneExitJob(**common, **zone)
        else:
            if candidate.comparison is None or candidate.threshold is None:
                return _needs_clarification(
                    "A count threshold is required.", "What count should trigger the event?"
                )
            compiled = CountThresholdJob(
                **common,
                **zone,
                comparison=candidate.comparison,
                threshold=candidate.threshold,
                confirmation_seconds=candidate.duration_seconds or 0,
            )
    return candidate, compiled


async def compile_rule_prompt(
    settings: ApiSettings,
    prompt: str,
    zones: list[Zone],
) -> CompilationResult:
    configured = settings.rule_compiler_provider
    configured_key = (
        settings.openai_api_key.get_secret_value().strip() if settings.openai_api_key else ""
    )
    api_key = configured_key or None
    warnings: list[str] = []

    if configured == "deterministic" or (configured == "auto" and not api_key):
        provider: CandidateProvider = DeterministicRuleProvider()
    elif not api_key:
        raise RuleCompilerProviderError(
            "VIDEO_INTEL_API_OPENAI_API_KEY is required when the OpenAI compiler is selected."
        )
    else:
        provider = OpenAIRuleProvider(api_key, settings.openai_rule_compiler_model)

    try:
        candidate = await provider.compile(prompt, zones)
    except RuleCompilerProviderError:
        if configured != "auto" or provider.name == "deterministic":
            raise
        provider = DeterministicRuleProvider()
        candidate = await provider.compile(prompt, zones)
        warnings.append(
            "OpenAI was unavailable, so the deterministic compiler handled this revision."
        )

    candidate, compiled = _resolve_candidate(candidate, zones)
    if compiled is not None:
        capability = check_job_capability(compiled, settings, prompt)
        if not capability.supported and capability.reason:
            warnings.append(f"Not deployable with the current model: {capability.reason}")
    logger.info(
        "Job compilation completed: provider=%s status=%s geometry_count=%d",
        provider.name,
        "ready_for_review" if compiled else "needs_clarification",
        len(zones),
    )
    return CompilationResult(provider.name, provider.model, candidate, compiled, warnings)
