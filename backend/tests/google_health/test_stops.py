"""Tests for google_health.stops on synthetic wrist-GPS tracks."""

import random

import pytest

import google_health.stops as stops
from tests._helpers.google_health import make_track


def _points(segments):
    track = make_track(segments)
    t0 = track[0]["time"]
    return [stops.TrackPoint((p["time"] - t0).total_seconds(), p["lat"], p["lon"]) for p in track]


def test_walking_has_no_stops():
    assert stops.detect_long_stops(_points([("walk", 900)]), min_seconds=120) == []


def test_long_rest_with_wobble_is_found():
    # 5 min walk, 8 min rest, 5 min walk.
    found = stops.detect_long_stops(_points([("walk", 300), ("rest", 480), ("walk", 300)]))
    assert len(found) == 1
    stop = found[0]
    # Approximate: within about a minute of the real 8 minutes, and never longer than the raw run.
    assert stop.trimmed_duration == pytest.approx(480, abs=40)
    assert stop.trimmed_duration <= stop.duration
    assert stop.trimmed_start == pytest.approx(300, abs=40)


def test_stop_shorter_than_minimum_is_ignored():
    # The 2 minute stand-still is below the default 5 minute minimum.
    assert stops.detect_long_stops(_points([("walk", 300), ("rest", 120), ("walk", 300)])) == []


def test_two_minute_stand_found_with_lower_minimum():
    found = stops.detect_long_stops(_points([("walk", 300), ("rest", 120), ("walk", 300)]), min_seconds=100)
    assert len(found) == 1
    assert found[0].trimmed_duration == pytest.approx(120, abs=45)


def test_photo_stop_is_not_a_long_stop():
    assert stops.detect_long_stops(_points([("walk", 300), ("rest", 40), ("walk", 300)]), min_seconds=100) == []


def test_gap_ends_a_run():
    points = _points([("rest", 400)])
    # Cut a 60 s hole in the middle: neither half reaches 300 s.
    cut = [p for p in points if not 170 <= p.t < 230]
    assert stops.detect_long_stops(cut, min_seconds=300) == []


def test_empty_and_single_point():
    assert stops.detect_long_stops([]) == []
    assert stops.detect_long_stops([stops.TrackPoint(0, 60.0, 5.0)]) == []


def test_dropped_points_do_not_split_a_stop():
    """Real band: 10-25 % of points go missing while sitting still, in gaps of 6-11 s."""
    walk = [stops.TrackPoint(float(t), 60.0 + t * 1e-5, 5.0) for t in range(120)]
    start = walk[-1].t + 1
    rng = random.Random(1)  # noqa: S311 - synthetic test data
    rest = []
    t = start
    while t < start + 1080:
        rest.append(stops.TrackPoint(t, 60.0012 + rng.uniform(-3e-5, 3e-5), 5.0 + rng.uniform(-5e-5, 5e-5)))
        t += rng.choice([1, 1, 1, 1, 2, 7, 11])
    points = walk + rest

    found = stops.detect_long_stops(points)

    assert len(found) == 1
    assert found[0].duration == pytest.approx(1080, abs=30)


def test_gap_longer_than_the_limit_ends_the_stop():
    still = [stops.TrackPoint(float(t), 60.0, 5.0) for t in range(0, 400)]
    after_gap = [stops.TrackPoint(float(t), 60.0, 5.0) for t in range(500, 900)]

    found = stops.detect_long_stops(still + after_gap)

    assert [round(stop.duration) for stop in found] == [399, 399]
