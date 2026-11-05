"""The Google Health import: what it does around store_activity."""

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
        patch("segments.service.refresh_efforts_after_import") as efforts,
        patch("coverage_map.service.refresh_cells_after_import") as cells,
    ):
        yield SimpleNamespace(parse=parse, remove=remove, efforts=efforts, cells=cells)


async def test_segments_and_cells_are_left_to_store_activity(patched):
    # store_activity refreshes both for every importer; doing it here as well
    # would match each Google Health activity twice.
    stored = [SimpleNamespace(id=5)]
    patched.parse.return_value = stored

    result = await activity_utils.import_exercise(data_point(), b"tcx", 7, MagicMock(), MagicMock())

    assert result == stored
    patched.efforts.assert_not_called()
    patched.cells.assert_not_called()
    patched.remove.assert_not_called()


@pytest.mark.parametrize("nothing", [None, []])
async def test_the_file_is_removed_when_it_did_not_parse(patched, nothing):
    patched.parse.return_value = nothing

    result = await activity_utils.import_exercise(data_point(), b"tcx", 7, MagicMock(), MagicMock())

    assert not result
    patched.remove.assert_called_once()
