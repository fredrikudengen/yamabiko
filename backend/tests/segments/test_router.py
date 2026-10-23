"""Tests for the segments API: real routes on a FastAPI app, real SQLite, login faked."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import activities.activity.models as activities_models
import activities.activity_streams.constants as streams_constants
import activities.activity_streams.models as streams_models
import auth.dependencies as auth_dependencies
import core.database as core_database
import segments.models as models
import segments.router as router
from tests._helpers.db import create_sqlite_session
from tests._helpers.segments import build_route, node

T0 = datetime(2026, 10, 14, 7, 0, 0, tzinfo=UTC)
ASCENT = [("walk", (0, 1800)), ("rest", 600), ("walk", (0, 0))]


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


@pytest.fixture
def current_user():
    """Mutable: ``current_user["id"] = 8`` switches who is logged in."""
    return {"id": 7}


@pytest.fixture
def client(db, current_user):
    app = FastAPI()
    app.include_router(router.router, prefix="/segments")
    app.dependency_overrides[core_database.get_db] = lambda: db
    app.dependency_overrides[auth_dependencies.validate_access_token] = lambda: None
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: current_user["id"]
    return TestClient(app)


def _add_activity(db, route, user_id=7, day=0, name="Fjelltur", **fields) -> int:
    start = T0 + timedelta(days=day)
    activity = activities_models.Activity(
        user_id=user_id,
        name=name,
        distance=1700,
        activity_type=12,
        start_time=start,
        end_time=start + timedelta(hours=1),
        total_elapsed_time=3600,
        total_timer_time=3600,
        created_at=start,
        **{c.name: False for c in activities_models.Activity.__table__.columns if c.name.startswith("hide_")},
        **fields,
    )
    db.add(activity)
    db.flush()

    def stamp(t):
        return (start + timedelta(seconds=t)).strftime("%Y-%m-%dT%H:%M:%S")

    streams = {
        streams_constants.STREAM_TYPE_MAP: [{"time": stamp(p.t), "lat": p.lat, "lon": p.lon} for p in route.points],
        streams_constants.STREAM_TYPE_HR: [{"time": stamp(s.t), "hr": int(s.value)} for s in route.heart_rate],
        streams_constants.STREAM_TYPE_ELEVATION: [{"time": stamp(s.t), "ele": s.value} for s in route.elevation],
    }
    for stream_type, waypoints in streams.items():
        db.add(
            streams_models.ActivityStreams(activity_id=activity.id, stream_type=stream_type, stream_waypoints=waypoints)
        )
    db.commit()
    return activity.id


def _body(name="Fjellet", start=None, end=None):
    n0, n1 = node(0, 0), node(0, 1800)
    return {
        "name": name,
        "start": start if start is not None else {"lat": n0.lat, "lon": n0.lon, "radius_m": 50},
        "end": end if end is not None else {"lat": n1.lat, "lon": n1.lon, "radius_m": 50},
    }


def _create(client, **kwargs):
    response = client.post("/segments", json=_body(**kwargs))
    assert response.status_code == 201, response.text
    return response.json()


class TestCreate:
    def test_creates_the_segment_and_its_efforts(self, client, db):
        activity_id = _add_activity(db, build_route(ASCENT))

        body = _create(client)

        assert body["name"] == "Fjellet"
        assert body["effort_count"] == 1
        assert body["start"]["radius_m"] == 50
        assert body["similar_segments"] == []
        (effort,) = client.get(f"/segments/{body['id']}/efforts").json()
        assert effort["activity_id"] == activity_id
        assert effort["activity_name"] == "Fjelltur"
        assert effort["segment_name"] == "Fjellet"
        assert effort["moving_s"] == pytest.approx(1700 / 1.2, abs=10)
        assert effort["average_hr"] == pytest.approx(136, abs=3)
        assert effort["details"]["start_node"]["radius_m"] == 50

    def test_the_radius_defaults_to_50_m(self, client):
        body = _body()
        del body["start"]["radius_m"]

        response = client.post("/segments", json=body)

        assert response.status_code == 201
        assert response.json()["start"]["radius_m"] == 50

    def test_a_coordinate_string_can_replace_lat_and_lon(self, client):
        n0, n1 = node(0, 0), node(0, 1800)
        body = _body(
            start={"coordinates": f"{n0.lat:.6f}, {n0.lon:.6f}"},
            end={"coordinates": f"{n1.lat:.6f} {n1.lon:.6f}", "radius_m": 80},
        )

        response = client.post("/segments", json=body)

        assert response.status_code == 201, response.text
        assert response.json()["start"]["lat"] == pytest.approx(n0.lat, abs=1e-6)
        assert response.json()["end"]["radius_m"] == 80

    @pytest.mark.parametrize(
        "start",
        [
            {"lat": 60.0},
            {},
            {"lat": 60.0, "lon": 5.0, "coordinates": "60.0, 5.0"},
            {"coordinates": "not a place"},
            {"coordinates": "151.2, -33.9"},
            {"lat": 95.0, "lon": 5.0},
        ],
    )
    def test_bad_positions_are_422(self, client, start):
        assert client.post("/segments", json=_body(start=start)).status_code == 422

    @pytest.mark.parametrize(
        ("field", "value"),
        [("radius_m", 25), ("radius_m", 10), ("radius_m", -5)],
    )
    def test_a_radius_of_25_m_or_less_is_422(self, client, field, value):
        n0 = node(0, 0)
        start = {"lat": n0.lat, "lon": n0.lon, field: value}

        response = client.post("/segments", json=_body(start=start))

        assert response.status_code == 422
        assert "radius" in response.text

    def test_overlapping_circles_are_422(self, client):
        n1 = node(0, 60)
        response = client.post("/segments", json=_body(end={"lat": n1.lat, "lon": n1.lon}))

        assert response.status_code == 422
        assert "overlap" in response.text

    def test_blank_name_and_unknown_fields_are_422(self, client):
        assert client.post("/segments", json=_body(name="   ")).status_code == 422
        assert client.post("/segments", json={**_body(), "owner": 1}).status_code == 422

    def test_nothing_is_stored_when_the_request_is_rejected(self, client, db):
        client.post("/segments", json=_body(name=" "))
        client.post("/segments", json=_body(end={"lat": node(0, 60).lat, "lon": node(0, 60).lon}))

        assert db.query(models.Segment).count() == 0

    def test_similar_segments_are_a_hint_not_an_error(self, client):
        first = _create(client, name="Fjellet")

        second = client.post("/segments", json=_body(name="Fjellet igjen"))

        assert second.status_code == 201
        assert second.json()["similar_segments"] == [{"id": first["id"], "name": "Fjellet"}]

    def test_sharing_only_the_start_is_not_similar(self, client):
        _create(client, name="Til toppen")
        mid = node(0, 900)

        second = _create(client, name="Til midten", end={"lat": mid.lat, "lon": mid.lon})

        assert second["similar_segments"] == []

    def test_sharing_only_the_end_is_not_similar(self, client):
        _create(client, name="Sti A")
        other_start = node(400, 0)

        second = _create(client, name="Sti B", start={"lat": other_start.lat, "lon": other_start.lon})

        assert second["similar_segments"] == []


class TestReadUpdateDelete:
    def test_list_and_get(self, client, db):
        _add_activity(db, build_route(ASCENT))
        a = _create(client, name="B segment")
        mid = node(0, 900)
        b = _create(client, name="A segment", end={"lat": mid.lat, "lon": mid.lon})

        listed = client.get("/segments").json()

        assert [s["name"] for s in listed] == ["A segment", "B segment"]
        assert client.get(f"/segments/{a['id']}").json()["effort_count"] == 1
        assert client.get(f"/segments/{b['id']}").json()["name"] == "A segment"

    def test_update_recomputes_the_efforts(self, client, db):
        _add_activity(db, build_route(ASCENT))
        segment = _create(client)
        assert segment["effort_count"] == 1
        far = node(500, 0)
        far_end = node(500, 1800)

        updated = client.put(
            f"/segments/{segment['id']}",
            json=_body(
                name="Annet fjell",
                start={"lat": far.lat, "lon": far.lon},
                end={"lat": far_end.lat, "lon": far_end.lon},
            ),
        )

        assert updated.status_code == 200
        assert updated.json()["name"] == "Annet fjell"
        assert updated.json()["effort_count"] == 0
        assert client.get(f"/segments/{segment['id']}/efforts").json() == []

    def test_a_rejected_update_changes_nothing(self, client):
        segment = _create(client)
        n0 = node(0, 0)

        response = client.put(
            f"/segments/{segment['id']}", json=_body(name="Ny", start={"lat": n0.lat, "lon": n0.lon, "radius_m": 10})
        )

        assert response.status_code == 422
        assert client.get(f"/segments/{segment['id']}").json()["name"] == "Fjellet"

    def test_a_segment_is_not_similar_to_itself_on_update(self, client):
        segment = _create(client)

        updated = client.put(f"/segments/{segment['id']}", json=_body(name="Samme"))

        assert updated.json()["similar_segments"] == []

    def test_delete_removes_the_segment_and_its_efforts(self, client, db):
        _add_activity(db, build_route(ASCENT))
        segment = _create(client)

        assert client.delete(f"/segments/{segment['id']}").status_code == 204

        assert client.get(f"/segments/{segment['id']}").status_code == 404
        assert db.query(models.SegmentEffort).count() == 0

    def test_refresh_picks_up_activities_added_later(self, client, db):
        segment = _create(client)
        assert segment["effort_count"] == 0
        _add_activity(db, build_route(ASCENT))

        refreshed = client.post(f"/segments/{segment['id']}/refresh")

        assert refreshed.status_code == 200
        assert refreshed.json()["effort_count"] == 1


class TestOwnership:
    def test_other_users_segments_are_404(self, client, current_user):
        segment = _create(client)
        current_user["id"] = 8

        assert client.get(f"/segments/{segment['id']}").status_code == 404
        assert client.get(f"/segments/{segment['id']}/efforts").status_code == 404
        assert client.put(f"/segments/{segment['id']}", json=_body()).status_code == 404
        assert client.delete(f"/segments/{segment['id']}").status_code == 404
        assert client.post(f"/segments/{segment['id']}/refresh").status_code == 404
        assert client.get("/segments").json() == []

    def test_other_users_activities_do_not_count(self, client, db):
        _add_activity(db, build_route(ASCENT), user_id=8)

        assert _create(client)["effort_count"] == 0


class TestPreview:
    def test_lists_matching_tours_without_saving(self, client, db):
        passing = _add_activity(db, build_route(ASCENT), day=0, name="Tur 1")
        _add_activity(db, build_route([("walk", (300, 1800))], start=(300, -150)), day=1, name="Annen tur")
        n0, n1 = node(0, 0), node(0, 1800)

        response = client.post(
            "/segments/preview",
            json={"start": {"lat": n0.lat, "lon": n0.lon}, "end": {"lat": n1.lat, "lon": n1.lon}},
        )

        assert response.status_code == 200
        (match,) = response.json()["matches"]
        assert match["activity_id"] == passing
        assert match["activity_name"] == "Tur 1"
        assert match["moving_s"] == pytest.approx(1700 / 1.2, abs=10)
        assert match["end_visits"] == 1
        assert len(match["end_visit_times"]) == 1
        assert match["closest_start_m"] < 10
        assert match["closest_end_m"] < 10
        assert db.query(models.Segment).count() == 0
        assert db.query(models.SegmentEffort).count() == 0

    def test_a_larger_radius_finds_more(self, client, db):
        _add_activity(db, build_route([("walk", (60, 1800))], start=(60, -150)))
        n0, n1 = node(0, 0), node(0, 1800)

        def preview(radius):
            return client.post(
                "/segments/preview",
                json={
                    "start": {"lat": n0.lat, "lon": n0.lon, "radius_m": radius},
                    "end": {"lat": n1.lat, "lon": n1.lon, "radius_m": radius},
                },
            ).json()["matches"]

        assert preview(50) == []
        assert len(preview(70)) == 1

    def test_near_misses_are_listed_with_the_radius_that_would_catch_them(self, client, db):
        missed = _add_activity(db, build_route([("walk", (90, 1800))], start=(90, -150)), name="Litt ved siden av")
        n0, n1 = node(0, 0), node(0, 1800)

        body = client.post(
            "/segments/preview",
            json={"start": {"lat": n0.lat, "lon": n0.lon}, "end": {"lat": n1.lat, "lon": n1.lon}},
        ).json()

        assert body["matches"] == []
        (miss,) = body["near_misses"]
        assert miss["activity_id"] == missed
        assert miss["activity_name"] == "Litt ved siden av"
        assert miss["reason"] == "both_not_reached"
        assert miss["closest_start_m"] == pytest.approx(90, abs=3)

    def test_bad_nodes_are_422(self, client):
        n0 = node(0, 0)
        response = client.post(
            "/segments/preview",
            json={"start": {"lat": n0.lat, "lon": n0.lon, "radius_m": 5}, "end": {"coordinates": "60.01, 5.0"}},
        )

        assert response.status_code == 422

    def test_reports_similar_saved_segments(self, client):
        saved = _create(client)
        n0, n1 = node(0, 0), node(0, 1800)

        body = client.post(
            "/segments/preview",
            json={"start": {"lat": n0.lat, "lon": n0.lon}, "end": {"lat": n1.lat, "lon": n1.lon}},
        ).json()

        assert body["similar_segments"] == [{"id": saved["id"], "name": "Fjellet"}]


SOURCE_CASES = [
    ("google_health", {"googlehealth_activity_id": "abc123", "import_info": {"import_source": "google_health"}}),
    ("strava", {"import_info": {"import_source": "Strava bulk import", "strava_activity_id": 42}}),
    ("strava", {"strava_activity_id": 4242}),
    ("garmin", {"garminconnect_activity_id": 99}),
    ("other", {}),
    ("other", {"import_info": {"import_source": "Basic bulk import"}}),
]


class TestSource:
    """Efforts and previews say where each tour came from, so heart rate and height are not mixed up."""

    def test_efforts_carry_the_source_of_their_activity(self, client, db):
        ids = {
            i: _add_activity(db, build_route(ASCENT), day=i, name=f"Tur {i}", **fields)
            for i, (_, fields) in enumerate(SOURCE_CASES)
        }
        segment = _create(client)

        efforts = {e["activity_id"]: e["source"] for e in client.get(f"/segments/{segment['id']}/efforts").json()}

        assert efforts == {ids[i]: expected for i, (expected, _) in enumerate(SOURCE_CASES)}

    def test_the_efforts_of_one_activity_carry_the_source(self, client, db):
        activity_id = _add_activity(db, build_route(ASCENT), googlehealth_activity_id="abc123")
        _create(client)

        (effort,) = client.get(f"/segments/activities/{activity_id}/efforts").json()

        assert effort["source"] == "google_health"

    def test_preview_matches_carry_the_source(self, client, db):
        activity_id = _add_activity(db, build_route(ASCENT), import_info={"import_source": "Strava bulk import"})
        n0, n1 = node(0, 0), node(0, 1800)

        response = client.post(
            "/segments/preview",
            json={"start": {"lat": n0.lat, "lon": n0.lon}, "end": {"lat": n1.lat, "lon": n1.lon}},
        )

        (match,) = response.json()["matches"]
        assert match["activity_id"] == activity_id
        assert match["source"] == "strava"


class TestActivityEfforts:
    def test_efforts_of_one_activity(self, client, db):
        activity_id = _add_activity(db, build_route(ASCENT))
        mid = node(0, 900)
        _create(client, name="Toppen")
        _create(client, name="Midten", end={"lat": mid.lat, "lon": mid.lon})

        efforts = client.get(f"/segments/activities/{activity_id}/efforts").json()

        assert sorted(e["segment_name"] for e in efforts) == ["Midten", "Toppen"]
        assert all(e["activity_id"] == activity_id for e in efforts)

    def test_someone_elses_or_unknown_activity_is_404(self, client, db):
        theirs = _add_activity(db, build_route(ASCENT), user_id=8)

        assert client.get(f"/segments/activities/{theirs}/efforts").status_code == 404
        assert client.get("/segments/activities/99999/efforts").status_code == 404

    def test_a_route_named_activities_is_not_taken_for_a_segment_id(self, client):
        # "/segments/activities/..." must reach the activity route, not "/{segment_id}/efforts".
        assert client.get("/segments/activities/1/efforts").status_code == 404
        assert client.get("/segments/activities/1/efforts").json()["detail"] == "Activity not found"


class TestParseCoordinates:
    def test_parses_a_pasted_pair(self, client):
        response = client.post("/segments/parse-coordinates", json={"text": "60,39 5,32"})

        assert response.status_code == 200
        assert response.json() == {"lat": 60.39, "lon": 5.32}

    def test_rejects_what_it_cannot_read(self, client):
        response = client.post("/segments/parse-coordinates", json={"text": "32V 301234 6700000"})

        assert response.status_code == 422
        assert "decimal" in response.text


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/segments"),
        ("post", "/segments"),
        ("post", "/segments/preview"),
        ("get", "/segments/1"),
        ("get", "/segments/1/efforts"),
        ("get", "/segments/activities/1/efforts"),
    ],
)
def test_the_routes_are_registered_and_need_a_login(method, path):
    # The real route table, no dependency overrides: not registered would be 404/405,
    # registered without a login check would not be 401/403.
    import core.config as core_config
    import core.routes as core_routes

    app = FastAPI()
    app.include_router(core_routes.router)

    response = getattr(TestClient(app), method)(core_config.ROOT_PATH + path)

    assert response.status_code in (401, 403), response.text
