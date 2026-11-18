"""Tests for the grid helpers behind segment suggestions."""

import segments.suggestions as suggestions


def test_touching_cells_join_into_one_area_also_corner_to_corner():
    cells = {(0, 0), (1, 1), (2, 2), (10, 10), (11, 10)}

    areas = sorted(suggestions.clusters(cells), key=len, reverse=True)

    assert areas == [{(0, 0), (1, 1), (2, 2)}, {(10, 10), (11, 10)}]


def test_growing_adds_every_touching_cell():
    assert suggestions.grow([(5, 5)]) == {(x, y) for x in (4, 5, 6) for y in (4, 5, 6)}


def test_the_farthest_pair_is_the_two_ends_of_a_line():
    a, b = suggestions.farthest_pair([(0, 0), (1, 0), (2, 1), (3, 1), (4, 2)])

    assert {a, b} == {(0, 0), (4, 2)}
