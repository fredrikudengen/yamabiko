"""Tests for the written feedback: real routes and SQLite, the Claude call replaced."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import anthropic
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import activities.activity.models as activities_models
import activities.activity_streams.constants as streams_constants
import activities.activity_streams.models as streams_models
import activity_feedback.client as feedback_client
import activity_feedback.facts as feedback_facts
import activity_feedback.router as router
import activity_feedback.service as feedback_service
import auth.dependencies as auth_dependencies
import core.database as core_database
import coverage_map.service as coverage_service
import segments.crud as segments_crud
import segments.service as segments_service
from tests._helpers.db import create_sqlite_session
from tests._helpers.segments import build_route, node

T0 = datetime(2026, 10, 14, 7, 0, 0, tzinfo=UTC)
ASCENT = [("walk", (0, 1800))]


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


@pytest.fixture
def current_user():
    return {"id": 7}


@pytest.fixture
def client(db, current_user):
    app = FastAPI()
    app.include_router(router.router, prefix="/feedback")
    app.dependency_overrides[core_database.get_db] = lambda: db
    app.dependency_overrides[auth_dependencies.validate_access_token] = lambda: None
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: current_user["id"]
    return TestClient(app)


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ACTIVITY_FEEDBACK_AUTO", raising=False)


@pytest.fixture
def written(monkeypatch):
    """Stands in for Claude: records the facts it was given and answers with a fixed text."""
    calls: list[dict] = []

    def fake(facts, language="nb"):
        calls.append(facts)
        return f"Tekst nummer {len(calls)}."

    monkeypatch.setattr(feedback_client, "write_feedback", fake)
    return calls


def add_tour(db, legs=ASCENT, day=0, user_id=7, speed=1.2, name="Løvstakken", created=None, notes=None) -> int:
    route = build_route(legs, speed=speed)
    start = T0 + timedelta(days=day)
    activity = activities_models.Activity(
        user_id=user_id,
        name=name,
        distance=1700,
        activity_type=12,
        start_time=start,
        end_time=start + timedelta(hours=1),
        timezone="Europe/Oslo",
        total_elapsed_time=3600,
        total_timer_time=3500,
        elevation_gain=320,
        elevation_loss=10,
        average_hr=140,
        max_hr=171,
        created_at=created or start,
        private_notes=notes,
        **{c.name: False for c in activities_models.Activity.__table__.columns if c.name.startswith("hide_")},
    )
    db.add(activity)
    db.flush()

    def stamp(t):
        return (start + timedelta(seconds=t)).strftime("%Y-%m-%dT%H:%M:%S")

    db.add(
        streams_models.ActivityStreams(
            activity_id=activity.id,
            stream_type=streams_constants.STREAM_TYPE_MAP,
            stream_waypoints=[{"time": stamp(p.t), "lat": p.lat, "lon": p.lon} for p in route.points],
        )
    )
    db.commit()
    coverage_service.refresh_activity_cells(activity.id, db)
    return activity.id


def add_segment(db, user_id=7):
    start, end = node(0, 0), node(0, 1800)
    segment = segments_crud.create_segment(user_id, "Til toppen", start, end, db)
    segments_service.refresh_segment_efforts(segment, db)
    return segment


class TestFacts:
    def test_the_tour_itself_is_described_in_its_own_time_zone(self, db):
        activity = db.get(activities_models.Activity, add_tour(db))

        tour = feedback_facts.build_facts(activity, db)["tour"]

        assert tour["name"] == "Løvstakken"
        assert tour["date"] == "2026-10-14"
        assert tour["start_time_local"] == "09:00"
        assert tour["distance_km"] == 1.7
        assert tour["elevation_gain_m"] == 320

    def test_no_coordinates_are_among_the_facts(self, db):
        add_tour(db, day=0)
        activity_id = add_tour(db, day=1, speed=1.0)
        add_segment(db)
        activity = db.get(activities_models.Activity, activity_id)

        text = feedback_client.facts_json(feedback_facts.build_facts(activity, db))

        assert '"lat"' not in text and '"lon"' not in text and "itude" not in text
        assert str(round(node(0, 0).lat, 2)) not in text
        assert str(round(node(0, 0).lon, 2)) not in text

    def test_a_slower_pass_is_ranked_and_compared_with_the_fastest(self, db):
        add_tour(db, day=0, speed=1.4)
        slower = add_tour(db, day=1, speed=1.0)
        add_segment(db)

        (segment,) = feedback_facts.build_facts(db.get(activities_models.Activity, slower), db)["segments"]

        assert segment["name"] == "Til toppen"
        assert segment["passes_so_far_including_this"] == 2
        assert segment["rank_by_moving_time_on_the_day"] == 2
        assert segment["was_personal_record_on_the_day"] is False
        against = segment["against_fastest_pass_so_far"]
        assert against["best_date"] == "2026-10-14"
        assert against["behind_at_finish_seconds"] == segment["moving_seconds"] - against["best_moving_seconds"]
        assert against["behind_at_finish_seconds"] > 300
        assert 0 < against["behind_halfway_seconds"] < against["behind_at_finish_seconds"]
        halves = against["lost_in_first_half_seconds"] + against["lost_in_second_half_seconds"]
        assert abs(halves - against["behind_at_finish_seconds"]) <= 1

    def test_the_fastest_pass_is_a_record_with_nothing_to_compare_against(self, db):
        add_tour(db, day=0, speed=1.0)
        faster = add_tour(db, day=1, speed=1.4)
        add_segment(db)

        (segment,) = feedback_facts.build_facts(db.get(activities_models.Activity, faster), db)["segments"]

        assert segment["was_personal_record_on_the_day"] is True
        assert "against_fastest_pass_so_far" not in segment

    def test_the_only_pass_of_a_segment_has_no_rank(self, db):
        only = add_tour(db)
        add_segment(db)

        (segment,) = feedback_facts.build_facts(db.get(activities_models.Activity, only), db)["segments"]

        assert segment["rank_by_moving_time_on_the_day"] is None
        assert segment["was_personal_record_on_the_day"] is False
        assert segment["earlier_passes_newest_first"] == []

    def test_new_ground_counts_the_cells_no_earlier_tour_passed(self, db):
        add_tour(db, day=0)
        again = add_tour(db, day=1)
        further = add_tour(db, legs=[("walk", (0, 1800)), ("walk", (0, 3600))], day=2)

        def new_ground(activity_id):
            return feedback_facts.build_facts(db.get(activities_models.Activity, activity_id), db)["new_ground"]

        assert new_ground(again)["of_them_never_visited_before"] == 0
        assert (
            0
            < new_ground(further)["of_them_never_visited_before"]
            < new_ground(further)["squares_of_about_300m_passed"]
        )

    def test_the_year_runs_through_the_tour_and_not_past_it(self, db):
        first = add_tour(db, day=0)
        add_tour(db, day=5)

        year = feedback_facts.build_facts(db.get(activities_models.Activity, first), db)["year"]

        assert year["this_year_through_this_tour"]["tours"] == 1
        assert year["this_year_through_this_tour"]["distance_km"] == 1.7
        assert year["last_year_by_same_date"]["tours"] == 0

    def test_milestones_name_the_round_number_this_tour_crossed(self, db):
        for day in range(-30, -21):  # nine earlier tours this year
            add_tour(db, day=day)
        add_tour(db, day=-400)  # one tour last year
        tenth = add_tour(db, day=0)

        year = feedback_facts.build_facts(db.get(activities_models.Activity, tenth), db)["year"]

        assert year["milestones"] == ["passed 10 tours this year"]

    def test_milestones_name_last_years_total_when_it_is_overtaken(self, db):
        add_tour(db, day=-400)
        add_tour(db, day=-390)  # two tours last year
        add_tour(db, day=-5)
        add_tour(db, day=-3)
        third = add_tour(db, day=0)

        milestones = feedback_facts.build_facts(db.get(activities_models.Activity, third), db)["year"]["milestones"]

        assert "overtook last year's full-year tours (2)" in milestones

    def test_an_ordinary_tour_has_no_milestones(self, db):
        add_tour(db, day=-3)
        second = add_tour(db, day=0)

        assert feedback_facts.build_facts(db.get(activities_models.Activity, second), db)["year"]["milestones"] == []

    def test_a_pass_is_judged_as_it_stood_on_its_day(self, db):
        old = add_tour(db, day=0, speed=1.1)
        add_tour(db, day=5, speed=1.5)  # faster, but walked later
        add_segment(db)

        (segment,) = feedback_facts.build_facts(db.get(activities_models.Activity, old), db)["segments"]

        assert segment["passes_so_far_including_this"] == 1
        assert segment["rank_by_moving_time_on_the_day"] is None
        assert "against_fastest_pass_so_far" not in segment

    def test_earlier_passes_come_newest_first_with_the_days_between(self, db):
        first = add_tour(db, day=0, speed=1.0)
        second = add_tour(db, day=3, speed=1.2)
        third = add_tour(db, day=10, speed=1.4)
        add_segment(db)

        (segment,) = feedback_facts.build_facts(db.get(activities_models.Activity, third), db)["segments"]

        dates = [p["date"] for p in segment["earlier_passes_newest_first"]]
        assert dates == ["2026-10-17", "2026-10-14"]
        assert segment["days_since_previous_pass"] == 7
        assert segment["fastest_this_year"] is True
        assert segment["was_personal_record_on_the_day"] is True
        assert first and second

    def test_heart_beats_per_100m_climbed_need_a_climb_and_a_heart_rate(self, db):
        effort = SimpleNamespace(net_elevation_m=300, average_hr=150, moving_s=1800)

        assert feedback_facts._beats_per_100m(effort) == 1500
        assert (
            feedback_facts._beats_per_100m(SimpleNamespace(net_elevation_m=10, average_hr=150, moving_s=1800)) is None
        )
        assert (
            feedback_facts._beats_per_100m(SimpleNamespace(net_elevation_m=300, average_hr=None, moving_s=1800)) is None
        )

    def test_the_tour_is_placed_among_this_years_tours_and_after_the_last_one(self, db):
        add_tour(db, day=-9)
        latest = add_tour(db, day=0)

        context = feedback_facts.build_facts(db.get(activities_models.Activity, latest), db)[
            "compared_with_your_other_tours"
        ]

        assert context["days_since_previous_tour"] == 9
        assert context["same_type_tours_this_year_so_far"] == 2
        assert context["rank_this_year_by_distance"] == 1

    def test_the_users_notes_come_with_the_tour_and_its_earlier_passes(self, db):
        add_tour(db, day=0, notes="Snø over 400 m. " + "Lang dag. " * 40)
        latest = add_tour(db, day=3, notes="Med Clara, tung sekk")
        add_segment(db)

        facts = feedback_facts.build_facts(db.get(activities_models.Activity, latest), db)
        (earlier,) = facts["segments"][0]["earlier_passes_newest_first"]

        assert facts["tour"]["your_notes"] == "Med Clara, tung sekk"
        assert earlier["your_notes"].startswith("Snø over 400 m.")
        assert len(earlier["your_notes"]) <= feedback_facts.EARLIER_NOTES_CHARS
        assert earlier["your_notes"].endswith("…")

    def test_a_tour_without_notes_has_none(self, db):
        activity = db.get(activities_models.Activity, add_tour(db))

        assert feedback_facts.build_facts(activity, db)["tour"]["your_notes"] is None

    def test_the_same_tour_gives_the_same_hash_and_new_numbers_another(self, db):
        activity = db.get(activities_models.Activity, add_tour(db))
        before = feedback_client.facts_hash(feedback_facts.build_facts(activity, db))

        assert feedback_client.facts_hash(feedback_facts.build_facts(activity, db)) == before
        add_tour(db, day=-3)
        assert feedback_client.facts_hash(feedback_facts.build_facts(activity, db)) != before


class TestApi:
    def test_without_a_key_the_feature_is_off_and_nothing_can_be_written(self, client, db, no_key, written):
        activity_id = add_tour(db)

        body = client.get(f"/feedback/activities/{activity_id}").json()

        assert body == {"enabled": False, "pending": False, "text": None, "model": None, "created_at": None}
        assert client.post(f"/feedback/activities/{activity_id}").status_code == 503
        assert written == []

    def test_writing_stores_the_text_with_the_facts_it_was_made_from(self, client, db, with_key, written):
        activity_id = add_tour(db)

        body = client.post(f"/feedback/activities/{activity_id}").json()

        assert body["enabled"] is True
        assert body["text"] == "Tekst nummer 1."
        assert body["model"] == feedback_client.MODEL
        stored = feedback_service.get_feedback(activity_id, db)
        assert stored.facts == written[0]
        assert stored.facts_hash == feedback_client.facts_hash(written[0])
        assert client.get(f"/feedback/activities/{activity_id}").json()["text"] == "Tekst nummer 1."

    def test_writing_again_asks_again_and_replaces_the_text(self, client, db, with_key, written):
        activity_id = add_tour(db)

        client.post(f"/feedback/activities/{activity_id}")
        body = client.post(f"/feedback/activities/{activity_id}").json()

        assert body["text"] == "Tekst nummer 2."
        assert len(written) == 2

    def test_a_failed_call_is_a_502_and_keeps_the_earlier_text(self, client, db, with_key, written, monkeypatch):
        activity_id = add_tour(db)
        client.post(f"/feedback/activities/{activity_id}")

        def fail(_facts, _language="nb"):
            raise feedback_client.FeedbackUnavailableError("rate limited")

        monkeypatch.setattr(feedback_client, "write_feedback", fail)

        assert client.post(f"/feedback/activities/{activity_id}").status_code == 502
        assert client.get(f"/feedback/activities/{activity_id}").json()["text"] == "Tekst nummer 1."

    def test_another_users_tour_is_not_found(self, client, db, with_key, written):
        theirs = add_tour(db, user_id=8)

        assert client.get(f"/feedback/activities/{theirs}").status_code == 404
        assert client.post(f"/feedback/activities/{theirs}").status_code == 404
        assert client.get("/feedback/activities/9999").status_code == 404
        assert written == []


class TestAfterImport:
    @pytest.fixture
    def inline(self, monkeypatch, db):
        """Run the background job at once, on the test's own session."""

        class Session:
            def __enter__(self):
                return db

            def __exit__(self, *_exc):
                return False

        monkeypatch.setattr(feedback_service, "SessionLocal", Session)
        monkeypatch.setattr(feedback_service, "_executor", SimpleNamespace(submit=lambda job, *args: job(*args)))

    def test_nothing_is_written_on_import_unless_it_is_switched_on(self, db, with_key, written, inline, monkeypatch):
        monkeypatch.delenv("ACTIVITY_FEEDBACK_AUTO", raising=False)
        activity_id = add_tour(db)

        feedback_service.write_after_import(activity_id)

        assert written == []

    def test_switched_on_a_new_tour_gets_its_text(self, db, with_key, written, inline, monkeypatch):
        monkeypatch.setenv("ACTIVITY_FEEDBACK_AUTO", "true")
        activity_id = add_tour(db)

        feedback_service.write_after_import(activity_id)

        assert feedback_service.get_feedback(activity_id, db).text == "Tekst nummer 1."

    def test_unchanged_facts_are_not_sent_twice(self, db, with_key, written, inline, monkeypatch):
        monkeypatch.setenv("ACTIVITY_FEEDBACK_AUTO", "true")
        activity_id = add_tour(db)

        feedback_service.write_after_import(activity_id)
        feedback_service.write_after_import(activity_id)

        assert len(written) == 1

    def test_a_failing_api_never_reaches_the_import(self, db, with_key, inline, monkeypatch):
        monkeypatch.setenv("ACTIVITY_FEEDBACK_AUTO", "true")
        activity_id = add_tour(db)

        def fail(_facts, _language="nb"):
            raise RuntimeError("boom")

        monkeypatch.setattr(feedback_client, "write_feedback", fail)

        feedback_service.write_after_import(activity_id)  # must not raise

        assert feedback_service.get_feedback(activity_id, db) is None

    def test_a_tour_just_imported_is_pending_until_its_text_is_there(self, client, db, with_key, monkeypatch):
        monkeypatch.setenv("ACTIVITY_FEEDBACK_AUTO", "true")
        fresh = add_tour(db, created=datetime.now(UTC))
        old = add_tour(db, day=1)

        assert client.get(f"/feedback/activities/{fresh}").json()["pending"] is True
        assert client.get(f"/feedback/activities/{old}").json()["pending"] is False


class TestClaudeCall:
    def _client(self, monkeypatch, response=None, error=None):
        sent = {}

        def create(**kwargs):
            sent.update(kwargs)
            if error:
                raise error
            return response

        fake = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        monkeypatch.setattr(anthropic, "Anthropic", lambda **_kwargs: fake)
        return sent

    def _response(self, stop_reason="end_turn", text="Fin tur."):
        return SimpleNamespace(
            stop_reason=stop_reason,
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        )

    def test_sends_the_facts_to_sonnet_and_returns_the_text(self, monkeypatch):
        sent = self._client(monkeypatch, self._response())

        text = feedback_client.write_feedback({"tour": {"name": "Ulriken"}})

        assert text == "Fin tur."
        assert sent["model"] == "claude-sonnet-5-5"
        assert sent["output_config"] == {"effort": "medium"}
        assert "thinking" not in sent
        assert '"Ulriken"' in sent["messages"][0]["content"]
        assert "Write in Norwegian Bokmål" in sent["system"]
        assert "your_notes" in sent["system"]

    def test_writes_in_the_app_language(self, monkeypatch):
        sent = self._client(monkeypatch, self._response())

        feedback_client.write_feedback({}, "en")

        assert "Write in English" in sent["system"]
        assert "{language}" not in sent["system"]

    def test_the_language_is_part_of_what_a_text_was_made_from(self):
        assert feedback_client.facts_hash({"a": 1}, "en") != feedback_client.facts_hash({"a": 1}, "nb")

    @pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
    def test_a_declined_or_cut_off_answer_is_no_text(self, monkeypatch, stop_reason):
        self._client(monkeypatch, self._response(stop_reason=stop_reason))

        with pytest.raises(feedback_client.FeedbackUnavailableError):
            feedback_client.write_feedback({})

    def test_an_empty_answer_is_no_text(self, monkeypatch):
        self._client(monkeypatch, self._response(text="  "))

        with pytest.raises(feedback_client.FeedbackUnavailableError):
            feedback_client.write_feedback({})

    def test_an_unreachable_api_is_no_text(self, monkeypatch):
        self._client(monkeypatch, error=anthropic.APIConnectionError(request=None))

        with pytest.raises(feedback_client.FeedbackUnavailableError, match="reach"):
            feedback_client.write_feedback({})
