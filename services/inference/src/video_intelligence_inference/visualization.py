from collections.abc import Iterable

import cv2
import numpy as np

from video_intelligence_inference.detector import Detection
from video_intelligence_inference.observer import ObserverSnapshot
from video_intelligence_inference.zones import Line, Zone

BOX_COLOR = (0, 200, 0)
TEXT_COLOR = (255, 255, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def draw_detections(frame: np.ndarray, detections: Iterable[Detection]) -> np.ndarray:
    """Return a copy of a frame with readable boxes and labels drawn on it."""

    annotated = frame.copy()
    for detection in detections:
        cv2.rectangle(
            annotated,
            (detection.x1, detection.y1),
            (detection.x2, detection.y2),
            BOX_COLOR,
            2,
        )

        track_text = f" #{detection.track_id}" if detection.track_id is not None else ""
        text = f"{detection.label}{track_text} {detection.confidence:.2f}"
        (text_width, text_height), baseline = cv2.getTextSize(text, FONT, 0.55, 1)
        text_y = max(detection.y1, text_height + baseline + 4)
        background_top = text_y - text_height - baseline - 4

        cv2.rectangle(
            annotated,
            (detection.x1, background_top),
            (detection.x1 + text_width + 6, text_y),
            BOX_COLOR,
            thickness=cv2.FILLED,
        )
        cv2.putText(
            annotated,
            text,
            (detection.x1 + 3, text_y - baseline - 2),
            FONT,
            0.55,
            TEXT_COLOR,
            1,
            cv2.LINE_AA,
        )

    return annotated


def draw_observer_status(frame: np.ndarray, snapshot: ObserverSnapshot) -> np.ndarray:
    """Return a copy with the latest continuous-observer state."""
    annotated = frame.copy()
    sequence = f" window {snapshot.sequence}" if snapshot.sequence is not None else ""
    text = f"VLM {snapshot.state}{sequence}"
    color = (0, 200, 255)
    if snapshot.decision is not None:
        label = "ALERT" if snapshot.decision.triggered else "clear"
        text = f"VLM {label} {snapshot.decision.confidence:.2f}: {snapshot.decision.summary}"
        color = (0, 0, 255) if snapshot.decision.triggered else (0, 200, 0)
    elif snapshot.error:
        text = f"VLM error: {snapshot.error}"
        color = (0, 0, 255)

    text = text[:110]
    cv2.rectangle(annotated, (8, 8), (min(annotated.shape[1] - 8, 900), 42), (0, 0, 0), cv2.FILLED)
    cv2.putText(annotated, text, (16, 32), FONT, 0.58, color, 2, cv2.LINE_AA)
    return annotated


def draw_zone(
    frame: np.ndarray, zone: Zone, *, color: tuple[int, int, int] = (0, 165, 255)
) -> np.ndarray:
    """Return a copy with a normalized polygon and its name rendered."""
    annotated = frame.copy()
    height, width = annotated.shape[:2]
    polygon = np.array(
        [[round(point.x * width), round(point.y * height)] for point in zone.points],
        dtype=np.int32,
    )
    cv2.polylines(annotated, [polygon], isClosed=True, color=color, thickness=2)
    label_x, label_y = polygon[0]
    cv2.putText(
        annotated,
        zone.name,
        (int(label_x), max(20, int(label_y) - 8)),
        FONT,
        0.6,
        color,
        2,
        cv2.LINE_AA,
    )
    return annotated


def draw_line(
    frame: np.ndarray, line: Line, *, color: tuple[int, int, int] = (255, 140, 0)
) -> np.ndarray:
    """Return a copy with a directed normalized line and label rendered."""
    annotated = frame.copy()
    height, width = annotated.shape[:2]
    start = (round(line.start.x * width), round(line.start.y * height))
    end = (round(line.end.x * width), round(line.end.y * height))
    cv2.arrowedLine(annotated, start, end, color, 2, tipLength=0.04)
    cv2.putText(
        annotated,
        line.name,
        (start[0], max(20, start[1] - 8)),
        FONT,
        0.6,
        color,
        2,
        cv2.LINE_AA,
    )
    return annotated
