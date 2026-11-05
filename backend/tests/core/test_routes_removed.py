"""The features Yamabiko dropped are gone from the API; what it kept is still there."""

from fastapi import FastAPI

import core.config as core_config
from core.routes import router

ROOT = core_config.ROOT_PATH


def _paths() -> set[str]:
    # From the OpenAPI document, the same way scripts/export_openapi.py builds
    # it: the included router's routes are not listed on ``app.routes``.
    app = FastAPI()
    app.include_router(router)
    return set(app.openapi()["paths"])


PATHS = _paths()


def test_the_path_list_is_not_empty():
    # Guards the tests below: "not in" holds trivially for an empty set.
    assert f"{ROOT}/activities/number" in PATHS or len(PATHS) > 100


def test_garmin_connect_is_gone():
    assert not [path for path in PATHS if path.startswith(f"{ROOT}/garminconnect")]


def test_the_strava_api_link_is_gone():
    for path in ("/link", "/activities", "/gear", "/client", "/unlink"):
        assert f"{ROOT}/strava{path}" not in PATHS


def test_the_strava_export_import_stays():
    assert f"{ROOT}/strava/import/activities" in PATHS


def test_gear_is_gone():
    assert not [path for path in PATHS if path.startswith((f"{ROOT}/gears", f"{ROOT}/gear_components"))]
    assert not [path for path in PATHS if path.startswith(f"{ROOT}/activities/gear")]
    assert f"{ROOT}/profile/default_gear" not in PATHS
    for kind in ("bikes", "shoes"):
        assert f"{ROOT}/strava/import/{kind}" not in PATHS


def test_the_laps_endpoints_are_gone():
    assert not [path for path in PATHS if "activities_laps" in path]


def test_the_integration_refresh_is_gone():
    assert f"{ROOT}/activities/refresh" not in PATHS


def test_health_is_gone():
    assert not [path for path in PATHS if path.startswith(f"{ROOT}/health")]


def test_google_health_stays():
    assert [path for path in PATHS if path.startswith(f"{ROOT}/googlehealth")]


def test_goals_are_gone():
    assert not [path for path in PATHS if path.startswith(f"{ROOT}/profile/goals")]


def test_the_activity_name_search_is_gone():
    assert not [path for path in PATHS if path.startswith(f"{ROOT}/activities/name/contains")]
