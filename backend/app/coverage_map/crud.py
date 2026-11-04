"""Reading the coverage grid back out, rolled up to the zoom the map asks for."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import coverage_map.models as coverage_models
import coverage_map.tiles as coverage_tiles


@dataclass(frozen=True)
class CellCount:
    """How many of the user's tours passed through one cell."""

    x: int
    y: int
    count: int


def cell_counts(user_id: int, zoom: int, db: Session) -> list[CellCount]:
    """The user's coverage, counted per cell at a zoom.

    Cells are stored at :data:`coverage_map.tiles.STORE_ZOOM` and rolled up here
    by dropping low bits, so a coarser zoom is a plain regrouping of the same
    rows. The count is of distinct activities: four stored cells of one tour
    inside one coarse cell still count as one tour.

    Args:
        user_id: Whose activities to count.
        zoom: Zoom to count at. Must not be finer than the stored zoom.
        db: Database session.

    Returns:
        One entry per cell that at least one activity passed through.

    Raises:
        ValueError: When ``zoom`` is outside the supported range.
    """
    if not coverage_tiles.MIN_ZOOM <= zoom <= coverage_tiles.MAX_ZOOM:
        raise ValueError(f"zoom must be between {coverage_tiles.MIN_ZOOM} and {coverage_tiles.MAX_ZOOM}")
    shift = coverage_tiles.STORE_ZOOM - zoom
    cell = coverage_models.ActivityCell
    x = cell.cell_x.op(">>")(shift).label("x")
    y = cell.cell_y.op(">>")(shift).label("y")
    stmt = (
        # Labelled ``tours`` rather than ``count``: a row attribute named
        # ``count`` would collide with the tuple method of the same name.
        select(x, y, func.count(func.distinct(cell.activity_id)).label("tours"))
        .join(activities_models.Activity, activities_models.Activity.id == cell.activity_id)
        .where(
            activities_models.Activity.user_id == user_id,
            cell.grid_zoom == coverage_tiles.STORE_ZOOM,
        )
        .group_by(x, y)
    )
    return [CellCount(x=row.x, y=row.y, count=row.tours) for row in db.execute(stmt)]


@dataclass(frozen=True)
class CellTour:
    """One of the user's tours that passed through a cell."""

    id: int
    name: str | None
    start_time: datetime


def tours_in_cell(user_id: int, zoom: int, x: int, y: int, db: Session) -> list[CellTour]:
    """The user's tours that passed through one cell, newest first.

    The cell is given at ``zoom`` and covers a square block of stored cells.
    The block is looked up as a range of ``cell_x`` and ``cell_y`` rather than
    by shifting each row, so ``ix_activity_cells_cell`` can serve it.

    Args:
        user_id: Whose tours to list.
        zoom: Zoom the cell is given at.
        x: Cell x at ``zoom``.
        y: Cell y at ``zoom``.
        db: Database session.

    Returns:
        Each tour once, however many of its stored cells lie in the block.

    Raises:
        ValueError: When ``zoom`` is outside the supported range, or the cell
            is not on the grid at that zoom.
    """
    if not coverage_tiles.MIN_ZOOM <= zoom <= coverage_tiles.MAX_ZOOM:
        raise ValueError(f"zoom must be between {coverage_tiles.MIN_ZOOM} and {coverage_tiles.MAX_ZOOM}")
    if not (0 <= x < 2**zoom and 0 <= y < 2**zoom):
        raise ValueError(f"cell ({x}, {y}) is not on the grid at zoom {zoom}")
    shift = coverage_tiles.STORE_ZOOM - zoom
    cell = coverage_models.ActivityCell
    activity = activities_models.Activity
    tours_here = (
        select(cell.activity_id)
        .where(
            cell.grid_zoom == coverage_tiles.STORE_ZOOM,
            cell.cell_x.between(x << shift, ((x + 1) << shift) - 1),
            cell.cell_y.between(y << shift, ((y + 1) << shift) - 1),
        )
        .distinct()
    )
    stmt = (
        select(activity.id, activity.name, activity.start_time)
        .where(activity.user_id == user_id, activity.id.in_(tours_here))
        .order_by(activity.start_time.desc(), activity.id.desc())
    )
    return [CellTour(id=row.id, name=row.name, start_time=row.start_time) for row in db.execute(stmt)]
