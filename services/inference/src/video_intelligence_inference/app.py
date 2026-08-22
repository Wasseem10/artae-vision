import logging
import time

import cv2
from pydantic import ValidationError

from video_intelligence_inference.camera import CameraError, WebcamCamera
from video_intelligence_inference.config import Settings, get_settings
from video_intelligence_inference.detector import YoloDetector
from video_intelligence_inference.local_alerts import LocalAlertNotifier
from video_intelligence_inference.logging_config import configure_logging
from video_intelligence_inference.observer import (
    ContinuousObserver,
    DryRunVisionClient,
    GeminiVisionClient,
    ObserverArtifactSink,
    OverlappingSheetSampler,
    QwenVisionClient,
    VisionObserverProvider,
)
from video_intelligence_inference.visualization import draw_detections, draw_observer_status

logger = logging.getLogger(__name__)


def run(settings: Settings) -> None:
    """Run the synchronous capture, inference, and display loop."""

    detector = YoloDetector(
        model_name=settings.model_name,
        confidence_threshold=settings.confidence_threshold,
        iou_threshold=settings.iou_threshold,
        device=settings.device,
    )
    camera = WebcamCamera(
        index=settings.camera_index,
        width=settings.camera_width,
        height=settings.camera_height,
        fps=settings.camera_fps,
    )
    sampler: OverlappingSheetSampler | None = None
    observer: ContinuousObserver | None = None
    if settings.observer_enabled:
        sampler = OverlappingSheetSampler(
            sample_fps=settings.observer_sample_fps,
            window_frames=settings.observer_window_frames,
            overlap_frames=settings.observer_overlap_frames,
            frame_width=settings.observer_frame_width,
            frame_height=settings.observer_frame_height,
            columns=settings.observer_sheet_columns,
        )
        provider: VisionObserverProvider
        if settings.observer_provider == "gemini":
            assert settings.gemini_api_key is not None
            provider = GeminiVisionClient(
                api_key=settings.gemini_api_key.get_secret_value(),
                base_url=str(settings.gemini_base_url),
                model=settings.gemini_model,
                timeout_seconds=settings.observer_request_timeout_seconds,
            )
        elif settings.observer_provider == "qwen":
            assert settings.qwen_api_key is not None
            provider = QwenVisionClient(
                api_key=settings.qwen_api_key.get_secret_value(),
                base_url=str(settings.qwen_base_url),
                model=settings.qwen_model,
                timeout_seconds=settings.observer_request_timeout_seconds,
            )
        else:
            provider = DryRunVisionClient(settings.observer_dry_run_trigger_every)
        observer = ContinuousObserver(
            provider,
            settings.observer_rule,
            queue_size=settings.observer_queue_size,
            max_requests_per_minute=settings.observer_max_requests_per_minute,
            max_requests_per_day=settings.observer_max_requests_per_day,
            artifact_sink=ObserverArtifactSink(
                settings.observer_artifacts_directory,
                settings.observer_artifact_mode,
            ),
            on_decision=LocalAlertNotifier(),
        )
        observer.start()
        logger.info(
            "Continuous observer enabled: provider=%s sample_fps=%.2f window=%d overlap=%d",
            provider.name,
            settings.observer_sample_fps,
            settings.observer_window_frames,
            settings.observer_overlap_frames,
        )

    logger.info("Starting webcam detection; press q or Esc to stop")
    try:
        with camera:
            while True:
                frame = camera.read()
                if sampler is not None and observer is not None:
                    window = sampler.add(frame, time.monotonic())
                    if window is not None:
                        observer.submit(window)
                        if settings.observer_show_sheet:
                            cv2.imshow(f"{settings.window_title} - Observer Sheet", window.sheet)
                detections = detector.detect(frame)
                annotated_frame = draw_detections(frame, detections)
                if observer is not None:
                    annotated_frame = draw_observer_status(annotated_frame, observer.snapshot())
                cv2.imshow(settings.window_title, annotated_frame)

                key = cv2.waitKey(1) & 0xFF
                if (
                    key in (ord("q"), 27)
                    or cv2.getWindowProperty(settings.window_title, cv2.WND_PROP_VISIBLE) < 1
                ):
                    logger.info("Stop requested from display window")
                    break
    finally:
        if observer is not None:
            observer.close()
        cv2.destroyAllWindows()


def main() -> int:
    """Load configuration and translate expected failures into a clean exit code."""

    try:
        settings = get_settings()
    except ValidationError as error:
        configure_logging("ERROR")
        logger.error("Invalid configuration:\n%s", error)
        return 2

    configure_logging(settings.log_level)
    try:
        run(settings)
    except CameraError as error:
        logger.error("Camera error: %s", error)
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception:
        logger.exception("Inference service stopped unexpectedly")
        return 1

    logger.info("Inference service stopped")
    return 0
