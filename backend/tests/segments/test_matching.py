"""Tests for segments.matching on synthetic routes.

The map is flat: the start node is at the origin and the summit node 1800 m north,
both with the default 50 m radius. A walker at 1.2 m/s leaves the start circle at
y = +50 and enters the summit circle at y = 1750, so a plain ascent from y = -150
takes 1700 m / 1.2 m/s = 1417 s between the nodes.
"""

import random

import pytest

import google_health.stops as stops
import segments.geo as geo
import segments.matching as matching
from tests._helpers.segments import build_route, height_at, node

START = node(0, 0)
SUMMIT = node(0, 1800)
CLIMB_S = 1700 / 1.2


def _match(route, start=START, end=SUMMIT):
    return matching.match_segment(route.points, start, end, route.heart_rate, route.elevation)


def test_a_plain_ascent_is_timed_from_leaving_the_start_to_entering_the_summit():
    route = build_route([("walk", (0, 1800))])

    result = _match(route)

    assert result is not None
    assert result.start_s == pytest.approx(200 / 1.2, abs=5)
    assert result.end_s == pytest.approx(1900 / 1.2, abs=5)
    assert result.elapsed_s == pytest.approx(CLIMB_S, abs=6)
    assert result.moving_s == pytest.approx(result.elapsed_s)
    assert result.stopped_s == 0
    assert result.distance_m == pytest.approx(1700, rel=0.1)


def test_the_rest_at_the_summit_is_not_part_of_the_segment():
    plain = _match(build_route([("walk", (0, 1800))]))
    with_rest = _match(build_route([("walk", (0, 1800)), ("rest", 900), ("walk", (0, 0))]))

    assert with_rest.elapsed_s == pytest.approx(plain.elapsed_s, abs=6)
    assert with_rest.end_s == pytest.approx(plain.end_s, abs=6)


def test_a_long_stop_on_the_way_counts_in_elapsed_time_but_not_in_moving_time():
    route = build_route([("walk", (0, 900)), ("rest", 480), ("walk", (0, 1800))])

    result = _match(route)

    assert result.stopped_s == pytest.approx(480, abs=40)
    assert result.elapsed_s == pytest.approx(CLIMB_S + 480, abs=40)
    assert result.moving_s == pytest.approx(CLIMB_S, abs=50)
    assert len(result.stops) == 1


def test_moving_time_is_the_same_whatever_the_rests_were():
    # The point of the segment comparison: a climb is a climb, with or without a long rest.
    tours = [
        build_route([("walk", (0, 1800))], seed=1),
        build_route([("walk", (0, 900)), ("rest", 480), ("walk", (0, 1800))], seed=2),
        build_route([("walk", (0, 600)), ("rest", 900), ("walk", (0, 1800))], seed=3),
    ]

    moving = [_match(tour).moving_s for tour in tours]

    assert max(moving) - min(moving) < 60
    assert moving[0] == pytest.approx(CLIMB_S, abs=10)


def test_a_short_rest_is_not_a_long_stop_and_stays_in_moving_time():
    route = build_route([("walk", (0, 900)), ("rest", 150), ("walk", (0, 1800))])

    result = _match(route)

    assert result.stopped_s == 0
    assert result.moving_s == pytest.approx(CLIMB_S + 150, abs=15)


def test_a_device_pause_inside_the_segment_is_taken_off_the_moving_time():
    route = build_route([("walk", (0, 900)), ("pause", 120), ("walk", (0, 1800))])

    result = _match(route)

    assert result.gap_s == pytest.approx(121, abs=2)
    assert result.elapsed_s == pytest.approx(CLIMB_S + 121, abs=8)
    assert result.moving_s == pytest.approx(CLIMB_S, abs=8)


def test_the_last_pass_of_the_start_before_the_summit_is_the_start():
    # Up 400 m, back down through the start node, and then the real climb.
    route = build_route([("walk", (0, 400)), ("walk", (0, -100)), ("walk", (0, 1800))])

    result = _match(route)

    assert result.start_visits == 3
    assert result.start_s == pytest.approx(1001, abs=6)
    assert result.elapsed_s == pytest.approx(CLIMB_S, abs=8)


def test_the_first_summit_visit_ends_the_segment_and_later_ones_are_ignored():
    route = build_route([("walk", (0, 1800)), ("walk", (0, 1000)), ("walk", (0, 1800))])

    result = _match(route)

    assert result.end_visits == 2
    assert result.end_s == pytest.approx(1900 / 1.2, abs=6)


def test_a_later_descent_through_the_start_does_not_change_the_result():
    up = _match(build_route([("walk", (0, 1800))]))
    up_and_down = _match(build_route([("walk", (0, 1800)), ("rest", 300), ("walk", (0, -150))]))

    assert up_and_down.start_s == pytest.approx(up.start_s, abs=6)
    assert up_and_down.elapsed_s == pytest.approx(up.elapsed_s, abs=8)


def test_the_wrong_direction_does_not_match():
    descent = build_route([("walk", (0, -150))], start=(0, 1900))

    assert _match(descent) is None


def test_passing_only_one_of_the_nodes_does_not_match():
    assert _match(build_route([("walk", (0, 900))])) is None  # never reaches the summit
    assert _match(build_route([("walk", (0, 1800))], start=(0, 300))) is None  # starts beyond the start node


def test_a_route_far_from_both_nodes_does_not_match():
    assert _match(build_route([("walk", (300, 1800))], start=(300, -150))) is None


def test_the_radius_is_per_node():
    # The walker is 60 m east of both node centres.
    route = build_route([("walk", (60, 1800))], start=(60, -150))

    assert _match(route) is None
    assert _match(route, node(0, 0, 70), node(0, 1800, 70)) is not None
    assert _match(route, node(0, 0, 70), node(0, 1800, 50)) is None
    assert _match(route, node(0, 0, 50), node(0, 1800, 70)) is None


def test_a_bigger_summit_circle_is_reached_earlier():
    route = build_route([("walk", (0, 1800))])

    small = _match(route, START, node(0, 1800, 50))
    large = _match(route, START, node(0, 1800, 150))

    assert large.end_s == pytest.approx(small.end_s - 100 / 1.2, abs=6)


def test_dropped_points_do_not_change_the_times_much():
    route = build_route([("walk", (0, 1800))])
    rng = random.Random(9)  # noqa: S311 - deterministic test data
    thinned = [p for p in route.points if rng.random() > 0.2]  # 20 % of the points lost
    complete = _match(route)

    result = matching.match_segment(thinned, START, SUMMIT, route.heart_rate, route.elevation)

    assert result is not None
    assert result.start_s == pytest.approx(complete.start_s, abs=8)
    assert result.end_s == pytest.approx(complete.end_s, abs=8)


def test_heart_rate_is_averaged_over_the_moving_part_only():
    route = build_route([("walk", (0, 900)), ("rest", 480), ("walk", (0, 1800))])

    result = _match(route)

    # Walking heart rate rises from 102 to 170 along the way (mean about 136); the resting
    # 80 bpm would pull a plain average down to about 122.
    assert result.average_hr == pytest.approx(136, abs=2.5)
    assert result.max_hr == pytest.approx(170, abs=1)
    assert result.hr_samples == pytest.approx(CLIMB_S, abs=50)


def test_zero_heart_rate_readings_are_dropped():
    route = build_route([("walk", (0, 1800))])
    route.heart_rate[400:500] = [matching.Sample(s.t, 0.0) for s in route.heart_rate[400:500]]
    complete = build_route([("walk", (0, 1800))])

    result = _match(route)

    assert result.hr_samples == _match(complete).hr_samples - 100
    assert result.average_hr > 100


def test_a_route_without_heart_rate_or_height_still_matches():
    route = build_route([("walk", (0, 1800))])

    result = matching.match_segment(route.points, START, SUMMIT)

    assert result is not None
    assert result.average_hr is None
    assert result.max_hr is None
    assert result.hr_samples == 0
    assert result.elevation_gain_m is None
    assert result.net_elevation_m is None


def test_elevation_is_taken_between_the_nodes():
    route = build_route([("walk", (0, 1800))])

    result = _match(route)

    net = height_at(1750) - height_at(50)  # 340 m
    assert result.net_elevation_m == pytest.approx(net, abs=3)
    assert result.elevation_gain_m == pytest.approx(net, rel=0.05)
    assert result.elevation_loss_m < 10


def test_elevation_outside_the_segment_is_not_counted():
    # The walker first goes 150 m south of the start (a 30 m descent), then climbs the whole way.
    route = build_route([("walk", (0, -300)), ("walk", (0, 1800))], start=(0, -150))

    result = _match(route)

    assert result.elevation_loss_m < 10
    assert result.elevation_gain_m == pytest.approx(height_at(1750) - height_at(50), rel=0.05)


def test_stops_can_be_given_instead_of_detected():
    route = build_route([("walk", (0, 900)), ("rest", 480), ("walk", (0, 1800))])
    given = stops.LongStop(start=800, duration=500, trimmed_start=810, trimmed_duration=400, farthest_m=5)

    result = matching.match_segment(route.points, START, SUMMIT, stops=[given])

    assert result.stopped_s == 400


def test_a_stop_outside_the_segment_is_not_taken_off():
    route = build_route([("walk", (0, 1800)), ("rest", 600)])
    summit_stop = stops.LongStop(start=1700, duration=600, trimmed_start=1700, trimmed_duration=600, farthest_m=5)

    result = matching.match_segment(route.points, START, SUMMIT, stops=[summit_stop])

    assert result.stopped_s == 0
    assert result.stops == ()


def test_too_few_points_do_not_match():
    assert matching.match_segment([], START, SUMMIT) is None
    assert matching.match_segment(build_route([("walk", (0, 1800))]).points[:1], START, SUMMIT) is None


def _v(enter: float, exit_: float) -> geo.Interval:
    return geo.Interval(enter, exit_)


def test_choose_passes_picks_the_first_end_after_a_start_and_the_last_start_before_it():
    starts = [_v(0, 10), _v(100, 110), _v(300, 310)]
    ends = [_v(5, 8), _v(200, 210), _v(400, 410)]  # the first end visit has no start before it

    assert matching.choose_passes(starts, ends) == (_v(100, 110), _v(200, 210))
    assert matching.choose_passes(starts, [_v(50, 60), _v(200, 210)]) == (_v(0, 10), _v(50, 60))
    assert matching.choose_passes([], ends) is None
    assert matching.choose_passes(starts, []) is None
    assert matching.choose_passes([_v(300, 310)], [_v(50, 60)]) is None


class TestValidateNodes:
    def test_accepts_the_default_radii(self):
        assert matching.validate_nodes(START, SUMMIT) == []

    def test_radius_must_be_larger_than_25_m(self):
        assert matching.validate_nodes(node(0, 0, 25), SUMMIT) != []
        assert matching.validate_nodes(node(0, 0, 25.1), SUMMIT) == []
        assert matching.validate_nodes(START, node(0, 1800, 10)) != []

    def test_the_circles_must_not_overlap(self):
        assert matching.validate_nodes(node(0, 0, 60), node(0, 100, 60)) != []
        assert matching.validate_nodes(node(0, 0, 60), node(0, 130, 60)) == []

    def test_coordinates_must_be_on_earth(self):
        assert matching.validate_nodes(matching.Node(91.0, 5.0), SUMMIT) != []
        assert matching.validate_nodes(matching.Node(60.0, 181.0), SUMMIT) != []
        assert matching.validate_nodes(matching.Node(float("nan"), 5.0), SUMMIT) != []


class TestClassifyMiss:
    def test_matching_tracks_have_no_miss(self):
        assert matching.classify_miss([_v(0, 10)], [_v(100, 110)]) is None

    def test_which_node_was_missed(self):
        assert matching.classify_miss([], [_v(100, 110)]) == matching.MISS_START_NOT_REACHED
        assert matching.classify_miss([_v(0, 10)], []) == matching.MISS_END_NOT_REACHED
        assert matching.classify_miss([], []) == matching.MISS_BOTH_NOT_REACHED

    def test_the_wrong_order(self):
        assert matching.classify_miss([_v(100, 110)], [_v(0, 10)]) == matching.MISS_WRONG_ORDER


def test_visit_times_are_reported_for_both_nodes():
    route = build_route([("walk", (0, 1800)), ("walk", (0, 1000)), ("walk", (0, 1800))])

    result = _match(route)

    assert len(result.start_visit_s) == result.start_visits == 1
    assert len(result.end_visit_s) == result.end_visits == 2
    assert result.end_visit_s[0] == pytest.approx(result.end_s)
    assert result.end_visit_s[0] < result.end_visit_s[1]
