"""Tests for the line-crossing rules in counting.py."""

import pytest

import counting

VERTICAL = [427, 0, 427, 480]  # splits the frame left/right
HORIZONTAL = [0, 240, 854, 240]  # splits the frame top/bottom


class TestBottomCenter:
    def test_takes_middle_of_the_bottom_edge(self):
        assert counting.bottom_center((100, 50, 200, 300)) == (150, 300)

    def test_returns_integers_for_float_boxes(self):
        point = counting.bottom_center((10.4, 20.9, 30.2, 40.7))
        assert point == (20, 40)
        assert all(isinstance(v, int) for v in point)


class TestSegmentsIntersect:
    def test_crossing_segments(self):
        assert counting.segments_intersect((0, 0), (10, 10), (0, 10), (10, 0))

    def test_parallel_segments_never_meet(self):
        assert not counting.segments_intersect((0, 0), (10, 0), (0, 5), (10, 5))

    def test_segment_stopping_short_of_the_line(self):
        assert not counting.segments_intersect((0, 0), (4, 0), (5, -5), (5, 5))

    def test_landing_exactly_on_the_line_counts(self):
        # The track reached the line, so it crossed. Requiring it to overshoot
        # would drop counts whenever a detection lands on the line.
        assert counting.segments_intersect((0, 0), (5, 0), (5, -5), (5, 5))

    def test_sliding_along_the_line_is_not_a_crossing(self):
        # Collinear movement never picks a side, so there is nothing to count.
        assert not counting.segments_intersect((0, 0), (10, 0), (5, 0), (15, 0))


class TestCrossingDirection:
    def test_left_to_right_over_a_vertical_line(self):
        assert counting.crossing_direction(VERTICAL, (400, 240), (450, 240)) == "out"

    def test_right_to_left_is_the_opposite(self):
        assert counting.crossing_direction(VERTICAL, (450, 240), (400, 240)) == "in"

    def test_flip_swaps_the_labels(self):
        forward = counting.crossing_direction(VERTICAL, (400, 240), (450, 240))
        flipped = counting.crossing_direction(VERTICAL, (400, 240), (450, 240), flip=True)
        assert forward != flipped

    def test_direction_follows_the_line_orientation(self):
        # Drawing the same line backwards mirrors which side counts as in.
        reversed_line = [VERTICAL[2], VERTICAL[3], VERTICAL[0], VERTICAL[1]]
        assert counting.crossing_direction(
            VERTICAL, (400, 240), (450, 240)
        ) != counting.crossing_direction(reversed_line, (400, 240), (450, 240))

    @pytest.mark.parametrize(
        "previous,current,expected",
        [
            ((427, 200), (427, 300), "in"),  # downward over a left-to-right line
            ((427, 300), (427, 200), "out"),  # upward
        ],
    )
    def test_horizontal_line(self, previous, current, expected):
        assert counting.crossing_direction(HORIZONTAL, previous, current) == expected


class TestCrossed:
    def test_returns_none_when_the_track_stays_on_one_side(self):
        assert counting.crossed(VERTICAL, (100, 240), (200, 240)) is None

    def test_reports_direction_when_the_line_is_crossed(self):
        assert counting.crossed(VERTICAL, (400, 240), (450, 240)) == "out"

    def test_opposite_travel_reports_the_opposite_direction(self):
        assert counting.crossed(VERTICAL, (450, 240), (400, 240)) == "in"

    def test_flip_is_honoured(self):
        assert counting.crossed(VERTICAL, (400, 240), (450, 240), flip=True) == "in"

    def test_a_round_trip_nets_to_zero(self):
        out = counting.crossed(VERTICAL, (400, 240), (450, 240))
        back = counting.crossed(VERTICAL, (450, 240), (400, 240))
        assert {out, back} == {"in", "out"}

    def test_diagonal_crossing_is_detected(self):
        assert counting.crossed(VERTICAL, (400, 100), (460, 380)) is not None


class TestRegionOfInterest:
    def test_shifts_a_point_back_into_full_frame_space(self):
        assert counting.to_full_frame((10, 20), origin=(100, 50)) == (110, 70)

    def test_a_zero_origin_changes_nothing(self):
        assert counting.to_full_frame((10, 20), origin=(0, 0)) == (10, 20)

    def test_detection_inside_a_region_still_crosses_the_full_frame_line(self):
        # A detection found at x=27 inside a region starting at x=400 really
        # sits at x=427 — exactly on the line. Forgetting the offset would
        # silently stop the counter, so pin the behaviour down.
        origin = (400, 200)
        previous = counting.to_full_frame((10, 40), origin)
        current = counting.to_full_frame((50, 40), origin)
        assert previous == (410, 240) and current == (450, 240)
        assert counting.crossed(VERTICAL, previous, current) == "out"
