"""Builders for segment tests: synthetic routes on a local flat map, with heart rate and height."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import google_health.stops as google_health_stops
import segments.matching as segments_matching

LAT0, LON0 = 60.0, 5.0
_M = 111_320.0


def latlon(x: float, y: float) -> tuple[float, float]:
    """Coordinates of the point ``x`` metres east and ``y`` metres north of the map origin."""
    return LAT0 + y / _M, LON0 + x / (_M * math.cos(math.radians(LAT0)))


def node(x: float, y: float, radius_m: float = 50.0) -> segments_matching.Node:
    lat, lon = latlon(x, y)
    return segments_matching.Node(lat, lon, radius_m)


@dataclass
class Route:
    points: list[google_health_stops.TrackPoint]
    heart_rate: list[segments_matching.Sample]
    elevation: list[segments_matching.Sample]


def height_at(y: float) -> float:
    """Height of the synthetic mountain: 0.2 m of climb per metre north."""
    return 100.0 + 0.2 * y


def build_route(
    legs: list[tuple],
    start: tuple[float, float] = (0.0, -150.0),
    speed: float = 1.2,
    seed: int = 3,
    noise_m: float = 0.3,
) -> Route:
    """A route from ``legs``, one point per second.

    Legs: ``("walk", (x, y))`` walks in a straight line to the point at about ``speed``;
    ``("rest", seconds)`` stands still with the slow wobble of a wrist-worn receiver;
    ``("pause", seconds)`` lets the clock run without any points (a device pause).
    Heart rate is 100 + 0.04 per metre north while walking and 80 at rest; height follows
    ``height_at``.
    """
    rng = random.Random(seed)  # noqa: S311 - deterministic test data, not cryptography
    x, y = start
    t = 0.0
    wob_x = wob_y = 0.0
    points: list[google_health_stops.TrackPoint] = []
    hr: list[segments_matching.Sample] = []
    ele: list[segments_matching.Sample] = []

    def emit(heart: float, wobble: float) -> None:
        nonlocal wob_x, wob_y
        wob_x = 0.9 * wob_x + rng.gauss(0, wobble * 0.45)
        wob_y = 0.9 * wob_y + rng.gauss(0, wobble * 0.45)
        lat, lon = latlon(x + wob_x + rng.gauss(0, noise_m), y + wob_y + rng.gauss(0, noise_m))
        points.append(google_health_stops.TrackPoint(t, lat, lon))
        hr.append(segments_matching.Sample(t, heart))
        ele.append(segments_matching.Sample(t, height_at(y)))

    emit(80.0, 1.0)
    for kind, arg in legs:
        if kind == "walk":
            tx, ty = arg
            steps = max(math.ceil(math.hypot(tx - x, ty - y) / speed), 1)
            dx, dy = (tx - x) / steps, (ty - y) / steps
            for _ in range(steps):
                x, y, t = x + dx, y + dy, t + 1
                emit(100.0 + 0.04 * y, 0.3)
        elif kind == "rest":
            for _ in range(int(arg)):
                t += 1
                emit(80.0, 2.5)
        elif kind == "pause":
            t += arg
        else:
            raise ValueError(kind)
    return Route(points, hr, ele)
