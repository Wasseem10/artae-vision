"""Cross-industry camera calibration scenarios and evidence-readiness scoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from video_intelligence_api.models import ReplayEvaluation, ReplayEvaluationStatus

MetricFamily = Literal["temporal_event", "structured_text"]
AutomationStatus = Literal["ready", "manual_only"]
CalibrationStatus = Literal["no_evidence", "collecting", "failing", "ready", "manual_only"]


@dataclass(frozen=True, slots=True)
class CalibrationScenarioDefinition:
    key: str
    title: str
    industry_examples: tuple[str, ...]
    prompt: str
    description: str
    recording_protocol: tuple[str, ...]
    temporal_mode: Literal["state", "transition", "sequence"]
    visual_skills: tuple[str, ...]
    metric_family: MetricFamily
    automation_status: AutomationStatus = "ready"
    minimum_positive_clips: int = 2
    minimum_negative_clips: int = 2
    recommended_environment_tags: tuple[str, ...] = (
        "normal_light",
        "low_light",
        "partial_occlusion",
        "far_distance",
    )


SCENARIOS: tuple[CalibrationScenarioDefinition, ...] = (
    CalibrationScenarioDefinition(
        key="person_presence",
        title="Person presence",
        industry_examples=("retail", "healthcare", "offices", "security"),
        prompt="Alert me when a person is present in Full frame (automatic).",
        description="Baseline known-object detection without requiring an action interpretation.",
        recording_protocol=(
            "Record two clips where one person is clearly visible for at least three seconds.",
            "Record two negative clips of the same scene with no person visible.",
            "Include at least one low-light, distant, or partly occluded clip.",
        ),
        temporal_mode="state",
        visual_skills=(),
        metric_family="temporal_event",
    ),
    CalibrationScenarioDefinition(
        key="person_entry",
        title="Person entry",
        industry_examples=("warehousing", "retail", "security", "hospitality"),
        prompt="Alert me when a person enters Full frame (automatic).",
        description="Persistent tracking and a visible outside-to-inside transition.",
        recording_protocol=(
            "Begin with the monitored area empty, then have one person enter fully.",
            "Record approaches that do not enter as negative clips.",
            "Repeat once near the frame edge or with partial occlusion.",
        ),
        temporal_mode="transition",
        visual_skills=(),
        metric_family="temporal_event",
    ),
    CalibrationScenarioDefinition(
        key="ppe_removal",
        title="PPE removal",
        industry_examples=("construction", "manufacturing", "utilities"),
        prompt="Alert me when a worker removes their hard hat.",
        description="Before/after PPE reasoning with a required visible baseline.",
        recording_protocol=(
            "Show a worker wearing a hard hat before they remove it in view.",
            "Record negative clips where the hard hat stays on throughout.",
            "Repeat with a turned head or brief hand occlusion.",
        ),
        temporal_mode="transition",
        visual_skills=("ppe_compliance",),
        metric_family="temporal_event",
    ),
    CalibrationScenarioDefinition(
        key="person_fall",
        title="Person fall",
        industry_examples=("elder care", "healthcare", "industrial safety"),
        prompt="Alert me when a person falls to the ground.",
        description="Pose/action transition that must not confuse sitting or bending with a fall.",
        recording_protocol=(
            "Use a safe staged descent with another person present as a spotter.",
            "Record sitting, kneeling, and picking up an object as hard negatives.",
            "Repeat from a diagonal view without performing an unsafe real fall.",
        ),
        temporal_mode="transition",
        visual_skills=("pose_action",),
        metric_family="temporal_event",
    ),
    CalibrationScenarioDefinition(
        key="equipment_stop",
        title="Equipment stops moving",
        industry_examples=("manufacturing", "gyms", "logistics"),
        prompt="Alert me when the production line stops moving.",
        description="Scene-specific motion change with normal-operation baseline memory.",
        recording_protocol=(
            "Show the equipment moving steadily before it stops visibly.",
            "Record continuous normal motion as negative clips.",
            "Include a person briefly crossing in front without the equipment stopping.",
        ),
        temporal_mode="transition",
        visual_skills=("open_grounding", "change_anomaly"),
        metric_family="temporal_event",
    ),
    CalibrationScenarioDefinition(
        key="spill_appears",
        title="Liquid spill appears",
        industry_examples=("food service", "retail", "facilities", "manufacturing"),
        prompt="Alert me when a liquid spill appears on the floor.",
        description="Region appearance and scene change without confusing shadows or reflections.",
        recording_protocol=(
            "Use a safe small amount of water where the full appearance is visible.",
            "Record shadows, reflections, and an unchanged clean floor as negatives.",
            "Repeat with lower contrast between the liquid and floor.",
        ),
        temporal_mode="transition",
        visual_skills=("segmentation", "change_anomaly"),
        metric_family="temporal_event",
    ),
    CalibrationScenarioDefinition(
        key="package_fall",
        title="Package falls from line",
        industry_examples=("logistics", "manufacturing", "fulfillment"),
        prompt="Alert me when a package falls off the production line.",
        description="Object grounding plus a short ordered movement transition.",
        recording_protocol=(
            "Use an empty lightweight box and show it leaving the line into a safe area.",
            "Record normal package movement and manual package pickup as negatives.",
            "Repeat with another object moving in the background.",
        ),
        temporal_mode="transition",
        visual_skills=("open_grounding", "segmentation", "change_anomaly"),
        metric_family="temporal_event",
    ),
    CalibrationScenarioDefinition(
        key="serial_number_ocr",
        title="Serial-number reading",
        industry_examples=("manufacturing", "logistics", "maintenance"),
        prompt="Read the serial number on the finished product label.",
        description="Text correctness requires value-level scoring, not only event timing.",
        recording_protocol=(
            "Show labels with known serial numbers at near, medium, and far distances.",
            "Include glare, angled labels, and visually similar characters.",
            "Record the exact ground-truth string for every clip.",
        ),
        temporal_mode="state",
        visual_skills=("ocr_text",),
        metric_family="structured_text",
        automation_status="manual_only",
        minimum_positive_clips=3,
        minimum_negative_clips=0,
    ),
)

SCENARIO_BY_KEY = {scenario.key: scenario for scenario in SCENARIOS}
CREDIBLE_SOURCE_KINDS = {"controlled", "field", "public_benchmark"}
SITE_SPECIFIC_SOURCE_KINDS = {"controlled", "field"}
CHALLENGING_TAGS = {"low_light", "partial_occlusion", "far_distance", "camera_motion"}


class CalibrationScenarioRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    title: str
    industry_examples: list[str]
    prompt: str
    description: str
    recording_protocol: list[str]
    temporal_mode: Literal["state", "transition", "sequence"]
    visual_skills: list[str]
    metric_family: MetricFamily
    automation_status: AutomationStatus
    minimum_positive_clips: int
    minimum_negative_clips: int
    recommended_environment_tags: list[str]


class CalibrationScenarioStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    title: str
    status: CalibrationStatus
    credible_scored_clips: int = 0
    public_benchmark_clips: int = 0
    site_specific_clips: int = 0
    site_specific_ready: bool = False
    positive_clips: int = 0
    negative_clips: int = 0
    synthetic_pipeline_checks: int = 0
    challenging_clips: int = 0
    best_f1: float | None = None
    worst_recall: float | None = None
    false_positives: int = 0
    recommendations: list[str] = Field(default_factory=list)


class CalibrationReadiness(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["no_evidence", "collecting", "failing", "ready"]
    real_world_accuracy_claimable: bool
    benchmark_accuracy_claimable: bool
    site_specific_accuracy_claimable: bool
    required_scenarios: int
    ready_scenarios: int
    site_specific_ready_scenarios: int
    credible_scored_clips: int
    public_benchmark_clips: int
    site_specific_clips: int
    synthetic_pipeline_checks: int
    message: str
    scenarios: list[CalibrationScenarioStatus]


def scenario_payloads() -> list[CalibrationScenarioRead]:
    return [CalibrationScenarioRead.model_validate(asdict(scenario)) for scenario in SCENARIOS]


def _scenario_status(
    definition: CalibrationScenarioDefinition,
    evaluations: list[ReplayEvaluation],
) -> CalibrationScenarioStatus:
    matching = [item for item in evaluations if item.scenario_key == definition.key]
    synthetic = [
        item
        for item in matching
        if item.source_kind == "synthetic" and item.status == ReplayEvaluationStatus.SCORED
    ]
    credible = [
        item
        for item in matching
        if item.source_kind in CREDIBLE_SOURCE_KINDS
        and item.status == ReplayEvaluationStatus.SCORED
    ]
    public_benchmark = [item for item in credible if item.source_kind == "public_benchmark"]
    site_specific = [item for item in credible if item.source_kind in SITE_SPECIFIC_SOURCE_KINDS]
    positive = [item for item in credible if item.scenario_variant == "positive"]
    negative = [item for item in credible if item.scenario_variant == "negative"]
    challenging = [
        item for item in credible if CHALLENGING_TAGS.intersection(item.environment_tags or [])
    ]
    f1_values = [float(item.metrics.get("f1", 0)) for item in positive]
    recall_values = [float(item.metrics.get("recall", 0)) for item in positive]
    false_positives = sum(int(item.metrics.get("false_positives", 0)) for item in credible)
    site_positive = [item for item in site_specific if item.scenario_variant == "positive"]
    site_negative = [item for item in site_specific if item.scenario_variant == "negative"]
    site_challenging = [
        item for item in site_specific if CHALLENGING_TAGS.intersection(item.environment_tags or [])
    ]
    site_quality_values = [
        value
        for item in site_positive
        for value in (
            float(item.metrics.get("f1", 0)),
            float(item.metrics.get("recall", 0)),
        )
    ]
    site_specific_ready = (
        definition.automation_status == "ready"
        and len(site_positive) >= definition.minimum_positive_clips
        and len(site_negative) >= definition.minimum_negative_clips
        and bool(site_challenging)
        and all(value >= 0.8 for value in site_quality_values)
        and all(int(item.metrics.get("false_positives", 0)) == 0 for item in site_negative)
    )

    recommendations: list[str] = []
    if definition.automation_status == "manual_only":
        status: CalibrationStatus = "manual_only"
        recommendations.append(
            "Value-level scoring is not automated yet; temporal event scores cannot "
            "prove text accuracy."
        )
    elif not credible:
        status = "no_evidence"
        recommendations.append(
            "Import licensed benchmark footage or add controlled/field positive and negative clips."
        )
    else:
        enough_positive = len(positive) >= definition.minimum_positive_clips
        enough_negative = len(negative) >= definition.minimum_negative_clips
        has_challenge = bool(challenging)
        quality_passes = all(value >= 0.8 for value in f1_values + recall_values)
        negatives_pass = all(int(item.metrics.get("false_positives", 0)) == 0 for item in negative)
        if (
            enough_positive
            and enough_negative
            and has_challenge
            and quality_passes
            and negatives_pass
        ):
            status = "ready"
        elif (f1_values and min(f1_values) < 0.8) or false_positives > 0:
            status = "failing"
        else:
            status = "collecting"
        if not enough_positive:
            missing_positive = definition.minimum_positive_clips - len(positive)
            recommendations.append(f"Add {missing_positive} positive credible clip(s).")
        if not enough_negative:
            missing_negative = definition.minimum_negative_clips - len(negative)
            recommendations.append(f"Add {missing_negative} negative credible clip(s).")
        if not has_challenge:
            recommendations.append("Add a low-light, distant, moving, or partly occluded clip.")
        if f1_values and min(f1_values) < 0.8:
            recommendations.append(
                "Review missed events; improve camera placement before lowering "
                "confidence thresholds."
            )
        if false_positives:
            recommendations.append(
                "Review false alarms; increase confirmation or transition-baseline requirements."
            )

    return CalibrationScenarioStatus(
        key=definition.key,
        title=definition.title,
        status=status,
        credible_scored_clips=len(credible),
        public_benchmark_clips=len(public_benchmark),
        site_specific_clips=len(site_specific),
        site_specific_ready=site_specific_ready,
        positive_clips=len(positive),
        negative_clips=len(negative),
        synthetic_pipeline_checks=len(synthetic),
        challenging_clips=len(challenging),
        best_f1=max(f1_values) if f1_values else None,
        worst_recall=min(recall_values) if recall_values else None,
        false_positives=false_positives,
        recommendations=recommendations,
    )


def assess_calibration_readiness(
    evaluations: list[ReplayEvaluation],
) -> CalibrationReadiness:
    scenarios = [_scenario_status(definition, evaluations) for definition in SCENARIOS]
    required = [
        item
        for definition, item in zip(SCENARIOS, scenarios, strict=True)
        if definition.automation_status == "ready"
    ]
    ready_count = sum(item.status == "ready" for item in required)
    site_specific_ready_count = sum(item.site_specific_ready for item in required)
    credible_count = sum(item.credible_scored_clips for item in scenarios)
    public_benchmark_count = sum(item.public_benchmark_clips for item in scenarios)
    site_specific_count = sum(item.site_specific_clips for item in scenarios)
    synthetic_count = sum(item.synthetic_pipeline_checks for item in scenarios)
    if ready_count == len(required):
        status: Literal["no_evidence", "collecting", "failing", "ready"] = "ready"
        message = (
            "Every automated core scenario has credible positive, negative, "
            "and challenging evidence."
        )
    elif any(item.status == "failing" for item in required):
        status = "failing"
        message = (
            "At least one scenario has measured misses or false alarms that require correction."
        )
    elif credible_count:
        status = "collecting"
        message = "Credible evidence exists, but the cross-industry calibration pack is incomplete."
    else:
        status = "no_evidence"
        message = "No licensed benchmark, controlled, or field replay has been scored yet."
    return CalibrationReadiness(
        status=status,
        # Keep the original field as a conservative, site-specific claim for
        # older clients. Public benchmarks prove the general pipeline, not a
        # customer's camera placement, lighting, or operating conditions.
        real_world_accuracy_claimable=site_specific_ready_count == len(required),
        benchmark_accuracy_claimable=status == "ready",
        site_specific_accuracy_claimable=site_specific_ready_count == len(required),
        required_scenarios=len(required),
        ready_scenarios=ready_count,
        site_specific_ready_scenarios=site_specific_ready_count,
        credible_scored_clips=credible_count,
        public_benchmark_clips=public_benchmark_count,
        site_specific_clips=site_specific_count,
        synthetic_pipeline_checks=synthetic_count,
        message=message,
        scenarios=scenarios,
    )
