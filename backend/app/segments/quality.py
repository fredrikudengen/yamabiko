"""When a pass's time is less trustworthy than the clock suggests.

Two things make it so:

* **A GPS gap inside the segment.** A gap longer than the gap limit is taken
  out of moving time, as a device pause would be. When the signal was lost
  while walking, the walking is taken out too, and the time is too fast by
  as much as the gap.
* **Only the edge of a circle.** The segment starts when the track leaves the
  start circle and ends when it enters the end circle. When the track came
  less than ``EDGE_DEPTH_M`` inside, the crossing is a shallow one, and a few
  metres of GPS noise move it along the path by tens of metres. The time is
  off by seconds rather than minutes, but the pass might as well have missed.

A doubtful pass keeps its rank: the badge says to read it with care. Passes
computed before the depth was recorded (matcher version 1) are only judged on
gaps until they are computed again.
"""

from __future__ import annotations

from typing import Any, Protocol

# About what a wrist-worn GPS wanders; less inside than this is touching the edge.
EDGE_DEPTH_M = 5.0

DOUBT_GPS_GAP = "gps_gap"
DOUBT_START_EDGE = "start_edge"
DOUBT_END_EDGE = "end_edge"


class _Effort(Protocol):
    gap_s: float
    details: dict[str, Any] | None


def _touched_edge(details: dict[str, Any], key: str) -> bool:
    depth = details.get(key)
    return isinstance(depth, int | float) and depth < EDGE_DEPTH_M


def effort_doubts(effort: _Effort) -> list[str]:
    """Why a pass's time may be off, in a fixed order; empty when there is no reason to doubt it."""
    doubts: list[str] = []
    if effort.gap_s > 0:
        doubts.append(DOUBT_GPS_GAP)
    details = effort.details or {}
    if _touched_edge(details, "start_depth_m"):
        doubts.append(DOUBT_START_EDGE)
    if _touched_edge(details, "end_depth_m"):
        doubts.append(DOUBT_END_EDGE)
    return doubts
