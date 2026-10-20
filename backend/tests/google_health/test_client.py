"""Tests for google_health.client with a mocked HTTP transport."""

from datetime import date

import httpx
import pytest

import google_health.client as client_module


def _client(handler) -> client_module.GoogleHealthClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client_module.GoogleHealthClient("token-123", http=http)


def test_filter_uses_civil_start_time_with_open_end():
    assert client_module.GoogleHealthClient.build_filter(date(2026, 10, 14), date(2026, 10, 15)) == (
        'exercise.interval.civil_start_time >= "2026-10-14" AND exercise.interval.civil_start_time < "2026-10-15"'
    )


@pytest.mark.asyncio
async def test_list_follows_pages_and_sends_token():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "pageToken" not in request.url.params:
            return httpx.Response(200, json={"dataPoints": [{"name": "a/1"}], "nextPageToken": "next"})
        return httpx.Response(200, json={"dataPoints": [{"name": "a/2"}]})

    async with _client(handler) as client:
        result = await client.list_exercises(date(2026, 10, 14), date(2026, 10, 15))

    assert [d["name"] for d in result] == ["a/1", "a/2"]
    assert seen[0].headers["Authorization"] == "Bearer token-123"
    assert seen[0].url.path.endswith("/dataTypes/exercise/dataPoints")
    assert seen[1].url.params["pageToken"] == "next"
    assert "civil_start_time" in seen[0].url.params["filter"]


@pytest.mark.asyncio
async def test_list_without_data_points_key():
    async with _client(lambda request: httpx.Response(200, json={})) as client:
        assert await client.list_exercises(date(2026, 10, 14), date(2026, 10, 15)) == []


@pytest.mark.asyncio
async def test_download_tcx_url_and_bytes():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"<tcx/>")

    async with _client(handler) as client:
        assert await client.download_tcx("123") == b"<tcx/>"

    assert seen[0].url.path.endswith("/dataTypes/exercise/dataPoints/123:exportExerciseTcx")
    assert seen[0].url.params["alt"] == "media"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_token_raises_auth_error(status):
    async with _client(lambda request: httpx.Response(status, json={})) as client:
        with pytest.raises(client_module.GoogleHealthAuthError):
            await client.list_exercises(date(2026, 10, 14), date(2026, 10, 15))


@pytest.mark.asyncio
async def test_other_http_errors_propagate():
    async with _client(lambda request: httpx.Response(500)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.download_tcx("123")
