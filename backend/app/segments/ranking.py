"""Where each pass of a segment stands among all passes of that segment.

Every pass counts, whatever source it was imported from: the time between two nodes is
computed from the GPS track in the same way for all sources (see ``segments.source``).
Heart rate and ascent are the numbers that differ between sources, and they play no part here.

The rank is the *current* standing, not whether the pass was a record on the day. A pass that
was the fastest when it was walked drops to 2nd when a faster one is added later.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class _HasTimes(Protocol):
    id: int
    moving_s: float
    elapsed_s: float


@dataclass(frozen=True)
class Standing:
    """The rank of one pass on moving time and on total time (1 = fastest), among ``count`` passes."""

    rank_moving: int
    rank_total: int
    count: int


def _whole_seconds(seconds: float) -> int:
    """Seconds rounded half up, as the interface shows them, so equal-looking times rank equal."""
    return math.floor(seconds + 0.5)


def _ranks(times: dict[int, int]) -> dict[int, int]:
    """Competition ranking: equal times share a rank and the next rank is skipped (1, 1, 3)."""
    ordered = sorted(times.values())
    return {key: ordered.index(value) + 1 for key, value in times.items()}


def rank_efforts(efforts: Sequence[_HasTimes]) -> dict[int, Standing]:
    """The standing of each pass by effort id. ``efforts`` must be all the passes of one segment."""
    count = len(efforts)
    moving = _ranks({e.id: _whole_seconds(e.moving_s) for e in efforts})
    total = _ranks({e.id: _whole_seconds(e.elapsed_s) for e in efforts})
    return {e.id: Standing(moving[e.id], total[e.id], count) for e in efforts}
