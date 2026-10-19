"""Tests for google_health.activity_utils (the import loop)."""

from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest

import google_health.activity_utils as activity_utils
import google_health.client as client_module
from tests._helpers.google_health import data_point


def _client(data_points: list[dict]) -> Mock:
    client = Mock()
    client.list_exercises = AsyncMock(return_value=data_points)
    client.download_tcx = AsyncMock(return_value=b"<tcx/>")
    return client


async def _run(client: Mock) -> list | None:
    return await activity_utils.fetch_and_process_exercises(
        client, date(2026, 10, 14), date(2026, 10, 15), user_id=1, ws_manager=Mock(), db=Mock()
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(activity_utils.google_health_crud, "activity_exists", Mock(return_value=False))
    monkeypatch.setattr(activity_utils, "import_exercise", AsyncMock(return_value=["stored"]))


@pytest.mark.asyncio
async def test_imports_only_what_passes_the_filter():
    client = _client(
        [
            data_point(exercise_id="1"),
            data_point(exercise_id="2", recording_method="PASSIVELY_MEASURED", has_gps=None),
            data_point(exercise_id="3", recording_method="UNKNOWN", has_gps=None),  # Strava copy
            data_point(exercise_id="4", events=("START",)),  # still recording
        ]
    )

    result = await _run(client)

    assert result == ["stored"]
    client.download_tcx.assert_awaited_once_with("1")


@pytest.mark.asyncio
async def test_already_stored_exercise_is_not_downloaded(monkeypatch):
    monkeypatch.setattr(activity_utils.google_health_crud, "activity_exists", Mock(return_value=True))
    client = _client([data_point(exercise_id="1")])

    assert await _run(client) is None
    client.download_tcx.assert_not_awaited()


@pytest.mark.asyncio
async def test_one_failing_exercise_does_not_stop_the_others(monkeypatch):
    monkeypatch.setattr(
        activity_utils, "import_exercise", AsyncMock(side_effect=[RuntimeError("bad file"), ["stored"]])
    )
    client = _client([data_point(exercise_id="1"), data_point(exercise_id="2")])

    assert await _run(client) == ["stored"]
    assert client.download_tcx.await_count == 2


@pytest.mark.asyncio
async def test_auth_error_propagates_so_the_caller_can_ask_to_link_again():
    client = _client([data_point(exercise_id="1")])
    client.download_tcx = AsyncMock(side_effect=client_module.GoogleHealthAuthError("401"))

    with pytest.raises(client_module.GoogleHealthAuthError):
        await _run(client)


def test_lookback_range_includes_today():
    assert activity_utils.lookback_range(7, today=date(2026, 10, 19)) == (date(2026, 10, 12), date(2026, 10, 20))
