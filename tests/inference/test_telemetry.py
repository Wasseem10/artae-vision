from video_intelligence_inference.detector import Detection
from video_intelligence_inference.telemetry import normalize_detections


def test_normalize_detections_clamps_boxes_to_source_frame() -> None:
    detections = [
        Detection(-10, 20, 110, 250, "person", 0.9, 4),
    ]

    result = normalize_detections(detections, frame_width=100, frame_height=200)

    assert len(result) == 1
    assert result[0].x1 == 0
    assert result[0].y1 == 0.1
    assert result[0].x2 == 1
    assert result[0].y2 == 1
    assert result[0].track_id == 4
