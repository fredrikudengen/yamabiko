"""A real SQLite database with activities and their GPS streams, for the coverage tests."""

from datetime import UTC, datetime, timedelta

import pytest

import activities.activity.models as activities_models
import activities.activity_streams.constants as streams_constants
import activities.activity_streams.models as streams_models
from tests._helpers.db import create_sqlite_session

T0 = datetime(2026, 10, 14, 7, 0, 0, tzinfo=UTC)


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


@pytest.fixture
def current_user():
    """Mutable: ``current_user["id"] = 8`` switches who is logged in."""
    return {"id": 7}


@pytest.fixture
def add_activity(db):
    """Store an activity with the route's streams. Pass ``None`` for an activity without GPS."""

    def _add(route, user_id=7, day=0, name="Fjelltur", **fields) -> int:
        start = T0 + timedelta(days=day)
        activity = activities_models.Activity(
            user_id=user_id,
            name=name,
            distance=1700,
            activity_type=12,
            start_time=start,
            end_time=start + timedelta(hours=1),
            total_elapsed_time=3600,
            total_timer_time=3600,
            created_at=start,
            **{c.name: False for c in activities_models.Activity.__table__.columns if c.name.startswith("hide_")},
            **fields,
        )
        db.add(activity)
        db.flush()
        if route is not None:

            def stamp(t):
                return (start + timedelta(seconds=t)).strftime("%Y-%m-%dT%H:%M:%S")

            db.add(
                streams_models.ActivityStreams(
                    activity_id=activity.id,
                    stream_type=streams_constants.STREAM_TYPE_MAP,
                    stream_waypoints=[{"time": stamp(p.t), "lat": p.lat, "lon": p.lon} for p in route.points],
                )
            )
        db.commit()
        return activity.id

    return _add
