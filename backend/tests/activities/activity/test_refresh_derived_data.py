"""Every importer stores through store_activity, which adds segment times and map cells."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from tests._helpers.db import create_sqlite_session
from tests._helpers.segments import build_route, node

import activities.activity.models as activities_models
import activities.activity.utils as activities_utils
import activities.activity_streams.constants as streams_constants
import activities.activity_streams.models as streams_models
import coverage_map.models as coverage_models
import segments.crud as segments_crud

USER = 7
T0 = datetime(2026, 10, 14, 7, 0, 0, tzinfo=UTC)


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


def _add_walk(db, user_id=USER) -> int:
    """An activity with only a GPS stream, the way a Strava export file leaves one."""
    activity = activities_models.Activity(
        user_id=user_id,
        name="Ulriken",
        distance=1800,
        activity_type=12,
        start_time=T0,
        end_time=T0 + timedelta(hours=1),
        total_elapsed_time=3600,
        total_timer_time=3600,
        created_at=T0,
        import_info={"import_source": "Strava bulk import"},
        **{c.name: False for c in activities_models.Activity.__table__.columns if c.name.startswith("hide_")},
    )
    db.add(activity)
    db.flush()
    route = build_route([("walk", (0, 1800))])
    db.add(
        streams_models.ActivityStreams(
            activity_id=activity.id,
            stream_type=streams_constants.STREAM_TYPE_MAP,
            stream_waypoints=[
                {"time": (T0 + timedelta(seconds=p.t)).strftime("%Y-%m-%dT%H:%M:%S"), "lat": p.lat, "lon": p.lon}
                for p in route.points
            ],
        )
    )
    db.commit()
    return activity.id


class TestRefreshDerivedData:
    def test_a_stored_activity_gets_its_segment_time_and_its_map_cells(self, db):
        segment = segments_crud.create_segment(USER, "Fjellet", node(0, 0), node(0, 1800), db)
        activity_id = _add_walk(db)

        activities_utils.refresh_derived_data(SimpleNamespace(id=activity_id, user_id=USER), db)

        assert [e.activity_id for e in segments_crud.get_efforts_for_segment(segment.id, db)] == [activity_id]
        cells = db.scalars(
            select(coverage_models.ActivityCell).where(coverage_models.ActivityCell.activity_id == activity_id)
        ).all()
        assert cells

    def test_another_users_segment_is_not_matched(self, db):
        segment = segments_crud.create_segment(8, "Fjellet", node(0, 0), node(0, 1800), db)
        activity_id = _add_walk(db)

        activities_utils.refresh_derived_data(SimpleNamespace(id=activity_id, user_id=USER), db)

        assert segments_crud.get_efforts_for_segment(segment.id, db) == []

    def test_an_activity_without_an_owner_is_left_alone(self):
        with (
            patch("segments.service.refresh_efforts_after_import") as efforts,
            patch("coverage_map.service.refresh_cells_after_import") as cells,
        ):
            activities_utils.refresh_derived_data(SimpleNamespace(id=1, user_id=None), MagicMock())

        efforts.assert_not_called()
        cells.assert_not_called()


class TestStoreActivityRefreshes:
    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.parse_activity_streams_from_file", return_value=None)
    def test_store_activity_hands_the_new_activity_to_both(self, _streams, crud):
        stored = SimpleNamespace(id=5, user_id=USER)
        crud.create_activity = AsyncMock(return_value=stored)
        db = MagicMock()

        with (
            patch("segments.service.refresh_efforts_after_import") as efforts,
            patch("coverage_map.service.refresh_cells_after_import") as cells,
        ):
            asyncio.run(activities_utils.store_activity({"activity": {}}, MagicMock(), db))

        efforts.assert_called_once_with([stored], USER, db)
        cells.assert_called_once_with([stored], USER, db)

    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.parse_activity_streams_from_file", return_value=None)
    def test_a_failure_in_either_does_not_undo_the_import(self, _streams, crud):
        stored = SimpleNamespace(id=5, user_id=USER)
        crud.create_activity = AsyncMock(return_value=stored)

        with patch("segments.service.refresh_activity_efforts", side_effect=RuntimeError("broken stream")):
            result = asyncio.run(activities_utils.store_activity({"activity": {}}, MagicMock(), MagicMock()))

        assert result is stored
