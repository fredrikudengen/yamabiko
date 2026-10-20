"""Tests for token storage (crud) and refresh logic (token_utils) on a real SQLite session."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest

import core.config as core_config
import google_health.crud as crud
import google_health.oauth as oauth
import google_health.token_utils as token_utils
from tests._helpers.db import create_sqlite_session

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
SCOPE = " ".join(oauth.SCOPES)


@pytest.fixture(autouse=True)
def fake_encryption():
    """Reversible stand-in for Fernet, so the tests can check what is stored."""
    with (
        patch("core.cryptography.encrypt_token_fernet", lambda t: None if t is None else f"enc:{t}"),
        patch("core.cryptography.decrypt_token_fernet", lambda t: None if t is None else t.removeprefix("enc:")),
    ):
        yield


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(core_config.settings, "GOOGLE_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setattr(core_config.settings, "GOOGLE_HEALTH_CLIENT_SECRET", "secret")
    monkeypatch.setattr(core_config.settings, "GOOGLE_HEALTH_REDIRECT_URI", None)


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


def _tokens(access="A", refresh="R", expires_in=3600) -> oauth.TokenSet:
    return oauth.TokenSet(access, NOW + timedelta(seconds=expires_in), refresh, SCOPE)


def _http(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _refresh_handler(calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"access_token": "NEW", "expires_in": 3600, "scope": SCOPE})

    return handler


def test_link_stores_tokens_encrypted_and_clears_state(db):
    crud.set_state(1, "st", db)
    assert crud.get_integrations_by_state("st", db).user_id == 1

    crud.link(1, _tokens(), db)

    row = crud.get_integrations(1, db)
    assert row.googlehealth_token == "enc:A"
    assert row.googlehealth_refresh_token == "enc:R"
    assert row.googlehealth_state is None
    assert crud.expires_at(row) == NOW + timedelta(hours=1)
    assert crud.get_integrations_by_state("st", db) is None
    assert crud.linked_user_ids(db) == [1]


def test_empty_state_never_matches(db):
    crud.set_state(1, None, db)
    assert crud.get_integrations_by_state("", db) is None


def test_unlink_clears_everything_and_is_safe_twice(db):
    crud.link(1, _tokens(), db)

    crud.unlink(1, db)
    crud.unlink(1, db)
    crud.unlink(99, db)  # no row at all

    row = crud.get_integrations(1, db)
    assert row.googlehealth_token is None
    assert row.googlehealth_refresh_token is None
    assert crud.expires_at(row) is None
    assert crud.linked_user_ids(db) == []


async def test_valid_token_is_returned_without_a_request(db, configured):
    crud.link(1, _tokens(expires_in=3600), db)
    calls = []

    async with _http(_refresh_handler(calls)) as http:
        token = await token_utils.get_valid_access_token(1, db, http, now=NOW)

    assert token == "A"
    assert calls == []


async def test_token_near_expiry_is_refreshed_and_stored(db, configured):
    crud.link(1, _tokens(expires_in=120), db)
    calls = []

    async with _http(_refresh_handler(calls)) as http:
        token = await token_utils.get_valid_access_token(1, db, http, now=NOW)

    assert token == "NEW"
    assert len(calls) == 1
    row = crud.get_integrations(1, db)
    assert row.googlehealth_token == "enc:NEW"
    # Google sends no new refresh token on refresh; the old one stays.
    assert row.googlehealth_refresh_token == "enc:R"


async def test_invalid_grant_unlinks_the_account(db, configured):
    crud.link(1, _tokens(expires_in=-10), db)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    async with _http(handler) as http:
        token = await token_utils.get_valid_access_token(1, db, http, now=NOW)

    assert token is None
    assert crud.linked_user_ids(db) == []


async def test_temporary_failure_keeps_the_tokens(db, configured):
    crud.link(1, _tokens(expires_in=-10), db)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with _http(handler) as http:
        token = await token_utils.get_valid_access_token(1, db, http, now=NOW)

    assert token is None
    assert crud.linked_user_ids(db) == [1]


async def test_unlinked_user_and_unconfigured_client_give_none(db, configured, monkeypatch):
    assert await token_utils.get_valid_access_token(1, db) is None

    crud.link(1, _tokens(expires_in=-10), db)
    monkeypatch.setattr(core_config.settings, "GOOGLE_HEALTH_CLIENT_SECRET", None)
    assert await token_utils.get_valid_access_token(1, db) is None
    assert crud.linked_user_ids(db) == [1]


def test_redirect_uri_defaults_to_the_callback_under_the_host(configured, monkeypatch):
    monkeypatch.setattr(core_config.settings, "ENDURAIN_HOST", "http://pc:8080/")
    assert token_utils.redirect_uri() == "http://pc:8080/api/v1/googlehealth/callback"

    monkeypatch.setattr(core_config.settings, "GOOGLE_HEALTH_REDIRECT_URI", "http://localhost/cb")
    assert token_utils.redirect_uri() == "http://localhost/cb"
