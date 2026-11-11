"""What the model is told about a tour: computed numbers only.

The facts are the app's own results — times, standings, new ground — never the
raw GPS or heart-rate streams, and never coordinates. The model can then word
the numbers but has none of its own to invent. Names of the tour and of its
segments are included; they are the only thing that says where the tour was.

Every value is rounded the way the interface shows it, so the same tour gives
the same facts, and the same hash, each time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import activities.activity.utils as activities_utils
import activities.activity_summaries.progress as summary_progress
import coverage_map.crud as coverage_crud
import google_health.stops as google_health_stops
import segments.crud as segments_crud
import segments.models as segments_models
import segments.profile as segments_profile
import segments.quality as segments_quality
import segments.ranking as segments_ranking
import segments.service as segments_service

# A stretch is a tenth of the way, as in the segment page's "against the best" card.
_STRETCH_STEPS = 10


def _local_start(activity: activities_models.Activity) -> datetime:
    """The start in the tour's own time zone, so "morning" means morning there."""
    start = activity.start_time
    if start.tzinfo is None:  # stored as UTC; some databases hand it back without the zone
        start = start.replace(tzinfo=UTC)
    try:
        return start.astimezone(ZoneInfo(activity.timezone)) if activity.timezone else start
    except (ZoneInfoNotFoundError, ValueError):
        return start


def _rounded(value: float | Decimal | None, digits: int = 0) -> float | int | None:
    if value is None:
        return None
    return round(float(value), digits) if digits else round(float(value))


def _stretch(behind: list[float], sign: int) -> dict[str, Any] | None:
    """The tenth of the way where the most time was lost (``sign`` 1) or won (-1)."""
    best: tuple[float, int] | None = None
    for start in range(len(behind) - _STRETCH_STEPS):
        change = (behind[start + _STRETCH_STEPS] - behind[start]) * sign
        if change >= 1 and (best is None or change > best[0]):
            best = (change, start)
    if best is None:
        return None
    return {"seconds": round(best[0]), "from_percent": best[1], "to_percent": best[1] + _STRETCH_STEPS}


def _against_best(
    segment: segments_models.Segment,
    effort: segments_models.SegmentEffort,
    best: segments_models.SegmentEffort,
    db: Session,
) -> dict[str, Any] | None:
    """How the pass went against the segment's fastest, along the way (moving time)."""
    mine = segments_service.effort_profile(segment, effort, db)
    theirs = segments_service.effort_profile(segment, best, db)
    if mine is None or theirs is None:
        return None
    behind = [a - b for a, b in zip(mine.moving_s, theirs.moving_s, strict=True)]
    return {
        "best_moving_seconds": round(best.moving_s),
        "best_date": best.start_time.date().isoformat(),
        "behind_at_finish_seconds": round(behind[-1]),
        "behind_halfway_seconds": round(behind[segments_profile.PROFILE_STEPS // 2]),
        "most_time_lost": _stretch(behind, 1),
        "most_time_won": _stretch(behind, -1),
    }


def _segments(activity_id: int, db: Session) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for effort in segments_crud.get_efforts_for_activity(activity_id, db):
        segment = effort.segment
        everyone = segments_crud.get_efforts_for_segment(segment.id, db)
        standing = segments_ranking.rank_efforts(everyone)[effort.id]
        best = min(everyone, key=lambda other: (round(other.moving_s), other.id))
        fact: dict[str, Any] = {
            "name": segment.name,
            "moving_seconds": round(effort.moving_s),
            "total_seconds": round(effort.elapsed_s),
            "long_stops_seconds": round(effort.stopped_s),
            "distance_m": round(effort.distance_m),
            "elevation_gain_m": _rounded(effort.elevation_gain_m),
            "average_heart_rate": _rounded(effort.average_hr),
            "passes_of_this_segment": standing.count,
            "rank_by_moving_time": standing.rank_moving if standing.count > 1 else None,
            "is_personal_record": standing.count > 1 and standing.rank_moving == 1,
            # Reasons the time may be off: gps_gap, start_edge, end_edge (see segments.quality).
            "time_uncertain_because": segments_quality.effort_doubts(effort),
        }
        if standing.count > 1 and best.id != effort.id:
            fact["against_fastest_pass"] = _against_best(segment, effort, best, db)
        facts.append(fact)
    return facts


def _long_stops(activity_id: int, db: Session) -> dict[str, Any] | None:
    track = segments_service.load_track(activity_id, db)
    if track is None:
        return None
    stops = google_health_stops.detect_long_stops(track.points)
    return {
        "count": len(stops),
        "total_seconds": round(sum(stop.trimmed_duration for stop in stops)),
        "longest_seconds": round(max((stop.trimmed_duration for stop in stops), default=0)),
    }


def _year_so_far(user_id: int, day: date, db: Session) -> dict[str, Any]:
    """The year up to and including the tour's day, against last year by the same date."""

    def totals(year: int, days: list[summary_progress.DayTotals]) -> dict[str, Any]:
        try:
            until = day.replace(year=year)
        except ValueError:  # 29 February in a common year
            until = date(year, 2, 28)
        chosen = [d for d in days if d.day.year == year and d.day <= until]
        return {
            "year": year,
            "tours": sum(d.activity_count for d in chosen),
            "distance_km": round(sum(d.distance for d in chosen) / 1000, 1),
            "elevation_gain_m": round(sum(d.elevation_gain for d in chosen)),
            "new_map_cells": sum(d.new_cells for d in chosen),
        }

    days = summary_progress.daily_progress(user_id, None, db)
    return {
        "through_this_tour": totals(day.year, days),
        "last_year_by_same_date": totals(day.year - 1, days),
    }


def build_facts(activity: activities_models.Activity, db: Session) -> dict[str, Any]:
    """Everything the model is told about one tour.

    Args:
        activity: The tour.
        db: Database session.

    Returns:
        A JSON-serialisable dict; the same tour and data give the same dict.
    """
    start = _local_start(activity)
    cells = coverage_crud.new_cells_of_activity(activity.user_id, activity.id, summary_progress.NEW_CELL_ZOOM, db)
    return {
        "tour": {
            "name": activity.name,
            "type": activities_utils.set_activity_name_based_on_activity_type(activity.activity_type),
            "date": start.date().isoformat(),
            "weekday": start.strftime("%A"),
            "start_time_local": start.strftime("%H:%M"),
            "distance_km": round((activity.distance or 0) / 1000, 2),
            "total_seconds": _rounded(activity.total_elapsed_time),
            "recorded_seconds": _rounded(activity.total_timer_time),
            "elevation_gain_m": _rounded(activity.elevation_gain),
            "elevation_loss_m": _rounded(activity.elevation_loss),
            "average_heart_rate": _rounded(activity.average_hr),
            "max_heart_rate": _rounded(activity.max_hr),
        },
        "long_stops": _long_stops(activity.id, db),
        "segments": _segments(activity.id, db),
        "new_ground": None
        if cells is None or cells.cells == 0
        else {
            "map_cells_passed": cells.cells,
            "map_cells_never_visited_before": cells.new_cells,
            "cell_size_m": 300,
        },
        "year": _year_so_far(activity.user_id, start.date(), db),
    }
