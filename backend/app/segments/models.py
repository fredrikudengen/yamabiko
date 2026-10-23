"""ORM models for segments and the efforts of activities on them."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

# Kept in step with ``segments.matching.MIN_NODE_RADIUS_M``.
_MIN_RADIUS_M = 25


def _now() -> datetime:
    return datetime.now(UTC)


class Segment(Base):
    """
    A directed segment: a start node and an end node (circles).

    Attributes:
        id: Primary key.
        user_id: Owner user ID.
        name: Segment name.
        start_latitude: Start node centre latitude (degrees).
        start_longitude: Start node centre longitude (degrees).
        start_radius_m: Start node radius (m).
        end_latitude: End node centre latitude (degrees).
        end_longitude: End node centre longitude (degrees).
        end_radius_m: End node radius (m).
        created_at: Creation timestamp.
        updated_at: Last change of the name or nodes.
        efforts: Efforts of the owner's activities on this segment.
    """

    __tablename__ = "segments"
    __table_args__ = (
        CheckConstraint(f"start_radius_m > {_MIN_RADIUS_M}", name="ck_segments_start_radius"),
        CheckConstraint(f"end_radius_m > {_MIN_RADIUS_M}", name="ck_segments_end_radius"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the segment belongs to",
    )
    name: Mapped[str] = mapped_column(String(250), nullable=False, comment="Segment name")
    start_latitude: Mapped[float] = mapped_column(Double, nullable=False, comment="Start node latitude")
    start_longitude: Mapped[float] = mapped_column(Double, nullable=False, comment="Start node longitude")
    start_radius_m: Mapped[float] = mapped_column(Double, nullable=False, default=50.0, comment="Start node radius (m)")
    end_latitude: Mapped[float] = mapped_column(Double, nullable=False, comment="End node latitude")
    end_longitude: Mapped[float] = mapped_column(Double, nullable=False, comment="End node longitude")
    end_radius_m: Mapped[float] = mapped_column(Double, nullable=False, default=50.0, comment="End node radius (m)")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    efforts: Mapped[list[SegmentEffort]] = relationship(
        back_populates="segment",
        cascade="all, delete-orphan",
    )


class SegmentEffort(Base):
    """
    One activity's pass of a segment (at most one per activity and segment).

    Times are in seconds. ``moving_s`` is the clock time between the nodes
    without long stops and stream gaps, so it is comparable between tours.

    Attributes:
        id: Primary key.
        segment_id: The segment.
        activity_id: The activity that passed it.
        start_time: When the activity left the start node (UTC).
        end_time: When the activity reached the end node (UTC).
        elapsed_s: Clock time between start_time and end_time.
        moving_s: Elapsed time minus long stops and stream gaps.
        stopped_s: Time in long stops inside the segment.
        gap_s: Time in GPS stream gaps inside the segment (device pauses).
        distance_m: GPS path length between the nodes.
        elevation_gain_m: Smoothed total ascent between the nodes.
        elevation_loss_m: Smoothed total descent between the nodes.
        net_elevation_m: Height at the end node minus height at the start node.
        average_hr: Mean heart rate over the moving part (bpm).
        max_hr: Highest heart rate over the moving part (bpm).
        matcher_version: ``segments.matching.MATCHER_VERSION`` at the time.
        details: The node parameters used, the stops, and the visit counts.
        computed_at: When the effort was computed.
    """

    __tablename__ = "segment_efforts"
    __table_args__ = (UniqueConstraint("segment_id", "activity_id", name="uq_segment_efforts_segment_activity"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    segment_id: Mapped[int] = mapped_column(
        ForeignKey("segments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Segment that was passed",
    )
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Activity that passed the segment",
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    elapsed_s: Mapped[float] = mapped_column(Double, nullable=False, comment="Clock time between the nodes (s)")
    moving_s: Mapped[float] = mapped_column(Double, nullable=False, comment="Time without long stops and gaps (s)")
    stopped_s: Mapped[float] = mapped_column(Double, nullable=False, default=0.0, comment="Time in long stops (s)")
    gap_s: Mapped[float] = mapped_column(Double, nullable=False, default=0.0, comment="Time in GPS stream gaps (s)")
    distance_m: Mapped[float] = mapped_column(Double, nullable=False, comment="GPS path between the nodes (m)")
    elevation_gain_m: Mapped[float | None] = mapped_column(Double, nullable=True, comment="Ascent (m)")
    elevation_loss_m: Mapped[float | None] = mapped_column(Double, nullable=True, comment="Descent (m)")
    net_elevation_m: Mapped[float | None] = mapped_column(
        Double, nullable=True, comment="End height - start height (m)"
    )
    average_hr: Mapped[float | None] = mapped_column(Double, nullable=True, comment="Mean heart rate while moving")
    max_hr: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Highest heart rate while moving")
    matcher_version: Mapped[int] = mapped_column(Integer, nullable=False, comment="How the effort was derived")
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="Node parameters, stops and visit counts")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    segment: Mapped[Segment] = relationship(back_populates="efforts")
