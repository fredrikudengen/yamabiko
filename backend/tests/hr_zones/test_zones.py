"""Tests for the heart-rate zone limits: the rules, the time in zones, and the API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth.dependencies as auth_dependencies
import core.database as core_database
import hr_zones.router as router
import hr_zones.zones as zones
import users.users.models as users_models
from tests._helpers.db import create_sqlite_session
from tests._helpers.users import make_user

LIMITS = [100, 120, 140, 160]


class TestRules:
    @pytest.mark.parametrize("limits", [[100, 120, 140, 160], (30, 31, 32, 250)])
    def test_four_increasing_whole_numbers_in_range_are_valid(self, limits):
        assert zones.is_valid(limits)

    @pytest.mark.parametrize(
        "limits",
        [
            None,
            [],
            [100, 120, 140],
            [100, 120, 140, 160, 180],
            [100, 100, 140, 160],
            [29, 120, 140, 160],
            [100, 120, 140, 251],
            [100.5, 120, 140, 160],
            [True, 120, 140, 160],
            "100,120,140,160",
        ],
    )
    def test_anything_else_is_not(self, limits):
        assert not zones.is_valid(limits)

    def test_invalid_or_missing_limits_fall_back_to_the_defaults(self):
        assert zones.limits_of(None) == zones.DEFAULT_LIMITS
        assert zones.limits_of([1, 2, 3]) == zones.DEFAULT_LIMITS
        assert zones.limits_of(LIMITS) == tuple(LIMITS)

    @pytest.mark.parametrize(("bpm", "zone"), [(99, 1), (100, 2), (139, 3), (140, 4), (160, 5), (200, 5)])
    def test_a_limit_starts_the_next_zone(self, bpm, zone):
        assert zones.zone_of(bpm, LIMITS) == zone


class TestZoneSeconds:
    def test_each_step_goes_to_the_zone_of_its_first_sample(self):
        samples = [(0, 110), (10, 110), (20, 150), (30, 150)]

        result = zones.zone_seconds(samples, LIMITS)

        assert result.seconds == (0, 20, 0, 10, 0)
        assert result.counted_s == 30

    def test_long_stops_are_left_out(self):
        samples = [(t, 110) for t in range(0, 101, 10)]

        result = zones.zone_seconds(samples, LIMITS, stops=[(20, 40)])

        assert result.seconds[1] == 60

    def test_a_step_longer_than_the_gap_limit_is_not_counted(self):
        result = zones.zone_seconds([(0, 110), (10, 110), (200, 110)], LIMITS)

        assert result.counted_s == 10

    def test_zero_readings_are_dropouts(self):
        result = zones.zone_seconds([(0, 110), (10, 0), (20, 110)], LIMITS)

        assert result.counted_s == 20


@pytest.fixture
def db():
    session = create_sqlite_session()
    session.add(make_user())
    session.commit()
    yield session
    session.close()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(router.router, prefix="/profile/hr_zones")
    app.dependency_overrides[core_database.get_db] = lambda: db
    app.dependency_overrides[auth_dependencies.validate_access_token] = lambda: None
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: 7
    return TestClient(app)


class TestApi:
    def test_a_new_user_has_the_defaults(self, client):
        assert client.get("/profile/hr_zones").json() == {"limits": list(zones.DEFAULT_LIMITS), "is_default": True}

    def test_limits_are_stored_and_read_back(self, client, db):
        body = client.put("/profile/hr_zones", json={"limits": LIMITS}).json()

        assert body == {"limits": LIMITS, "is_default": False}
        assert client.get("/profile/hr_zones").json() == body
        assert db.get(users_models.Users, 7).hr_zone_limits == LIMITS

    def test_null_goes_back_to_the_defaults(self, client, db):
        client.put("/profile/hr_zones", json={"limits": LIMITS})

        body = client.put("/profile/hr_zones", json={"limits": None}).json()

        assert body["is_default"] is True
        assert db.get(users_models.Users, 7).hr_zone_limits is None

    def test_invalid_limits_are_refused_and_nothing_changes(self, client, db):
        client.put("/profile/hr_zones", json={"limits": LIMITS})

        assert client.put("/profile/hr_zones", json={"limits": [100, 90, 140, 160]}).status_code == 422
        assert db.get(users_models.Users, 7).hr_zone_limits == LIMITS
