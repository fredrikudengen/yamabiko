"""What the model is told about a tour: computed numbers only.

The facts are the app's own results — times, standings, new ground — never the
raw GPS or heart-rate streams, and never coordinates. The model can then word
the numbers but has none of its own to invent. Names of the tour and of its
segments are included; they are the only thing that says where the tour was.

Every value is rounded the way the interface shows it, so the same tour gives
the same facts, and the same hash, each time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
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
        # Given outright: left to subtract, the model can misread how the gap grew.
        "lost_in_first_half_seconds": round(behind[segments_profile.PROFILE_STEPS // 2]),
        "lost_in_second_half_seconds": round(behind[-1] - behind[segments_profile.PROFILE_STEPS // 2]),
        "most_time_lost": _stretch(behind, 1),
        "most_time_won": _stretch(behind, -1),
    }


# Below this net climb a segment is too flat for "beats per 100 m climbed" to mean anything
# (the same threshold as the segment table's column).
MIN_NET_CLIMB_M = 20

# How many earlier passes of a segment the model sees.
EARLIER_PASSES = 5


def _beats_per_100m(effort: segments_models.SegmentEffort) -> int | None:
    """Heart beats spent per 100 m climbed: lower is fitter, at a comparable effort.

    Only comparable between passes measured by the same kind of device (source).
    """
    climb = effort.net_elevation_m
    if climb is None or climb < MIN_NET_CLIMB_M or not effort.average_hr or effort.moving_s <= 0:
        return None
    return round(effort.average_hr * effort.moving_s / 60 / climb * 100)


def _segments(activity_id: int, db: Session) -> list[dict[str, Any]]:
    """The segments the tour passed, as they stood on the day it was walked.

    Passes walked later are left out of the rank, the record and the comparison,
    so a text written for an old tour says what was true that day.
    """
    facts: list[dict[str, Any]] = []
    for effort in segments_crud.get_efforts_for_activity(activity_id, db):
        segment = effort.segment
        upto = [
            other
            for other in segments_crud.get_efforts_for_segment(segment.id, db)
            if (other.start_time, other.id) <= (effort.start_time, effort.id)
        ]
        earlier = [other for other in upto if other.id != effort.id]
        sources = segments_service.activity_sources([other.activity_id for other in upto], db)
        standing = segments_ranking.rank_efforts(upto)[effort.id]
        best = min(upto, key=lambda other: (round(other.moving_s), other.id))
        same_year = [other for other in upto if other.start_time.year == effort.start_time.year]
        fact: dict[str, Any] = {
            "name": segment.name,
            "moving_seconds": round(effort.moving_s),
            "long_stops_seconds": round(effort.stopped_s),
            "net_climb_m": _rounded(effort.net_elevation_m),
            "average_heart_rate": _rounded(effort.average_hr),
            "beats_per_100m_climbed": _beats_per_100m(effort),
            "passes_so_far_including_this": standing.count,
            "rank_by_moving_time_on_the_day": standing.rank_moving if standing.count > 1 else None,
            "was_personal_record_on_the_day": standing.count > 1 and standing.rank_moving == 1,
            "fastest_this_year": len(same_year) > 1
            and min(same_year, key=lambda other: (round(other.moving_s), other.id)).id == effort.id,
            "days_since_previous_pass": (effort.start_time.date() - earlier[-1].start_time.date()).days
            if earlier
            else None,
            # Reasons the time may be off: gps_gap, start_edge, end_edge (see segments.quality).
            "time_uncertain_because": segments_quality.effort_doubts(effort),
            "earlier_passes_newest_first": [
                {
                    "date": other.start_time.date().isoformat(),
                    "moving_seconds": round(other.moving_s),
                    # Only beside a pass measured the same way: across sources the counts
                    # cannot be compared, and a number that must not be used invites comment.
                    "beats_per_100m_climbed": _beats_per_100m(other)
                    if sources.get(other.activity_id) == sources.get(effort.activity_id)
                    else None,
                    "time_uncertain": bool(segments_quality.effort_doubts(other)),
                }
                for other in reversed(earlier[-EARLIER_PASSES:])
            ],
        }
        if standing.count > 1 and best.id != effort.id:
            fact["against_fastest_pass_so_far"] = _against_best(segment, effort, best, db)
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


def _year(user_id: int, day: date, db: Session) -> dict[str, Any]:
    """The year through the tour's day against last year, and what this tour pushed past.

    ``milestones`` names the round numbers this day crossed and last year's
    totals it overtook; the model mentions the year only when there is one.
    """
    days = summary_progress.daily_progress(user_id, None, db)

    def totals(year: int, until: date) -> dict[str, float]:
        chosen = [d for d in days if d.day.year == year and d.day <= until]
        return {
            "tours": sum(d.activity_count for d in chosen),
            "distance_km": round(sum(d.distance for d in chosen) / 1000, 1),
            "elevation_gain_m": round(sum(d.elevation_gain for d in chosen)),
            "new_map_cells": sum(d.new_cells for d in chosen),
        }

    try:
        same_day_last_year = day.replace(year=day.year - 1)
    except ValueError:  # 29 February
        same_day_last_year = date(day.year - 1, 2, 28)
    now = totals(day.year, day)
    before = totals(day.year, day - timedelta(days=1))
    last_year_by_now = totals(day.year - 1, same_day_last_year)
    last_year_whole = totals(day.year - 1, date(day.year - 1, 12, 31))

    milestones: list[str] = []
    steps = {"tours": 10, "distance_km": 100, "elevation_gain_m": 5000}
    for key, step in steps.items():
        if now[key] // step > before[key] // step:
            milestones.append(f"passed {int(now[key] // step * step)} {key} this year")
        if last_year_whole[key] and before[key] <= last_year_whole[key] < now[key]:
            milestones.append(f"overtook last year's full-year {key} ({last_year_whole[key]})")
    return {
        "year": day.year,
        "this_year_through_this_tour": now,
        "last_year_by_same_date": last_year_by_now,
        "last_year_whole": last_year_whole,
        "milestones": milestones,
    }


def _tour_context(activity: activities_models.Activity, db: Session) -> dict[str, Any]:
    """Where the tour stands among the user's own tours, and how long since the last one."""
    model = activities_models.Activity
    earlier = db.execute(
        select(model.start_time)
        .where(model.user_id == activity.user_id, model.start_time < activity.start_time)
        .order_by(model.start_time.desc())
        .limit(1)
    ).scalar_one_or_none()
    year_start = datetime(activity.start_time.year, 1, 1, tzinfo=UTC)
    this_year = db.execute(
        select(model.id, model.distance, model.elevation_gain).where(
            model.user_id == activity.user_id,
            model.activity_type == activity.activity_type,
            model.start_time >= year_start,
            model.start_time <= activity.start_time,
        )
    ).all()

    def rank(key: str) -> int | None:
        mine = getattr(activity, key)
        if mine is None:
            return None
        return 1 + sum(1 for row in this_year if (getattr(row, key) or 0) > mine)

    def days_between(a: datetime, b: datetime) -> int:
        """Calendar days, so a tour yesterday evening is one day ago, whatever the hour."""
        return (a.date() - b.date()).days

    return {
        "days_since_previous_tour": days_between(activity.start_time, earlier) if earlier else None,
        "same_type_tours_this_year_so_far": len(this_year),
        "rank_this_year_by_distance": rank("distance"),
        "rank_this_year_by_elevation_gain": rank("elevation_gain"),
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
        "compared_with_your_other_tours": _tour_context(activity, db),
        "long_stops": _long_stops(activity.id, db),
        "segments": _segments(activity.id, db),
        "new_ground": None
        if cells is None or cells.cells == 0
        else {
            "squares_of_about_300m_passed": cells.cells,
            "of_them_never_visited_before": cells.new_cells,
        },
        "year": _year(activity.user_id, start.date(), db),
    }
