"""First OpenVector-style vertical slice: camera -> rule -> evidence -> action."""

from __future__ import annotations

import argparse
import logging
import queue
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np
from pydantic import ValidationError

from video_intelligence_inference.actions import (
    BackgroundEvidenceUploader,
    BackgroundWebhookDispatcher,
)
from video_intelligence_inference.config import Settings, get_settings
from video_intelligence_inference.control_credentials import control_plane_headers
from video_intelligence_inference.control_plane import (
    ControlPlaneConfigError,
    ResolvedAgentConfig,
    ResolvedRuleConfig,
    fetch_agent_config,
)
from video_intelligence_inference.detector import YoloDetector
from video_intelligence_inference.events import (
    CompletedEvidence,
    EventRecord,
    EvidenceError,
    EvidenceRecorder,
    JsonlEventSink,
)
from video_intelligence_inference.logging_config import configure_logging
from video_intelligence_inference.observer import (
    ContinuousObserver,
    DryRunVisionClient,
    GeminiVisionClient,
    ObservationWindow,
    ObserverArtifactSink,
    ObserverDecision,
    OverlappingSheetSampler,
    QwenVisionClient,
    VisionObserverProvider,
)
from video_intelligence_inference.routing import route_rules
from video_intelligence_inference.rules import (
    CountThresholdRule,
    CountThresholdRuleEngine,
    DwellRule,
    DwellRuleEngine,
    LineCrossingRule,
    LineCrossingRuleEngine,
    RuleEngine,
    RuleMatch,
    RuleSetEngine,
    ZoneTransitionRule,
    ZoneTransitionRuleEngine,
)
from video_intelligence_inference.source import EndOfStream, OpenCVVideoSource, SourceError
from video_intelligence_inference.stream_publisher import BackgroundFramePublisher
from video_intelligence_inference.telemetry import FrameTelemetry, normalize_detections
from video_intelligence_inference.visualization import draw_detections, draw_line, draw_zone
from video_intelligence_inference.zones import Line, Zone

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _SemanticTrigger:
    rule: ResolvedRuleConfig
    window: ObservationWindow
    decision: ObserverDecision


class _SemanticDecisionGate:
    """Confirm and deduplicate positive VLM windows before creating events."""

    def __init__(
        self,
        rule: ResolvedRuleConfig,
        outbox: queue.SimpleQueue[_SemanticTrigger],
    ) -> None:
        self._rule = rule
        self._outbox = outbox
        self._positive_windows = 0
        self._last_emitted_at = float("-inf")

    def __call__(self, window: ObservationWindow, decision: ObserverDecision) -> None:
        if not decision.triggered or decision.confidence < self._rule.minimum_confidence:
            self._positive_windows = 0
            return
        self._positive_windows += 1
        if self._positive_windows < self._rule.confirmation_windows:
            return
        self._positive_windows = 0
        if window.ended_at - self._last_emitted_at < self._rule.cooldown_seconds:
            return
        self._last_emitted_at = window.ended_at
        self._outbox.put(_SemanticTrigger(self._rule, window, decision))


def _semantic_provider(settings: Settings) -> VisionObserverProvider:
    if settings.observer_provider == "gemini":
        if settings.gemini_api_key is None:
            raise ValueError("Gemini semantic jobs require VIDEO_INTEL_GEMINI_API_KEY")
        return GeminiVisionClient(
            api_key=settings.gemini_api_key.get_secret_value(),
            base_url=str(settings.gemini_base_url),
            model=settings.gemini_model,
            timeout_seconds=settings.observer_request_timeout_seconds,
        )
    if settings.observer_provider == "qwen":
        if settings.qwen_api_key is None:
            raise ValueError("Qwen semantic jobs require VIDEO_INTEL_QWEN_API_KEY")
        return QwenVisionClient(
            api_key=settings.qwen_api_key.get_secret_value(),
            base_url=str(settings.qwen_base_url),
            model=settings.qwen_model,
            timeout_seconds=settings.observer_request_timeout_seconds,
        )
    return DryRunVisionClient(settings.observer_dry_run_trigger_every)


def _semantic_match(trigger: _SemanticTrigger) -> RuleMatch:
    rule = trigger.rule
    window = trigger.window
    decision = trigger.decision
    return RuleMatch(
        rule_id=rule.rule_id,
        track_id=None,
        object_class=rule.object_class,
        zone_name=rule.geometry.name,
        entered_at_seconds=window.started_at,
        occurred_at_seconds=window.ended_at,
        dwell_seconds=max(0, window.ended_at - window.started_at),
        confidence=decision.confidence,
        event_type="semantic_vision",
        details={
            "instruction": rule.instruction or "",
            "summary": decision.summary,
            "first_frame": decision.first_frame,
            "window_sequence": window.sequence,
            "window_started_at_seconds": window.started_at,
            "window_ended_at_seconds": window.ended_at,
            "scene_observations": [
                observation.model_dump(mode="json") for observation in decision.scene_observations
            ],
        },
    )


def _engine_for(config: ResolvedRuleConfig) -> RuleEngine:
    rule_type = config.rule_type
    common = {
        "id": config.rule_id,
        "object_class": config.object_class,
        "minimum_confidence": config.minimum_confidence,
    }
    if rule_type in {"object_dwell", "zone_dwell", "zone_presence"}:
        duration = config.duration_seconds
        if rule_type == "zone_presence":
            duration = config.confirmation_seconds
        return DwellRuleEngine(
            DwellRule(
                **common,
                zone=config.zone,
                duration_seconds=duration,
                absence_grace_seconds=config.absence_grace_seconds,
                event_type=rule_type,
            )
        )
    if rule_type in {"zone_entry", "zone_exit"}:
        return ZoneTransitionRuleEngine(
            ZoneTransitionRule(
                **common,
                event_type=rule_type,
                zone=config.zone,
                absence_grace_seconds=config.absence_grace_seconds,
            )
        )
    if rule_type == "count_threshold":
        return CountThresholdRuleEngine(
            CountThresholdRule(
                **common,
                zone=config.zone,
                comparison=config.comparison,
                threshold=config.threshold,
                confirmation_seconds=config.confirmation_seconds,
            )
        )
    if rule_type == "line_crossing" and isinstance(config.geometry, Line):
        return LineCrossingRuleEngine(
            LineCrossingRule(
                **common,
                line=config.geometry,
                direction=config.direction,
                absence_grace_seconds=config.absence_grace_seconds,
            )
        )
    raise ValueError(f"Unsupported camera job type: {rule_type}")


def run(
    settings: Settings,
    *,
    source_override: str | None = None,
    display: bool = True,
    max_frames: int | None = None,
    resolved_config: ResolvedAgentConfig | None = None,
    publish_url: str | None = None,
    on_frame: Callable[[FrameTelemetry], None] | None = None,
    on_preview: Callable[[np.ndarray], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> int:
    """Run one camera and all assigned jobs until stopped."""
    if max_frames is not None and max_frames <= 0:
        raise ValueError("max_frames must be greater than zero.")

    source_name = source_override or settings.agent_source
    camera_id = settings.camera_id
    local_zone = Zone.parse(settings.zone_name, settings.zone_points)
    rules = [
        DwellRule(
            id=settings.dwell_rule_id,
            object_class="person",
            zone=local_zone,
            duration_seconds=settings.dwell_seconds,
            minimum_confidence=settings.confidence_threshold,
            absence_grace_seconds=settings.tracking_absence_grace_seconds,
        )
    ]
    remote = resolved_config
    if remote is None and settings.control_plane_camera_ref:
        credentials = control_plane_headers(settings)
        if settings.control_plane_url is None or not credentials:
            raise ValueError(
                "The control-plane URL and credentials are required when a camera reference is set."
            )
        remote = fetch_agent_config(
            str(settings.control_plane_url),
            headers=credentials,
            camera_ref=settings.control_plane_camera_ref,
            rule_ref=settings.control_plane_rule_ref,
            timeout_seconds=settings.webhook_timeout_seconds,
        )
    if remote is not None:
        source_name = source_override or remote.source_uri
        camera_id = remote.camera_id
    semantic_rules: list[ResolvedRuleConfig] = []
    if remote is None:
        engines: list[RuleEngine] = [DwellRuleEngine(rule) for rule in rules]
        geometries: list[Zone | Line] = [rule.zone for rule in rules]
        detector_rules = rules
    else:
        execution_plan = route_rules(remote.rules)
        semantic_rules = list(execution_plan.semantic_rules)
        deterministic_rules = list(execution_plan.deterministic_rules)
        engines = [_engine_for(rule) for rule in deterministic_rules]
        geometries = [rule.geometry for rule in deterministic_rules]
        detector_rules = deterministic_rules
    engine = RuleSetEngine(engines) if engines else None
    geometries = list(dict.fromkeys(geometries))
    detector = (
        YoloDetector(
            model_name=settings.model_name,
            confidence_threshold=min(rule.minimum_confidence for rule in detector_rules),
            iou_threshold=settings.iou_threshold,
            device=settings.device,
        )
        if detector_rules
        else None
    )
    source = OpenCVVideoSource(
        source_name,
        width=settings.camera_width,
        height=settings.camera_height,
        fps=settings.camera_fps,
    )
    event_sink = JsonlEventSink(settings.events_directory / "events.jsonl")
    webhook_url = str(settings.webhook_url) if settings.webhook_url else None
    control_plane_url = None
    control_plane_api_base = None
    control_headers: dict[str, str] = {}
    if settings.control_plane_url:
        control_headers = control_plane_headers(settings)
        if not control_headers:
            raise ValueError(
                "A device token or development agent key is required when the control plane is set."
            )
        control_plane_api_base = str(settings.control_plane_url).rstrip("/") + "/api/v1"
        control_plane_url = control_plane_api_base + "/agent/events"
    processed_frames = 0
    last_frame_at: float | None = None
    semantic_outbox: queue.SimpleQueue[_SemanticTrigger] = queue.SimpleQueue()
    semantic_sampler = (
        OverlappingSheetSampler(
            sample_fps=settings.observer_sample_fps,
            window_frames=settings.observer_window_frames,
            overlap_frames=settings.observer_overlap_frames,
            frame_width=settings.observer_frame_width,
            frame_height=settings.observer_frame_height,
            columns=settings.observer_sheet_columns,
        )
        if semantic_rules
        else None
    )
    semantic_observers: list[ContinuousObserver] = []
    for rule in semantic_rules:
        assert rule.instruction is not None
        semantic_observers.append(
            ContinuousObserver(
                _semantic_provider(settings),
                rule.instruction,
                queue_size=settings.observer_queue_size,
                max_requests_per_minute=settings.observer_max_requests_per_minute,
                max_requests_per_day=settings.observer_max_requests_per_day,
                artifact_sink=ObserverArtifactSink(
                    settings.observer_artifacts_directory / camera_id / rule.rule_id,
                    settings.observer_artifact_mode,
                ),
                on_decision=_SemanticDecisionGate(rule, semantic_outbox),
            )
        )

    logger.info(
        "Starting camera agent: source=%s jobs=%d geometries=%d",
        source.display_name,
        len(remote.rules) if remote else len(rules),
        len(geometries),
    )
    for observer in semantic_observers:
        observer.start()
    try:
        with (
            source,
            BackgroundFramePublisher(publish_url, fps=source.fps) as stream_publisher,
            BackgroundWebhookDispatcher(
                webhook_url,
                timeout_seconds=settings.webhook_timeout_seconds,
            ) as webhooks,
            BackgroundWebhookDispatcher(
                control_plane_url,
                timeout_seconds=settings.webhook_timeout_seconds,
                headers=control_headers,
                outbox_path=settings.offline_outbox_path if control_plane_url else None,
            ) as control_plane,
            BackgroundEvidenceUploader(
                control_plane_api_base,
                headers=control_headers,
                timeout_seconds=settings.webhook_timeout_seconds,
            ) as evidence_uploads,
        ):
            evidence = EvidenceRecorder(
                output_directory=settings.events_directory / "clips",
                fps=source.fps,
                pre_event_seconds=max(
                    settings.evidence_pre_seconds,
                    (
                        settings.observer_window_frames / settings.observer_sample_fps + 5
                        if semantic_rules
                        else 0
                    ),
                ),
                post_event_seconds=settings.evidence_post_seconds,
            )
            try:
                while max_frames is None or processed_frames < max_frames:
                    if should_stop is not None and should_stop():
                        logger.info("Managed stop requested")
                        break
                    try:
                        packet = source.read()
                    except EndOfStream:
                        logger.info("Finite video source completed")
                        break

                    frame = packet.image
                    stream_publisher.submit(frame)
                    if on_preview is not None:
                        on_preview(frame)
                    if semantic_sampler is not None:
                        window = semantic_sampler.add(frame, packet.timestamp_seconds)
                        if window is not None:
                            for observer in semantic_observers:
                                observer.submit(window)
                    height, width = frame.shape[:2]
                    inference_started = time.perf_counter()
                    detections = detector.track(frame) if detector is not None else []
                    inference_latency_ms = (time.perf_counter() - inference_started) * 1000
                    frame_at = time.perf_counter()
                    fps = (
                        0.0 if last_frame_at is None else 1.0 / max(frame_at - last_frame_at, 1e-6)
                    )
                    last_frame_at = frame_at
                    if on_frame is not None:
                        observer_snapshots = [
                            observer.snapshot() for observer in semantic_observers
                        ]
                        latest_observer = max(
                            observer_snapshots,
                            key=lambda snapshot: snapshot.sequence or -1,
                            default=None,
                        )
                        latest_decision = latest_observer.decision if latest_observer else None
                        on_frame(
                            FrameTelemetry(
                                fps=fps,
                                inference_latency_ms=inference_latency_ms,
                                frame_width=width,
                                frame_height=height,
                                detections=normalize_detections(detections, width, height),
                                analysis_state=(latest_observer.state if latest_observer else None),
                                analysis_sequence=(
                                    latest_observer.sequence if latest_observer else None
                                ),
                                analysis_triggered=(
                                    latest_decision.triggered if latest_decision else None
                                ),
                                analysis_confidence=(
                                    latest_decision.confidence if latest_decision else None
                                ),
                                analysis_summary=(
                                    latest_decision.summary if latest_decision else None
                                ),
                                analysis_error=(latest_observer.error if latest_observer else None),
                                analysis_requests_today=sum(
                                    snapshot.requests_today for snapshot in observer_snapshots
                                ),
                                analysis_request_limit_day=sum(
                                    snapshot.request_limit_day for snapshot in observer_snapshots
                                ),
                                analysis_request_limit_minute=sum(
                                    snapshot.request_limit_minute for snapshot in observer_snapshots
                                ),
                            )
                        )
                    matches = (
                        engine.evaluate(
                            detections,
                            timestamp_seconds=packet.timestamp_seconds,
                            frame_width=width,
                            frame_height=height,
                        )
                        if engine is not None
                        else []
                    )
                    while True:
                        try:
                            matches.append(_semantic_match(semantic_outbox.get_nowait()))
                        except queue.Empty:
                            break

                    new_events: list[EventRecord] = []
                    for match in matches:
                        event_id = str(uuid.uuid4())
                        record = EventRecord.create(
                            match,
                            camera_id=camera_id,
                            clip_path=evidence.path_for(event_id),
                            event_id=event_id,
                        )
                        new_events.append(record)

                    completed = evidence.process_frame(
                        frame,
                        timestamp_seconds=packet.timestamp_seconds,
                        new_events=new_events,
                    )
                    _handle_completed(completed, evidence_uploads, source.fps)
                    for record in new_events:
                        event_sink.write(record)
                        webhooks.submit(record)
                        control_plane.submit(record)
                        logger.warning(
                            "CAMERA EVENT: type=%s camera=%s track=%s geometry=%s metric=%.2f",
                            record.event_type,
                            record.camera_id,
                            record.track_id,
                            record.zone_name,
                            record.dwell_seconds,
                        )

                    processed_frames += 1
                    if display:
                        annotated = draw_detections(frame, detections)
                        for geometry in geometries:
                            annotated = (
                                draw_line(annotated, geometry)
                                if isinstance(geometry, Line)
                                else draw_zone(annotated, geometry)
                            )
                        cv2.imshow(settings.window_title, annotated)
                        if (
                            cv2.waitKey(1) & 0xFF in (ord("q"), 27)
                            or cv2.getWindowProperty(settings.window_title, cv2.WND_PROP_VISIBLE)
                            < 1
                        ):
                            logger.info("Stop requested from display window")
                            break
            finally:
                _handle_completed(evidence.close(), evidence_uploads, source.fps)
    finally:
        for observer in semantic_observers:
            observer.close()
        if display:
            cv2.destroyAllWindows()

    logger.info("Camera agent stopped after %d frames", processed_frames)
    return processed_frames


def _handle_completed(
    clips: list[CompletedEvidence], uploader: BackgroundEvidenceUploader, fps: float
) -> None:
    for clip in clips:
        logger.info(
            "Evidence ready for downstream indexing: event=%s path=%s frames=%d",
            clip.event_id,
            clip.path,
            clip.frame_count,
        )
        uploader.submit(clip.event_id, clip.path, duration_seconds=clip.frame_count / fps)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a tracked person-dwell rule on a webcam, MP4, or RTSP stream."
    )
    parser.add_argument(
        "--source",
        help="Override VIDEO_INTEL_AGENT_SOURCE (webcam:0, path.mp4, or rtsp://...)",
    )
    parser.add_argument("--no-display", action="store_true", help="Run without a GUI window")
    parser.add_argument(
        "--max-frames",
        type=int,
        help="Optional bounded frame count for smoke tests",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        settings = get_settings()
    except ValidationError as error:
        configure_logging("ERROR")
        logger.error("Invalid configuration:\n%s", error)
        return 2

    configure_logging(settings.log_level)
    try:
        run(
            settings,
            source_override=args.source,
            display=not args.no_display,
            max_frames=args.max_frames,
        )
    except (ControlPlaneConfigError, EvidenceError, SourceError, ValueError) as error:
        logger.error("Agent configuration/runtime error: %s", error)
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception:
        logger.exception("Dwell agent stopped unexpectedly")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
