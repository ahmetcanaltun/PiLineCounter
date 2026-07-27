"""Line-crossing geometry.

Kept free of OpenCV, numpy and the model runtime so the counting rules can be
reasoned about — and tested — on their own. `camera_processor` supplies the
detections; everything here is pure arithmetic.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

Point = tuple[int, int]
Line = Sequence[int]  # [x1, y1, x2, y2]
Box = Sequence[float]  # [x1, y1, x2, y2]
Direction = Literal["in", "out"]


def bottom_center(box: Box) -> Point:
    """Reference point of a detection: the middle of its bottom edge.

    Feet and wheels sit on the ground plane, so this point tracks along the
    surface an object actually moves on, unlike the box centre which drifts
    upward as the box grows.
    """
    x1, _, x2, y2 = box
    return (int(x1 + x2) // 2, int(y2))


def to_full_frame(point: Point, origin: Point) -> Point:
    """Shift a point from region-of-interest space back into full-frame space."""
    return (point[0] + origin[0], point[1] + origin[1])


def _ccw(a: Point, b: Point, c: Point) -> bool:
    """True when a, b, c wind counter-clockwise."""
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """True when segment AB crosses segment CD.

    A track point landing exactly on the line counts as a crossing — it did
    reach the line. Collinear overlap does not: a track sliding *along* the
    line never picks a side, so there is no direction to report.
    """
    return _ccw(a, c, d) != _ccw(b, c, d) and _ccw(a, b, c) != _ccw(a, b, d)


def crossing_direction(
    line: Line,
    previous: Point,
    current: Point,
    flip: bool = False,
) -> Direction:
    """Which way a track crossed the line.

    The sign of the cross product between the line vector and the movement
    vector says which side the object came from. `flip` swaps the labels, which
    is friendlier than asking the user to redraw the line backwards.
    """
    line_dx = line[2] - line[0]
    line_dy = line[3] - line[1]
    move_dx = current[0] - previous[0]
    move_dy = current[1] - previous[1]

    cross = line_dx * move_dy - line_dy * move_dx
    direction: Direction = "in" if cross > 0 else "out"

    if flip:
        direction = "out" if direction == "in" else "in"
    return direction


def crossed(
    line: Line,
    previous: Point,
    current: Point,
    flip: bool = False,
) -> Direction | None:
    """Direction of travel if the track crossed the line, otherwise None."""
    start = (line[0], line[1])
    end = (line[2], line[3])
    if not segments_intersect(previous, current, start, end):
        return None
    return crossing_direction(line, previous, current, flip)
