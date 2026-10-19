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
# Trackpoints are 1 Hz; a larger step is a gap (explicit pause) that ends a run.
GAP_THRESHOLD_S = 5.0

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


def detect_long_stops(
    points: list[TrackPoint],
    radius_m: float = STOP_RADIUS_M,
    min_seconds: float = STOP_MIN_SECONDS,
    trim_radius_m: float = STOP_TRIM_RADIUS_M,
) -> list[LongStop]:
    """Find runs where every point stays within ``radius_m`` of the run's first point.

    A run counts as a stop when it lasts at least ``min_seconds``. A time gap
    larger than ``GAP_THRESHOLD_S`` between points ends a run.
    """
    stops: list[LongStop] = []
    n = len(points)
    i = 0
    while i < n - 1:
        j = i
        farthest = 0.0
        while j + 1 < n and points[j + 1].t - points[j].t <= GAP_THRESHOLD_S:
            d = distance_m(points[i], points[j + 1])
            if d > radius_m:
                break
            farthest = max(farthest, d)
            j += 1
        if points[j].t - points[i].t >= min_seconds:
            trimmed_start, trimmed_duration = _trim(points, i, j, trim_radius_m)
            stops.append(
                LongStop(
                    start=points[i].t,
                    duration=points[j].t - points[i].t,
                    trimmed_start=trimmed_start,
                    trimmed_duration=trimmed_duration,
                    farthest_m=farthest,
                )
            )
            i = j + 1
        else:
            i += 1
    return stops
