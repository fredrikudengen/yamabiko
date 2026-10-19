# ruff: noqa: T201
"""Try the Google Health import against a real token, without touching the database.

    export GOOGLE_HEALTH_TOKEN=...        # an access token (valid for about an hour)
    cd backend && uv run python scripts/google_health_check.py --days 7

It lists the exercises in the date range, says which would be imported and
why the others are skipped, and for the importable ones it downloads the TCX,
runs the real ``parse_tcx_file`` and ``apply_google_health_overrides`` and
prints the result. Nothing is stored. Only aggregates are printed (no token,
no coordinates), so the output can be pasted.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# The app reads settings at import time. Dummy values are enough here: nothing
# touches the database, encryption or sessions.
os.environ.setdefault("DB_PASSWORD", "unused")
os.environ.setdefault("SECRET_KEY", "unused-secret-key-for-the-check-script-only")
if "FERNET_KEY" not in os.environ:
    from cryptography.fernet import Fernet

    os.environ["FERNET_KEY"] = Fernet.generate_key().decode()

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import activities.activity_file_import.utils as import_utils
import activities.activity_file_import.utils_tcx as tcx_utils
import google_health.activity_utils as gh_activity_utils
import google_health.client as gh_client
import google_health.filters as gh_filters
import google_health.overrides as gh_overrides


def _privacy_settings() -> SimpleNamespace:
    """Stand-in for the user's privacy settings (only used to build the schema)."""
    names = [
        "hide_start_time",
        "hide_location",
        "hide_map",
        "hide_hr",
        "hide_power",
        "hide_cadence",
        "hide_elevation",
        "hide_speed",
        "hide_pace",
        "hide_laps",
        "hide_workout_sets_steps",
        "hide_gear",
    ]
    return SimpleNamespace(**dict.fromkeys(names, False), default_activity_visibility=0)


def parse_and_override(tcx_path: Path, data_point: dict) -> dict:
    """The real parser and overrides, with database and geocoding stubbed out."""
    with (
        patch.object(tcx_utils.user_default_gear_utils, "get_user_default_gear_by_activity_type", return_value=None),
        patch.object(import_utils, "resolve_location", return_value=None),
        patch.object(import_utils, "resolve_timezone_from_lat_lon", return_value="Europe/Oslo"),
        patch.object(import_utils, "build_activity_privacy_kwargs", return_value={}),
    ):
        parsed = tcx_utils.parse_tcx_file(str(tcx_path), 1, _privacy_settings(), db=None)
        before = parsed["activity"].model_copy(deep=True)
        after = gh_overrides.apply_google_health_overrides(parsed, data_point, str(tcx_path))["activity"]
    return {"before": before, "after": after}


def _mmss(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def describe(data_point: dict) -> str:
    exercise = data_point.get("exercise") or {}
    interval = exercise.get("interval") or {}
    method = (data_point.get("dataSource") or {}).get("recordingMethod", "?")
    has_gps = (exercise.get("exerciseMetadata") or {}).get("hasGps", "-")
    events = ",".join(e.get("exerciseEventType", "?") for e in exercise.get("exerciseEvents") or []) or "-"
    return (
        f"...{(gh_filters.exercise_id(data_point) or '?')[-6:]}  {interval.get('startTime', '?')}  "
        f"{exercise.get('exerciseType', '?'):<8} {method:<18} hasGps={has_gps!s:<5} events={events}"
    )


def print_result(result: dict) -> None:
    before, after = result["before"], result["after"]
    info = after.import_info
    distance = info["distance_m"]
    stops = info["long_stops"]["stops"]

    def fmt(value: float | None) -> str:
        return "-" if value is None else f"{value:.1f}"

    print(f"    distance  stored {after.distance} m (parser alone: {before.distance} m), used: {distance['used']}")
    print(
        f"              last trackpoint {fmt(distance['last_trackpoint'])} / GPS path {fmt(distance['gps_path'])}"
        f" / summary {fmt(distance['summary'])}"
    )
    elevation = info["elevation_gain_m"]
    print(
        f"    elevation gain {after.elevation_gain} m (parser alone: {before.elevation_gain} m);"
        f" device {fmt(elevation['device_summary'])}, naive {fmt(elevation['naive_tcx'])}"
    )
    print(
        f"    time      clock {_mmss(after.total_elapsed_time)}, timer {_mmss(after.total_timer_time)}"
        f" = clock - paused {info['paused_seconds']} s - long stops {info['long_stops']['stopped_seconds']} s"
        f" (device activeDuration {info['device_active_duration_s']};"
        f" stream gaps: {info['stream_gaps']['count']}, {info['stream_gaps']['seconds']} s)"
    )
    print(f"    long stops: {len(stops)}")
    for stop in stops:
        print(
            f"      at {_mmss(stop['start_s'])}  {_mmss(stop['duration_s'])}"
            f" (untrimmed {_mmss(stop['untrimmed_duration_s'])})"
        )
    print(f"    type {after.activity_type}, name {after.name!r}, pace {after.pace:.4f} s/m")


async def run(token: str, days: int) -> None:
    start, end = gh_activity_utils.lookback_range(days)
    print(f"Exercises starting {start} .. {end} (end exclusive)")
    async with gh_client.GoogleHealthClient(token) as client:
        data_points = await client.list_exercises(start, end)
        print(f"Listed {len(data_points)} exercises\n")

        importable = []
        for data_point in sorted(data_points, key=lambda d: d["exercise"]["interval"]["startTime"]):
            reason = gh_filters.skip_reason(data_point)
            print(
                f"{'IMPORT' if reason is None else 'skip  '}  {describe(data_point)}"
                + (f"  [{reason}]" if reason else "")
            )
            if reason is None:
                importable.append(data_point)

        for data_point in importable:
            exercise_id = gh_filters.exercise_id(data_point)
            print(f"\n--- ...{exercise_id[-6:]} ---")
            tcx_bytes = await client.download_tcx(exercise_id)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / f"{exercise_id}.tcx"
                path.write_bytes(tcx_bytes)
                print_result(parse_and_override(path, data_point))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=7, help="how many days back to look (default 7)")
    args = parser.parse_args()
    token = os.environ.get("GOOGLE_HEALTH_TOKEN")
    if not token:
        sys.exit("Set GOOGLE_HEALTH_TOKEN to an access token first.")
    try:
        asyncio.run(run(token, args.days))
    except gh_client.GoogleHealthAuthError as err:
        sys.exit(f"The token was rejected ({err}). It lasts about an hour; make a new one.")


if __name__ == "__main__":
    main()
