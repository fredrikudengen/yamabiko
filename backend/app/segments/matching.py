"""Does a track pass a segment, and what happened between the two nodes.

A segment is a start node and an end node, each a circle (centre and radius). A
track matches when it visits the start node and, afterwards, the end node. The
direction matters: only start -> end counts.

Choosing the passes
    * The end is the first visit to the end node that follows a visit to the
      start node (arriving at the summit; a second summit later is ignored).
    * The start is the last visit to the start node before that (walking back to
      the trailhead and starting over restarts the segment).

Times
    The segment starts when the track *leaves* the start circle for the last time
    before the end, and ends when it *enters* the end circle. Standing around inside
    the start circle (parking, putting on shoes) and the rest at the summit are
    therefore not part of it. The radii change the times a little (a bigger
    summit circle is reached earlier), so a result is only comparable with results
    for the same nodes; the radii are stored with each effort.

    Moving time is clock time between those two moments minus the long stops
    (``google_health.stops``, the same detection as for a whole activity) and minus
    gaps in the GPS stream longer than ``GAP_THRESHOLD_S``, which is how a device pause
    shows up in the track. Because the stop detection is the same everywhere, moving
    time is comparable between tours.

Heart rate is averaged over the moving part only, so a long rest does not pull
the average down.
"""

from __future__ import annotations

import math
import statistics
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise

import activities.activity.utils as activities_utils
import google_health.stops as google_health_stops
import segments.geo as segments_geo

# Bump when the way an effort is derived changes, so old rows can be told apart.
MATCHER_VERSION = 1

DEFAULT_NODE_RADIUS_M = 50.0
# A wrist-worn GPS is only good to about this much; a smaller circle would miss a
# walker who is on the path but on the wrong side of the jitter.
MIN_NODE_RADIUS_M = 25.0
# Net elevation compares the height around the two moments, with this much each side.
ELEVATION_NEAR_S = 5.0


@dataclass(frozen=True)
class Node:
    """A circle on the map."""

    lat: float
    lon: float
    radius_m: float = DEFAULT_NODE_RADIUS_M


@dataclass(frozen=True)
class Sample:
    """A measured value at a time (seconds since the first GPS point)."""

    t: float
    value: float


@dataclass(frozen=True)
class SegmentMatch:
    """What a track did between a segment's two nodes. Times are seconds since the first GPS point."""

    start_s: float
    end_s: float
    elapsed_s: float
    moving_s: float
    stopped_s: float
    gap_s: float
    distance_m: float
    elevation_gain_m: float | None
    elevation_loss_m: float | None
    net_elevation_m: float | None
    average_hr: float | None
    max_hr: int | None
    hr_samples: int
    # (start, duration) of the long stops that overlap the segment, trimmed as for an activity.
    stops: tuple[tuple[float, float], ...] = field(default_factory=tuple)
    start_visits: int = 0
    end_visits: int = 0


def validate_nodes(start: Node, end: Node) -> list[str]:
    """Problems with a segment's nodes (an empty list means it is fine)."""
    problems: list[str] = []
    for label, node in (("start", start), ("end", end)):
        if not (-90.0 <= node.lat <= 90.0 and math.isfinite(node.lat)):
            problems.append(f"{label} latitude must be between -90 and 90")
        if not (-180.0 <= node.lon <= 180.0 and math.isfinite(node.lon)):
            problems.append(f"{label} longitude must be between -180 and 180")
        if not (math.isfinite(node.radius_m) and node.radius_m > MIN_NODE_RADIUS_M):
            problems.append(f"{label} radius must be larger than {MIN_NODE_RADIUS_M:g} m")
    if not problems:
        gap = segments_geo.distance_m(start.lat, start.lon, end.lat, end.lon)
        if gap <= start.radius_m + end.radius_m:
            problems.append("the start and end circles must not overlap")
    return problems


def find_visits(points: list[google_health_stops.TrackPoint], node: Node) -> list[segments_geo.Interval]:
    """The visits to a node, in time order (see ``geo.time_inside_circle``)."""
    return segments_geo.time_inside_circle(points, node.lat, node.lon, node.radius_m)


def choose_passes(
    start_visits: Sequence[segments_geo.Interval], end_visits: Sequence[segments_geo.Interval]
) -> tuple[segments_geo.Interval, segments_geo.Interval] | None:
    """The first end visit that follows a start visit, and the last start visit before it."""
    for end_visit in end_visits:
        before = [visit for visit in start_visits if visit.exit < end_visit.enter]
        if before:
            return max(before, key=lambda visit: visit.exit), end_visit
    return None


def _position_at(points: list[google_health_stops.TrackPoint], times: list[float], t: float) -> tuple[float, float]:
    """Position at time ``t``, interpolated between points unless a long gap lies between them."""
    i = bisect_right(times, t) - 1
    if i < 0:
        return points[0].lat, points[0].lon
    if i >= len(points) - 1:
        return points[-1].lat, points[-1].lon
    p, q = points[i], points[i + 1]
    if t == p.t or q.t - p.t > google_health_stops.GAP_THRESHOLD_S:
        return p.lat, p.lon
    f = (t - p.t) / (q.t - p.t)
    return p.lat + f * (q.lat - p.lat), p.lon + f * (q.lon - p.lon)


def _path_m(points: list[google_health_stops.TrackPoint], start_s: float, end_s: float) -> float:
    """Length of the GPS path between two moments (the same kind of distance as for an activity)."""
    times = [p.t for p in points]
    path = [_position_at(points, times, start_s)]
    path += [(p.lat, p.lon) for p in points if start_s < p.t < end_s]
    path.append(_position_at(points, times, end_s))
    return sum(segments_geo.distance_m(a[0], a[1], b[0], b[1]) for a, b in pairwise(path))


def _overlap_s(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(min(a_end, b_end) - max(a_start, b_start), 0.0)


def _gap_seconds(points: list[google_health_stops.TrackPoint], start_s: float, end_s: float) -> float:
    """Seconds of the window lost to gaps in the GPS stream longer than the gap limit."""
    return sum(
        _overlap_s(p.t, q.t, start_s, end_s)
        for p, q in pairwise(points)
        if q.t - p.t > google_health_stops.GAP_THRESHOLD_S
    )


def _elevation_near(samples: Sequence[Sample], t: float) -> float | None:
    near = [s.value for s in samples if abs(s.t - t) <= ELEVATION_NEAR_S]
    return statistics.median(near) if near else None


def match_segment(
    points: list[google_health_stops.TrackPoint],
    start: Node,
    end: Node,
    heart_rate: Sequence[Sample] = (),
    elevation: Sequence[Sample] = (),
    stops: list[google_health_stops.LongStop] | None = None,
) -> SegmentMatch | None:
    """Match a track against a segment; None when it does not pass start and then end.

    Args:
        points: GPS points in time order, as seconds since the first point.
        start: The start node.
        end: The end node.
        heart_rate: Heart-rate samples (bpm) on the same time axis.
        elevation: Height samples (m) on the same time axis.
        stops: The long stops of the whole track. Detected here when not given.
    """
    if len(points) < 2:
        return None
    start_visits = find_visits(points, start)
    end_visits = find_visits(points, end)
    chosen = choose_passes(start_visits, end_visits)
    if chosen is None:
        return None
    start_visit, end_visit = chosen
    start_s, end_s = start_visit.exit, end_visit.enter

    if stops is None:
        stops = google_health_stops.detect_long_stops(points)
    inside_stops = [
        (stop.trimmed_start, stop.trimmed_duration)
        for stop in stops
        if _overlap_s(stop.trimmed_start, stop.trimmed_start + stop.trimmed_duration, start_s, end_s) > 0
    ]
    stopped_s = sum(_overlap_s(first, first + duration, start_s, end_s) for first, duration in inside_stops)
    gap_s = _gap_seconds(points, start_s, end_s)
    elapsed_s = end_s - start_s
    moving_s = max(elapsed_s - stopped_s - gap_s, 0.0)

    # Heart rate over the moving part: zero readings are dropouts, and samples taken
    # during a long stop would dilute the average.
    moving_hr = [
        int(sample.value)
        for sample in heart_rate
        if start_s <= sample.t <= end_s
        and sample.value > 0
        and not any(first <= sample.t <= first + duration for first, duration in inside_stops)
    ]

    window_elevation = [s for s in elevation if start_s <= s.t <= end_s]
    gain = loss = None
    if len(window_elevation) >= 2:
        gain, loss = activities_utils.compute_elevation_gain_and_loss([{"ele": s.value} for s in window_elevation])
    ele_start = _elevation_near(elevation, start_s)
    ele_end = _elevation_near(elevation, end_s)
    net = ele_end - ele_start if ele_start is not None and ele_end is not None else None

    return SegmentMatch(
        start_s=start_s,
        end_s=end_s,
        elapsed_s=elapsed_s,
        moving_s=moving_s,
        stopped_s=stopped_s,
        gap_s=gap_s,
        distance_m=_path_m(points, start_s, end_s),
        elevation_gain_m=gain,
        elevation_loss_m=loss,
        net_elevation_m=net,
        average_hr=sum(moving_hr) / len(moving_hr) if moving_hr else None,
        max_hr=max(moving_hr) if moving_hr else None,
        hr_samples=len(moving_hr),
        stops=tuple(inside_stops),
        start_visits=len(start_visits),
        end_visits=len(end_visits),
    )
