"""Tests for google_health.stops on synthetic wrist-GPS tracks."""

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
