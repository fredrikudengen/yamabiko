"""Geometry for segment matching: when does a GPS track stay inside a circle.

Positions are projected onto a flat plane around the circle's centre
(equirectangular). That is accurate to well below a metre for the few hundred
metres around a node, which is all that is needed here.

A track is a polyline through the points, not only the points themselves. The
band drops points (gaps of 6-11 s were common on a real hike) and a walker covers
about 12 m in 10 s, so a pass through a small circle can fall entirely between two
points. Crossing times are interpolated along the line between consecutive points.
That is only done across short gaps: after a long gap (device pause, lost signal)
the position in between is unknown and nothing is assumed about it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

import google_health.stops as google_health_stops

METRES_PER_DEGREE = 111_320.0
# Two interval ends closer than this (seconds) count as touching.
_TOUCH_EPSILON_S = 1e-6


@dataclass(frozen=True)
class Interval:
    """A stretch of time (seconds since the first point) spent inside a circle."""

    enter: float
    exit: float


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in metres between two coordinates (equirectangular)."""
    dy = (lat2 - lat1) * METRES_PER_DEGREE
    dx = (lon2 - lon1) * METRES_PER_DEGREE * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def _local(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Metres east and north of (lat0, lon0)."""
    return (
        (lon - lon0) * METRES_PER_DEGREE * math.cos(math.radians(lat0)),
        (lat - lat0) * METRES_PER_DEGREE,
    )


def _chord_fractions(p: tuple[float, float], q: tuple[float, float], radius_m: float) -> tuple[float, float] | None:
    """Fractions (0..1) of the way from p to q where the line is inside the circle at the origin."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    a = dx * dx + dy * dy
    c = p[0] * p[0] + p[1] * p[1] - radius_m * radius_m
    if a == 0.0:
        return (0.0, 1.0) if c <= 0 else None
    b = 2.0 * (p[0] * dx + p[1] * dy)
    disc = b * b - 4.0 * a * c
    if disc < 0:
        return None
    root = math.sqrt(disc)
    lo = max((-b - root) / (2.0 * a), 0.0)
    hi = min((-b + root) / (2.0 * a), 1.0)
    return (lo, hi) if lo <= hi else None


def time_inside_circle(
    points: list[google_health_stops.TrackPoint],
    lat: float,
    lon: float,
    radius_m: float,
    max_gap_s: float = google_health_stops.GAP_THRESHOLD_S,
) -> list[Interval]:
    """The stretches of time the track spends inside the circle, in time order.

    Consecutive stretches that touch (the track stays inside across several
    points) are one interval. The entry and exit times are interpolated between
    the points on each side of the circle's edge. Between two points more than
    ``max_gap_s`` apart nothing is interpolated: only the points themselves can
    be inside.
    """
    if not points:
        return []
    projected = [_local(p.lat, p.lon, lat, lon) for p in points]
    if len(points) == 1:
        inside = math.hypot(*projected[0]) <= radius_m
        return [Interval(points[0].t, points[0].t)] if inside else []

    raw: list[Interval] = []
    for i, (p, q) in enumerate(pairwise(points)):
        a, b = projected[i], projected[i + 1]
        if q.t - p.t > max_gap_s:
            if math.hypot(*a) <= radius_m:
                raw.append(Interval(p.t, p.t))
            if math.hypot(*b) <= radius_m:
                raw.append(Interval(q.t, q.t))
            continue
        chord = _chord_fractions(a, b, radius_m)
        if chord is not None:
            raw.append(Interval(p.t + chord[0] * (q.t - p.t), p.t + chord[1] * (q.t - p.t)))

    merged: list[Interval] = []
    for interval in raw:
        if merged and interval.enter <= merged[-1].exit + _TOUCH_EPSILON_S:
            merged[-1] = Interval(merged[-1].enter, max(merged[-1].exit, interval.exit))
        else:
            merged.append(interval)
    return merged


def closest_approach_m(
    points: list[google_health_stops.TrackPoint],
    lat: float,
    lon: float,
    max_gap_s: float = google_health_stops.GAP_THRESHOLD_S,
) -> float | None:
    """How close the track came to a position, in metres; None for an empty track.

    This is the smallest circle radius around the position that the track still
    touches. The line between two points counts (the walker passed between them),
    except across a gap longer than ``max_gap_s``, where only the points themselves count.
    """
    if not points:
        return None
    projected = [_local(p.lat, p.lon, lat, lon) for p in points]
    best = min(math.hypot(*xy) for xy in projected)
    for i, (p, q) in enumerate(pairwise(points)):
        if q.t - p.t > max_gap_s:
            continue
        a, b = projected[i], projected[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length_sq = dx * dx + dy * dy
        if length_sq == 0.0:
            continue
        f = min(max(-(a[0] * dx + a[1] * dy) / length_sq, 0.0), 1.0)
        best = min(best, math.hypot(a[0] + f * dx, a[1] + f * dy))
    return best
