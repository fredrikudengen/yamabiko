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


class TestCellTours:
    def _a_cell_of(self, client, zoom=ZOOM) -> tuple[int, int]:
        return next(iter(_cells(client.get(f"/coverage?zoom={zoom}").json())))

    def test_lists_the_tours_that_passed_through_with_name_and_start(self, client, db, add_activity):
        activity_id = add_activity(build_route(ASCENT), name="Ulriken")
        service.refresh_activity_cells(activity_id, db)
        x, y = self._a_cell_of(client)

        body = client.get(f"/coverage/cells/{x}/{y}?zoom={ZOOM}").json()

        assert len(body) == 1
        assert body[0]["id"] == activity_id
        assert body[0]["name"] == "Ulriken"
        assert body[0]["start_time"].startswith("2026-10-14T07:00:00")

    def test_newest_tour_comes_first(self, client, db, add_activity):
        older = add_activity(build_route(ASCENT), day=0)
        newer = add_activity(build_route(ASCENT), day=5)
        for activity_id in (older, newer):
            service.refresh_activity_cells(activity_id, db)
        x, y = self._a_cell_of(client)

        body = client.get(f"/coverage/cells/{x}/{y}?zoom={ZOOM}").json()

        assert [tour["id"] for tour in body] == [newer, older]

    @pytest.mark.parametrize("zoom", [ZOOM, ZOOM - 1, ZOOM - 3, tiles.MIN_ZOOM])
    def test_every_cell_lists_as_many_tours_as_the_map_counts(self, client, db, add_activity, zoom):
        # Two routes that share the start, so some cells hold one tour and some two.
        service.refresh_activity_cells(add_activity(build_route(ASCENT)), db)
        service.refresh_activity_cells(add_activity(build_route([("walk", (0, 600))]), day=1), db)

        counts = _cells(client.get(f"/coverage?zoom={zoom}").json())

        assert 2 in counts.values()
        for (x, y), count in counts.items():
            assert len(client.get(f"/coverage/cells/{x}/{y}?zoom={zoom}").json()) == count

    def test_a_cell_nobody_walked_through_is_empty(self, client, db, add_activity):
        service.refresh_activity_cells(add_activity(build_route(ASCENT)), db)
        x, y = self._a_cell_of(client)

        assert client.get(f"/coverage/cells/{x + 50}/{y + 50}?zoom={ZOOM}").json() == []

    def test_another_users_tours_are_not_listed(self, client, db, add_activity, current_user):
        service.refresh_activity_cells(add_activity(build_route(ASCENT), user_id=8), db)
        current_user["id"] = 8
        x, y = self._a_cell_of(client)
        current_user["id"] = 7

        assert client.get(f"/coverage/cells/{x}/{y}?zoom={ZOOM}").json() == []

    @pytest.mark.parametrize(("x", "y", "zoom"), [(-1, 0, ZOOM), (0, 2**ZOOM, ZOOM), (2**8, 0, 8), (0, 0, 7)])
    def test_a_cell_off_the_grid_is_refused(self, client, x, y, zoom):
        assert client.get(f"/coverage/cells/{x}/{y}?zoom={zoom}").status_code == 422


class TestFirstVisit:
    def test_each_cell_carries_the_start_of_the_earliest_tour_through_it(self, client, db, add_activity):
        service.refresh_activity_cells(add_activity(build_route(ASCENT), day=3), db)
        service.refresh_activity_cells(add_activity(build_route([("walk", (0, 600))]), day=1), db)

        body = client.get(f"/coverage?zoom={ZOOM}").json()
        first = {(cell["x"], cell["y"]): cell["first_visit"][:10] for cell in body["cells"]}
        short = service.cells_of_track(build_route([("walk", (0, 600))]).points, ZOOM)

        assert {first[key] for key in short} == {"2026-10-15"}
        assert {first[key] for key in set(first) - short} == {"2026-10-17"}


LONGER = [("walk", (0, 1800)), ("walk", (0, 3600))]


class TestActivityCells:
    def _get(self, client, activity_id, zoom=ZOOM):
        return client.get(f"/coverage/activities/{activity_id}?zoom={zoom}")

    def test_the_first_tour_is_first_in_every_cell(self, client, db, add_activity):
        activity_id = add_activity(build_route(ASCENT))
        service.refresh_activity_cells(activity_id, db)

        body = self._get(client, activity_id).json()

        assert body["zoom"] == ZOOM
        assert body["cells"] == len(service.cells_of_track(build_route(ASCENT).points, ZOOM))
        assert body["new_cells"] == body["cells"]

    def test_walking_the_same_way_again_finds_nothing_new(self, client, db, add_activity):
        service.refresh_activity_cells(add_activity(build_route(ASCENT), day=0), db)
        again = add_activity(build_route(ASCENT), day=1)
        service.refresh_activity_cells(again, db)

        assert self._get(client, again).json()["new_cells"] == 0

    @pytest.mark.parametrize("zoom", [ZOOM, ZOOM - 1, ZOOM - 3])
    def test_going_further_counts_only_the_cells_beyond(self, client, db, add_activity, zoom):
        service.refresh_activity_cells(add_activity(build_route(ASCENT), day=0), db)
        further = add_activity(build_route(LONGER), day=1)
        service.refresh_activity_cells(further, db)

        long_cells = service.cells_of_track(build_route(LONGER).points, zoom)
        short_cells = service.cells_of_track(build_route(ASCENT).points, zoom)
        body = self._get(client, further, zoom).json()

        assert body["cells"] == len(long_cells)
        assert body["new_cells"] == len(long_cells - short_cells)
        assert 0 < body["new_cells"] < body["cells"]

    def test_earlier_is_by_start_time_not_by_when_it_was_imported(self, client, db, add_activity):
        later = add_activity(build_route(ASCENT), day=5)
        earlier = add_activity(build_route(ASCENT), day=1)
        for activity_id in (later, earlier):
            service.refresh_activity_cells(activity_id, db)

        assert self._get(client, later).json()["new_cells"] == 0
        assert self._get(client, earlier).json()["new_cells"] > 0

    def test_of_two_tours_starting_together_the_first_stored_gets_the_cells(self, client, db, add_activity):
        first = add_activity(build_route(ASCENT))
        second = add_activity(build_route(ASCENT))
        for activity_id in (first, second):
            service.refresh_activity_cells(activity_id, db)

        assert self._get(client, first).json()["new_cells"] > 0
        assert self._get(client, second).json()["new_cells"] == 0

    def test_another_users_earlier_tour_takes_nothing_away(self, client, db, add_activity):
        service.refresh_activity_cells(add_activity(build_route(ASCENT), user_id=8, day=0), db)
        mine = add_activity(build_route(ASCENT), day=1)
        service.refresh_activity_cells(mine, db)

        body = self._get(client, mine).json()

        assert body["new_cells"] == body["cells"] > 0

    def test_a_tour_without_gps_has_no_cells(self, client, db, add_activity):
        activity_id = add_activity(None)

        assert self._get(client, activity_id).json() == {"zoom": ZOOM, "cells": 0, "new_cells": 0}

    def test_another_users_tour_is_not_found(self, client, db, add_activity):
        theirs = add_activity(build_route(ASCENT), user_id=8)
        service.refresh_activity_cells(theirs, db)

        assert self._get(client, theirs).status_code == 404
        assert self._get(client, 9999).status_code == 404

    def test_a_zoom_outside_the_grid_is_refused(self, client, db, add_activity):
        activity_id = add_activity(build_route(ASCENT))

        assert self._get(client, activity_id, zoom=ZOOM + 1).status_code == 422
