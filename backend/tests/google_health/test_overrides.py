"""Tests for google_health.overrides on a synthetic TCX file."""

import pytest

import activities.activity.schema as activities_schema
import google_health.overrides as overrides
from tests._helpers.google_health import data_point, make_track, write_tcx


def _parsed_info(elapsed: float, ele_waypoints: list[dict], summary_distance: int) -> dict:
    """The parts of ``parse_tcx_file``'s payload that the overrides touch."""
    activity = activities_schema.Activity(
        distance=summary_distance,
        name="Workout",
        activity_type=10,
        total_elapsed_time=elapsed,
        total_timer_time=elapsed,
    )
    return {
        "activity": activity,
        "ele_waypoints": ele_waypoints,
        "laps": [{"total_distance": summary_distance}],
    }


@pytest.fixture
def track():
    return make_track([("walk", 300), ("rest", 480), ("walk", 300)])


def test_distance_uses_last_trackpoint_not_the_lower_summary(tmp_path, track):
    path = write_tcx(tmp_path / "a.tcx", track, summary_distance=track[-1]["distance"] * 0.85)
    parsed = _parsed_info(
        1079, [{"ele": p["ele"]} for p in track], summary_distance=round(track[-1]["distance"] * 0.85)
    )
    point = data_point(exercise_id="42", distance_mm=round(track[-1]["distance"] * 0.85 * 1000))

    result = overrides.apply_google_health_overrides(parsed, point, str(path))

    activity = result["activity"]
    assert activity.distance == round(track[-1]["distance"])
    info = activity.import_info["distance_m"]
    assert info["used"] == "last_trackpoint"
    assert info["summary"] == pytest.approx(track[-1]["distance"] * 0.85, abs=0.1)
    assert info["gps_path"] == pytest.approx(track[-1]["distance"], rel=0.01)
    # The single lap follows the activity.
    assert result["laps"][0]["total_distance"] == activity.distance
    # Pace follows timer time (here the 8 min rest is removed), not the clock.
    assert activity.pace == pytest.approx(activity.total_timer_time / activity.distance)
    assert activity.pace < 1079 / activity.distance


def test_timer_time_excludes_long_stop_but_elapsed_is_clock_time(tmp_path, track):
    path = write_tcx(tmp_path / "a.tcx", track)
    parsed = _parsed_info(1079, [{"ele": p["ele"]} for p in track], summary_distance=1000)

    activity = overrides.apply_google_health_overrides(parsed, data_point(), str(path))["activity"]

    stopped = activity.import_info["long_stops"]["stopped_seconds"]
    assert stopped == pytest.approx(480, abs=40)
    assert activity.total_elapsed_time == 1079
    assert activity.total_timer_time == pytest.approx(1079 - stopped)
    assert len(activity.import_info["long_stops"]["stops"]) == 1


def test_no_stop_leaves_timer_time_equal_to_elapsed(tmp_path):
    walk = make_track([("walk", 600)])
    path = write_tcx(tmp_path / "a.tcx", walk)
    parsed = _parsed_info(599, [{"ele": p["ele"]} for p in walk], summary_distance=1)

    activity = overrides.apply_google_health_overrides(parsed, data_point(), str(path))["activity"]

    assert activity.total_timer_time == 599
    assert activity.import_info["long_stops"]["stops"] == []


def test_identity_type_name_and_elevation(tmp_path, track):
    path = write_tcx(tmp_path / "a.tcx", track)
    # Height rises 1 m every 10 s (a smooth 0.02 m/s climb would fall under Endurain's
    # 0.1 m per-step threshold and count as 0, so the profile is stepped like real data).
    stepped = [{"ele": 50 + i // 10} for i in range(len(track))]
    parsed = _parsed_info(1079, stepped, summary_distance=1)
    point = data_point(exercise_id="5644645117879480480", exercise_type="HIKING", elevation_gain_mm=22555)

    activity = overrides.apply_google_health_overrides(parsed, point, str(path))["activity"]

    assert activity.googlehealth_activity_id == "5644645117879480480"
    assert activity.activity_type == 12  # Hike
    assert activity.name == "Gåing"
    # Gain is the device figure; loss comes from the smoothed track.
    assert activity.elevation_gain == 23
    assert activity.import_info["elevation_gain_m"]["used"] == "device_summary"
    assert activity.import_info["elevation_gain_m"]["endurain_smoothing"] == pytest.approx(107, abs=10)
    assert activity.import_info["elevation_gain_m"]["device_summary"] == pytest.approx(22.555)
    assert activity.import_info["import_source"] == "google_health"
    assert activity.elevation_loss == 0


def test_elevation_gain_falls_back_to_smoothing_without_a_device_figure(tmp_path, track):
    path = write_tcx(tmp_path / "a.tcx", track)
    stepped = [{"ele": 50 + i // 10} for i in range(len(track))]
    parsed = _parsed_info(1079, stepped, summary_distance=1)

    activity = overrides.apply_google_health_overrides(parsed, data_point(), str(path))["activity"]

    assert activity.import_info["elevation_gain_m"]["used"] == "endurain_smoothing"
    assert activity.elevation_gain == pytest.approx(107, abs=10)
    assert activity.import_info["elevation_gain_m"]["device_summary"] is None


@pytest.mark.parametrize(
    ("last", "path", "summary", "expected"),
    [
        (463.5, 464.8, 392.8, (463.5, "last_trackpoint")),
        (None, 464.8, 392.8, (464.8, "gps_path")),
        (0.0, None, 392.8, (392.8, "summary")),
        (None, None, None, (0.0, "none")),
    ],
)
def test_choose_distance_priority(last, path, summary, expected):
    assert overrides.choose_distance(last, path, summary) == expected


def test_device_pauses_are_subtracted_from_timer_time(tmp_path):
    walk = make_track([("walk", 600)])
    path = write_tcx(tmp_path / "a.tcx", walk)
    parsed = _parsed_info(599, [{"ele": p["ele"]} for p in walk], summary_distance=1)
    point = data_point()
    point["exercise"]["activeDuration"] = "3588s"  # interval is 3600 s: 12 s paused

    activity = overrides.apply_google_health_overrides(parsed, point, str(path))["activity"]

    assert activity.import_info["paused_seconds"] == 12
    assert activity.total_elapsed_time == 599
    assert activity.total_timer_time == 599 - 12


def test_missing_or_malformed_active_duration_means_no_pause(tmp_path):
    walk = make_track([("walk", 600)])
    path = write_tcx(tmp_path / "a.tcx", walk)
    for broken in (None, "n/a"):
        parsed = _parsed_info(599, [{"ele": p["ele"]} for p in walk], summary_distance=1)
        point = data_point()
        point["exercise"]["activeDuration"] = broken
        activity = overrides.apply_google_health_overrides(parsed, point, str(path))["activity"]
        assert activity.import_info["paused_seconds"] == 0
        assert activity.total_timer_time == 599


def test_stream_gap_is_reported(tmp_path):
    walk = make_track([("walk", 600)])
    cut = [p for p in walk if not 200 <= (p["time"] - walk[0]["time"]).total_seconds() < 260]
    path = write_tcx(tmp_path / "a.tcx", cut)
    parsed = _parsed_info(599, [{"ele": p["ele"]} for p in cut], summary_distance=1)

    activity = overrides.apply_google_health_overrides(parsed, data_point(), str(path))["activity"]

    assert activity.import_info["stream_gaps"] == {"count": 1, "seconds": 61}


def test_average_speed_and_pace_use_timer_time_and_max_speed_is_the_fastest_minute(tmp_path, track):
    path = write_tcx(tmp_path / "a.tcx", track)
    parsed = _parsed_info(1079, [{"ele": p["ele"]} for p in track], summary_distance=1)

    activity = overrides.apply_google_health_overrides(parsed, data_point(), str(path))["activity"]

    assert activity.average_speed == pytest.approx(activity.distance / activity.total_timer_time)
    assert activity.pace == pytest.approx(1 / activity.average_speed)
    # The fastest minute is a stretch of the walking segments, not the rest.
    assert activity.max_speed == pytest.approx(2.64, rel=0.05)
    info = activity.import_info
    assert info["pace"]["basis"] == "timer_time"
    assert info["pace"]["elapsed_s_per_m"] == pytest.approx(1079 / activity.distance)
    assert info["speed"]["max_window_s"] == 60.0


def test_fastest_speed_skips_windows_with_gaps_and_short_tracks():
    flat = [overrides.google_health_stops.TrackPoint(float(t), 60.0, 5.0) for t in range(120)]
    assert overrides.fastest_speed_m_s(flat) == pytest.approx(0.0)
    assert overrides.fastest_speed_m_s(flat[:30]) is None
    assert overrides.fastest_speed_m_s([]) is None
    # A 90 s hole in the stream: no 60 s window without a gap is long enough to count.
    gapped = flat[:40] + [
        overrides.google_health_stops.TrackPoint(p.t + 90.0, p.lat + 0.01, p.lon) for p in flat[40:80]
    ]
    assert overrides.fastest_speed_m_s(gapped) is None


@pytest.mark.parametrize(("raw", "expected"), [("14803", 14803), (9000, 9000), (None, None), ("x", None)])
def test_steps_are_stored_in_import_info(tmp_path, raw, expected):
    walk = make_track([("walk", 600)])
    path = write_tcx(tmp_path / "a.tcx", walk)
    parsed = _parsed_info(599, [{"ele": p["ele"]} for p in walk], summary_distance=1)
    point = data_point()
    if raw is not None:
        point["exercise"]["metricsSummary"]["steps"] = raw

    activity = overrides.apply_google_health_overrides(parsed, point, str(path))["activity"]

    assert activity.import_info["steps"] == expected


@pytest.mark.parametrize(
    ("exercise_type", "gain_mm", "hike"),
    [
        ("WALKING", 430_000, True),
        ("WALKING", 99_000, False),
        ("WALKING", None, False),
        ("RUNNING", 430_000, False),
        ("HIKING", 5_000, False),  # already a hike per the band; nothing to remap
    ],
)
def test_walks_with_a_real_climb_become_hikes(tmp_path, exercise_type, gain_mm, hike):
    walk = make_track([("walk", 600)])
    path = write_tcx(tmp_path / "a.tcx", walk)
    parsed = _parsed_info(599, [{"ele": 50} for _ in walk], summary_distance=1)
    point = data_point(exercise_type=exercise_type, elevation_gain_mm=gain_mm)

    activity = overrides.apply_google_health_overrides(parsed, point, str(path))["activity"]

    expected_type = overrides.activities_utils.define_activity_type(
        "HIKING" if hike or exercise_type == "HIKING" else exercise_type
    )
    assert activity.activity_type == expected_type
    assert (activity.name == overrides.HIKE_NAME) is hike
    assert activity.import_info["activity_type"]["remapped_to_hike"] is hike
