"""Day-by-day totals over the user's whole history, for the year-over-year chart.

The chart adds the days up through each year, so a year can be laid over the
others: how far into March 2026 the user had climbed as much as in all of
March 2025. The server sends one row per day with something on it and leaves
the running sums to the client, which can then sum whichever metric it shows.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import coverage_map.models as coverage_models
import coverage_map.tiles as coverage_tiles
from activities.activity.models import Activity

# New ground is counted at the coverage map's default cell size (about 300 m in
# southern Norway), so the chart agrees with the map and with a tour's page.
NEW_CELL_ZOOM = coverage_tiles.STORE_ZOOM - 1


@dataclass
class DayTotals:
    """What the user did on one day."""

    day: date
    distance: float = 0.0
    duration: float = 0.0
    elevation_gain: float = 0.0
    activity_count: int = 0
    new_cells: int = 0


@dataclass
class _Days:
    by_day: dict[date, DayTotals] = field(default_factory=dict)

    def get(self, day: date) -> DayTotals:
        if day not in self.by_day:
            self.by_day[day] = DayTotals(day=day)
        return self.by_day[day]


def _as_date(value: date | datetime | str) -> date:
    """A day as the database gives it: a date on Postgres, a string on SQLite."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def daily_progress(user_id: int, activity_type_id: int | None, db: Session) -> list[DayTotals]:
    """The user's totals per day, over their whole history, oldest first.

    A day counts by the date of the tour's start, as the rest of the summary
    does. New cells are the cells at :data:`NEW_CELL_ZOOM` whose first tour
    started that day; with a type filter, "first" is among tours of that type.

    Args:
        user_id: Whose tours to add up.
        activity_type_id: Only tours of this type, or every tour when ``None``.
        db: Database session.

    Returns:
        One entry per day with at least one tour on it.
    """
    days = _Days()
    by_type = [Activity.activity_type == activity_type_id] if activity_type_id is not None else []

    day = func.date(Activity.start_time).label("day")
    totals = (
        select(
            day,
            func.coalesce(func.sum(Activity.distance), 0).label("distance"),
            func.coalesce(func.sum(Activity.total_timer_time), 0.0).label("duration"),
            func.coalesce(func.sum(Activity.elevation_gain), 0).label("elevation_gain"),
            func.count(Activity.id).label("activity_count"),
        )
        .where(Activity.user_id == user_id, *by_type)
        .group_by(day)
    )
    for row in db.execute(totals):
        totals_of_day = days.get(_as_date(row.day))
        totals_of_day.distance = float(row.distance)
        totals_of_day.duration = float(row.duration)
        totals_of_day.elevation_gain = float(row.elevation_gain)
        totals_of_day.activity_count = int(row.activity_count)

    shift = coverage_tiles.STORE_ZOOM - NEW_CELL_ZOOM
    cell = coverage_models.ActivityCell
    first_visits = (
        select(func.min(Activity.start_time).label("first"))
        .select_from(cell)
        .join(Activity, Activity.id == cell.activity_id)
        .where(Activity.user_id == user_id, cell.grid_zoom == coverage_tiles.STORE_ZOOM, *by_type)
        .group_by(cell.cell_x.op(">>")(shift), cell.cell_y.op(">>")(shift))
        .subquery()
    )
    first_day = func.date(first_visits.c.first).label("day")
    new_cells: dict[date, int] = defaultdict(int)
    for row in db.execute(select(first_day, func.count().label("cells")).group_by(first_day)):
        new_cells[_as_date(row.day)] += int(row.cells)
    for day_of_cells, count in new_cells.items():
        days.get(day_of_cells).new_cells = count

    return sorted(days.by_day.values(), key=lambda totals_of_day: totals_of_day.day)
