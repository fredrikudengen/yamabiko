"""The rules for where an activity came from, and which sources can be compared."""

import pytest

import segments.source as source


@pytest.mark.parametrize(
    ("googlehealth_id", "strava_id", "garmin_id", "import_info", "expected"),
    [
        # Google Health: its importer sets both the exercise id and import_source.
        ("abc", None, None, {"import_source": "google_health"}, "google_health"),
        ("abc", None, None, None, "google_health"),
        (None, None, None, {"import_source": "google_health"}, "google_health"),
        # Strava bulk import leaves strava_activity_id empty, so import_info is the only trace.
        (None, None, None, {"import_source": "Strava bulk import"}, "strava"),
        (None, 123, None, None, "strava"),
        (None, None, 456, None, "garmin"),
        # Nothing known: a manual upload or a basic bulk import.
        (None, None, None, None, "other"),
        (None, None, None, {}, "other"),
        (None, None, None, {"import_source": "Basic bulk import"}, "other"),
        # Mis-shaped import_info must not raise.
        (None, None, None, "not a dict", "other"),
    ],
)
def test_activity_source(googlehealth_id, strava_id, garmin_id, import_info, expected):
    assert source.activity_source(googlehealth_id, strava_id, garmin_id, import_info) == expected


def test_google_health_wins_over_a_strava_copy_id():
    assert source.activity_source("abc", 123, None, None) == "google_health"


def test_sources_list_matches_the_values_the_function_can_return():
    assert set(source.SOURCES) == {"google_health", "strava", "garmin", "other"}


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("google_health", "google_health", True),
        ("strava", "strava", True),
        ("garmin", "garmin", True),
        ("google_health", "strava", False),
        ("strava", "garmin", False),
        # Two unknowns may be two different devices.
        ("other", "other", False),
        ("other", "strava", False),
    ],
)
def test_comparable_sources(a, b, expected):
    assert source.comparable_sources(a, b) is expected
