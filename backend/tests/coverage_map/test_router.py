"""Tests for the coverage API: real routes on a FastAPI app, real SQLite, login faked."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth.dependencies as auth_dependencies
import core.database as core_database
import coverage_map.router as router
import coverage_map.service as service
import coverage_map.tiles as tiles
from tests._helpers.segments import build_route

ZOOM = tiles.STORE_ZOOM
ASCENT = [("walk", (0, 1800))]


@pytest.fixture
def client(db, current_user):
    app = FastAPI()
    app.include_router(router.router, prefix="/coverage")
    app.dependency_overrides[core_database.get_db] = lambda: db
    app.dependency_overrides[auth_dependencies.validate_access_token] = lambda: None
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: current_user["id"]
    return TestClient(app)


def _cells(body) -> dict[tuple[int, int], int]:
    return {(cell["x"], cell["y"]): cell["count"] for cell in body["cells"]}


class TestGetCoverage:
    def test_an_empty_map_answers_with_no_cells(self, client):
        body = client.get("/coverage").json()

        assert body["cells"] == []
        assert body["max_count"] == 0

    def test_the_default_zoom_is_one_step_coarser_than_the_stored_grid(self, client):
        assert client.get("/coverage").json()["zoom"] == ZOOM - 1

    def test_a_walk_shows_up_as_cells_passed_once(self, client, db, add_activity):
        activity_id = add_activity(build_route(ASCENT))
        service.refresh_activity_cells(activity_id, db)

        body = client.get(f"/coverage?zoom={ZOOM}").json()

        assert set(_cells(body)) == service.cells_of_track(build_route(ASCENT).points, ZOOM)
        assert set(_cells(body).values()) == {1}
        assert body["max_count"] == 1

    def test_walking_the_same_route_twice_counts_two(self, client, db, add_activity):
        for day in (0, 1):
            service.refresh_activity_cells(add_activity(build_route(ASCENT), day=day), db)

        body = client.get(f"/coverage?zoom={ZOOM}").json()

        assert set(_cells(body).values()) == {2}
        assert body["max_count"] == 2

    def test_one_tour_counts_once_per_cell_however_long_it_lingered(self, client, db, add_activity):
        # Half an hour standing still inside one cell is still one tour there.
        service.refresh_activity_cells(add_activity(build_route([("rest", 1800)])), db)

        assert set(_cells(client.get(f"/coverage?zoom={ZOOM}").json()).values()) == {1}

    def test_a_coarse_cell_counts_a_tour_once_even_when_it_holds_four_of_its_cells(self, client, db, add_activity):
        service.refresh_activity_cells(add_activity(build_route(ASCENT)), db)

        coarse = _cells(client.get(f"/coverage?zoom={ZOOM - 2}").json())

        assert coarse
        assert set(coarse.values()) == {1}

    def test_rolling_up_gathers_the_fine_cells_into_the_coarse_ones(self, client, db, add_activity):
        service.refresh_activity_cells(add_activity(build_route(ASCENT)), db)

        fine = _cells(client.get(f"/coverage?zoom={ZOOM}").json())
        coarse = _cells(client.get(f"/coverage?zoom={ZOOM - 1}").json())

        assert {tiles.roll_up(x, y, ZOOM, ZOOM - 1) for x, y in fine} == set(coarse)
        assert len(coarse) < len(fine)

    def test_another_users_walks_are_not_on_my_map(self, client, db, add_activity, current_user):
        service.refresh_activity_cells(add_activity(build_route(ASCENT), user_id=8), db)

        assert client.get("/coverage").json()["cells"] == []

        current_user["id"] = 8
        assert client.get("/coverage").json()["cells"]

    @pytest.mark.parametrize("zoom", [tiles.MIN_ZOOM - 1, tiles.MAX_ZOOM + 1, 0])
    def test_a_zoom_outside_the_grid_is_refused(self, client, zoom):
        assert client.get(f"/coverage?zoom={zoom}").status_code == 422


class TestRefresh:
    def test_the_rebuild_fills_the_map_from_activities_that_were_never_hooked(self, client, db, add_activity):
        add_activity(build_route(ASCENT), import_info={"import_source": "Strava bulk import"})
        assert client.get("/coverage").json()["cells"] == []

        body = client.post("/coverage/refresh").json()

        assert body["activities"] == 1
        assert body["cells"] > 0
        assert client.get("/coverage").json()["cells"]

    def test_running_the_rebuild_twice_does_not_double_the_counts(self, client, db, add_activity):
        add_activity(build_route(ASCENT))
        client.post("/coverage/refresh")

        client.post("/coverage/refresh")

        assert client.get(f"/coverage?zoom={ZOOM}").json()["max_count"] == 1

    def test_the_rebuild_leaves_another_users_activities_alone(self, client, db, add_activity):
        add_activity(build_route(ASCENT), user_id=8)

        assert client.post("/coverage/refresh").json() == {"activities": 0, "cells": 0}
