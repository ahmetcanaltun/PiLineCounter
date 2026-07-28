"""Everything drawn on top of a frame.

Separated from the processing pipeline because none of it affects what gets
counted — it only affects what an operator sees. Each function takes explicit
values rather than reading processor state, so the drawing can be changed
without touching the counting rules.

Colours are BGR, matching OpenCV.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import cv2

LINE = (255, 0, 255)  # counting line, magenta
ROI = (0, 200, 255)  # region of interest, amber
TRAIL = (0, 200, 255)  # track history
COUNTED = (0, 255, 100)  # a track that has already been counted, green
TRACKING = (255, 255, 0)  # a track still being followed, cyan
IN = (0, 255, 100)
OUT = (100, 100, 255)
MUTED = (150, 150, 150)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

FONT = cv2.FONT_HERSHEY_SIMPLEX
TRAIL_LENGTH = 30


def draw_line(frame, line: Sequence[int]) -> None:
    """The counting line and its two draggable endpoints."""
    start = (line[0], line[1])
    end = (line[2], line[3])
    cv2.line(frame, start, end, LINE, 2)
    for point in (start, end):
        cv2.circle(frame, point, 6, WHITE, -1)
        cv2.circle(frame, point, 6, LINE, 1)


def draw_roi(frame, x: int, y: int, width: int, height: int) -> None:
    """Outline the area inference is restricted to."""
    cv2.rectangle(frame, (x, y), (x + width, y + height), ROI, 2)
    cv2.putText(frame, "ROI", (x + 5, y + 20), FONT, 0.5, ROI, 1)


def draw_detection(
    frame,
    box: Sequence[int],
    label: str,
    counted: bool,
    trail: Sequence[tuple[int, int]],
    center: tuple[int, int],
) -> None:
    """One tracked object: its box, label, movement trail and reference point."""
    x1, y1, x2, y2 = box
    color = COUNTED if counted else TRACKING

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)

    (text_w, text_h), _ = cv2.getTextSize(label, FONT, 0.4, 1)
    cv2.rectangle(frame, (x1, y1 - text_h - 4), (x1 + text_w + 4, y1), BLACK, -1)
    cv2.putText(frame, label, (x1 + 2, y1 - 2), FONT, 0.4, color, 1)

    # The trail thins out towards older points.
    for i in range(1, len(trail)):
        thickness = max(1, int(math.sqrt(TRAIL_LENGTH / float(i + 1)) * 1.2))
        cv2.line(frame, trail[i - 1], trail[i], TRAIL, thickness)

    cv2.circle(frame, center, 3, BLACK, -1)
    cv2.circle(frame, center, 2, WHITE, -1)


def draw_hud(frame, fps: float, count_in: int, count_out: int) -> None:
    """Frame rate and running totals, on a dimmed panel in the corner."""
    panel = frame.copy()
    cv2.rectangle(panel, (4, 4), (95, 60), BLACK, -1)
    cv2.addWeighted(panel, 0.6, frame, 0.4, 0, frame)

    cv2.putText(frame, f"{fps:.1f} fps", (8, 18), FONT, 0.4, MUTED, 1)
    cv2.putText(frame, f"IN:  {count_in}", (8, 38), FONT, 0.5, IN, 1)
    cv2.putText(frame, f"OUT: {count_out}", (8, 55), FONT, 0.5, OUT, 1)


def draw_direction(frame, line: Sequence[int], flip: bool = False) -> None:
    """Arrows either side of the line showing which way counts as in."""
    dx = line[2] - line[0]
    dy = line[3] - line[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return

    # Unit vector perpendicular to the line; this side is "in" unless flipped.
    px, py = -dy / length, dx / length
    if flip:
        px, py = -px, -py

    cx = (line[0] + line[2]) // 2
    cy = (line[1] + line[3]) // 2
    offset, arrow = 30, 15

    # The wider "OUT" label needs a little more nudging to stay centred.
    for sign, text, color, nudge in ((1, "IN", IN, 8), (-1, "OUT", OUT, 12)):
        tip_x = int(cx + px * offset * sign)
        tip_y = int(cy + py * offset * sign)
        tail_x = int(tip_x + px * arrow * sign)
        tail_y = int(tip_y + py * arrow * sign)
        cv2.arrowedLine(frame, (tail_x, tail_y), (tip_x, tip_y), color, 1, tipLength=0.4)
        cv2.putText(frame, text, (tip_x - nudge, tip_y - 8), FONT, 0.4, color, 1)
