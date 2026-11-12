"""The user's heart-rate zones, and the time a tour spent in each.

Five zones split by four limits (bpm). The defaults are Google Health's lines
for its own zone graph. Time in a zone is counted on moving time, the same way
the zone card on a tour's page counts it (``frontend/.../hrZoneTime.ts``): each
step between two heart-rate samples goes to the zone of the first sample, less
any part inside a long stop; a step longer than the gap limit is not counted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import google_health.stops as google_health_stops

DEFAULT_LIMITS: tuple[int, int, int, int] = (103, 113, 126, 154)
ZONE_COUNT = 5
MIN_BPM = 30
MAX_BPM = 250


def is_valid(value: Any) -> bool:
    """Whether a value is four whole bpm values within bounds, each larger than the one before."""
    if not isinstance(value, list | tuple) or len(value) != ZONE_COUNT - 1:
        return False
    if not all(isinstance(limit, int) and not isinstance(limit, bool) for limit in value):
        return False
    return all(MIN_BPM <= limit <= MAX_BPM for limit in value) and all(a < b for a, b in pairwise(value))


def limits_of(stored: Any) -> tuple[int, int, int, int]:
    """The limits to use: the stored ones when they are valid, the defaults otherwise."""
    return tuple(stored) if is_valid(stored) else DEFAULT_LIMITS  # type: ignore[return-value]


def zone_of(heart_rate: float, limits: Sequence[int]) -> int:
    """The zone (1-5) of a heart rate: one up for each limit it reaches."""
    return 1 + sum(1 for limit in limits if heart_rate >= limit)


@dataclass(frozen=True)
class ZoneTime:
    """Seconds in each zone (index 0 is zone 1), and how much time was counted."""

    seconds: tuple[float, ...]
    counted_s: float


def _overlap(start: float, end: float, windows: Sequence[tuple[float, float]]) -> float:
    return sum(max(0.0, min(end, b) - max(start, a)) for a, b in windows)


def zone_seconds(
    samples: Sequence[tuple[float, float]],
    limits: Sequence[int],
    stops: Sequence[tuple[float, float]] = (),
    max_step_s: float = google_health_stops.GAP_THRESHOLD_S,
) -> ZoneTime:
    """Seconds of moving time in each zone.

    Args:
        samples: ``(time, bpm)`` pairs, seconds on any common axis.
        limits: The four zone limits.
        stops: ``(start, duration)`` of long stops on the same axis; their time is left out.
        max_step_s: A longer step between samples is a gap and is not counted.

    Returns:
        The seconds per zone and their sum.
    """
    ordered = sorted((t, bpm) for t, bpm in samples if bpm and bpm > 0)
    windows = [(start, start + duration) for start, duration in stops if duration > 0]
    seconds = [0.0] * ZONE_COUNT
    for (t1, bpm), (t2, _) in pairwise(ordered):
        step = t2 - t1
        if step <= 0 or step > max_step_s:
            continue
        seconds[zone_of(bpm, limits) - 1] += step - _overlap(t1, t2, windows)
    return ZoneTime(seconds=tuple(seconds), counted_s=sum(seconds))
