import numpy as np
from video_intelligence_inference.detector import Detection
from video_intelligence_inference.visualization import draw_detections


def test_draw_detections_returns_annotated_copy() -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    detection = Detection(
        x1=10,
        y1=20,
        x2=80,
        y2=90,
        label="person",
        confidence=0.876,
    )

    annotated = draw_detections(frame, [detection])

    assert annotated is not frame
    assert np.count_nonzero(annotated) > 0
    assert np.count_nonzero(frame) == 0
