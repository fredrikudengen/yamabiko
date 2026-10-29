"""The Google Health import adds new activities to the coverage map."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import google_health.activity_utils as activity_utils
from tests._helpers.google_health import data_point


@pytest.fixture
def patched():
    with (
        patch("core.file_uploads.save_validated_bytes", AsyncMock(return_value="x.tcx")),
        patch("core.file_uploads.safe_remove_within") as remove,
        patch("activities.activity.utils.parse_and_store_activity_from_file", new_callable=AsyncMock) as parse,
        patch("segments.service.refresh_efforts_after_import"),
        patch("coverage_map.service.refresh_cells_after_import") as cells,
    ):
        yield SimpleNamespace(parse=parse, cells=cells, remove=remove)


async def test_a_stored_activity_is_added_to_the_coverage_map(patched):
    stored = [SimpleNamespace(id=5)]
    patched.parse.return_value = stored
    db = MagicMock()

    result = await activity_utils.import_exercise(data_point(), b"tcx", 7, MagicMock(), db)

    assert result == stored
    patched.cells.assert_called_once_with(stored, 7, db)


@pytest.mark.parametrize("nothing", [None, []])
async def test_nothing_is_added_when_the_file_did_not_parse(patched, nothing):
    patched.parse.return_value = nothing

    result = await activity_utils.import_exercise(data_point(), b"tcx", 7, MagicMock(), MagicMock())

    assert not result
    patched.cells.assert_not_called()
