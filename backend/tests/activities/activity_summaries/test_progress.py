"""Tests for the day-by-day totals behind the year-over-year chart: real routes, real SQLite."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests._helpers.db import create_sqlite_session

import activities.activity.models as activities_models
import activities.activity_summaries.router as router
import auth.dependencies as auth_dependencies
import core.database as core_database
import coverage_map.models as coverage_models
import coverage_map.tiles as tiles

HIKE = 12
RUN = 1


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(router.router, prefix="/activities_summaries")
    app.dependency_overrides[core_database.get_db] = lambda: db
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: 7
    return TestClient(app)


@pytest.fixture
def add_tour(db):
    """Store a tour on a day, with the stored cells it passed through."""

    def _add(start, cells=(), user_id=7, activity_type=HIKE, distance=5000, climb=300, seconds=7200) -> int:
        activity = activities_models.Activity(
            user_id=user_id,
            name="Tur",
            distance=distance,
            activity_type=activity_type,
            start_time=start,
            end_time=start + timedelta(seconds=seconds),
            total_elapsed_time=seconds,
            total_timer_time=seconds,
            elevation_gain=climb,
            created_at=start,
            **{c.name: False for c in activities_models.Activity.__table__.columns if c.name.startswith("hide_")},
        )
        db.add(activity)
        db.flush()
        for x, y in cells:
            db.add(
                coverage_models.ActivityCell(activity_id=activity.id, cell_x=x, cell_y=y, grid_zoom=tiles.STORE_ZOOM)
            )
        db.commit()
        return activity.id

    return _add


def at(day: str, hour: int = 9) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hour, tzinfo=UTC)


def _days(client, query=""):
    return {row["day"]: row for row in client.get(f"/activities_summaries/progress/days{query}").json()}


def test_no_tours_gives_no_days(client):
    assert client.get("/activities_summaries/progress/days").json() == []


def test_two_tours_on_one_day_are_added_up(client, add_tour):
    add_tour(at("2026-03-14", 8), distance=4000, climb=200, seconds=3600)
    add_tour(at("2026-03-14", 15), distance=6000, climb=500, seconds=5400)

    day = _days(client)["2026-03-14"]

    assert day["distance"] == 10_000
    assert day["elevation_gain"] == 700
    assert day["duration"] == 9000
    assert day["activity_count"] == 2


def test_days_come_oldest_first_and_span_years(client, add_tour):
    add_tour(at("2026-01-02"))
    add_tour(at("2024-07-01"))
    add_tour(at("2025-12-31"))

    rows = client.get("/activities_summaries/progress/days").json()

    assert [row["day"] for row in rows] == ["2024-07-01", "2025-12-31", "2026-01-02"]


def test_a_cell_is_new_only_on_the_day_of_its_first_tour(client, add_tour):
    # Stored cells (2, 2) and (3, 3) roll up into the same map cell (1, 1); (8, 8) is a cell of its own.
    add_tour(at("2025-05-01"), cells=[(2, 2)])
    add_tour(at("2026-03-14"), cells=[(3, 3), (8, 8)])
    add_tour(at("2026-04-01"), cells=[(2, 2), (8, 8)])

    days = _days(client)

    assert days["2025-05-01"]["new_cells"] == 1
    assert days["2026-03-14"]["new_cells"] == 1
    assert days["2026-04-01"]["new_cells"] == 0


def test_the_type_filter_narrows_the_totals_and_what_counts_as_first(client, add_tour):
    add_tour(at("2025-05-01"), cells=[(2, 2)], activity_type=RUN, distance=10_000)
    add_tour(at("2026-03-14"), cells=[(2, 2)], activity_type=HIKE, distance=5000)

    every = _days(client)
    hikes = _days(client, f"?type={HIKE}")

    assert every["2026-03-14"]["new_cells"] == 0
    assert set(hikes) == {"2026-03-14"}
    assert hikes["2026-03-14"]["distance"] == 5000
    assert hikes["2026-03-14"]["new_cells"] == 1


def test_another_users_tours_are_left_out(client, add_tour):
    add_tour(at("2025-05-01"), cells=[(2, 2)], user_id=8)
    add_tour(at("2026-03-14"), cells=[(2, 2)])

    days = _days(client)

    assert set(days) == {"2026-03-14"}
    assert days["2026-03-14"]["new_cells"] == 1
