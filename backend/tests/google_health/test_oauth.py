"""Tests for google_health.oauth with a mocked token endpoint."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

import google_health.oauth as oauth

REQUIRED_SCOPE = " ".join(oauth.SCOPES)


def _http(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_auth_url_asks_for_offline_access_and_both_scopes():
    url = oauth.build_auth_url("cid", "http://localhost/cb", "st4te")

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == oauth.AUTH_URL
    assert query["client_id"] == ["cid"]
    assert query["redirect_uri"] == ["http://localhost/cb"]
    assert query["state"] == ["st4te"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["response_type"] == ["code"]
    assert query["scope"] == [REQUIRED_SCOPE]
    # Merging earlier grants would bring in cloud-platform, which the API rejects.
    assert "include_granted_scopes" not in query


async def test_exchange_code_posts_the_code_and_parses_tokens():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(parse_qs(request.content.decode()))
        return httpx.Response(
            200,
            json={"access_token": "A", "refresh_token": "R", "expires_in": 3599, "scope": REQUIRED_SCOPE},
        )

    before = datetime.now(UTC)
    async with _http(handler) as http:
        tokens = await oauth.exchange_code("the-code", "cid", "secret", "http://localhost/cb", http)

    assert seen["grant_type"] == ["authorization_code"]
    assert seen["code"] == ["the-code"]
    assert seen["redirect_uri"] == ["http://localhost/cb"]
    assert (tokens.access_token, tokens.refresh_token) == ("A", "R")
    assert before + timedelta(seconds=3590) < tokens.expires_at < before + timedelta(seconds=3610)


async def test_exchange_code_rejects_missing_scope():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"access_token": "A", "refresh_token": "R", "expires_in": 3600, "scope": oauth.SCOPES[0]},
        )

    async with _http(handler) as http:
        with pytest.raises(oauth.GoogleHealthOAuthError, match="location"):
            await oauth.exchange_code("c", "cid", "s", "http://localhost/cb", http)


async def test_exchange_code_rejects_missing_refresh_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "A", "expires_in": 3600, "scope": REQUIRED_SCOPE})

    async with _http(handler) as http:
        with pytest.raises(oauth.GoogleHealthOAuthError, match="refresh token"):
            await oauth.exchange_code("c", "cid", "s", "http://localhost/cb", http)


async def test_refresh_keeps_no_new_refresh_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert parse_qs(request.content.decode())["grant_type"] == ["refresh_token"]
        return httpx.Response(200, json={"access_token": "A2", "expires_in": 3600, "scope": REQUIRED_SCOPE})

    async with _http(handler) as http:
        tokens = await oauth.refresh_access_token("R", "cid", "s", http)

    assert tokens.access_token == "A2"
    assert tokens.refresh_token is None


async def test_invalid_grant_is_its_own_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    async with _http(handler) as http:
        with pytest.raises(oauth.InvalidGrantError):
            await oauth.refresh_access_token("R", "cid", "s", http)


async def test_other_errors_do_not_leak_the_response_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="secret-ish body")

    async with _http(handler) as http:
        with pytest.raises(oauth.GoogleHealthOAuthError) as info:
            await oauth.refresh_access_token("R", "cid", "s", http)

    assert not isinstance(info.value, oauth.InvalidGrantError)
    assert "secret-ish" not in str(info.value)


async def test_network_error_becomes_oauth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    async with _http(handler) as http:
        with pytest.raises(oauth.GoogleHealthOAuthError, match="ConnectError"):
            await oauth.refresh_access_token("R", "cid", "s", http)
