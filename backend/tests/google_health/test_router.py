"""Tests for the link callback and for sync_user, using a real SQLite session."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import core.config as core_config
import google_health.activity_utils as activity_utils
import google_health.client as google_health_client
import google_health.crud as crud
import google_health.oauth as oauth
import google_health.router as router
from tests._helpers.db import create_sqlite_session

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
SCOPE = " ".join(oauth.SCOPES)


@pytest.fixture(autouse=True)
def fake_encryption():
    with (
        patch("core.cryptography.encrypt_token_fernet", lambda t: None if t is None else f"enc:{t}"),
        patch("core.cryptography.decrypt_token_fernet", lambda t: None if t is None else t.removeprefix("enc:")),
    ):
        yield


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(core_config.settings, "GOOGLE_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setattr(core_config.settings, "GOOGLE_HEALTH_CLIENT_SECRET", "secret")
    monkeypatch.setattr(core_config.settings, "GOOGLE_HEALTH_REDIRECT_URI", "http://localhost/cb")


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


def _tokens() -> oauth.TokenSet:
    return oauth.TokenSet("A", NOW + timedelta(hours=1), "R", SCOPE)


async def test_callback_links_the_user_and_consumes_the_state(db):
    crud.set_state(7, "st", db)

    with patch("google_health.oauth.exchange_code", AsyncMock(return_value=_tokens())) as exchange:
        response = await router.googlehealth_callback(db, state="st", code="the-code")

    assert response.status_code == 303
    assert response.headers["location"] == "/settings/integrations?googlehealth=linked"
    exchange.assert_awaited_once_with("the-code", "cid", "secret", "http://localhost/cb")
    assert crud.linked_user_ids(db) == [7]
    assert crud.get_integrations_by_state("st", db) is None


async def test_callback_with_unknown_state_is_rejected_without_calling_google(db):
    with patch("google_health.oauth.exchange_code", AsyncMock()) as exchange:
        response = await router.googlehealth_callback(db, state="nope", code="c")

    assert response.status_code == 400
    exchange.assert_not_awaited()


async def test_callback_state_cannot_be_reused(db):
    crud.set_state(7, "st", db)
    with patch("google_health.oauth.exchange_code", AsyncMock(return_value=_tokens())):
        await router.googlehealth_callback(db, state="st", code="c")
        second = await router.googlehealth_callback(db, state="st", code="c")

    assert second.status_code == 400


async def test_callback_when_user_denies_access_links_nothing(db):
    crud.set_state(7, "st", db)

    with patch("google_health.oauth.exchange_code", AsyncMock()) as exchange:
        response = await router.googlehealth_callback(db, state="st", error="access_denied")

    assert response.status_code == 303
    assert response.headers["location"].endswith("googlehealth=denied")
    exchange.assert_not_awaited()
    assert crud.linked_user_ids(db) == []
    assert crud.get_integrations_by_state("st", db) is None


async def test_callback_failed_exchange_links_nothing_and_does_not_leak(db):
    crud.set_state(7, "st", db)
    failing = AsyncMock(side_effect=oauth.GoogleHealthOAuthError("Not all required permissions were granted: x"))

    with patch("google_health.oauth.exchange_code", failing):
        response = await router.googlehealth_callback(db, state="st", code="c")

    assert response.status_code == 303
    assert response.headers["location"].endswith("googlehealth=scopes")
    assert crud.linked_user_ids(db) == []


async def test_callback_other_exchange_failure_redirects_with_a_generic_error(db):
    crud.set_state(7, "st", db)

    with patch("google_health.oauth.exchange_code", AsyncMock(side_effect=oauth.GoogleHealthOAuthError("boom"))):
        response = await router.googlehealth_callback(db, state="st", code="c")

    assert response.headers["location"].endswith("googlehealth=error")
    assert crud.linked_user_ids(db) == []


async def test_auth_url_stores_a_fresh_state(db):
    result = await router.googlehealth_auth_url(None, None, 7, db)

    state = crud.get_integrations(7, db).googlehealth_state
    assert state
    assert f"state={state}" in result["url"]


async def test_auth_url_needs_a_configured_client(db, monkeypatch):
    monkeypatch.setattr(core_config.settings, "GOOGLE_HEALTH_CLIENT_ID", None)
    with pytest.raises(router.HTTPException) as info:
        await router.googlehealth_auth_url(None, None, 7, db)
    assert info.value.status_code == 503


async def test_status_never_returns_tokens(db):
    crud.link(7, _tokens(), db)

    result = await router.googlehealth_status(None, None, 7, db)

    assert result["linked"] is True
    assert result["configured"] is True
    assert result["access_token_expires_at"] is not None
    assert not {"access_token", "refresh_token", "token"} & set(result)


async def test_sync_user_unlinks_when_google_rejects_the_token(db):
    crud.link(7, _tokens(), db)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("google_health.token_utils.get_valid_access_token", AsyncMock(return_value="A")),
        patch("google_health.client.GoogleHealthClient", return_value=client),
        patch(
            "google_health.activity_utils.fetch_and_process_exercises",
            AsyncMock(side_effect=google_health_client.GoogleHealthAuthError("403")),
        ),
    ):
        result = await activity_utils.sync_user(7, 7, MagicMock(), db)

    assert result is None
    assert crud.linked_user_ids(db) == []


async def test_sync_user_skips_unlinked_users(db):
    with (
        patch("google_health.token_utils.get_valid_access_token", AsyncMock(return_value=None)),
        patch("google_health.client.GoogleHealthClient") as client,
    ):
        assert await activity_utils.sync_user(7, 7, MagicMock(), db) is None
    client.assert_not_called()
