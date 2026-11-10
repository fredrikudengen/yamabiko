"""Tests for the clock along a pass of a segment."""

import pytest

import segments.matching as matching
import segments.profile as profile
from tests._helpers.segments import build_route, node

START = node(0, 0)
SUMMIT = node(0, 1800)


def _profile(legs):
    route = build_route(legs)
    match = matching.match_segment(route.points, START, SUMMIT)
    assert match is not None
    return match, profile.effort_profile(route.points, match)


def test_the_profile_runs_from_zero_to_the_pass_times_at_every_hundredth():
    match, result = _profile([("walk", (0, 1800))])

    assert len(result.elapsed_s) == len(result.moving_s) == profile.PROFILE_STEPS + 1
    assert result.elapsed_s[0] == 0
    assert result.elapsed_s[-1] == pytest.approx(match.elapsed_s, abs=1)
    assert result.moving_s[-1] == pytest.approx(match.moving_s, abs=1)
    assert result.distance_m == pytest.approx(match.distance_m, rel=0.01)


def test_the_wander_during_a_long_stop_is_not_counted_as_way():
    match, result = _profile([("walk", (0, 900)), ("rest", 600), ("walk", (0, 1800))])
    _, without_stop = _profile([("walk", (0, 900)), ("walk", (0, 1800))])

    assert result.distance_m < match.distance_m
    assert result.distance_m == pytest.approx(without_stop.distance_m, rel=0.03)


def test_at_an_even_pace_half_the_way_takes_half_the_time():
    _, result = _profile([("walk", (0, 1800))])

    assert result.elapsed_s[50] == pytest.approx(result.elapsed_s[-1] / 2, rel=0.03)
    assert result.moving_s == pytest.approx(result.elapsed_s, abs=1)


def test_the_clock_never_runs_backwards():
    _, result = _profile([("walk", (0, 900)), ("rest", 600), ("walk", (0, 1800))])

    assert all(b >= a for a, b in zip(result.elapsed_s, result.elapsed_s[1:], strict=False))
    assert all(b >= a for a, b in zip(result.moving_s, result.moving_s[1:], strict=False))


def test_a_long_stop_halfway_jumps_the_total_clock_there_but_not_the_moving_one():
    match, result = _profile([("walk", (0, 900)), ("rest", 600), ("walk", (0, 1800))])

    assert match.stopped_s > 0
    # A tenth of the way is about 170 m, some 150 s of walking; the stop adds 600 s to the total clock.
    assert result.elapsed_s[55] - result.elapsed_s[45] > 600
    assert result.moving_s[55] - result.moving_s[45] < 200
    assert result.moving_s[-1] == pytest.approx(match.moving_s, abs=2)


def test_a_device_pause_is_off_the_moving_clock():
    match, result = _profile([("walk", (0, 900)), ("pause", 300), ("walk", (0, 1800))])

    assert match.gap_s > 0
    assert result.elapsed_s[-1] - result.moving_s[-1] == pytest.approx(match.gap_s, abs=2)
