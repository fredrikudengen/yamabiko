# ruff: noqa: T201  (a CLI report: printing is the point)
"""Testbench for TCX imports: Endurain's parser vs independent calculations.

Runs the real ``parse_tcx_file`` on one or more TCX files (database and
geocoding are stubbed out) and prints, side by side:

* distance: what the parser stores vs. summary, last trackpoint and GPS path
* elevation gain: what the parser stores vs. Endurain's smoothing function,
  plus a sensitivity sweep over the smoothing parameters
* time: gaps in the trackpoint stream (pauses) and a naive active time

Only aggregates are printed, never coordinates, so the output is safe to
paste into a chat even for real GPS files.

Usage (from ``backend/``):

    python scripts/tcx_bench.py path/to/a.tcx [path/to/b.tcx ...]
"""

import argparse
import itertools
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

# Endurain's modules read secrets at import time. The bench never touches a
# database, so throwaway values are enough.
os.environ.setdefault("DB_PASSWORD", "bench")
os.environ.setdefault("SECRET_KEY", "bench")
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())

import tcxreader

import activities.activity.utils as activities_utils
import activities.activity_file_import.utils as import_utils
import activities.activity_file_import.utils_tcx as utils_tcx

GAP_THRESHOLD_S = 1.5  # trackpoints are 1 Hz; anything above is a gap


def _privacy_settings() -> SimpleNamespace:
    """Privacy settings with everything visible (only needed by the parser)."""
    return SimpleNamespace(
        default_activity_visibility="public",
        hide_activity_start_time=False,
        hide_activity_location=False,
        hide_activity_map=False,
        hide_activity_hr=False,
        hide_activity_power=False,
        hide_activity_cadence=False,
        hide_activity_elevation=False,
        hide_activity_speed=False,
        hide_activity_pace=False,
        hide_activity_laps=False,
        hide_activity_workout_sets_steps=False,
        hide_activity_gear=False,
    )


def run_parser(path: Path) -> dict:
    """Run the real parse_tcx_file with DB and network lookups stubbed."""
    with (
        patch.object(
            utils_tcx.user_default_gear_utils,
            "get_user_default_gear_by_activity_type",
            return_value=None,
        ),
        patch.object(import_utils, "resolve_location", return_value=None),
        patch.object(
            import_utils,
            "resolve_timezone_from_lat_lon",
            side_effect=lambda lat, lon, fallback: fallback,
        ),
    ):
        return utils_tcx.parse_tcx_file(
            file=str(path),
            user_id=1,
            user_privacy_settings=_privacy_settings(),
            db=None,
            activity_name_input=path.stem,
        )


def pct(value: float, reference: float) -> str:
    """Format ``value`` as a signed percentage deviation from ``reference``."""
    if not reference:
        return "n/a"
    return f"{(value - reference) / reference * 100:+.1f} %"


def report_distance(tcx, parsed_distance: float) -> None:
    """Compare the distance sources."""
    points = [tp for tp in tcx.trackpoints if tp.latitude is not None and tp.longitude is not None]
    gps = import_utils.compute_distance_from_waypoints([{"lat": tp.latitude, "lon": tp.longitude} for tp in points])
    last_tp = next(
        (tp.distance for tp in reversed(tcx.trackpoints) if tp.distance is not None),
        None,
    )

    print("\nDISTANCE (m)")
    rows = [
        ("GPS path (geodesic sum)", gps),
        ("summary (tcx_file.distance)", tcx.distance),
        ("last trackpoint", last_tp),
        ("stored by parser", parsed_distance),
    ]
    for label, value in rows:
        if value is None:
            print(f"  {label:<30} n/a")
        else:
            print(f"  {label:<30} {value:>9.1f}   vs GPS {pct(value, gps)}")


def report_elevation(tcx, parsed_gain) -> None:
    """Compare elevation gain methods and sweep smoothing parameters."""
    ele = [{"ele": tp.elevation} for tp in tcx.trackpoints if tp.elevation is not None]
    if not ele:
        print("\nELEVATION: no elevation data")
        return

    gain, loss = activities_utils.compute_elevation_gain_and_loss(ele)
    print("\nELEVATION GAIN (m)")
    print(f"  stored by parser (tcxreader ascent, naive) {parsed_gain!s:>8}")
    print(f"  tcxreader ascent (unrounded)               {tcx.ascent:>8.1f}")
    print(f"  Endurain smoothing (defaults 6/3/0.1)      {gain:>8.1f}   loss {loss:.1f}")

    print("\n  sensitivity of Endurain smoothing (gain, m)")
    thresholds = (0.0, 0.1, 0.3)
    print("  median/avg window      " + "".join(f"thr {t:<8}" for t in thresholds))
    for median_w in (1, 3, 6, 9):
        for avg_w in (1, 3, 5):
            cells = "".join(
                f"{activities_utils.compute_elevation_gain_and_loss(ele, median_w, avg_w, t)[0]:<12.1f}"
                for t in thresholds
            )
            print(f"  {median_w:>2} / {avg_w:<2}                {cells}")


def report_time(tcx) -> None:
    """Report gaps in the trackpoint stream and a naive active time."""
    times = [tp.time for tp in tcx.trackpoints if tp.time is not None]
    if len(times) < 2:
        print("\nTIME: too few timestamps")
        return

    elapsed = (times[-1] - times[0]).total_seconds()
    gaps = [(b - a).total_seconds() for a, b in itertools.pairwise(times) if (b - a).total_seconds() > GAP_THRESHOLD_S]
    gap_total = sum(gaps)

    print("\nTIME (s)")
    print(f"  trackpoints                    {len(times)}")
    print(f"  elapsed (first -> last)        {elapsed:.0f}")
    print(
        f"  gaps > {GAP_THRESHOLD_S} s                  {len(gaps)}   total {gap_total:.0f}   max {max(gaps, default=0):.0f}"
    )
    print(f"  elapsed minus gaps (naive)     {elapsed - gap_total:.0f}")


def report_file(path: Path) -> None:
    """Print the full report for one TCX file."""
    print("=" * 72)
    print(f"{path.name}")
    print("=" * 72)

    payload = run_parser(path)
    activity = payload["activity"]
    tcx = tcxreader.TCXReader().read(str(path))

    print("\nPARSER OUTPUT")
    print(f"  activity_type (id)   {activity.activity_type}   (TCX Sport = {tcx.activity_type!r})")
    print(f"  distance             {activity.distance}")
    print(f"  elevation gain/loss  {activity.elevation_gain} / {activity.elevation_loss}")
    print(f"  avg/max HR           {activity.average_hr} / {activity.max_hr}")
    print(f"  pace (s/m)           {activity.pace}")
    print(f"  timezone             {activity.timezone}")
    print(f"  start -> end         {activity.start_time} -> {activity.end_time}")
    print(f"  elapsed / timer      {activity.total_elapsed_time} / {activity.total_timer_time}")
    print(
        "  streams              " + ", ".join(f"{k}={len(v)}" for k, v in payload.items() if k.endswith("_waypoints"))
    )

    report_distance(tcx, activity.distance)
    report_elevation(tcx, activity.elevation_gain)
    report_time(tcx)
    print()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path, help="TCX files to analyse")
    args = parser.parse_args()
    for path in args.files:
        report_file(path)


if __name__ == "__main__":
    main()
