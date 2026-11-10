"""How a pass of a segment went along the way: the clock at each step of the path.

Two passes of the same segment are compared at the same share of the way, not
at the same metre: the GPS path of one tour is a little longer or shorter than
another's on the same trail, so "1200 m in" is not the same place twice. At
each hundredth of the pass's own path the profile gives the clock as total time
and as moving time, where moving time leaves out the long stops and the GPS gaps
in the same way the pass's moving time does. Subtracting the best pass's profile
from another's shows where on the way the time was won or lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import google_health.stops as google_health_stops
import segments.geo as segments_geo
import segments.matching as segments_matching

# The profile has a value at every hundredth of the way, both ends included.
PROFILE_STEPS = 100


@dataclass(frozen=True)
class Profile:
    """The clock along one pass, at ``PROFILE_STEPS + 1`` evenly spaced shares of its path.

    ``distance_m`` is the path without the wander during long stops, so it can be a little
    shorter than the pass's own distance.
    """

    distance_m: float
    elapsed_s: list[float]
    moving_s: list[float]


def _overlap_s(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(min(a_end, b_end) - max(a_start, b_start), 0.0)


def effort_profile(points: list[google_health_stops.TrackPoint], match: segments_matching.SegmentMatch) -> Profile:
    """The clock along the pass ``match`` found in ``points``.

    Args:
        points: The track's GPS points, seconds since the first point.
        match: The pass, as ``segments.matching.match_segment`` found it in the same track.

    Returns:
        The profile. Where the walker stood still, the clock runs on while the
        distance does not, so a stop shows up at the share of the way where it was.
    """
    start_s, end_s = match.start_s, match.end_s
    times = [p.t for p in points]
    path = [(start_s, *segments_matching.position_at(points, times, start_s))]
    path += [(p.t, p.lat, p.lon) for p in points if start_s < p.t < end_s]
    path.append((end_s, *segments_matching.position_at(points, times, end_s)))

    # Standing still, a wrist-worn receiver wanders a metre or so each second; over a long stop that
    # adds up to hundreds of metres that were never walked. They are left out of the way, so the stop
    # sits at one share of it instead of being spread over a stretch.
    stops = [(first, first + duration) for first, duration in match.stops]
    along = [0.0]
    for (t1, lat1, lon1), (t2, lat2, lon2) in pairwise(path):
        mid = (t1 + t2) / 2
        standing = any(first <= mid <= last for first, last in stops)
        along.append(along[-1] + (0.0 if standing else segments_geo.distance_m(lat1, lon1, lat2, lon2)))
    total_m = along[-1]

    # The clock stops in long stops and in gaps of the GPS stream, as for the pass's moving time.
    off_clock = list(stops)
    off_clock += [(p.t, q.t) for p, q in pairwise(points) if q.t - p.t > google_health_stops.GAP_THRESHOLD_S]

    def moving_at(t: float) -> float:
        paused = sum(_overlap_s(a, b, start_s, t) for a, b in off_clock)
        return max(t - start_s - paused, 0.0)

    elapsed: list[float] = []
    moving: list[float] = []
    i = 1
    for step in range(PROFILE_STEPS + 1):
        target = total_m * step / PROFILE_STEPS
        while i < len(along) - 1 and along[i] < target:
            i += 1
        before, after = along[i - 1], along[i]
        share = (target - before) / (after - before) if after > before else 1.0
        t = path[i - 1][0] + min(max(share, 0.0), 1.0) * (path[i][0] - path[i - 1][0])
        if step == 0:
            t = start_s
        elapsed.append(t - start_s)
        moving.append(moving_at(t))
    return Profile(distance_m=total_m, elapsed_s=elapsed, moving_s=moving)
