"""Request and response models for the segments API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import segments.coordinates as segments_coordinates
import segments.matching as segments_matching


class NodeIn(BaseModel):
    """A node as the client sends it: ``lat`` and ``lon``, or one ``coordinates`` string such as ``60.39, 5.32``."""

    model_config = ConfigDict(extra="forbid")

    lat: float | None = None
    lon: float | None = None
    coordinates: str | None = Field(default=None, max_length=100)
    radius_m: float = segments_matching.DEFAULT_NODE_RADIUS_M

    @model_validator(mode="after")
    def _resolve_position(self) -> NodeIn:
        has_pair = self.lat is not None or self.lon is not None
        if self.coordinates is not None and has_pair:
            raise ValueError("give either lat and lon, or coordinates, not both")
        if self.coordinates is not None:
            self.lat, self.lon = segments_coordinates.parse_coordinates(self.coordinates)
        elif self.lat is None or self.lon is None:
            raise ValueError("give lat and lon, or coordinates")
        return self

    def to_node(self) -> segments_matching.Node:
        """The matching node. Both coordinates are set once the model has validated."""
        if self.lat is None or self.lon is None:
            raise ValueError("the node has no position")
        return segments_matching.Node(self.lat, self.lon, self.radius_m)


class SegmentIn(BaseModel):
    """Create or change a segment."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=250)
    start: NodeIn
    end: NodeIn

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("the name must not be empty")
        return value


class PreviewIn(BaseModel):
    """Two nodes to try out before saving."""

    model_config = ConfigDict(extra="forbid")

    start: NodeIn
    end: NodeIn


class ParseCoordinatesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=100)


class NodeOut(BaseModel):
    lat: float
    lon: float
    radius_m: float


class ParsedCoordinatesOut(BaseModel):
    lat: float
    lon: float


class SimilarSegmentOut(BaseModel):
    id: int
    name: str


class SegmentOut(BaseModel):
    id: int
    name: str
    start: NodeOut
    end: NodeOut
    effort_count: int
    created_at: datetime
    updated_at: datetime


class SegmentSavedOut(SegmentOut):
    """The answer to create and update: the segment, plus segments it looks like (a hint, not an error)."""

    similar_segments: list[SimilarSegmentOut]


class EffortOut(BaseModel):
    """One pass of a segment. Times in seconds; ``moving_s`` is without long stops and stream gaps."""

    id: int
    segment_id: int
    segment_name: str
    activity_id: int
    activity_name: str | None
    source: str
    start_time: datetime
    end_time: datetime
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
    matcher_version: int
    details: dict[str, Any] | None


class PreviewMatchOut(BaseModel):
    activity_id: int
    activity_name: str | None
    source: str
    start_time: datetime
    end_time: datetime
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
    start_visits: int
    end_visits: int
    closest_start_m: float
    closest_end_m: float
    start_visit_times: list[datetime]
    end_visit_times: list[datetime]


class NearMissOut(BaseModel):
    """An activity that came near both nodes but does not match; ``reason`` says why.

    Reasons: ``start_not_reached``, ``end_not_reached``, ``both_not_reached`` (the radius
    was too small; the closest-approach distances say how large it would have to be) and
    ``wrong_order`` (it passed both, but the end before the start).
    """

    activity_id: int
    activity_name: str | None
    start_time: datetime
    reason: str
    closest_start_m: float
    closest_end_m: float


class PreviewOut(BaseModel):
    """Which of the user's activities pass the nodes, and which nearly do, oldest first. Nothing is saved."""

    matches: list[PreviewMatchOut]
    near_misses: list[NearMissOut]
    similar_segments: list[SimilarSegmentOut]
