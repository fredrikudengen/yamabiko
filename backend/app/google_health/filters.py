"""Which Google Health exercises should be imported.

Only actively measured sessions with a GPS track are imported:

- Passively measured sessions (the band detects a walk on its own) have no
  GPS; distance is steps x a fixed stride and elevation is whole floors.
- Copies written by other apps (for example Strava via Apple Health) have an
  empty ``exerciseMetadata`` and would duplicate the original.
- A session without a STOP event is still being recorded (the record is
  created a few minutes after the start and updated after the end).
"""

from __future__ import annotations

ACTIVELY_MEASURED = "ACTIVELY_MEASURED"
STOP_EVENT = "STOP"


def exercise_id(data_point: dict) -> str | None:
    """The id part of ``users/<user>/dataTypes/exercise/dataPoints/<id>``."""
    name = data_point.get("name")
    if not isinstance(name, str) or "/" not in name:
        return None
    return name.rsplit("/", 1)[1] or None


def skip_reason(data_point: dict) -> str | None:
    """Why a data point should not be imported, or None if it should be."""
    if exercise_id(data_point) is None:
        return "no id"
    if data_point.get("dataSource", {}).get("recordingMethod") != ACTIVELY_MEASURED:
        return "not actively measured"
    exercise = data_point.get("exercise") or {}
    # ``hasGps`` is absent on passive sessions and on copies from other apps.
    if not (exercise.get("exerciseMetadata") or {}).get("hasGps", False):
        return "no GPS"
    events = exercise.get("exerciseEvents") or []
    if not any(event.get("exerciseEventType") == STOP_EVENT for event in events):
        return "not finished (no STOP event)"
    return None


def is_importable(data_point: dict) -> bool:
    """True when the data point passes every import filter."""
    return skip_reason(data_point) is None
