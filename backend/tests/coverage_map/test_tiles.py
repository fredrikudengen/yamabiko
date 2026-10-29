"""The cell grid: a position lands in one cell, and coarser cells contain finer ones."""

import math

import pytest

import coverage_map.tiles as tiles

# Fløyen, Bergen. Everything here is checked against this latitude.
BERGEN = (60.396, 5.329)


class TestTileXy:
    def test_the_origin_of_the_grid_is_the_north_west_corner(self):
        assert tiles.tile_xy(85.0, -180.0, 2) == (0, 0)

    def test_the_prime_meridian_at_the_equator_is_the_middle_of_the_world(self):
        assert tiles.tile_xy(0.0, 0.0, 1) == (1, 1)

    def test_a_position_lands_in_the_cell_its_fraction_points_at(self):
        x, y = tiles.tile_xy_float(*BERGEN, 17)

        assert tiles.tile_xy(*BERGEN, 17) == (int(x), int(y))

    def test_longitudes_past_the_antimeridian_wrap_instead_of_leaving_the_grid(self):
        scale = 2**8

        x, _ = tiles.tile_xy(0.0, 181.0, 8)

        assert 0 <= x < scale

    @pytest.mark.parametrize("lat", [90.0, -90.0])
    def test_the_poles_are_clamped_to_the_edge_of_the_projection(self, lat):
        scale = 2**8

        _, y = tiles.tile_xy(lat, 0.0, 8)

        assert 0 <= y < scale


class TestRollUp:
    def test_four_cells_of_one_zoom_fill_one_cell_of_the_next(self):
        parents = {tiles.roll_up(x, y, 17, 16) for x in (10, 11) for y in (20, 21)}

        assert parents == {(5, 10)}

    def test_neighbouring_pairs_fall_in_different_parents(self):
        assert tiles.roll_up(11, 20, 17, 16) != tiles.roll_up(12, 20, 17, 16)

    def test_rolling_up_nowhere_leaves_the_cell_alone(self):
        assert tiles.roll_up(1234, 5678, 17, 17) == (1234, 5678)

    def test_rolling_up_in_one_step_matches_rolling_up_one_zoom_at_a_time(self):
        x, y = 98_765, 54_321
        step_by_step = (x, y)
        for zoom in range(17, 13, -1):
            step_by_step = tiles.roll_up(*step_by_step, zoom, zoom - 1)

        assert step_by_step == tiles.roll_up(x, y, 17, 13)

    def test_a_finer_zoom_is_refused_because_it_cannot_be_invented(self):
        with pytest.raises(ValueError, match="finer"):
            tiles.roll_up(1, 1, 16, 17)


class TestCellSize:
    def test_a_stored_cell_is_about_150_metres_in_southern_norway(self):
        assert tiles.cell_size_m(BERGEN[0], tiles.STORE_ZOOM) == pytest.approx(151, abs=1)

    def test_the_default_map_zoom_is_about_300_metres_there(self):
        assert tiles.cell_size_m(BERGEN[0], tiles.STORE_ZOOM - 1) == pytest.approx(302, abs=2)

    def test_cells_shrink_towards_the_pole(self):
        assert tiles.cell_size_m(60.0, 17) < tiles.cell_size_m(0.0, 17)

    def test_each_zoom_halves_the_cell(self):
        assert tiles.cell_size_m(60.0, 16) == pytest.approx(2 * tiles.cell_size_m(60.0, 17))


class TestCellBounds:
    def test_the_box_contains_the_position_that_produced_the_cell(self):
        x, y = tiles.tile_xy(*BERGEN, 17)

        south, west, north, east = tiles.cell_bounds(x, y, 17)

        assert south < BERGEN[0] < north
        assert west < BERGEN[1] < east

    def test_the_box_is_as_wide_as_the_cell_size_says(self):
        x, y = tiles.tile_xy(*BERGEN, 17)

        south, west, north, east = tiles.cell_bounds(x, y, 17)
        middle = (south + north) / 2
        width_m = (east - west) * 111_320.0 * math.cos(math.radians(middle))

        assert width_m == pytest.approx(tiles.cell_size_m(middle, 17), rel=0.01)

    def test_a_neighbour_starts_where_the_cell_ends(self):
        _, _, _, east = tiles.cell_bounds(100, 200, 17)
        _, west, _, _ = tiles.cell_bounds(101, 200, 17)

        assert east == pytest.approx(west)
