"""Stretches the user walks again and again without a segment on them.

Segments are drawn by hand, so a stretch walked ten times may have none. This
finds them from the coverage grid (``activity_cells``):

1. Cells at least ``MIN_TOURS`` different tours passed through.
2. Less the cells an existing segment already covers (the cells its passes
   went through, and their neighbours, for GPS spread).
3. Less the cells around where tours often start and end: home, the car park.
   Every tour passes there, which says nothing about a climb.
4. What is left, joined into connected areas; an area of at least
   ``MIN_CELLS`` cells is a suggestion.

For each area the two cells farthest apart become the ends, placed on the
newest tour's own track so the suggested nodes sit on the path, and ordered the
way most tours walked it. The user still draws the segment; this only says where.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import coverage_map.models as coverage_models
import coverage_map.service as coverage_service
import coverage_map.tiles as coverage_tiles
import google_health.stops as google_health_stops
import segments.crud as segments_crud
import segments.geo as segments_geo
import segments.service as segments_service

Cell = tuple[int, int]

# A stretch walked this many times is worth timing.
MIN_TOURS = 3
# About 600 m at the stored cell size: shorter than that is not much of a climb.
MIN_CELLS = 4
# Tours starting or ending in a cell this often make it a home or a car park.
MIN_ENDPOINT_TOURS = 2
# How many tours' tracks are read to place the ends and find the direction.
DIRECTION_TOURS = 8


@dataclass(frozen=True)
class SuggestedTour:
    id: int
    name: str | None
    start_time: datetime


@dataclass(frozen=True)
class Suggestion:
    """One often-walked stretch without a segment."""

    key: str
    cells: list[Cell]
    tours: list[SuggestedTour]
    start: tuple[float, float]
    end: tuple[float, float]
    straight_m: float


def neighbours(cell: Cell) -> list[Cell]:
    """The eight cells around a cell, and the cell itself."""
    x, y = cell
    return [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


def grow(cells: Iterable[Cell]) -> set[Cell]:
    """The cells and every cell touching them."""
    return {near for cell in cells for near in neighbours(cell)}


def clusters(cells: set[Cell]) -> list[set[Cell]]:
    """The cells joined into areas, where touching (also corner to corner) joins two cells."""
    left = set(cells)
    areas: list[set[Cell]] = []
    while left:
        seed = left.pop()
        area = {seed}
        frontier = [seed]
        while frontier:
            for near in neighbours(frontier.pop()):
                if near in left:
                    left.remove(near)
                    area.add(near)
                    frontier.append(near)
        areas.append(area)
    return areas


def cell_centre(cell: Cell) -> tuple[float, float]:
    south, west, north, east = coverage_tiles.cell_bounds(cell[0], cell[1])
    return (south + north) / 2, (west + east) / 2


def farthest_pair(cells: Iterable[Cell]) -> tuple[Cell, Cell]:
    """The two cells farthest apart (by their centres)."""
    listed = sorted(cells)
    best = (listed[0], listed[0])
    best_m = -1.0
    for i, a in enumerate(listed):
        for b in listed[i + 1 :]:
            d = math.hypot(a[0] - b[0], a[1] - b[1])
            if d > best_m:
                best, best_m = (a, b), d
    return best


def _tour_cells(user_id: int, db: Session) -> dict[Cell, set[int]]:
    cell = coverage_models.ActivityCell
    stmt = (
        select(cell.cell_x, cell.cell_y, cell.activity_id)
        .join(activities_models.Activity, activities_models.Activity.id == cell.activity_id)
        .where(activities_models.Activity.user_id == user_id, cell.grid_zoom == coverage_tiles.STORE_ZOOM)
    )
    tours: dict[Cell, set[int]] = defaultdict(set)
    for row in db.execute(stmt):
        tours[(row.cell_x, row.cell_y)].add(row.activity_id)
    return tours


def _aware(moment: datetime) -> datetime:
    """A stored time with its zone; times are stored in UTC, and some databases drop the zone."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _segment_cells(user_id: int, db: Session) -> set[Cell]:
    """The cells the passes of the user's segments went through between their nodes."""
    covered: set[Cell] = set()
    for segment in segments_crud.get_user_segments(user_id, db):
        for effort in segments_crud.get_efforts_for_segment(segment.id, db)[-DIRECTION_TOURS:]:
            track = segments_service.load_track(effort.activity_id, db)
            if track is None:
                continue
            start_s = (_aware(effort.start_time) - track.start).total_seconds()
            end_s = (_aware(effort.end_time) - track.start).total_seconds()
            covered |= coverage_service.cells_of_track([p for p in track.points if start_s <= p.t <= end_s])
    return covered


def _endpoint_cells(tour_ids: Iterable[int], db: Session) -> set[Cell]:
    """Cells where tours often start or end: homes and car parks."""
    counts: Counter[Cell] = Counter()
    for tour_id in tour_ids:
        track = segments_service.load_track(tour_id, db)
        if track is None or not track.points:
            continue
        ends = {
            coverage_tiles.tile_xy(track.points[0].lat, track.points[0].lon),
            coverage_tiles.tile_xy(track.points[-1].lat, track.points[-1].lon),
        }
        counts.update(ends)
    return {cell for cell, n in counts.items() if n >= MIN_ENDPOINT_TOURS}


def _nearest(points: list[google_health_stops.TrackPoint], lat: float, lon: float) -> google_health_stops.TrackPoint:
    return min(points, key=lambda p: segments_geo.distance_m(p.lat, p.lon, lat, lon))


def _place_ends(
    a: Cell, b: Cell, tours: list[SuggestedTour], db: Session
) -> tuple[tuple[float, float], tuple[float, float]]:
    """The two ends on the newest tour's track, ordered the way most tours walked between them."""
    a_lat, a_lon = cell_centre(a)
    b_lat, b_lon = cell_centre(b)
    a_first = 0
    placed: tuple[tuple[float, float], tuple[float, float]] | None = None
    for tour in tours[:DIRECTION_TOURS]:
        track = segments_service.load_track(tour.id, db)
        if track is None or len(track.points) < 2:
            continue
        near_a = _nearest(track.points, a_lat, a_lon)
        near_b = _nearest(track.points, b_lat, b_lon)
        a_first += 1 if near_a.t < near_b.t else -1
        if placed is None:
            placed = ((near_a.lat, near_a.lon), (near_b.lat, near_b.lon))
    start, end = placed or ((a_lat, a_lon), (b_lat, b_lon))
    return (start, end) if a_first >= 0 else (end, start)


def suggest(user_id: int, db: Session, min_tours: int = MIN_TOURS) -> list[Suggestion]:
    """Often-walked stretches without a segment, the most walked first.

    Args:
        user_id: Whose tours and segments to look at.
        db: Database session.
        min_tours: How many different tours must have walked a stretch.

    Returns:
        The suggestions; empty when every often-walked stretch has a segment.
    """
    tours_by_cell = _tour_cells(user_id, db)
    all_tours = {tour for tours in tours_by_cell.values() for tour in tours}
    excluded = grow(_segment_cells(user_id, db)) | grow(_endpoint_cells(all_tours, db))
    often = {cell for cell, tours in tours_by_cell.items() if len(tours) >= min_tours and cell not in excluded}

    activity = activities_models.Activity
    info = {
        row.id: SuggestedTour(row.id, row.name, row.start_time)
        for row in db.execute(select(activity.id, activity.name, activity.start_time).where(activity.id.in_(all_tours)))
    }

    suggestions: list[Suggestion] = []
    for area in clusters(often):
        if len(area) < MIN_CELLS:
            continue
        # A tour counts for the stretch when it passed through at least half of it.
        passes: Counter[int] = Counter(tour for cell in area for tour in tours_by_cell[cell])
        tour_ids = [tour for tour, n in passes.items() if n * 2 >= len(area)]
        if len(tour_ids) < min_tours:
            continue
        tours = sorted((info[t] for t in tour_ids if t in info), key=lambda t: t.start_time, reverse=True)
        a, b = farthest_pair(area)
        start, end = _place_ends(a, b, tours, db)
        cells = sorted(area)
        suggestions.append(
            Suggestion(
                key=hashlib.sha1(repr(cells).encode()).hexdigest()[:12],  # noqa: S324 - an id, not security
                cells=cells,
                tours=tours,
                start=start,
                end=end,
                straight_m=segments_geo.distance_m(start[0], start[1], end[0], end[1]),
            )
        )
    return sorted(suggestions, key=lambda s: (-len(s.tours), -len(s.cells)))
