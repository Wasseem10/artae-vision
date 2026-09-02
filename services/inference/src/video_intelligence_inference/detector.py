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


@dataclass(frozen=True, slots=True)
class PoseKeypoint:
    """One COCO pose landmark in source-frame pixel coordinates."""

    x: float
    y: float
    confidence: float


@dataclass(frozen=True, slots=True)
class PoseObservation:
    """A tracked person box and its 17-keypoint COCO pose."""

    detection: Detection
    keypoints: tuple[PoseKeypoint, ...]


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


class YoloPoseDetector:
    """Run a dedicated person-pose model with persistent track identities."""

    def __init__(
        self,
        model_name: str,
        confidence_threshold: float,
        iou_threshold: float,
        device: str | None = None,
    ) -> None:
        logger.info("Loading YOLO pose model: %s", model_name)
        self._model = YOLO(model_name)
        self._confidence_threshold = confidence_threshold
        self._iou_threshold = iou_threshold
        self._device = device or None
        logger.info("YOLO pose model loaded")

    def track(self, frame: np.ndarray) -> list[PoseObservation]:
        results = self._model.track(
            source=frame,
            conf=self._confidence_threshold,
            iou=self._iou_threshold,
            device=self._device,
            persist=True,
            tracker="bytetrack.yaml",
            verbose=False,
        )
        return _convert_pose_result(results[0])


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


def _convert_pose_result(result: object) -> list[PoseObservation]:
    boxes = result.boxes
    keypoints = getattr(result, "keypoints", None)
    keypoint_data = getattr(keypoints, "data", None)
    if boxes is None or len(boxes) == 0 or keypoint_data is None:
        return []

    coordinates = boxes.xyxy.cpu().tolist()
    confidences = boxes.conf.cpu().tolist()
    box_ids = getattr(boxes, "id", None)
    track_ids = box_ids.int().cpu().tolist() if box_ids is not None else [None] * len(boxes)
    pose_rows = keypoint_data.cpu().tolist()
    observations: list[PoseObservation] = []
    for box, confidence, track_id, pose_row in zip(
        coordinates,
        confidences,
        track_ids,
        pose_rows,
        strict=True,
    ):
        landmarks = tuple(
            PoseKeypoint(
                x=float(values[0]),
                y=float(values[1]),
                confidence=float(values[2]) if len(values) > 2 else 1.0,
            )
            for values in pose_row
        )
        observations.append(
            PoseObservation(
                detection=Detection(
                    x1=round(box[0]),
                    y1=round(box[1]),
                    x2=round(box[2]),
                    y2=round(box[3]),
                    label="person",
                    confidence=float(confidence),
                    track_id=int(track_id) if track_id is not None else None,
                ),
                keypoints=landmarks,
            )
        )
    return observations
