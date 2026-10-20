"""Load an activity's streams, match them against segments and store the efforts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import activities.activity_streams.constants as streams_constants
import activities.activity_streams.models as streams_models
import google_health.stops as google_health_stops
import segments.crud as segments_crud
import segments.matching as segments_matching
import segments.models as segments_models

_STREAM_TYPES = (
    streams_constants.STREAM_TYPE_HR,
    streams_constants.STREAM_TYPE_ELEVATION,
    streams_constants.STREAM_TYPE_MAP,
)


@dataclass(frozen=True)
class Track:
    """An activity's GPS points, heart rate and height on one time axis (seconds since the first GPS point)."""

    start: datetime
    points: list[google_health_stops.TrackPoint]
    heart_rate: list[segments_matching.Sample]
    elevation: list[segments_matching.Sample]


@dataclass(frozen=True)
class PreviewMatch:
    """An activity that passes a (possibly unsaved) segment."""

    activity_id: int
    start_time: datetime
    end_time: datetime
    match: segments_matching.SegmentMatch


def _parse_time(value: str) -> datetime:
    """Parse a stored waypoint time. Stream times are UTC, written without an offset."""
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _samples(waypoints: list[dict], key: str, start: datetime) -> list[segments_matching.Sample]:
    samples = [
        segments_matching.Sample((_parse_time(w["time"]) - start).total_seconds(), float(w[key]))
        for w in waypoints
        if w.get("time") and w.get(key) is not None
    ]
    return sorted(samples, key=lambda sample: sample.t)


def build_track(waypoints_by_type: dict[int, list[dict]]) -> Track | None:
    """A ``Track`` from stored stream waypoints; None when there are fewer than two GPS points."""
    gps = [
        w
        for w in waypoints_by_type.get(streams_constants.STREAM_TYPE_MAP) or []
        if w.get("time") and w.get("lat") is not None and w.get("lon") is not None
    ]
    if len(gps) < 2:
        return None
    timed = sorted(((_parse_time(w["time"]), w) for w in gps), key=lambda item: item[0])
    start = timed[0][0]
    points = [
        google_health_stops.TrackPoint((moment - start).total_seconds(), float(w["lat"]), float(w["lon"]))
        for moment, w in timed
    ]
    return Track(
        start=start,
        points=points,
        heart_rate=_samples(waypoints_by_type.get(streams_constants.STREAM_TYPE_HR) or [], "hr", start),
        elevation=_samples(waypoints_by_type.get(streams_constants.STREAM_TYPE_ELEVATION) or [], "ele", start),
    )


def load_track(activity_id: int, db: Session) -> Track | None:
    """Load an activity's track from its streams; None when it has no GPS stream."""
    stmt = select(streams_models.ActivityStreams).where(
        streams_models.ActivityStreams.activity_id == activity_id,
        streams_models.ActivityStreams.stream_type.in_(_STREAM_TYPES),
    )
    waypoints = {stream.stream_type: stream.stream_waypoints for stream in db.execute(stmt).scalars()}
    return build_track(waypoints)


def match_track(
    track: Track, segment: segments_models.Segment, stops: list[google_health_stops.LongStop] | None = None
) -> segments_matching.SegmentMatch | None:
    """Match a track against a segment (nothing is stored)."""
    start, end = segments_crud.nodes_of(segment)
    return segments_matching.match_segment(
        track.points, start, end, heart_rate=track.heart_rate, elevation=track.elevation, stops=stops
    )


def build_effort(
    segment: segments_models.Segment,
    activity_id: int,
    track: Track,
    match: segments_matching.SegmentMatch,
) -> segments_models.SegmentEffort:
    """The effort row for a match (not yet added to a session)."""
    return segments_models.SegmentEffort(
        segment_id=segment.id,
        activity_id=activity_id,
        start_time=track.start + timedelta(seconds=match.start_s),
        end_time=track.start + timedelta(seconds=match.end_s),
        elapsed_s=match.elapsed_s,
        moving_s=match.moving_s,
        stopped_s=match.stopped_s,
        gap_s=match.gap_s,
        distance_m=match.distance_m,
        elevation_gain_m=match.elevation_gain_m,
        elevation_loss_m=match.elevation_loss_m,
        net_elevation_m=match.net_elevation_m,
        average_hr=match.average_hr,
        max_hr=match.max_hr,
        matcher_version=segments_matching.MATCHER_VERSION,
        details={
            "start_node": {
                "lat": segment.start_latitude,
                "lon": segment.start_longitude,
                "radius_m": segment.start_radius_m,
            },
            "end_node": {"lat": segment.end_latitude, "lon": segment.end_longitude, "radius_m": segment.end_radius_m},
            "long_stops": [{"start_s": round(first), "duration_s": round(duration)} for first, duration in match.stops],
            "stop_parameters": {
                "radius_m": google_health_stops.STOP_RADIUS_M,
                "min_seconds": google_health_stops.STOP_MIN_SECONDS,
                "trim_radius_m": google_health_stops.STOP_TRIM_RADIUS_M,
                "gap_threshold_s": google_health_stops.GAP_THRESHOLD_S,
            },
            "start_visits": match.start_visits,
            "end_visits": match.end_visits,
            "hr_samples": match.hr_samples,
        },
    )


def _user_activity_ids(user_id: int, db: Session) -> list[int]:
    stmt = (
        select(activities_models.Activity.id)
        .where(activities_models.Activity.user_id == user_id)
        .order_by(activities_models.Activity.start_time)
    )
    return list(db.execute(stmt).scalars())


def preview_matches(
    user_id: int,
    start: segments_matching.Node,
    end: segments_matching.Node,
    db: Session,
) -> list[PreviewMatch]:
    """Which of the user's activities pass these nodes, with times. Nothing is stored.

    Raises ValueError when the nodes are not acceptable.
    """
    problems = segments_matching.validate_nodes(start, end)
    if problems:
        raise ValueError("; ".join(problems))
    hits: list[PreviewMatch] = []
    for activity_id in _user_activity_ids(user_id, db):
        track = load_track(activity_id, db)
        if track is None:
            continue
        match = segments_matching.match_segment(
            track.points, start, end, heart_rate=track.heart_rate, elevation=track.elevation
        )
        if match is not None:
            hits.append(
                PreviewMatch(
                    activity_id=activity_id,
                    start_time=track.start + timedelta(seconds=match.start_s),
                    end_time=track.start + timedelta(seconds=match.end_s),
                    match=match,
                )
            )
    return hits


def refresh_segment_efforts(segment: segments_models.Segment, db: Session) -> list[segments_models.SegmentEffort]:
    """Recompute every effort on the segment from the owner's activities.

    Run after a segment is created, or after its nodes change. Old efforts are
    removed first, so none are left over from earlier nodes.
    """
    efforts: list[segments_models.SegmentEffort] = []
    for activity_id in _user_activity_ids(segment.user_id, db):
        track = load_track(activity_id, db)
        match = match_track(track, segment) if track is not None else None
        if track is not None and match is not None:
            efforts.append(build_effort(segment, activity_id, track, match))
    db.execute(delete(segments_models.SegmentEffort).where(segments_models.SegmentEffort.segment_id == segment.id))
    db.add_all(efforts)
    db.commit()
    return efforts


def refresh_activity_efforts(activity_id: int, user_id: int, db: Session) -> list[segments_models.SegmentEffort]:
    """Recompute one activity's efforts on all of the user's segments.

    Run after an activity is imported or its streams change.
    """
    segments = segments_crud.get_user_segments(user_id, db)
    track = load_track(activity_id, db)
    stops = google_health_stops.detect_long_stops(track.points) if track is not None else None
    efforts: list[segments_models.SegmentEffort] = []
    for segment in segments:
        match = match_track(track, segment, stops) if track is not None else None
        if track is not None and match is not None:
            efforts.append(build_effort(segment, activity_id, track, match))
    segment_ids = [segment.id for segment in segments]
    if segment_ids:
        db.execute(
            delete(segments_models.SegmentEffort).where(
                segments_models.SegmentEffort.activity_id == activity_id,
                segments_models.SegmentEffort.segment_id.in_(segment_ids),
            )
        )
    db.add_all(efforts)
    db.commit()
    return efforts
