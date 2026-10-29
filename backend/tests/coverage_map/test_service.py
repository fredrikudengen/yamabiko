"""Turning a track into cells: what counts as having been somewhere, and what does not."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import coverage_map.models as models
import coverage_map.service as service
import coverage_map.tiles as tiles
import google_health.stops as google_health_stops
from tests._helpers.segments import LAT0, LON0, build_route, latlon

ZOOM = tiles.STORE_ZOOM


def point(t: float, x: float, y: float) -> google_health_stops.TrackPoint:
    """A GPS point ``x`` metres east and ``y`` metres north of the test origin."""
    lat, lon = latlon(x, y)
    return google_health_stops.TrackPoint(t, lat, lon)


def cell_of(x: float, y: float) -> tuple[int, int]:
    return tiles.tile_xy(*latlon(x, y), ZOOM)


def _is_connected(cells: set[tuple[int, int]]) -> bool:
    """Whether the cells form one unbroken run, counting corners as touching."""
    if not cells:
        return True
    start = next(iter(cells))
    seen, queue = {start}, [start]
    while queue:
        x, y = queue.pop()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neighbour = (x + dx, y + dy)
                if neighbour in cells and neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
    return seen == cells


class TestCellsOfTrack:
    def test_a_track_that_goes_nowhere_covers_one_cell(self):
        points = [point(t, 0.0, 0.0) for t in range(5)]

        assert service.cells_of_track(points, ZOOM) == {cell_of(0, 0)}

    def test_an_empty_track_covers_nothing(self):
        assert service.cells_of_track([], ZOOM) == set()

    def test_standing_still_for_an_hour_counts_the_same_as_walking_past(self):
        passing = [point(t, 0.0, 0.0) for t in range(2)]
        summit_stop = [point(t, 0.0, 0.0) for t in range(3600)]

        assert service.cells_of_track(summit_stop, ZOOM) == service.cells_of_track(passing, ZOOM)

    def test_every_point_brings_its_own_cell(self):
        far = 5_000.0
        points = [point(0, 0.0, 0.0), point(10_000, far, 0.0)]

        cells = service.cells_of_track(points, ZOOM)

        assert cell_of(0, 0) in cells
        assert cell_of(far, 0) in cells

    def test_a_cell_crossed_between_two_points_counts_too(self):
        # Two points 600 m apart, far more than a 151 m cell: the cells in
        # between were walked through even though no point landed in them.
        points = [point(0, 0.0, 0.0), point(20, 600.0, 0.0)]

        cells = service.cells_of_track(points, ZOOM)

        assert len(cells) >= 4
        assert cell_of(300, 0) in cells

    def test_the_line_is_not_drawn_across_a_lost_signal(self):
        # The same two points, but half a minute later: the watch lost its fix
        # and where the walk actually went is unknown.
        points = [point(0, 0.0, 0.0), point(20 + service.GAP_THRESHOLD_S, 600.0, 0.0)]

        cells = service.cells_of_track(points, ZOOM)

        assert cells == {cell_of(0, 0), cell_of(600, 0)}

    def test_a_gap_exactly_at_the_threshold_is_still_joined(self):
        points = [point(0, 0.0, 0.0), point(service.GAP_THRESHOLD_S, 600.0, 0.0)]

        assert len(service.cells_of_track(points, ZOOM)) >= 4

    def test_a_diagonal_line_leaves_no_hole_behind(self):
        points = [point(0, 0.0, 0.0), point(25, 900.0, 900.0)]

        cells = service.cells_of_track(points, ZOOM)

        assert len(cells) >= 6
        assert _is_connected(cells)

    def test_a_corrupt_coordinate_keeps_both_ends_without_painting_the_world(self):
        points = [point(0, 0.0, 0.0), google_health_stops.TrackPoint(1.0, -33.9, 151.2)]

        cells = service.cells_of_track(points, ZOOM)

        assert len(cells) == 2
        assert cell_of(0, 0) in cells

    def test_a_coarser_grid_gathers_the_same_walk_into_fewer_cells(self):
        route = build_route([("walk", (0, 1800))])

        fine = service.cells_of_track(route.points, ZOOM)
        coarse = service.cells_of_track(route.points, ZOOM - 2)

        assert 0 < len(coarse) < len(fine)

    def test_counting_a_fine_track_and_rolling_it_up_gives_the_coarse_cells(self):
        route = build_route([("walk", (0, 1800)), ("rest", 300), ("walk", (900, 1800))])

        rolled = {tiles.roll_up(x, y, ZOOM, ZOOM - 1) for x, y in service.cells_of_track(route.points, ZOOM)}

        assert rolled == service.cells_of_track(route.points, ZOOM - 1)

    def test_a_walk_up_the_mountain_covers_roughly_its_length_in_cells(self):
        # 1800 m north in a straight line, cells about 151 m: a dozen or so.
        route = build_route([("walk", (0, 1800))], start=(0.0, 0.0))

        cells = service.cells_of_track(route.points, ZOOM)

        assert 10 <= len(cells) <= 16
        assert _is_connected(cells)

    def test_the_cells_are_where_the_walk_was(self):
        route = build_route([("walk", (0, 1800))], start=(0.0, 0.0))

        for x, y in service.cells_of_track(route.points, ZOOM):
            south, west, north, east = tiles.cell_bounds(x, y, ZOOM)
            assert west < LON0 + 0.01
            assert east > LON0 - 0.01
            assert LAT0 - 0.01 < (south + north) / 2 < LAT0 + 0.03


class TestLineFillIsSymmetric:
    @pytest.mark.parametrize("target", [(600.0, 0.0), (0.0, 600.0), (-600.0, 400.0), (400.0, -600.0)])
    def test_walking_a_leg_backwards_covers_the_same_cells(self, target):
        forward = [point(0, 0.0, 0.0), point(20, *target)]
        backward = [point(0, *target), point(20, 0.0, 0.0)]

        assert service.cells_of_track(forward, ZOOM) == service.cells_of_track(backward, ZOOM)


class TestStoredRows:
    def test_the_rows_are_the_cells_at_the_stored_zoom(self, db, add_activity):
        route = build_route([("walk", (0, 1800))])
        activity_id = add_activity(route)

        stored = service.refresh_activity_cells(activity_id, db)

        rows = db.query(models.ActivityCell).filter_by(activity_id=activity_id).all()
        assert stored == len(rows) == len(service.cells_of_track(route.points, ZOOM))
        assert {row.grid_zoom for row in rows} == {ZOOM}
        assert {(row.cell_x, row.cell_y) for row in rows} == service.cells_of_track(route.points, ZOOM)

    def test_recomputing_replaces_the_old_rows_instead_of_adding_to_them(self, db, add_activity):
        activity_id = add_activity(build_route([("walk", (0, 1800))]))
        service.refresh_activity_cells(activity_id, db)

        again = service.refresh_activity_cells(activity_id, db)

        assert db.query(models.ActivityCell).filter_by(activity_id=activity_id).count() == again

    def test_an_activity_without_a_gps_stream_gets_no_cells(self, db, add_activity):
        activity_id = add_activity(None)

        assert service.refresh_activity_cells(activity_id, db) == 0
        assert db.query(models.ActivityCell).filter_by(activity_id=activity_id).count() == 0

    def test_the_backfill_covers_every_activity_the_user_owns(self, db, add_activity):
        mine = [add_activity(build_route([("walk", (0, 900))]), day=day) for day in range(3)]
        theirs = add_activity(build_route([("walk", (0, 900))]), user_id=8)

        assert service.refresh_user_cells(7, db) == len(mine)
        assert db.query(models.ActivityCell).filter_by(activity_id=theirs).count() == 0
        for activity_id in mine:
            assert db.query(models.ActivityCell).filter_by(activity_id=activity_id).count() > 0

    def test_a_failure_while_building_cells_is_swallowed_so_the_import_survives(self):
        session = MagicMock()
        with patch("coverage_map.service.refresh_activity_cells", side_effect=RuntimeError("no streams")):
            service.refresh_cells_after_import([SimpleNamespace(id=5)], 7, session)

        session.rollback.assert_called_once()

    def test_the_backfill_does_not_care_which_importer_brought_the_activity_in(self, db, add_activity):
        from_strava = add_activity(
            build_route([("walk", (0, 900))]), import_info={"import_source": "Strava bulk import"}
        )

        service.refresh_user_cells(7, db)

        assert db.query(models.ActivityCell).filter_by(activity_id=from_strava).count() > 0
