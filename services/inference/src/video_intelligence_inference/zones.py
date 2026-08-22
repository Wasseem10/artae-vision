"""Normalized polygon zones independent of camera resolution."""

from __future__ import annotations

from dataclasses import dataclass

from video_intelligence_inference.detector import Detection


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.x <= 1.0 or not 0.0 <= self.y <= 1.0:
            raise ValueError("Zone coordinates must be normalized between 0 and 1.")


@dataclass(frozen=True, slots=True)
class Zone:
    name: str
    points: tuple[Point, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Zone name cannot be empty.")
        if len(self.points) < 3:
            raise ValueError("A polygon zone requires at least three points.")

    def contains_point(self, point: Point) -> bool:
        """Return whether a point is inside the polygon, including its boundary."""
        inside = False
        previous = self.points[-1]
        for current in self.points:
            if _point_on_segment(point, previous, current):
                return True
            crosses = (current.y > point.y) != (previous.y > point.y)
            if crosses:
                intersection_x = (previous.x - current.x) * (point.y - current.y) / (
                    previous.y - current.y
                ) + current.x
                if point.x < intersection_x:
                    inside = not inside
            previous = current
        return inside

    def contains_detection(
        self,
        detection: Detection,
        *,
        frame_width: int,
        frame_height: int,
    ) -> bool:
        """Use the box's bottom-center point as the object's ground position."""
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("Frame dimensions must be greater than zero.")
        anchor = Point(
            x=((detection.x1 + detection.x2) / 2) / frame_width,
            y=detection.y2 / frame_height,
        )
        return self.contains_point(anchor)

    @classmethod
    def parse(cls, name: str, value: str) -> Zone:
        """Parse `x,y;x,y;x,y` coordinates from environment or CLI input."""
        try:
            points = tuple(
                Point(*(float(part) for part in pair.split(",", maxsplit=1)))
                for pair in value.split(";")
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Zone points must use normalized 'x,y;x,y;x,y' syntax.") from exc
        return cls(name=name, points=points)


@dataclass(frozen=True, slots=True)
class Line:
    """A directed two-point line used for crossing jobs."""

    name: str
    start: Point
    end: Point

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Line name cannot be empty.")
        if self.start == self.end:
            raise ValueError("A line requires two distinct points.")

    def side(self, point: Point) -> float:
        """Signed side: positive is left of start->end, negative is right."""
        return (self.end.x - self.start.x) * (point.y - self.start.y) - (
            self.end.y - self.start.y
        ) * (point.x - self.start.x)


def detection_anchor(detection: Detection, frame_width: int, frame_height: int) -> Point:
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("Frame dimensions must be greater than zero.")
    return Point(
        x=((detection.x1 + detection.x2) / 2) / frame_width,
        y=detection.y2 / frame_height,
    )


def _point_on_segment(point: Point, start: Point, end: Point, epsilon: float = 1e-9) -> bool:
    cross = (point.y - start.y) * (end.x - start.x) - (point.x - start.x) * (end.y - start.y)
    if abs(cross) > epsilon:
        return False
    return (
        min(start.x, end.x) - epsilon <= point.x <= max(start.x, end.x) + epsilon
        and min(start.y, end.y) - epsilon <= point.y <= max(start.y, end.y) + epsilon
    )
