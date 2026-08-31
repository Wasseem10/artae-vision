"""Small model-independent telemetry values emitted by the inference loop."""

from __future__ import annotations

from dataclasses import dataclass

from video_intelligence_inference.detector import Detection


@dataclass(frozen=True, slots=True)
class NormalizedDetection:
    x1: float
    y1: float
    x2: float
    y2: float
    label: str
    confidence: float
    track_id: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "label": self.label,
            "confidence": self.confidence,
            "track_id": self.track_id,
        }


@dataclass(frozen=True, slots=True)
class FrameTelemetry:
    fps: float
    inference_latency_ms: float
    frame_width: int
    frame_height: int
    detections: tuple[NormalizedDetection, ...]
    analysis_state: str | None = None
    analysis_sequence: int | None = None
    analysis_triggered: bool | None = None
    analysis_confidence: float | None = None
    analysis_summary: str | None = None
    analysis_error: str | None = None
    analysis_requests_today: int = 0
    analysis_request_limit_day: int = 0
    analysis_request_limit_minute: int = 0
    frames_processed: int = 0
    reconnect_count: int = 0
    recording_state: str = "disabled"
    recording_segments_completed: int = 0
    recording_dropped_frames: int = 0
    recording_error: str | None = None


def normalize_detections(
    detections: list[Detection], frame_width: int, frame_height: int
) -> tuple[NormalizedDetection, ...]:
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("Frame dimensions must be positive")

    def clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    return tuple(
        NormalizedDetection(
            x1=clamp(detection.x1 / frame_width),
            y1=clamp(detection.y1 / frame_height),
            x2=clamp(detection.x2 / frame_width),
            y2=clamp(detection.y2 / frame_height),
            label=detection.label,
            confidence=detection.confidence,
            track_id=detection.track_id,
        )
        for detection in detections
    )
