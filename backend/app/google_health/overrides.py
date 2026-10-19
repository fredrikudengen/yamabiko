"""Overrides applied to the parsed TCX of a Google Health exercise.

``parse_tcx_file`` is left untouched. Its result is corrected afterwards,
because for Fitbit TCX files three of its values are not what we want:

- distance: the lap summary (``tcx_file.distance``) is ~15 % below the real
  distance on short walks. Measured against a route on a map (463 m), the last
  trackpoint's cumulative distance (463.5 m) and the geodesic GPS path
  (464.8 m) were right and the summary (392.8 m) was not.
- elevation: ``tcx_file.ascent`` is a naive sum of height changes (+8.6 %
  on a 430 m climb); Endurain's smoothing is used instead.
- timer time: the TCX importer sets it to the clock time. It is set to the
  time without long stops (see ``stops.py``).
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

import tcxreader

import activities.activity.utils as activities_utils
import google_health.filters as google_health_filters
import google_health.stops as google_health_stops

IMPORT_SOURCE = "google_health"
# Bump when the way values are derived changes, so old rows can be told apart.
IMPORT_VERSION = 1


def _gps_path_m(points: list[google_health_stops.TrackPoint]) -> float:
    """Sum of distances between consecutive GPS points (includes jitter)."""
    return sum(google_health_stops.distance_m(a, b) for a, b in pairwise(points))


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

    first_time, last_time = None, None
    timed = [tp for tp in tcx_file.trackpoints if tp.time is not None]
    if timed:
        first_time, last_time = timed[0].time, timed[-1].time
    if first_time and last_time and activity.distance:
        activity.pace = activities_utils.calculate_pace(activity.distance, first_time, last_time)

    # A single-lap file: keep the lap's distance consistent with the activity.
    laps = parsed_info.get("laps") or []
    if len(laps) == 1 and activity.distance:
        laps[0]["total_distance"] = activity.distance

    # ---- elevation ------------------------------------------------------
    ele_waypoints = parsed_info.get("ele_waypoints") or []
    if ele_waypoints:
        gain, loss = activities_utils.compute_elevation_gain_and_loss(ele_waypoints)
        activity.elevation_gain = round(gain)
        activity.elevation_loss = round(loss)
    device_gain_mm = summary.get("elevationGainMillimeters")

    # ---- time without long stops ---------------------------------------
    stops = google_health_stops.detect_long_stops(points) if points else []
    stopped_s = sum(stop.trimmed_duration for stop in stops)
    elapsed = activity.total_elapsed_time
    if elapsed is not None:
        activity.total_timer_time = max(elapsed - stopped_s, 0)

    # ---- identity, type, name ------------------------------------------
    activity.googlehealth_activity_id = google_health_filters.exercise_id(exercise_data_point)
    exercise_type = exercise.get("exerciseType")
    if exercise_type:
        activity.activity_type = activities_utils.define_activity_type(exercise_type)
    display_name = exercise.get("displayName")
    if display_name:
        activity.name = display_name

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
            "used": "endurain_smoothing",
            "device_summary": float(device_gain_mm) / 1000 if device_gain_mm is not None else None,
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
        "device_active_duration_s": exercise.get("activeDuration"),
    }
    return parsed_info
