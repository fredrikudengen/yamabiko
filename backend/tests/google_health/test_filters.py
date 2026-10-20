"""Tests for google_health.filters."""

import pytest

import google_health.filters as filters
from tests._helpers.google_health import data_point


def test_active_gps_session_with_stop_is_importable():
    assert filters.is_importable(data_point())


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"recording_method": "PASSIVELY_MEASURED", "has_gps": None}, "not actively measured"),
        # A copy written by another app (Strava via Apple Health) has no metadata at all.
        ({"recording_method": "UNKNOWN", "has_gps": None}, "not actively measured"),
        ({"has_gps": None}, "no GPS"),
        ({"has_gps": False}, "no GPS"),
        ({"events": ("START", "PAUSE")}, "not finished (no STOP event)"),
        ({"events": ()}, "not finished (no STOP event)"),
    ],
)
def test_skip_reasons(kwargs, reason):
    assert filters.skip_reason(data_point(**kwargs)) == reason


def test_exercise_id_is_last_path_segment():
    assert filters.exercise_id(data_point(exercise_id="5644645117879480480")) == "5644645117879480480"


@pytest.mark.parametrize("bad", [{}, {"name": None}, {"name": "noslash"}, {"name": "a/"}])
def test_exercise_id_missing(bad):
    assert filters.exercise_id(bad) is None
    assert filters.skip_reason(bad) == "no id"
