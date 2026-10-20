"""Tests for segments.geo: time spent inside a circle along a GPS track."""

import pytest

import google_health.stops as stops
import segments.geo as geo
from tests._helpers.segments import latlon


def _p(t: float, x: float, y: float) -> stops.TrackPoint:
    lat, lon = latlon(x, y)
    return stops.TrackPoint(t, lat, lon)


def _inside(points, x=0.0, y=0.0, radius=50.0):
    lat, lon = latlon(x, y)
    return geo.time_inside_circle(points, lat, lon, radius)


def test_entry_and_exit_are_interpolated_between_points():
    # 20 m/s straight through the centre of a 50 m circle: inside from x=-50 to x=50.
    (visit,) = _inside([_p(0, -100, 0), _p(10, 100, 0)])

    assert visit.enter == pytest.approx(2.5, abs=0.05)
    assert visit.exit == pytest.approx(7.5, abs=0.05)


def test_a_pass_that_falls_between_two_points_is_found():
    # No point is inside the circle, but the line between them crosses it.
    points = [_p(0, -100, 0), _p(10, 100, 0)]
    assert all(geo.distance_m(*latlon(0, 0), p.lat, p.lon) > 50 for p in points)

    assert len(_inside(points)) == 1


def test_a_line_that_misses_the_circle_is_not_a_visit():
    assert _inside([_p(0, -100, 60), _p(10, 100, 60)]) == []


def test_staying_inside_across_several_points_is_one_visit():
    points = [_p(t, -80 + 16 * t, 0) for t in range(0, 11)]  # x from -80 to 80

    (visit,) = _inside(points)

    assert visit.enter == pytest.approx(1.875, abs=0.05)  # x = -50
    assert visit.exit == pytest.approx(8.125, abs=0.05)  # x = 50


def test_two_separate_passes_are_two_visits():
    points = [_p(0, -100, 0), _p(10, 100, 0), _p(20, 100, 20), _p(30, -100, 20)]

    visits = _inside(points)

    assert len(visits) == 2
    assert visits[0].exit < visits[1].enter


def test_a_track_that_begins_inside_enters_at_its_first_point():
    (visit,) = _inside([_p(5, 0, 0), _p(10, 100, 0)])

    assert visit.enter == 5
    assert visit.exit == pytest.approx(7.5, abs=0.05)


def test_a_track_that_ends_inside_exits_at_its_last_point():
    (visit,) = _inside([_p(0, -100, 0), _p(10, 0, 0)])

    assert visit.exit == 10


def test_nothing_is_interpolated_across_a_long_gap():
    # The same straight line, but 60 s apart (a device pause): the position in between
    # is unknown, so the circle is not counted as visited.
    assert _inside([_p(0, -100, 0), _p(60, 100, 0)]) == []


def test_points_inside_are_still_visits_next_to_a_long_gap():
    visits = _inside([_p(0, -100, 0), _p(60, 10, 0)])

    assert [(v.enter, v.exit) for v in visits] == [(60, 60)]


def test_single_point_and_empty_track():
    assert _inside([]) == []
    assert _inside([_p(0, 0, 0)]) == [geo.Interval(0, 0)]
    assert _inside([_p(0, 500, 0)]) == []


def test_distance_m_matches_the_flat_map():
    assert geo.distance_m(*latlon(0, 0), *latlon(30, 40)) == pytest.approx(50.0, abs=0.01)
