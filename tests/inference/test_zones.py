import pytest
from video_intelligence_inference.detector import Detection
from video_intelligence_inference.zones import Point, Zone


def test_zone_uses_bottom_center_of_detection() -> None:
    zone = Zone.parse("loading-zone", "0.20,0.20;0.80,0.20;0.80,0.90;0.20,0.90")
    inside = Detection(40, 20, 60, 80, "person", 0.9, track_id=1)
    outside = Detection(0, 0, 10, 10, "person", 0.9, track_id=2)

    assert zone.contains_detection(inside, frame_width=100, frame_height=100)
    assert not zone.contains_detection(outside, frame_width=100, frame_height=100)
    assert zone.contains_point(Point(0.2, 0.2))


def test_invalid_zone_coordinates_are_rejected() -> None:
    with pytest.raises(ValueError, match="normalized"):
        Zone.parse("bad-zone", "0,0;2,0;0,1")
