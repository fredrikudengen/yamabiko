"""Overrides applied to the parsed TCX of a Google Health exercise.

``parse_tcx_file`` is left untouched. Its result is corrected afterwards,
because for Fitbit TCX files three of its values are not what we want:

- distance: the lap summary (``tcx_file.distance``) is ~15 % below the real
  distance on short walks. Measured against a route on a map (463 m), the last
  trackpoint's cumulative distance (463.5 m) and the geodesic GPS path
  (464.8 m) were right and the summary (392.8 m) was not.
- elevation: ``tcx_file.ascent`` is a naive sum of height changes (+8.6 %
  on a 430 m climb). Gain is the device's own figure, with Endurain's smoothing
  as the fallback and for loss.
- timer time: the TCX importer sets it to the clock time. It is set to the
  clock time minus device pauses (PAUSE/RESUME events) and long stops (see
  ``stops.py``).

It also adds what the TCX file lacks: pace and average speed on timer time, the
fastest minute as max speed, the step count, and Hike instead of Walk for walks
with a real climb.
"""

from __future__ import annotations

from datetime import datetime
from itertools import pairwise
from typing import Any

import tcxreader

import activities.activity.utils as activities_utils
import google_health.filters as google_health_filters
import google_health.stops as google_health_stops

IMPORT_SOURCE = "google_health"
# Bump when the way values are derived changes, so old rows can be told apart.
IMPORT_VERSION = 2

# A Fitbit "walk" that climbs at least this much (metres of gain) is a hike. The
# band has no hike/walk switch of its own for sessions started as a plain walk.
HIKE_MIN_GAIN_M = 100.0
HIKE_NAME = "Hike"
# Max speed is the fastest stretch of this length: a single GPS step of a wrist
# tracker says more about jitter than about speed.
MAX_SPEED_WINDOW_S = 60.0


def _gps_path_m(points: list[google_health_stops.TrackPoint]) -> float:
    """Sum of distances between consecutive GPS points (includes jitter)."""
    return sum(google_health_stops.distance_m(a, b) for a, b in pairwise(points))


def fastest_speed_m_s(
    points: list[google_health_stops.TrackPoint], window_s: float = MAX_SPEED_WINDOW_S
) -> float | None:
    """Speed over the fastest stretch of at least ``window_s`` seconds, in m/s.

    Stretches that contain a gap in the GPS stream longer than the stop gap limit
    are skipped. Returns None when no stretch is long enough.
    """
    if len(points) < 2:
        return None
    # cumulative[i] = GPS path length up to point i; gap_before[i] = a long gap ends at i
    cumulative = [0.0]
    gap_count = [0]
    for a, b in pairwise(points):
        cumulative.append(cumulative[-1] + google_health_stops.distance_m(a, b))
        gap_count.append(gap_count[-1] + (1 if b.t - a.t > google_health_stops.GAP_THRESHOLD_S else 0))
    best: float | None = None
    j = 0
    for i in range(len(points)):
        j = max(j, i)
        while j < len(points) - 1 and points[j].t - points[i].t < window_s:
            j += 1
        duration = points[j].t - points[i].t
        if duration < window_s or gap_count[j] - gap_count[i] > 0:
            continue
        speed = (cumulative[j] - cumulative[i]) / duration
        best = speed if best is None else max(best, speed)
    return best


def _steps(summary: dict) -> int | None:
    """The step count from the summary (the API may send 64-bit integers as strings)."""
    try:
        return int(summary["steps"])
    except (KeyError, TypeError, ValueError):
        return None


def choose_distance(
    last_trackpoint_m: float | None, gps_path_m: float | None, summary_m: float | None
) -> tuple[float, str]:
    """Pick the distance: last trackpoint, then GPS path, then the summary.

    Returns (metres, name of the source that was used).
    """
    for value, source in (
        (last_trackpoint_m, "last_trackpoint"),
        (gps_path_m, "gps_path"),
        (summary_m, "summary"),
    ):
        if value:
            return float(value), source
    return 0.0, "none"


def _paused_seconds(exercise: dict) -> float:
    """Seconds the device was paused: the interval minus ``activeDuration``.

    Real Charge 4 sessions contain PAUSE/RESUME events (and a PAUSE a few
    seconds before STOP at the end), and the device subtracts them from
    ``activeDuration``. It is not moving time (a stand-still without a pause
    event is counted as active), but explicit pauses should not count as time.
    """
    interval = exercise.get("interval") or {}
    try:
        start = datetime.fromisoformat(interval["startTime"])
        end = datetime.fromisoformat(interval["endTime"])
        active = float(str(exercise["activeDuration"]).removesuffix("s"))
    except (KeyError, TypeError, ValueError):
        return 0.0
    return max((end - start).total_seconds() - active, 0.0)


def _stream_gaps(points: list[google_health_stops.TrackPoint]) -> tuple[int, float]:
    """Number and total length of time gaps in the GPS stream (longer than the stop gap limit)."""
    gaps = [b.t - a.t for a, b in pairwise(points) if b.t - a.t > google_health_stops.GAP_THRESHOLD_S]
    return len(gaps), sum(gaps)


def _track_points(tcx_file: Any) -> list[google_health_stops.TrackPoint]:
    """GPS points as seconds since the first point and position."""
    raw = [
        tp
        for tp in tcx_file.trackpoints
        if tp.time is not None and tp.latitude is not None and tp.longitude is not None
    ]
    if not raw:
        return []
    t0 = raw[0].time
    return [google_health_stops.TrackPoint((tp.time - t0).total_seconds(), tp.latitude, tp.longitude) for tp in raw]


def _last_trackpoint_distance(tcx_file: Any) -> float | None:
    """Cumulative distance of the last trackpoint that has one."""
    for tp in reversed(tcx_file.trackpoints):
        if tp.distance is not None:
            return float(tp.distance)
    return None


def apply_google_health_overrides(parsed_info: dict, exercise_data_point: dict, tcx_path: str) -> dict:
    """Correct ``parsed_info`` (the result of ``parse_tcx_file``) in place.

    Args:
        parsed_info: Payload from ``parse_tcx_file``.
        exercise_data_point: The Google Health data point (JSON) the TCX
            was exported from.
        tcx_path: Path to the TCX file.

    Returns:
        The same payload, with distance, pace, elevation, timer time, type,
        name and import metadata set.
    """
    activity = parsed_info["activity"]
    exercise = exercise_data_point.get("exercise") or {}
    summary = exercise.get("metricsSummary") or {}

    tcx_file = tcxreader.TCXReader().read(tcx_path)
    points = _track_points(tcx_file)

    # ---- distance -------------------------------------------------------
    summary_mm = summary.get("distanceMillimeters")
    summary_m = float(summary_mm) / 1000 if summary_mm is not None else tcx_file.distance
    last_trackpoint_m = _last_trackpoint_distance(tcx_file)
    gps_path_m = _gps_path_m(points) if len(points) > 1 else None
    distance_m, distance_source = choose_distance(last_trackpoint_m, gps_path_m, summary_m)
    activity.distance = round(distance_m)

    # A single-lap file: keep the lap's distance consistent with the activity.
    laps = parsed_info.get("laps") or []
    if len(laps) == 1 and activity.distance:
        laps[0]["total_distance"] = activity.distance

    # ---- elevation ------------------------------------------------------
    # Gain is the device's own figure (what the Google Health app shows; it matched
    # the smoothing on a 430 m climb and was 2-3 m lower on small walks). Loss
    # exists only in the track, so it comes from Endurain's smoothing, which is
    # also the fallback for gain when the summary has no elevation.
    ele_waypoints = parsed_info.get("ele_waypoints") or []
    smoothed_gain: float | None = None
    if ele_waypoints:
        smoothed_gain, loss = activities_utils.compute_elevation_gain_and_loss(ele_waypoints)
        activity.elevation_loss = round(loss)
    device_gain_mm = summary.get("elevationGainMillimeters")
    device_gain_m = float(device_gain_mm) / 1000 if device_gain_mm is not None else None
    if device_gain_m is not None:
        activity.elevation_gain = round(device_gain_m)
        gain_source = "device_summary"
    elif smoothed_gain is not None:
        activity.elevation_gain = round(smoothed_gain)
        gain_source = "endurain_smoothing"
    else:
        gain_source = "none"

    # ---- time without long stops ---------------------------------------
    stops = google_health_stops.detect_long_stops(points) if points else []
    stopped_s = sum(stop.trimmed_duration for stop in stops)
    paused_s = _paused_seconds(exercise)
    gap_count, gap_seconds = _stream_gaps(points)
    elapsed = activity.total_elapsed_time
    if elapsed is not None:
        activity.total_timer_time = max(elapsed - paused_s - stopped_s, 0)

    # ---- pace and speed (on timer time, so a long rest does not slow them) ----
    moving_s = activity.total_timer_time or elapsed
    pace_basis = "none"
    if activity.distance and moving_s:
        activity.pace = moving_s / activity.distance
        activity.average_speed = activity.distance / moving_s
        pace_basis = "timer_time"
    max_speed = fastest_speed_m_s(points)
    if max_speed is not None:
        activity.max_speed = max_speed
    elapsed_pace = elapsed / activity.distance if elapsed and activity.distance else None

    # ---- identity, type, name ------------------------------------------
    activity.googlehealth_activity_id = google_health_filters.exercise_id(exercise_data_point)
    exercise_type = exercise.get("exerciseType")
    if exercise_type:
        activity.activity_type = activities_utils.define_activity_type(exercise_type)
    display_name = exercise.get("displayName")
    if display_name:
        activity.name = display_name
    climb_m = device_gain_m if device_gain_m is not None else smoothed_gain
    remapped_to_hike = False
    if (
        exercise_type
        and activity.activity_type == activities_utils.define_activity_type("WALKING")
        and climb_m is not None
        and climb_m >= HIKE_MIN_GAIN_M
    ):
        activity.activity_type = activities_utils.define_activity_type("HIKING")
        activity.name = HIKE_NAME
        remapped_to_hike = True

    activity.import_info = {
        "import_source": IMPORT_SOURCE,
        "import_version": IMPORT_VERSION,
        "distance_m": {
            "used": distance_source,
            "last_trackpoint": last_trackpoint_m,
            "gps_path": gps_path_m,
            "summary": summary_m,
        },
        "elevation_gain_m": {
            "used": gain_source,
            "device_summary": device_gain_m,
            "endurain_smoothing": smoothed_gain,
            "naive_tcx": tcx_file.ascent,
        },
        "long_stops": {
            "radius_m": google_health_stops.STOP_RADIUS_M,
            "min_seconds": google_health_stops.STOP_MIN_SECONDS,
            "trim_radius_m": google_health_stops.STOP_TRIM_RADIUS_M,
            "stopped_seconds": round(stopped_s),
            "stops": [
                {
                    "start_s": round(stop.trimmed_start),
                    "duration_s": round(stop.trimmed_duration),
                    "untrimmed_duration_s": round(stop.duration),
                }
                for stop in stops
            ],
        },
        "steps": _steps(summary),
        "pace": {"basis": pace_basis, "elapsed_s_per_m": elapsed_pace},
        "speed": {
            "average_m_s": activity.average_speed,
            "max_m_s": max_speed,
            "max_window_s": MAX_SPEED_WINDOW_S,
        },
        "activity_type": {
            "google_health": exercise_type,
            "remapped_to_hike": remapped_to_hike,
            "hike_min_gain_m": HIKE_MIN_GAIN_M,
        },
        "device_active_duration_s": exercise.get("activeDuration"),
        "paused_seconds": round(paused_s),
        "stream_gaps": {"count": gap_count, "seconds": round(gap_seconds)},
    }
    return parsed_info
