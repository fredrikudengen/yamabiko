"""Database access for segments and their efforts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

import segments.matching as segments_matching
import segments.models as segments_models


def nodes_of(segment: segments_models.Segment) -> tuple[segments_matching.Node, segments_matching.Node]:
    """The segment's start and end node."""
    return (
        segments_matching.Node(segment.start_latitude, segment.start_longitude, segment.start_radius_m),
        segments_matching.Node(segment.end_latitude, segment.end_longitude, segment.end_radius_m),
    )


def _checked(name: str, start: segments_matching.Node, end: segments_matching.Node) -> str:
    """The cleaned name; raises ValueError when the name or the nodes are not acceptable."""
    cleaned = name.strip()
    problems = [] if cleaned else ["the name must not be empty"]
    problems += segments_matching.validate_nodes(start, end)
    if problems:
        raise ValueError("; ".join(problems))
    return cleaned


def create_segment(
    user_id: int,
    name: str,
    start: segments_matching.Node,
    end: segments_matching.Node,
    db: Session,
) -> segments_models.Segment:
    """Create a segment for the user. Raises ValueError when the name or nodes are not acceptable."""
    segment = segments_models.Segment(
        user_id=user_id,
        name=_checked(name, start, end),
        start_latitude=start.lat,
        start_longitude=start.lon,
        start_radius_m=start.radius_m,
        end_latitude=end.lat,
        end_longitude=end.lon,
        end_radius_m=end.radius_m,
    )
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return segment


def update_segment(
    segment: segments_models.Segment,
    name: str,
    start: segments_matching.Node,
    end: segments_matching.Node,
    db: Session,
) -> segments_models.Segment:
    """Change the name and nodes. The efforts are stale afterwards: see ``service.refresh_segment_efforts``."""
    segment.name = _checked(name, start, end)
    segment.start_latitude, segment.start_longitude, segment.start_radius_m = start.lat, start.lon, start.radius_m
    segment.end_latitude, segment.end_longitude, segment.end_radius_m = end.lat, end.lon, end.radius_m
    db.commit()
    db.refresh(segment)
    return segment


def delete_segment(segment: segments_models.Segment, db: Session) -> None:
    """Delete the segment and, with it, its efforts."""
    db.delete(segment)
    db.commit()


def get_segment(segment_id: int, user_id: int, db: Session) -> segments_models.Segment | None:
    """The user's segment, or None (also when the segment belongs to someone else)."""
    stmt = select(segments_models.Segment).where(
        segments_models.Segment.id == segment_id,
        segments_models.Segment.user_id == user_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_user_segments(user_id: int, db: Session) -> list[segments_models.Segment]:
    """All segments of the user, by name."""
    stmt = (
        select(segments_models.Segment)
        .where(segments_models.Segment.user_id == user_id)
        .order_by(segments_models.Segment.name, segments_models.Segment.id)
    )
    return list(db.execute(stmt).scalars())


def get_efforts_for_segment(segment_id: int, db: Session) -> list[segments_models.SegmentEffort]:
    """The efforts on a segment, oldest first."""
    stmt = (
        select(segments_models.SegmentEffort)
        .where(segments_models.SegmentEffort.segment_id == segment_id)
        .order_by(segments_models.SegmentEffort.start_time, segments_models.SegmentEffort.id)
    )
    return list(db.execute(stmt).scalars())


def get_efforts_for_activity(activity_id: int, db: Session) -> list[segments_models.SegmentEffort]:
    """The efforts an activity has on any segment."""
    stmt = (
        select(segments_models.SegmentEffort)
        .where(segments_models.SegmentEffort.activity_id == activity_id)
        .order_by(segments_models.SegmentEffort.segment_id)
    )
    return list(db.execute(stmt).scalars())
