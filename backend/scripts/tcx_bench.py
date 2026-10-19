# ruff: noqa: T201  (a CLI report: printing is the point)
"""Testbench for TCX imports: Endurain's parser vs independent calculations.

Runs the real ``parse_tcx_file`` on one or more TCX files (database and
geocoding are stubbed out) and prints, side by side:

* distance: what the parser stores vs. summary, last trackpoint and GPS path
* elevation gain: what the parser stores vs. Endurain's smoothing function,
  plus a sensitivity sweep over the smoothing parameters
* time: gaps in the trackpoint stream (pauses) and a naive active time
* moving time: seconds above a speed threshold, swept over speed signal,
  smoothing window and threshold, plus a list of example stops

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
from geopy.distance import geodesic

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


# Moving-time analysis. Windows are (first, last) point offsets around point i;
# speed at i is the displacement across the window divided by its duration.
# Using displacement (not summed step lengths) lets GPS jitter cancel out.
MOVING_WINDOWS = {"1 s (raw step)": (-1, 0), "5 s": (-2, 2), "11 s": (-5, 5)}
MOVING_THRESHOLDS_MS = (0.1, 0.2, 0.3, 0.5, 0.8)
# (window name, m/s) per signal; only used to list example stops. GPS needs a
# longer window than Fitbit's distance because jitter does not cancel in short ones.
STOP_DETECTION = {"tp": ("5 s", 0.3), "gps": ("11 s", 0.3)}
STOP_MIN_S = 20


def _mmss(seconds: float) -> str:
    """Format seconds as mm:ss."""
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def _point_series(tcx) -> dict | None:
    """Trackpoint arrays for the moving-time analysis, or None without GPS."""
    points = [
        tp for tp in tcx.trackpoints if tp.time is not None and tp.latitude is not None and tp.longitude is not None
    ]
    if len(points) < 12:
        return None

    t0 = points[0].time
    t = [(tp.time - t0).total_seconds() for tp in points]
    # dt[i] = time since the previous point; 0 for the first point and for gaps
    # (explicit pauses), so gaps count as neither moving nor stopped.
    dt = [0.0] + [d if 0 < d <= GAP_THRESHOLD_S else 0.0 for d in (b - a for a, b in itertools.pairwise(t))]
    # gap_cum[k] = number of gap intervals among the first k intervals
    gap_cum = [0]
    for a, b in itertools.pairwise(t):
        gap_cum.append(gap_cum[-1] + (0 if 0 < b - a <= GAP_THRESHOLD_S else 1))

    has_distance = all(tp.distance is not None for tp in points)
    return {
        "t": t,
        "dt": dt,
        "gap_cum": gap_cum,
        "latlon": [(tp.latitude, tp.longitude) for tp in points],
        "cum_distance": [tp.distance for tp in points] if has_distance else None,
    }


def _window_speeds(series: dict, signal: str, window: tuple[int, int]) -> list[float | None]:
    """Speed (m/s) at every point over a window; None where undefined."""
    n = len(series["t"])
    first, last = window
    speeds: list[float | None] = []
    for i in range(n):
        lo, hi = max(0, i + first), min(n - 1, i + last)
        # undefined at the edges, and where the window spans a gap
        if hi <= lo or series["gap_cum"][hi] - series["gap_cum"][lo] > 0:
            speeds.append(None)
            continue
        duration = series["t"][hi] - series["t"][lo]
        if signal == "gps":
            metres = geodesic(series["latlon"][lo], series["latlon"][hi]).meters
        else:
            metres = series["cum_distance"][hi] - series["cum_distance"][lo]
        speeds.append(metres / duration)
    return speeds


def _moving_seconds(dt: list[float], speeds: list[float | None], threshold: float) -> float:
    """Seconds at or above ``threshold`` (points with undefined speed are skipped)."""
    return sum(d for d, s in zip(dt, speeds, strict=True) if d > 0 and s is not None and s >= threshold)


def _stop_runs(
    t: list[float], dt: list[float], speeds: list[float | None], threshold: float
) -> list[tuple[float, float]]:
    """Contiguous runs below ``threshold`` as (start offset s, duration s)."""
    runs: list[tuple[float, float]] = []
    start = None
    duration = 0.0
    for offset, d, s in zip(t, dt, speeds, strict=True):
        if d > 0 and s is not None and s < threshold:
            if start is None:
                start = offset - d
            duration += d
        elif start is not None:
            runs.append((start, duration))
            start, duration = None, 0.0
    if start is not None:
        runs.append((start, duration))
    return runs


def _distance_during(series: dict, start: float, duration: float) -> tuple[float | None, float, float]:
    """Distance added between ``start`` and ``start + duration`` (metres).

    Returns (Fitbit cumulative distance or None, GPS path length, GPS net
    displacement). Jitter while standing still inflates the GPS path but not
    the net displacement; if Fitbit's cumulative distance also grows during a
    stop, a "last trackpoint" distance includes that drift.
    """
    offsets = series["t"]
    inside = [i for i, x in enumerate(offsets) if start - 0.5 <= x <= start + duration + 0.5]
    lo, hi = inside[0], inside[-1]
    fitbit = None
    if series["cum_distance"] is not None:
        fitbit = series["cum_distance"][hi] - series["cum_distance"][lo]
    path = sum(geodesic(series["latlon"][i], series["latlon"][i + 1]).meters for i in range(lo, hi))
    net = geodesic(series["latlon"][lo], series["latlon"][hi]).meters
    return fitbit, path, net


def report_moving(tcx) -> None:
    """Moving time vs elapsed time, derived from the trackpoint stream."""
    series = _point_series(tcx)
    if series is None:
        print("\nMOVING TIME: too few trackpoints with GPS")
        return

    covered = sum(series["dt"])
    signals = [("gps", "GPS displacement")]
    if series["cum_distance"] is not None:
        signals.insert(0, ("tp", "Fitbit cumulative distance (trackpoint)"))

    print(f"\nMOVING TIME (s)   covered time (gaps excluded): {covered:.0f}")
    print("  speed over a window; a second counts as moving when speed >= threshold (m/s)")
    for signal, label in signals:
        print(f"\n  signal: {label}")
        print("  window            " + "".join(f"{v:<9}" for v in MOVING_THRESHOLDS_MS))
        for name, window in MOVING_WINDOWS.items():
            speeds = _window_speeds(series, signal, window)
            cells = "".join(f"{_moving_seconds(series['dt'], speeds, v):<9.0f}" for v in MOVING_THRESHOLDS_MS)
            print(f"  {name:<17} {cells}")

    print(f"\n  example stops (>= {STOP_MIN_S} s), found separately by each signal")
    print("  not a recommendation, only to show what the data contains")
    print("  accrued = distance added during the stop: Fitbit cumulative / GPS path / GPS net displacement")
    for signal, label in signals:
        window_name, threshold = STOP_DETECTION[signal]
        speeds = _window_speeds(series, signal, MOVING_WINDOWS[window_name])
        runs = [r for r in _stop_runs(series["t"], series["dt"], speeds, threshold) if r[1] >= STOP_MIN_S]
        print(f"\n  stops by {label} (window {window_name}, < {threshold} m/s)")
        if not runs:
            print("    none")
            continue
        for start, duration in runs[:15]:
            fitbit, path, net = _distance_during(series, start, duration)
            fitbit_text = "n/a" if fitbit is None else f"{fitbit:.1f}"
            print(
                f"    at {_mmss(start)}  {_mmss(duration)}   accrued: Fitbit {fitbit_text} m"
                f" / GPS path {path:.1f} m / net {net:.1f} m"
            )
        if len(runs) > 15:
            print(f"    ... {len(runs) - 15} more")
        print(f"    total {len(runs)} stops, {sum(d for _, d in runs):.0f} s, longest {max(d for _, d in runs):.0f} s")


TIMELINE_BUCKET_S = 30


def report_timeline(tcx) -> None:
    """Per-30-second buckets: where distance accrues and what the pulse does.

    A real stand-still shows as a bucket with Fitbit ~0 m and net ~0 m (GPS
    path above that is jitter). Pulse often drops during it, independent of GPS.
    """
    series = _point_series(tcx)
    if series is None:
        return
    hr_by_index = [
        tp.hr_value
        for tp in tcx.trackpoints
        if tp.time is not None and tp.latitude is not None and tp.longitude is not None
    ]
    offsets = series["t"]
    print("\nTIMELINE (30 s buckets; Fitbit = cumulative-distance gain, path/net = GPS)")
    print("  from    Fitbit m   GPS path m   GPS net m   avg HR")
    end = offsets[-1]
    start = 0.0
    while start < end:
        idx = [i for i, x in enumerate(offsets) if start <= x < start + TIMELINE_BUCKET_S + 1]
        if len(idx) >= 2:
            lo, hi = idx[0], idx[-1]
            fitbit = series["cum_distance"][hi] - series["cum_distance"][lo] if series["cum_distance"] else float("nan")
            path = sum(geodesic(series["latlon"][i], series["latlon"][i + 1]).meters for i in range(lo, hi))
            net = geodesic(series["latlon"][lo], series["latlon"][hi]).meters
            hrs = [hr_by_index[i] for i in idx if hr_by_index[i] is not None]
            avg_hr = f"{sum(hrs) / len(hrs):.0f}" if hrs else "-"
            print(f"  {_mmss(start)}   {fitbit:8.1f}   {path:10.1f}   {net:9.1f}   {avg_hr:>6}")
        start += TIMELINE_BUCKET_S


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
    report_moving(tcx)
    report_timeline(tcx)
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
