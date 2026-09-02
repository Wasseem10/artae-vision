"""Offline MP4 execution that emits evaluation intervals instead of incidents."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from video_intelligence_inference.agent import _engine_for, _semantic_provider
from video_intelligence_inference.config import Settings
from video_intelligence_inference.control_plane import ResolvedRuleConfig
from video_intelligence_inference.detector import YoloDetector, YoloPoseDetector
from video_intelligence_inference.observer import (
    OverlappingSheetSampler,
    RequestBudget,
    VisionObserverProvider,
)
from video_intelligence_inference.pose_action import PersonFallRule, PersonFallRuleEngine
from video_intelligence_inference.source import EndOfStream, OpenCVVideoSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReplayInterval:
    start_seconds: float
    end_seconds: float
    label: str = "event"
    detected_at_seconds: float | None = None
    confidence: float | None = None

    def to_dict(self) -> dict[str, float | str]:
        payload: dict[str, float | str] = {
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "label": self.label,
        }
        if self.detected_at_seconds is not None:
            payload["detected_at_seconds"] = self.detected_at_seconds
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        return payload


@dataclass(frozen=True, slots=True)
class ReplayOutput:
    intervals: tuple[ReplayInterval, ...]
    provider_requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def _bounded_interval(
    *,
    start_seconds: float,
    end_seconds: float,
    duration_seconds: float,
    confidence: float,
) -> ReplayInterval | None:
    start = max(0.0, min(start_seconds, duration_seconds))
    end = max(start + 0.001, min(end_seconds, duration_seconds))
    if start >= duration_seconds:
        return None
    end = min(end, duration_seconds)
    return ReplayInterval(
        start_seconds=round(start, 6),
        end_seconds=round(end, 6),
        detected_at_seconds=round(end, 6),
        confidence=confidence,
    )


def _run_deterministic(
    settings: Settings,
    source_uri: str,
    duration_seconds: float,
    rule: ResolvedRuleConfig,
    *,
    source_factory: Callable[..., OpenCVVideoSource],
    detector_factory: Callable[..., YoloDetector],
    on_progress: Callable[[float], None] | None,
) -> ReplayOutput:
    source = source_factory(
        source_uri,
        width=settings.camera_width,
        height=settings.camera_height,
        fps=settings.camera_fps,
    )
    detector = detector_factory(
        model_name=settings.model_name,
        confidence_threshold=rule.minimum_confidence,
        iou_threshold=settings.iou_threshold,
        device=settings.device,
    )
    engine = _engine_for(rule)
    intervals: list[ReplayInterval] = []
    with source:
        while True:
            try:
                packet = source.read()
            except EndOfStream:
                break
            if on_progress is not None:
                on_progress(min(packet.timestamp_seconds, duration_seconds))
            height, width = packet.image.shape[:2]
            matches = engine.evaluate(
                detector.track(packet.image),
                timestamp_seconds=packet.timestamp_seconds,
                frame_width=width,
                frame_height=height,
            )
            for match in matches:
                interval = _bounded_interval(
                    start_seconds=match.entered_at_seconds,
                    end_seconds=match.occurred_at_seconds,
                    duration_seconds=duration_seconds,
                    confidence=match.confidence,
                )
                if interval is not None:
                    intervals.append(interval)
    return ReplayOutput(tuple(intervals))


def _run_semantic(
    settings: Settings,
    source_uri: str,
    duration_seconds: float,
    rule: ResolvedRuleConfig,
    *,
    source_factory: Callable[..., OpenCVVideoSource],
    provider_factory: Callable[[Settings], VisionObserverProvider],
    on_progress: Callable[[float], None] | None,
    request_budget: RequestBudget | None,
) -> ReplayOutput:
    assert rule.instruction is not None
    source = source_factory(
        source_uri,
        width=settings.camera_width,
        height=settings.camera_height,
        fps=settings.camera_fps,
    )
    sampler = OverlappingSheetSampler(
        sample_fps=settings.observer_sample_fps,
        window_frames=settings.observer_window_frames,
        overlap_frames=settings.observer_overlap_frames,
        frame_width=settings.observer_frame_width,
        frame_height=settings.observer_frame_height,
        columns=settings.observer_sheet_columns,
    )
    budget = request_budget or RequestBudget(
        per_minute=settings.replay_max_requests_per_minute,
        per_day=settings.replay_max_requests_per_day,
    )
    provider = provider_factory(settings)
    intervals: list[ReplayInterval] = []
    provider_requests = 0
    input_tokens = 0
    output_tokens = 0
    positive_windows = 0
    baseline_windows = 0
    in_window_baseline_allowed = True
    last_emitted_at = float("-inf")

    def process_window(window) -> None:
        nonlocal provider_requests, input_tokens, output_tokens
        nonlocal positive_windows, baseline_windows, in_window_baseline_allowed
        nonlocal last_emitted_at
        allowed, reason = budget.acquire(now_monotonic=time.monotonic())
        if not allowed:
            raise RuntimeError(f"Replay provider budget exhausted: {reason}")
        decision = provider.analyze(window, rule.instruction)
        provider_requests += 1
        input_tokens += decision.input_tokens
        output_tokens += decision.output_tokens
        if not decision.triggered:
            positive_windows = 0
            if (
                rule.temporal_mode == "transition"
                and decision.confidence >= rule.minimum_confidence
            ):
                baseline_windows = min(baseline_windows + 1, rule.baseline_windows)
                in_window_baseline_allowed = True
            return
        if decision.confidence < rule.minimum_confidence:
            positive_windows = 0
            return
        has_in_window_baseline = (
            in_window_baseline_allowed
            and decision.first_frame is not None
            and decision.first_frame > 1
        )
        if (
            rule.temporal_mode == "transition"
            and baseline_windows < rule.baseline_windows
            and not has_in_window_baseline
        ):
            positive_windows = 0
            return
        positive_windows += 1
        if positive_windows < rule.confirmation_windows:
            return
        positive_windows = 0
        if window.ended_at - last_emitted_at < rule.cooldown_seconds:
            return
        last_emitted_at = window.ended_at
        if rule.temporal_mode == "transition":
            baseline_windows = 0
            in_window_baseline_allowed = False
        first_frame = decision.first_frame or 1
        visible_at = window.started_at + ((first_frame - 1) / settings.observer_sample_fps)
        interval = _bounded_interval(
            start_seconds=visible_at,
            end_seconds=window.ended_at,
            duration_seconds=duration_seconds,
            confidence=decision.confidence,
        )
        if interval is not None:
            intervals.append(interval)

    try:
        with source:
            while True:
                try:
                    packet = source.read()
                except EndOfStream:
                    break
                if on_progress is not None:
                    on_progress(min(packet.timestamp_seconds, duration_seconds))
                window = sampler.add(packet.image, packet.timestamp_seconds)
                if window is None:
                    continue
                process_window(window)
            partial = sampler.flush()
            if partial is not None:
                process_window(partial)
    finally:
        provider.close()
    return ReplayOutput(
        tuple(intervals),
        provider_requests=provider_requests,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _run_pose(
    settings: Settings,
    source_uri: str,
    duration_seconds: float,
    rule: ResolvedRuleConfig,
    *,
    source_factory: Callable[..., OpenCVVideoSource],
    pose_detector_factory: Callable[..., YoloPoseDetector],
    on_progress: Callable[[float], None] | None,
) -> ReplayOutput:
    source = source_factory(
        source_uri,
        width=settings.camera_width,
        height=settings.camera_height,
        fps=settings.camera_fps,
    )
    detector = pose_detector_factory(
        model_name=settings.pose_model_name,
        confidence_threshold=rule.minimum_confidence,
        iou_threshold=settings.iou_threshold,
        device=settings.device,
    )
    engine = PersonFallRuleEngine(
        PersonFallRule(
            id=rule.rule_id,
            zone=rule.zone,
            minimum_confidence=rule.minimum_confidence,
            absence_grace_seconds=rule.absence_grace_seconds,
            cooldown_seconds=rule.cooldown_seconds,
        )
    )
    intervals: list[ReplayInterval] = []
    with source:
        while True:
            try:
                packet = source.read()
            except EndOfStream:
                break
            if on_progress is not None:
                on_progress(min(packet.timestamp_seconds, duration_seconds))
            height, width = packet.image.shape[:2]
            matches = engine.evaluate(
                detector.track(packet.image),
                timestamp_seconds=packet.timestamp_seconds,
                frame_width=width,
                frame_height=height,
            )
            for match in matches:
                interval = _bounded_interval(
                    start_seconds=match.entered_at_seconds,
                    end_seconds=match.occurred_at_seconds,
                    duration_seconds=duration_seconds,
                    confidence=match.confidence,
                )
                if interval is not None:
                    intervals.append(interval)
    return ReplayOutput(tuple(intervals))


def run_replay(
    settings: Settings,
    *,
    source_uri: str,
    duration_seconds: float,
    rule: ResolvedRuleConfig,
    source_factory: Callable[..., OpenCVVideoSource] = OpenCVVideoSource,
    detector_factory: Callable[..., YoloDetector] = YoloDetector,
    pose_detector_factory: Callable[..., YoloPoseDetector] = YoloPoseDetector,
    provider_factory: Callable[[Settings], VisionObserverProvider] = _semantic_provider,
    on_progress: Callable[[float], None] | None = None,
    request_budget: RequestBudget | None = None,
) -> ReplayOutput:
    """Execute exactly one stored job over a finite video source."""

    if source_uri.casefold().startswith(("webcam:", "rtsp://", "rtsps://")):
        raise ValueError("Replay evaluations require a finite video file")
    if rule.execution_strategy == "specialized_pose":
        return _run_pose(
            settings,
            source_uri,
            duration_seconds,
            rule,
            source_factory=source_factory,
            pose_detector_factory=pose_detector_factory,
            on_progress=on_progress,
        )
    if rule.rule_type == "semantic_vision":
        return _run_semantic(
            settings,
            source_uri,
            duration_seconds,
            rule,
            source_factory=source_factory,
            provider_factory=provider_factory,
            on_progress=on_progress,
            request_budget=request_budget,
        )
    return _run_deterministic(
        settings,
        source_uri,
        duration_seconds,
        rule,
        source_factory=source_factory,
        detector_factory=detector_factory,
        on_progress=on_progress,
    )
