"""Turn an activity's GPS track into the cells it passed through, and store them."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import core.logger as core_logger
import coverage_map.models as coverage_models
import coverage_map.tiles as coverage_tiles
import google_health.stops as google_health_stops
import segments.service as segments_service

# Points further apart in time than this are not joined: the watch lost its
# signal, and the straight line between them says nothing about where the walk
# went. The same threshold the pace graph and the heart-rate zones use.
GAP_THRESHOLD_S = google_health_stops.GAP_THRESHOLD_S

# Sampling step along a line, in cells. Half a cell cannot step over a whole
# one, so no cell on the way is missed.
_STEP_CELLS = 0.5

# A pair of points this far apart in cells is not a walk — a corrupt coordinate,
# or a track crossing the antimeridian. Both ends are kept, the line between
# them is not drawn.
_MAX_FILL_CELLS = 2048


def cells_of_track(
    points: Sequence[google_health_stops.TrackPoint],
    zoom: int = coverage_tiles.STORE_ZOOM,
    gap_s: float = GAP_THRESHOLD_S,
) -> set[tuple[int, int]]:
    """The cells a track passed through.

    Every point's own cell is included. Between two consecutive points the line
    is filled in as well, so a cell the track crossed without a GPS point landing
    in it still counts — unless the two points are more than ``gap_s`` apart,
    where there is no evidence of what happened in between.

    Args:
        points: GPS points, in time order, seconds since the first point.
        zoom: Zoom of the grid to count in.
        gap_s: Longest gap between points that is still joined (s).

    Returns:
        The set of ``(x, y)`` cells at ``zoom``.
    """
    cells: set[tuple[int, int]] = set()
    previous: tuple[float, float] | None = None
    previous_t: float | None = None
    for point in points:
        current = coverage_tiles.tile_xy_float(point.lat, point.lon, zoom)
        cells.add(coverage_tiles.tile_xy(point.lat, point.lon, zoom))
        if previous is not None and previous_t is not None and point.t - previous_t <= gap_s:
            cells.update(_line_cells(previous, current, zoom))
        previous, previous_t = current, point.t
    return cells


def _line_cells(start: tuple[float, float], end: tuple[float, float], zoom: int) -> set[tuple[int, int]]:
    """The cells a straight line in tile space crosses, endpoints included."""
    scale = 2**zoom
    dx, dy = end[0] - start[0], end[1] - start[1]
    span = max(abs(dx), abs(dy))
    if span > _MAX_FILL_CELLS:
        return set()
    steps = max(1, math.ceil(span / _STEP_CELLS))
    cells = set()
    for step in range(steps + 1):
        fraction = step / steps
        x = math.floor(start[0] + dx * fraction)
        y = math.floor(start[1] + dy * fraction)
        cells.add((min(scale - 1, max(0, x)), min(scale - 1, max(0, y))))
    return cells


def _user_activity_ids(user_id: int, db: Session) -> list[int]:
    """The user's activity ids, oldest first."""
    stmt = (
        select(activities_models.Activity.id)
        .where(activities_models.Activity.user_id == user_id)
        .order_by(activities_models.Activity.start_time)
    )
    return [row.id for row in db.execute(stmt)]


def refresh_activity_cells(activity_id: int, db: Session) -> int:
    """Recompute one activity's cells from its GPS stream.

    Activities without a GPS stream simply end up with no cells.

    Args:
        activity_id: The activity to recompute.
        db: Database session.

    Returns:
        How many cells the activity now has.
    """
    track = segments_service.load_track(activity_id, db)
    cells = cells_of_track(track.points) if track is not None else set()
    db.execute(delete(coverage_models.ActivityCell).where(coverage_models.ActivityCell.activity_id == activity_id))
    db.add_all(
        coverage_models.ActivityCell(activity_id=activity_id, cell_x=x, cell_y=y, grid_zoom=coverage_tiles.STORE_ZOOM)
        for x, y in sorted(cells)
    )
    db.commit()
    return len(cells)


def refresh_user_cells(user_id: int, db: Session) -> int:
    """Recompute the cells of every activity the user owns.

    This is the backfill: it does not care which importer brought an activity in,
    so activities imported from a Strava file are covered by the same code as the
    ones that come from Google Health.

    Args:
        user_id: The owner.
        db: Database session.

    Returns:
        How many activities were recomputed.
    """
    activity_ids = _user_activity_ids(user_id, db)
    for activity_id in activity_ids:
        refresh_activity_cells(activity_id, db)
    return len(activity_ids)


def refresh_cells_after_import(activities: Sequence[Any], user_id: int, db: Session) -> None:
    """Add freshly imported activities to the coverage map; never raises.

    Called by the importers after an activity is stored. A failure here must not
    undo or hide the import, so it is logged and the session rolled back. The
    cells can be rebuilt at any time (``POST /coverage/refresh``).

    Args:
        activities: The activities that were just stored.
        user_id: The owner, for the log line.
        db: Database session.

    Returns:
        None.
    """
    for activity in activities:
        try:
            refresh_activity_cells(activity.id, db)
        except Exception as err:
            db.rollback()
            core_logger.print_to_log(
                f"User {user_id}: building coverage cells for activity {getattr(activity, 'id', None)} failed: "
                f"{type(err).__name__}",
                "error",
                exc=err,
            )
