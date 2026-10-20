"""Detection of long stops (for example a rest at a summit) in a GPS track.

Speed thresholds do not work on a wrist-worn GPS: while standing still the
position jitters (and moves with the arm), which gives an apparent speed of
0.2-0.45 m/s, right at any sensible threshold. Instead a stop is a run of
points that all stay within a radius of where the run began, for at least a
minimum time. Walking leaves the radius within seconds, while jitter and arm
movement stay within a few metres.

Tested against real Fitbit Charge 4 tracks: a 2 minute stand-still was found,
and no 5 minute stops were reported on 80 minutes of walking without a long
rest. Durations are approximate: slow walking just before and after a stop
also stays inside the radius, so the trimmed duration is the better estimate
(about 30-40 s too long on a 2 minute stop).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Parameters. Stored with each import so a result can be reproduced or
# recomputed with other values later.
STOP_RADIUS_M = 20.0
STOP_MIN_SECONDS = 300.0
STOP_TRIM_RADIUS_M = 10.0
# Trackpoints are 1 Hz, but the band drops 10-25 % of them while the wearer sits
# still (gaps of 6-11 s were common during an 18 min summit rest on a real hike).
# A limit of 5 s cut that rest into pieces and found only 7:34 of it. Every point
# must stay within the stop radius anyway, so bridging up to 30 s cannot hide a
# walk away from the spot; a longer gap (device pause, lost signal) ends the run.
GAP_THRESHOLD_S = 30.0
# Shorter runs are not worth merging; this only keeps the candidate list small.
MIN_CANDIDATE_SECONDS = 30.0

_METRES_PER_DEGREE = 111_320.0


@dataclass(frozen=True)
class TrackPoint:
    """One GPS point: seconds since the first point, and position."""

    t: float
    lat: float
    lon: float


@dataclass(frozen=True)
class LongStop:
    """A detected stop, in seconds since the first point."""

    start: float
    duration: float
    trimmed_start: float
    trimmed_duration: float
    farthest_m: float


def distance_m(a: TrackPoint, b: TrackPoint) -> float:
    """Approximate distance in metres (equirectangular; fine below ~1 km)."""
    dy = (b.lat - a.lat) * _METRES_PER_DEGREE
    dx = (b.lon - a.lon) * _METRES_PER_DEGREE * math.cos(math.radians((a.lat + b.lat) / 2))
    return math.hypot(dx, dy)


def _trim(points: list[TrackPoint], first: int, last: int, trim_radius_m: float) -> tuple[float, float]:
    """Shrink a run to the points close to its median position."""
    run = points[first : last + 1]
    lats = sorted(p.lat for p in run)
    lons = sorted(p.lon for p in run)
    centre = TrackPoint(0.0, lats[len(lats) // 2], lons[len(lons) // 2])
    near = [p for p in run if distance_m(p, centre) <= trim_radius_m]
    if len(near) < 2:
        return points[first].t, points[last].t - points[first].t
    return near[0].t, near[-1].t - near[0].t


def _median_point(run: list[TrackPoint]) -> TrackPoint:
    lats = sorted(p.lat for p in run)
    lons = sorted(p.lon for p in run)
    return TrackPoint(0.0, lats[len(lats) // 2], lons[len(lons) // 2])


def _merge_runs(points: list[TrackPoint], runs: list[tuple[int, int]], radius_m: float) -> list[tuple[int, int]]:
    """Join runs that follow each other and together stay within ``radius_m`` of their median.

    A run is anchored on its first point. If that point lies a few metres off the
    resting place, jitter can push later points past the radius and one rest comes
    out as two runs back to back.
    """
    merged: list[tuple[int, int]] = []
    for first, last in runs:
        if merged:
            prev_first, prev_last = merged[-1]
            touching = points[first].t - points[prev_last].t <= GAP_THRESHOLD_S
            if touching:
                combined = points[prev_first : last + 1]
                centre = _median_point(combined)
                if max(distance_m(p, centre) for p in combined) <= radius_m:
                    merged[-1] = (prev_first, last)
                    continue
        merged.append((first, last))
    return merged


def detect_long_stops(
    points: list[TrackPoint],
    radius_m: float = STOP_RADIUS_M,
    min_seconds: float = STOP_MIN_SECONDS,
    trim_radius_m: float = STOP_TRIM_RADIUS_M,
) -> list[LongStop]:
    """Find runs where every point stays within ``radius_m`` of the run's first point.

    A run counts as a stop when it lasts at least ``min_seconds``. A time gap
    larger than ``GAP_THRESHOLD_S`` between points ends a run; shorter gaps
    (dropped points) are bridged. Runs that follow each other and stay together
    within the radius are merged into one stop, so a rest split by an unlucky anchor
    still counts as one.
    """
    runs: list[tuple[int, int]] = []
    n = len(points)
    i = 0
    while i < n - 1:
        j = i
        while j + 1 < n and points[j + 1].t - points[j].t <= GAP_THRESHOLD_S:
            if distance_m(points[i], points[j + 1]) > radius_m:
                break
            j += 1
        duration = points[j].t - points[i].t
        # A short run is only kept when it directly follows a long one, as a
        # candidate for the merge. Otherwise slide the anchor on by one point.
        follows_run = bool(runs) and points[i].t - points[runs[-1][1]].t <= GAP_THRESHOLD_S
        if duration >= min_seconds or (follows_run and duration >= MIN_CANDIDATE_SECONDS):
            runs.append((i, j))
            i = j + 1
        else:
            i += 1

    stops: list[LongStop] = []
    for first, last in _merge_runs(points, runs, radius_m):
        if points[last].t - points[first].t < min_seconds:
            continue
        run = points[first : last + 1]
        centre = _median_point(run)
        trimmed_start, trimmed_duration = _trim(points, first, last, trim_radius_m)
        stops.append(
            LongStop(
                start=points[first].t,
                duration=points[last].t - points[first].t,
                trimmed_start=trimmed_start,
                trimmed_duration=trimmed_duration,
                farthest_m=max(distance_m(p, centre) for p in run),
            )
        )
    return stops
