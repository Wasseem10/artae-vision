import logging
from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Detection:
    """A model-independent object detection used by downstream modules."""

    x1: int
    y1: int
    x2: int
    y2: int
    label: str
    confidence: float
    track_id: int | None = None


class YoloDetector:
    """Load one Ultralytics YOLO model and run it on individual frames."""

    def __init__(
        self,
        model_name: str,
        confidence_threshold: float,
        iou_threshold: float,
        device: str | None = None,
    ) -> None:
        logger.info("Loading YOLO model: %s", model_name)
        self._model = YOLO(model_name)
        self._confidence_threshold = confidence_threshold
        self._iou_threshold = iou_threshold
        self._device = device or None
        logger.info("YOLO model loaded")

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self._model.predict(
            source=frame,
            conf=self._confidence_threshold,
            iou=self._iou_threshold,
            device=self._device,
            verbose=False,
        )
        return _convert_result(results[0])

    def track(self, frame: np.ndarray) -> list[Detection]:
        """Run persistent ByteTrack tracking and return stable object IDs."""
        results = self._model.track(
            source=frame,
            conf=self._confidence_threshold,
            iou=self._iou_threshold,
            device=self._device,
            persist=True,
            tracker="bytetrack.yaml",
            verbose=False,
        )
        return _convert_result(results[0])


def _convert_result(result: object) -> list[Detection]:
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return []

    coordinates = boxes.xyxy.cpu().tolist()
    confidences = boxes.conf.cpu().tolist()
    class_ids = boxes.cls.cpu().tolist()
    box_ids = getattr(boxes, "id", None)
    track_ids = box_ids.int().cpu().tolist() if box_ids is not None else [None] * len(boxes)

    return [
        Detection(
            x1=round(box[0]),
            y1=round(box[1]),
            x2=round(box[2]),
            y2=round(box[3]),
            label=str(result.names[int(class_id)]),
            confidence=float(confidence),
            track_id=int(track_id) if track_id is not None else None,
        )
        for box, confidence, class_id, track_id in zip(
            coordinates,
            confidences,
            class_ids,
            track_ids,
            strict=True,
        )
    ]
