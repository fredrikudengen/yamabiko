"""Reading the coverage grid back out, rolled up to the zoom the map asks for."""

from __future__ import annotations

from dataclasses import dataclass

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
