"""The Strava export import starts whether or not the user has gear."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth.dependencies as auth_dependencies
import core.database as core_database
import strava.router as strava_router
import websocket.manager as websocket_manager


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(strava_router.router, prefix="/strava")
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: 7
    app.dependency_overrides[websocket_manager.get_websocket_manager] = lambda: MagicMock()
    return TestClient(app)


def test_the_import_is_queued_for_a_user_without_gear():
    # It used to be dropped here: an empty gear dictionary counted as a failure,
    # and the endpoint still answered that the import had started.
    loop = MagicMock()
    with (
        patch.object(strava_router.strava_bulk_import_utils, "iterate_over_activities_csv", return_value={"1.gpx": {}}),
        patch.object(strava_router.asyncio, "get_event_loop", return_value=loop),
    ):
        response = _client().post("/strava/import/activities")

    assert response.status_code == 201
    loop.run_in_executor.assert_called_once()
    queued = loop.run_in_executor.call_args.args[1]
    assert queued.func is strava_router.strava_bulk_import_utils.queue_bulk_export_activities_for_import
    assert queued.args[0] == 7


def test_a_missing_activities_csv_still_aborts():
    loop = MagicMock()
    with (
        patch.object(strava_router.strava_bulk_import_utils, "iterate_over_activities_csv", return_value=None),
        patch.object(strava_router.asyncio, "get_event_loop", return_value=loop),
    ):
        _client().post("/strava/import/activities")

    loop.run_in_executor.assert_not_called()
