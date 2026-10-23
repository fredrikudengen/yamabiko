"""Tests for the segment database layer and service, on an in-memory SQLite database."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import activities.activity.models as activities_models
import activities.activity_streams.constants as streams_constants
import activities.activity_streams.models as streams_models
import segments.crud as crud
import segments.matching as matching
import segments.models as models
import segments.service as service
from tests._helpers.db import create_sqlite_session
from tests._helpers.segments import build_route, latlon, node

USER = 7
OTHER_USER = 8
T0 = datetime(2026, 10, 14, 7, 0, 0, tzinfo=UTC)
START = node(0, 0)
SUMMIT = node(0, 1800)


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


def _waypoints(route) -> dict[int, list[dict]]:
    """Stored-stream waypoints (UTC time strings without offset) for a synthetic route."""

    def stamp(t: float) -> str:
        return (T0 + timedelta(seconds=t)).strftime("%Y-%m-%dT%H:%M:%S")

    return {
        streams_constants.STREAM_TYPE_MAP: [{"time": stamp(p.t), "lat": p.lat, "lon": p.lon} for p in route.points],
        streams_constants.STREAM_TYPE_HR: [{"time": stamp(s.t), "hr": int(s.value)} for s in route.heart_rate],
        streams_constants.STREAM_TYPE_ELEVATION: [{"time": stamp(s.t), "ele": s.value} for s in route.elevation],
    }


def _add_activity(db, route, user_id=USER, day=0, streams=None) -> int:
    start = T0 + timedelta(days=day)
    activity = activities_models.Activity(
        user_id=user_id,
        name="Hike",
        distance=1700,
        activity_type=12,
        start_time=start,
        end_time=start + timedelta(hours=1),
        total_elapsed_time=3600,
        total_timer_time=3600,
        created_at=start,
        **{c.name: False for c in activities_models.Activity.__table__.columns if c.name.startswith("hide_")},
    )
    db.add(activity)
    db.flush()
    waypoints = _waypoints(route) if streams is None else streams
    for stream_type, wp in waypoints.items():
        db.add(streams_models.ActivityStreams(activity_id=activity.id, stream_type=stream_type, stream_waypoints=wp))
    db.commit()
    return activity.id


def _segment(db, name="Fjellet", user_id=USER):
    return crud.create_segment(user_id, name, START, SUMMIT, db)


ASCENT = [("walk", (0, 1800)), ("rest", 600), ("walk", (0, 0))]


class TestBuildTrack:
    def test_converts_stored_waypoints_to_seconds_since_the_first_point(self):
        route = build_route([("walk", (0, 100))])
        track = service.build_track(_waypoints(route))

        assert track.start == T0
        assert track.points[0].t == 0
        assert track.points[-1].t == route.points[-1].t
        assert track.points[0].lat == pytest.approx(route.points[0].lat)
        assert len(track.heart_rate) == len(route.heart_rate)
        assert len(track.elevation) == len(route.elevation)

    def test_a_track_without_gps_has_no_track(self):
        route = build_route([("walk", (0, 100))])
        hr_only = {streams_constants.STREAM_TYPE_HR: _waypoints(route)[streams_constants.STREAM_TYPE_HR]}

        assert service.build_track(hr_only) is None
        assert service.build_track({}) is None

    def test_points_without_position_are_skipped_and_time_zones_are_respected(self):
        waypoints = {
            streams_constants.STREAM_TYPE_MAP: [
                {"time": "2026-10-14T09:00:05+02:00", "lat": 60.0, "lon": 5.0},
                {"time": "2026-10-14T07:00:00", "lat": None, "lon": None},
                {"time": "2026-10-14T07:00:10", "lat": 60.0, "lon": 5.0001},
            ]
        }

        track = service.build_track(waypoints)

        assert track.start == datetime(2026, 10, 14, 7, 0, 5, tzinfo=UTC)
        assert [p.t for p in track.points] == [0, 5]


class TestSegmentCrud:
    def test_create_and_read_back(self, db):
        segment = _segment(db)

        assert crud.get_segment(segment.id, USER, db).name == "Fjellet"
        start, end = crud.nodes_of(segment)
        assert start == START
        assert end == SUMMIT

    def test_the_name_is_trimmed_and_nodes_are_checked(self, db):
        assert crud.create_segment(USER, "  Fjellet  ", START, SUMMIT, db).name == "Fjellet"
        with pytest.raises(ValueError, match="radius"):
            crud.create_segment(USER, "x", node(0, 0, 20), SUMMIT, db)
        with pytest.raises(ValueError, match="name"):
            crud.create_segment(USER, "   ", START, SUMMIT, db)
        with pytest.raises(ValueError, match="overlap"):
            crud.create_segment(USER, "x", START, node(0, 60), db)

    def test_a_segment_belongs_to_its_user(self, db):
        segment = _segment(db)

        assert crud.get_segment(segment.id, OTHER_USER, db) is None
        assert crud.get_user_segments(OTHER_USER, db) == []
        assert [s.id for s in crud.get_user_segments(USER, db)] == [segment.id]

    def test_update_changes_the_nodes(self, db):
        segment = _segment(db)

        crud.update_segment(segment, "Ny", node(0, 0, 80), SUMMIT, db)

        assert segment.name == "Ny"
        assert segment.start_radius_m == 80

    def test_update_with_bad_nodes_changes_nothing(self, db):
        segment = _segment(db)

        with pytest.raises(ValueError):
            crud.update_segment(segment, "Ny", node(0, 0, 10), SUMMIT, db)

        assert segment.name == "Fjellet"
        assert segment.start_radius_m == 50

    def test_delete_removes_the_efforts_too(self, db):
        segment = _segment(db)
        _add_activity(db, build_route(ASCENT))
        service.refresh_segment_efforts(segment, db)
        assert db.scalars(select(models.SegmentEffort)).all()

        crud.delete_segment(segment, db)

        assert db.scalars(select(models.Segment)).all() == []
        assert db.scalars(select(models.SegmentEffort)).all() == []


class TestRefreshSegmentEfforts:
    def test_stores_an_effort_for_each_activity_that_passes(self, db):
        segment = _segment(db)
        passing = _add_activity(db, build_route(ASCENT), day=0)
        passing_later = _add_activity(db, build_route([("walk", (0, 900)), ("rest", 480), ("walk", (0, 1800))]), day=3)
        missing = _add_activity(db, build_route([("walk", (300, 1800))], start=(300, -150)), day=5)
        no_gps = _add_activity(db, build_route(ASCENT), day=6, streams={})

        efforts = service.refresh_segment_efforts(segment, db)

        assert sorted(e.activity_id for e in efforts) == [passing, passing_later]
        assert missing not in {e.activity_id for e in efforts}
        assert no_gps not in {e.activity_id for e in efforts}
        stored = crud.get_efforts_for_segment(segment.id, db)
        assert [e.activity_id for e in stored] == [passing, passing_later]  # oldest first

    def test_an_effort_has_absolute_times_and_the_measured_values(self, db):
        segment = _segment(db)
        _add_activity(db, build_route(ASCENT))

        (effort,) = service.refresh_segment_efforts(segment, db)
        db.refresh(effort)

        start = effort.start_time.replace(tzinfo=UTC)
        end = effort.end_time.replace(tzinfo=UTC)
        assert (start - T0).total_seconds() == pytest.approx(200 / 1.2, abs=5)
        assert (end - start).total_seconds() == pytest.approx(effort.elapsed_s, abs=0.01)
        assert effort.moving_s == pytest.approx(1700 / 1.2, abs=10)
        assert effort.distance_m == pytest.approx(1700, rel=0.1)
        assert effort.average_hr == pytest.approx(136, abs=3)
        assert effort.max_hr == pytest.approx(170, abs=1)
        assert effort.net_elevation_m == pytest.approx(340, abs=4)
        assert effort.matcher_version == matching.MATCHER_VERSION

    def test_the_node_parameters_are_stored_with_the_effort(self, db):
        segment = crud.create_segment(USER, "Fjellet", node(0, 0, 60), node(0, 1800, 90), db)
        _add_activity(db, build_route(ASCENT))

        (effort,) = service.refresh_segment_efforts(segment, db)

        assert effort.details["start_node"]["radius_m"] == 60
        assert effort.details["end_node"]["radius_m"] == 90
        assert effort.details["end_visits"] == 1
        assert effort.details["stop_parameters"]["min_seconds"] == 300

    def test_refreshing_again_replaces_the_efforts(self, db):
        segment = _segment(db)
        _add_activity(db, build_route(ASCENT))
        service.refresh_segment_efforts(segment, db)

        again = service.refresh_segment_efforts(segment, db)

        assert len(again) == 1
        assert len(crud.get_efforts_for_segment(segment.id, db)) == 1

    def test_changed_nodes_remove_efforts_that_no_longer_match(self, db):
        segment = _segment(db)
        _add_activity(db, build_route(ASCENT))
        service.refresh_segment_efforts(segment, db)

        crud.update_segment(segment, "Annet", node(500, 0), node(500, 1800), db)
        service.refresh_segment_efforts(segment, db)

        assert crud.get_efforts_for_segment(segment.id, db) == []

    def test_only_the_owners_activities_count(self, db):
        segment = _segment(db)
        _add_activity(db, build_route(ASCENT), user_id=OTHER_USER)

        assert service.refresh_segment_efforts(segment, db) == []

    def test_a_segment_with_no_matching_activity_is_fine(self, db):
        assert service.refresh_segment_efforts(_segment(db), db) == []


class TestRefreshActivityEfforts:
    def test_matches_one_activity_against_all_segments(self, db):
        fjellet = _segment(db, "Fjellet")
        other = crud.create_segment(USER, "Annet", node(500, 0), node(500, 1800), db)
        activity_id = _add_activity(db, build_route(ASCENT))

        efforts = service.refresh_activity_efforts(activity_id, USER, db)

        assert [e.segment_id for e in efforts] == [fjellet.id]
        assert other.id not in {e.segment_id for e in crud.get_efforts_for_activity(activity_id, db)}

    def test_replaces_only_that_activitys_efforts(self, db):
        segment = _segment(db)
        first = _add_activity(db, build_route(ASCENT), day=0)
        second = _add_activity(db, build_route(ASCENT), day=1)
        service.refresh_segment_efforts(segment, db)

        service.refresh_activity_efforts(first, USER, db)

        assert len(crud.get_efforts_for_activity(first, db)) == 1
        assert len(crud.get_efforts_for_activity(second, db)) == 1
        assert len(crud.get_efforts_for_segment(segment.id, db)) == 2

    def test_an_activity_whose_gps_is_gone_loses_its_efforts(self, db):
        segment = _segment(db)
        activity_id = _add_activity(db, build_route(ASCENT))
        service.refresh_segment_efforts(segment, db)
        db.execute(streams_models.ActivityStreams.__table__.delete())
        db.commit()

        service.refresh_activity_efforts(activity_id, USER, db)

        assert crud.get_efforts_for_activity(activity_id, db) == []

    def test_no_segments_is_fine(self, db):
        activity_id = _add_activity(db, build_route(ASCENT))

        assert service.refresh_activity_efforts(activity_id, USER, db) == []


class TestPreview:
    def test_lists_the_activities_that_pass_without_storing_anything(self, db):
        passing = _add_activity(db, build_route(ASCENT), day=0)
        _add_activity(db, build_route([("walk", (300, 1800))], start=(300, -150)), day=1)

        hits = service.preview_matches(USER, START, SUMMIT, db)

        assert [hit.activity_id for hit in hits] == [passing]
        assert hits[0].match.moving_s == pytest.approx(1700 / 1.2, abs=10)
        assert hits[0].end_time - hits[0].start_time == timedelta(seconds=hits[0].match.elapsed_s)
        assert db.scalars(select(models.SegmentEffort)).all() == []

    def test_rejects_bad_nodes(self, db):
        with pytest.raises(ValueError, match="radius"):
            service.preview_matches(USER, node(0, 0, 10), SUMMIT, db)

    def test_a_larger_radius_can_find_more(self, db):
        route = build_route([("walk", (60, 1800))], start=(60, -150))
        _add_activity(db, route)

        assert service.preview_matches(USER, START, SUMMIT, db) == []
        assert len(service.preview_matches(USER, node(0, 0, 70), node(0, 1800, 70), db)) == 1


def test_latlon_helper_round_trip():
    # Guards the test map itself: 0.001 deg of latitude is about 111 m.
    lat, lon = latlon(0, 111.32)
    assert lat == pytest.approx(60.001)
    assert lon == pytest.approx(5.0)


class TestRefreshAfterImport:
    def test_matches_each_imported_activity(self, db):
        segment = _segment(db)
        first = _add_activity(db, build_route(ASCENT), day=0)
        second = _add_activity(db, build_route(ASCENT), day=1)

        service.refresh_efforts_after_import([SimpleNamespace(id=first), SimpleNamespace(id=second)], USER, db)

        assert sorted(e.activity_id for e in crud.get_efforts_for_segment(segment.id, db)) == [first, second]

    def test_a_failure_is_logged_and_never_raised(self, db, monkeypatch):
        calls = []

        def boom(activity_id, user_id, session):
            calls.append(activity_id)
            raise RuntimeError("stream data is broken")

        monkeypatch.setattr(service, "refresh_activity_efforts", boom)
        rolled_back = []
        monkeypatch.setattr(db, "rollback", lambda: rolled_back.append(True))

        service.refresh_efforts_after_import([SimpleNamespace(id=1), SimpleNamespace(id=2)], USER, db)

        assert calls == [1, 2]  # the second one is still tried
        assert rolled_back == [True, True]

    def test_nothing_to_do_for_no_activities(self, db):
        service.refresh_efforts_after_import([], USER, db)


class TestPreviewDetails:
    def test_matches_carry_the_closest_approach_and_visit_times(self, db):
        _add_activity(db, build_route([("walk", (0, 1800)), ("walk", (0, 1000)), ("walk", (0, 1800))]))

        (hit,) = service.preview(USER, START, SUMMIT, db).matches

        assert hit.closest_start_m < 5
        assert hit.closest_end_m < 5
        assert len(hit.end_visit_times) == 2
        assert hit.end_visit_times[0] == hit.end_time
        assert hit.end_visit_times[0] < hit.end_visit_times[1]

    def test_near_misses_say_how_large_a_radius_would_have_caught_them(self, db):
        # 90 m east of both nodes: a 50 m circle misses it, a 100 m circle catches it.
        missed = _add_activity(db, build_route([("walk", (90, 1800))], start=(90, -150)))

        result = service.preview(USER, START, SUMMIT, db)

        assert result.matches == []
        (miss,) = result.near_misses
        assert miss.activity_id == missed
        assert miss.reason == matching.MISS_BOTH_NOT_REACHED
        assert miss.closest_start_m == pytest.approx(90, abs=3)
        assert miss.closest_end_m == pytest.approx(90, abs=3)
        assert len(service.preview(USER, node(0, 0, 100), node(0, 1800, 100), db).matches) == 1

    def test_the_reason_names_the_missed_node(self, db):
        _add_activity(db, build_route([("walk", (0, 1800))], start=(0, 300)))  # starts beyond the start node
        _add_activity(db, build_route([("walk", (0, 1500))]), day=1)  # stops 300 m short of the top

        reasons = [miss.reason for miss in service.preview(USER, START, SUMMIT, db).near_misses]

        assert reasons == [matching.MISS_START_NOT_REACHED, matching.MISS_END_NOT_REACHED]

    def test_a_descent_is_a_wrong_order_near_miss(self, db):
        _add_activity(db, build_route([("walk", (0, -150))], start=(0, 1900)))

        (miss,) = service.preview(USER, START, SUMMIT, db).near_misses

        assert miss.reason == matching.MISS_WRONG_ORDER

    def test_tours_far_from_the_nodes_are_not_near_misses(self, db):
        _add_activity(db, build_route([("walk", (3000, 1800))], start=(3000, -150)))

        assert service.preview(USER, START, SUMMIT, db).near_misses == []

    def test_only_the_owners_tours_and_only_tours_with_gps_are_listed(self, db):
        _add_activity(db, build_route([("walk", (90, 1800))], start=(90, -150)), user_id=OTHER_USER)
        _add_activity(db, build_route([("walk", (90, 1800))], start=(90, -150)), day=1, streams={})

        assert service.preview(USER, START, SUMMIT, db).near_misses == []
