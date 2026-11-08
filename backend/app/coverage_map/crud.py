"""Reading the coverage grid back out, rolled up to the zoom the map asks for."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

import activities.activity.models as activities_models
import coverage_map.models as coverage_models
import coverage_map.tiles as coverage_tiles


@dataclass(frozen=True)
class CellCount:
    """How many of the user's tours passed through one cell, and when the first did."""

    x: int
    y: int
    count: int
    first_visit: datetime


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
        One entry per cell that at least one activity passed through, with the
        start of the earliest of them.

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
        select(
            x,
            y,
            func.count(func.distinct(cell.activity_id)).label("tours"),
            func.min(activities_models.Activity.start_time).label("first_visit"),
        )
        .join(activities_models.Activity, activities_models.Activity.id == cell.activity_id)
        .where(
            activities_models.Activity.user_id == user_id,
            cell.grid_zoom == coverage_tiles.STORE_ZOOM,
        )
        .group_by(x, y)
    )
    return [CellCount(x=row.x, y=row.y, count=row.tours, first_visit=row.first_visit) for row in db.execute(stmt)]


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


@dataclass(frozen=True)
class ActivityCells:
    """How many cells one tour passed through, and in how many it was the first."""

    cells: int
    new_cells: int


def new_cells_of_activity(user_id: int, activity_id: int, zoom: int, db: Session) -> ActivityCells | None:
    """How many of a tour's cells none of the user's earlier tours had passed through.

    "Earlier" is by start time, with the activity id breaking a tie, so of two
    tours that start together exactly one gets the cells. Later tours never
    take a cell away: the count of a tour does not change when the user walks
    the same way again.

    Args:
        user_id: Whose tours count as earlier.
        activity_id: The tour to count for.
        zoom: Zoom to count at. Must not be finer than the stored zoom.
        db: Database session.

    Returns:
        The counts, or ``None`` when the activity is not the user's.

    Raises:
        ValueError: When ``zoom`` is outside the supported range.
    """
    if not coverage_tiles.MIN_ZOOM <= zoom <= coverage_tiles.MAX_ZOOM:
        raise ValueError(f"zoom must be between {coverage_tiles.MIN_ZOOM} and {coverage_tiles.MAX_ZOOM}")
    activity = activities_models.Activity
    tour = db.get(activity, activity_id)
    if tour is None or tour.user_id != user_id:
        return None

    shift = coverage_tiles.STORE_ZOOM - zoom
    cell = coverage_models.ActivityCell
    mine = (
        select(cell.cell_x.op(">>")(shift).label("x"), cell.cell_y.op(">>")(shift).label("y"))
        .where(cell.activity_id == activity_id, cell.grid_zoom == coverage_tiles.STORE_ZOOM)
        .distinct()
        .subquery()
    )
    # A cell at ``zoom`` covers a block of stored cells. It is looked up as a
    # range, as in ``tours_in_cell``, so ``ix_activity_cells_cell`` can serve it.
    other = aliased(cell)
    earlier = (
        select(other.activity_id)
        .join(activity, activity.id == other.activity_id)
        .where(
            activity.user_id == user_id,
            or_(
                activity.start_time < tour.start_time,
                and_(activity.start_time == tour.start_time, activity.id < activity_id),
            ),
            other.grid_zoom == coverage_tiles.STORE_ZOOM,
            other.cell_x.between(mine.c.x.op("<<")(shift), (mine.c.x + 1).op("<<")(shift) - 1),
            other.cell_y.between(mine.c.y.op("<<")(shift), (mine.c.y + 1).op("<<")(shift) - 1),
        )
        .exists()
    )
    row = db.execute(select(func.count(), func.count().filter(~earlier)).select_from(mine)).one()
    return ActivityCells(cells=row[0], new_cells=row[1])
