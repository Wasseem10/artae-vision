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
from video_intelligence_inference.continuous_recording import BackgroundSegmentRecorder
from video_intelligence_inference.control_credentials import control_plane_headers
from video_intelligence_inference.control_plane import (
    ControlPlaneConfigError,
    ResolvedAgentConfig,
    ResolvedRuleConfig,
    fetch_agent_config,
)
from video_intelligence_inference.detector import YoloDetector, YoloPoseDetector
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
from video_intelligence_inference.pose_action import (
    PersonFallRule,
    PersonFallRuleSetEngine,
    pose_detections,
)
from video_intelligence_inference.recording_archive import BackgroundRecordingArchiveUploader
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
    proposer_model: str | None = None
    verifier_decision: ObserverDecision | None = None
    verifier_model: str | None = None
    verification_error: str | None = None


class _SemanticDecisionGate:
    """Confirm and deduplicate positive VLM windows before creating events."""

    def __init__(
        self,
        rule: ResolvedRuleConfig,
        outbox: queue.SimpleQueue[_SemanticTrigger],
        *,
        proposer_model: str | None = None,
        verifier: VisionObserverProvider | None = None,
    ) -> None:
        self._rule = rule
        self._outbox = outbox
        self._proposer_model = proposer_model
        self._verifier = verifier
        self._positive_windows = 0
        self._baseline_windows = 0
        self._in_window_baseline_allowed = True
        self._last_emitted_at = float("-inf")

    def __call__(self, window: ObservationWindow, decision: ObserverDecision) -> None:
        if not decision.triggered:
            self._positive_windows = 0
            if (
                self._rule.temporal_mode == "transition"
                and decision.confidence >= self._rule.minimum_confidence
            ):
                self._baseline_windows = min(
                    self._baseline_windows + 1,
                    self._rule.baseline_windows,
                )
                self._in_window_baseline_allowed = True
            return
        if decision.confidence < self._rule.minimum_confidence:
            self._positive_windows = 0
            return
        has_in_window_baseline = (
            self._in_window_baseline_allowed
            and decision.first_frame is not None
            and decision.first_frame > 1
        )
        if (
            self._rule.temporal_mode == "transition"
            and self._baseline_windows < self._rule.baseline_windows
            and not has_in_window_baseline
        ):
            self._positive_windows = 0
            return
        self._positive_windows += 1
        if self._positive_windows < self._rule.confirmation_windows:
            return
        self._positive_windows = 0
        if window.ended_at - self._last_emitted_at < self._rule.cooldown_seconds:
            return
        self._last_emitted_at = window.ended_at
        if self._rule.temporal_mode == "transition":
            self._baseline_windows = 0
            self._in_window_baseline_allowed = False
        verifier_decision = None
        verification_error = None
        if self._verifier is not None:
            try:
                verifier_decision = self._verifier.analyze(
                    window,
                    (
                        "Independently verify this proposed event using only direct visual "
                        f"evidence. Original rule: {self._rule.instruction or ''}. "
                        f"Proposer summary: {decision.summary}"
                    ),
                )
            except Exception as exc:
                verification_error = type(exc).__name__
                logger.exception(
                    "Independent semantic verification failed for rule=%s",
                    self._rule.rule_id,
                )
        self._outbox.put(
            _SemanticTrigger(
                self._rule,
                window,
                decision,
                proposer_model=self._proposer_model,
                verifier_decision=verifier_decision,
                verifier_model=self._verifier.name if self._verifier is not None else None,
                verification_error=verification_error,
            )
        )


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


def _semantic_verifier(settings: Settings) -> VisionObserverProvider | None:
    """Return a genuinely distinct verifier, or require operator review downstream."""
    if (
        settings.observer_provider != "gemini"
        or settings.gemini_api_key is None
        or settings.gemini_verifier_model.casefold() == settings.gemini_model.casefold()
    ):
        return None
    return GeminiVisionClient(
        api_key=settings.gemini_api_key.get_secret_value(),
        base_url=str(settings.gemini_base_url),
        model=settings.gemini_verifier_model,
        timeout_seconds=settings.observer_request_timeout_seconds,
    )


def _semantic_match(trigger: _SemanticTrigger) -> RuleMatch:
    rule = trigger.rule
    window = trigger.window
    decision = trigger.decision
    independent_verification = None
    if trigger.verifier_decision is not None:
        verifier_decision = trigger.verifier_decision
        if verifier_decision.confidence < rule.minimum_confidence:
            verifier_status = "uncertain"
        else:
            verifier_status = "confirmed" if verifier_decision.triggered else "rejected"
        independent_verification = {
            "status": verifier_status,
            "triggered": verifier_decision.triggered,
            "confidence": verifier_decision.confidence,
            "summary": verifier_decision.summary,
            "verifier_model": trigger.verifier_model,
        }
    elif trigger.verifier_model is not None or trigger.verification_error is not None:
        independent_verification = {
            "status": "uncertain",
            "triggered": None,
            "confidence": None,
            "summary": "Independent verification was unavailable; operator review is required.",
            "verifier_model": trigger.verifier_model,
            "error": trigger.verification_error,
        }
    details: dict[str, object] = {
        "instruction": rule.instruction or "",
        "summary": decision.summary,
        "first_frame": decision.first_frame,
        "window_sequence": window.sequence,
        "window_started_at_seconds": window.started_at,
        "window_ended_at_seconds": window.ended_at,
        "temporal_mode": rule.temporal_mode,
        "baseline_windows": rule.baseline_windows,
        "proposer_model": trigger.proposer_model,
        "scene_observations": [
            observation.model_dump(mode="json") for observation in decision.scene_observations
        ],
    }
    if independent_verification is not None:
        details["independent_verification"] = independent_verification
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
        details=details,
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
    pose_rules: list[ResolvedRuleConfig] = []
    if remote is None:
        engines: list[RuleEngine] = [DwellRuleEngine(rule) for rule in rules]
        geometries: list[Zone | Line] = [rule.zone for rule in rules]
        detector_rules = rules
    else:
        execution_plan = route_rules(remote.rules)
        semantic_rules = list(execution_plan.semantic_rules)
        pose_rules = list(execution_plan.pose_rules)
        deterministic_rules = list(execution_plan.deterministic_rules)
        engines = [_engine_for(rule) for rule in deterministic_rules]
        geometries = [rule.geometry for rule in [*deterministic_rules, *pose_rules]]
        detector_rules = deterministic_rules
    engine = RuleSetEngine(engines) if engines else None
    geometries = list(dict.fromkeys(geometries))
    # Semantic rules still use the vision-language observer for the actual
    # decision, but a lightweight local detector keeps the live preview
    # understandable by drawing tracked people and objects for the operator.
    detector = (
        YoloDetector(
            model_name=settings.model_name,
            confidence_threshold=(
                min(rule.minimum_confidence for rule in detector_rules)
                if detector_rules
                else settings.confidence_threshold
            ),
            iou_threshold=settings.iou_threshold,
            device=settings.device,
        )
        if detector_rules or semantic_rules
        else None
    )
    pose_detector = (
        YoloPoseDetector(
            model_name=settings.pose_model_name,
            confidence_threshold=min(0.25, *(rule.minimum_confidence for rule in pose_rules)),
            iou_threshold=settings.iou_threshold,
            device=settings.device,
        )
        if pose_rules
        else None
    )
    pose_engine = (
        PersonFallRuleSetEngine(
            [
                PersonFallRule(
                    id=rule.rule_id,
                    zone=rule.zone,
                    minimum_confidence=rule.minimum_confidence,
                    absence_grace_seconds=rule.absence_grace_seconds,
                    cooldown_seconds=rule.cooldown_seconds,
                )
                for rule in pose_rules
            ]
        )
        if pose_rules
        else None
    )
    source = OpenCVVideoSource(
        source_name,
        width=settings.camera_width,
        height=settings.camera_height,
        fps=settings.camera_fps,
        open_timeout_seconds=settings.camera_open_timeout_seconds,
        read_timeout_seconds=settings.camera_read_timeout_seconds,
        reconnect_attempts=settings.camera_reconnect_attempts,
        reconnect_backoff_seconds=settings.camera_reconnect_backoff_seconds,
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
    semantic_verifiers: list[VisionObserverProvider] = []
    for rule in semantic_rules:
        assert rule.instruction is not None
        proposer = _semantic_provider(settings)
        verifier = _semantic_verifier(settings)
        if verifier is not None:
            semantic_verifiers.append(verifier)
        semantic_observers.append(
            ContinuousObserver(
                proposer,
                rule.instruction,
                queue_size=settings.observer_queue_size,
                max_requests_per_minute=settings.observer_max_requests_per_minute,
                max_requests_per_day=settings.observer_max_requests_per_day,
                artifact_sink=ObserverArtifactSink(
                    settings.observer_artifacts_directory / camera_id / rule.rule_id,
                    settings.observer_artifact_mode,
                ),
                on_decision=_SemanticDecisionGate(
                    rule,
                    semantic_outbox,
                    proposer_model=proposer.name,
                    verifier=verifier,
                ),
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
            BackgroundRecordingArchiveUploader(
                control_plane_api_base,
                enabled=settings.continuous_recording_archive_enabled,
                headers=control_headers,
                spool_directory=settings.continuous_recording_spool_directory / camera_id,
                timeout_seconds=settings.webhook_timeout_seconds,
            ) as recording_uploads,
            BackgroundSegmentRecorder(
                enabled=settings.continuous_recording_enabled,
                camera_id=camera_id,
                output_directory=settings.continuous_recording_directory,
                fps=source.fps,
                segment_seconds=settings.continuous_recording_segment_seconds,
                retention_hours=settings.continuous_recording_retention_hours,
                maximum_bytes=settings.continuous_recording_max_bytes,
                queue_size=settings.continuous_recording_queue_size,
                on_segment=recording_uploads.submit,
            ) as continuous_recorder,
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
                    3 if pose_rules else 0,
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
                    continuous_recorder.submit(frame, packet.timestamp_seconds)
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
                    pose_observations = (
                        pose_detector.track(frame) if pose_detector is not None else []
                    )
                    if detector is None and pose_observations:
                        detections = pose_detections(pose_observations)
                    inference_latency_ms = (time.perf_counter() - inference_started) * 1000
                    frame_at = time.perf_counter()
                    fps = (
                        0.0 if last_frame_at is None else 1.0 / max(frame_at - last_frame_at, 1e-6)
                    )
                    last_frame_at = frame_at
                    if on_frame is not None:
                        recording = continuous_recorder.snapshot()
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
                                frames_processed=processed_frames + 1,
                                reconnect_count=source.reconnect_count,
                                recording_state=recording.state,
                                recording_segments_completed=recording.segments_completed,
                                recording_dropped_frames=recording.dropped_frames,
                                recording_error=recording.error,
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
                    if pose_engine is not None:
                        matches.extend(
                            pose_engine.evaluate(
                                pose_observations,
                                timestamp_seconds=packet.timestamp_seconds,
                                frame_width=width,
                                frame_height=height,
                            )
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
        for verifier in semantic_verifiers:
            verifier.close()
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
