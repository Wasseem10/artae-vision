from typing import Any, ClassVar

import numpy as np
import pytest
import video_intelligence_inference.detector as detector_module
from video_intelligence_inference.detector import (
    Detection,
    PoseKeypoint,
    PoseObservation,
    YoloDetector,
    YoloPoseDetector,
)


class FakeTensor:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def cpu(self) -> "FakeTensor":
        return self

    def tolist(self) -> list[Any]:
        return self._values

    def int(self) -> "FakeTensor":
        return self


class FakeBoxes:
    xyxy = FakeTensor([[10.2, 20.4, 80.6, 90.8]])
    conf = FakeTensor([0.876])
    cls = FakeTensor([0.0])
    id = None

    def __len__(self) -> int:
        return 1


class FakeResult:
    boxes = FakeBoxes()
    names: ClassVar[dict[int, str]] = {0: "person"}


class FakeTrackedBoxes(FakeBoxes):
    id = FakeTensor([42])


class FakeTrackedResult(FakeResult):
    boxes = FakeTrackedBoxes()


class FakeKeypoints:
    data = FakeTensor([[[float(index), float(index + 1), 0.9] for index in range(17)]])


class FakePoseResult(FakeTrackedResult):
    keypoints = FakeKeypoints()


class FakeModel:
    def __init__(self) -> None:
        self.predict_arguments: dict[str, Any] = {}
        self.track_arguments: dict[str, Any] = {}

    def predict(self, **kwargs: Any) -> list[FakeResult]:
        self.predict_arguments = kwargs
        return [FakeResult()]

    def track(self, **kwargs: Any) -> list[FakeTrackedResult]:
        self.track_arguments = kwargs
        return [FakeTrackedResult()]


class FakePoseModel(FakeModel):
    def track(self, **kwargs: Any) -> list[FakePoseResult]:
        self.track_arguments = kwargs
        return [FakePoseResult()]


def test_detector_converts_yolo_result_to_model_independent_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_model = FakeModel()
    monkeypatch.setattr(detector_module, "YOLO", lambda _: fake_model)
    detector = YoloDetector(
        model_name="fake-model.pt",
        confidence_threshold=0.3,
        iou_threshold=0.5,
        device="cpu",
    )
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    detections = detector.detect(frame)

    assert detections == [
        Detection(x1=10, y1=20, x2=81, y2=91, label="person", confidence=0.876)
    ]
    assert fake_model.predict_arguments == {
        "source": frame,
        "conf": 0.3,
        "iou": 0.5,
        "device": "cpu",
        "verbose": False,
    }


def test_detector_returns_persistent_track_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_model = FakeModel()
    monkeypatch.setattr(detector_module, "YOLO", lambda _: fake_model)
    detector = YoloDetector("fake-model.pt", 0.3, 0.5, "cpu")
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    detections = detector.track(frame)

    assert detections[0].track_id == 42
    assert fake_model.track_arguments == {
        "source": frame,
        "conf": 0.3,
        "iou": 0.5,
        "device": "cpu",
        "persist": True,
        "tracker": "bytetrack.yaml",
        "verbose": False,
    }


def test_pose_detector_returns_tracked_person_landmarks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_model = FakePoseModel()
    monkeypatch.setattr(detector_module, "YOLO", lambda _: fake_model)
    detector = YoloPoseDetector("fake-pose.pt", 0.4, 0.5, "cpu")
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    observations = detector.track(frame)

    assert observations == [
        PoseObservation(
            detection=Detection(
                x1=10,
                y1=20,
                x2=81,
                y2=91,
                label="person",
                confidence=0.876,
                track_id=42,
            ),
            keypoints=tuple(
                PoseKeypoint(float(index), float(index + 1), 0.9) for index in range(17)
            ),
        )
    ]
