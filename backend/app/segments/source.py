"""Where an activity came from, so comparisons can say which numbers are comparable.

The source is how the activity got into Yamabiko, which is not the same as which
device measured it: a Strava archive can hold files from any watch or phone. It is
still the best available proxy, because heart rate and elevation come from different
sensors and corrections per source (barometer on the Fitbit, a terrain model on
Strava), while GPS time between two nodes is computed the same way for all sources.
"""

from __future__ import annotations

from typing import Any

SOURCE_GOOGLE_HEALTH = "google_health"
SOURCE_STRAVA = "strava"
SOURCE_GARMIN = "garmin"
SOURCE_OTHER = "other"

SOURCES = (SOURCE_GOOGLE_HEALTH, SOURCE_STRAVA, SOURCE_GARMIN, SOURCE_OTHER)

# Values Endurain and Yamabiko write to ``import_info["import_source"]``.
_IMPORT_SOURCE_GOOGLE_HEALTH = "google_health"
_IMPORT_SOURCE_STRAVA_BULK = "Strava bulk import"


def activity_source(
    googlehealth_activity_id: str | None,
    strava_activity_id: int | None,
    garminconnect_activity_id: int | None,
    import_info: dict[str, Any] | None,
) -> str:
    """The source of an activity: one of ``SOURCES``.

    Google Health comes first because its importer sets both the exercise id and
    ``import_source``. The Strava bulk import deliberately leaves ``strava_activity_id``
    empty (Endurain would think the activity is linked to Strava), so it is recognised
    by ``import_info`` instead. Everything else, such as a manual file upload, is
    ``other``: nothing is known about which device measured it.
    """
    import_source = import_info.get("import_source") if isinstance(import_info, dict) else None
    if googlehealth_activity_id or import_source == _IMPORT_SOURCE_GOOGLE_HEALTH:
        return SOURCE_GOOGLE_HEALTH
    if strava_activity_id or import_source == _IMPORT_SOURCE_STRAVA_BULK:
        return SOURCE_STRAVA
    if garminconnect_activity_id:
        return SOURCE_GARMIN
    return SOURCE_OTHER


def comparable_sources(a: str, b: str) -> bool:
    """Whether heart rate and elevation from two sources can be compared.

    Only the same known source qualifies. Two ``other`` activities may come from different
    devices, so they do not count.
    """
    return a == b and a != SOURCE_OTHER
