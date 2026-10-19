"""Database lookups specific to Google Health imports."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

import activities.activity.models as activities_models


def activity_exists(googlehealth_activity_id: str, user_id: int, db: Session) -> bool:
    """True when the user already has an activity imported from this exercise."""
    stmt = select(activities_models.Activity.id).where(
        activities_models.Activity.user_id == user_id,
        activities_models.Activity.googlehealth_activity_id == googlehealth_activity_id,
    )
    return db.execute(stmt).first() is not None
