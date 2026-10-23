"""Tests for Strava bulk-import file handling."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

import strava.bulk_import_utils as bulk_import_utils
from core.file_uploads import UploadKind


class _MockGear:
    def __init__(self, gear_id: int, brand: str | None, model: str | None, nickname: str):
        self.id = gear_id
        self.brand = brand
        self.model = model
        self.nickname = nickname


@pytest.mark.asyncio
async def test_bulk_media_import_validates_before_move(tmp_path, monkeypatch):
    """Media import validates images before moving them into storage."""
    validate = AsyncMock()
    create_media = Mock()
    moves = []
    media_dir = str(tmp_path / "activity-media")

    monkeypatch.setattr(bulk_import_utils.os.path, "exists", lambda _: True)
    monkeypatch.setattr(bulk_import_utils.os, "makedirs", Mock())
    monkeypatch.setattr(
        bulk_import_utils.core_config.settings,
        "ACTIVITY_MEDIA_DIR",
        media_dir,
        raising=False,
    )
    monkeypatch.setattr(bulk_import_utils.file_uploads, "validate_local_file", validate)
    monkeypatch.setattr(
        bulk_import_utils.file_uploads,
        "move_within",
        lambda src, dest, *, filename, src_base_dir=None: moves.append((src, dest, filename, src_base_dir)),
    )
    monkeypatch.setattr(
        bulk_import_utils.activity_media_crud,
        "create_activity_media",
        create_media,
    )

    photo_path = str(tmp_path / "strava" / "photo.jpg")
    await bulk_import_utils.create_activity_media_from_strava_bulk_import(
        7,
        "photo.jpg",
        photo_path,
        Mock(),
    )

    validate.assert_awaited_once_with(
        photo_path,
        kind=UploadKind.IMAGE,
        filename="photo.jpg",
    )
    assert moves == [
        (
            photo_path,
            media_dir,
            "7_photo.jpg",
            bulk_import_utils.core_config.STRAVA_BULK_IMPORT_MEDIA_DIR,
        )
    ]
    create_media.assert_called_once()
    assert create_media.call_args.args[1] == os.path.join(media_dir, "7_photo.jpg")


@pytest.mark.asyncio
async def test_bulk_media_import_rejects_invalid_image(tmp_path, monkeypatch):
    """Invalid media is rejected before move or DB insert."""
    validate = AsyncMock(side_effect=HTTPException(status_code=400, detail="bad image"))
    move = Mock()
    create_media = Mock()
    photo_path = str(tmp_path / "strava" / "photo.jpg")

    monkeypatch.setattr(bulk_import_utils.os.path, "exists", lambda _: True)
    monkeypatch.setattr(bulk_import_utils.os, "makedirs", Mock())
    monkeypatch.setattr(bulk_import_utils.file_uploads, "validate_local_file", validate)
    monkeypatch.setattr(bulk_import_utils.file_uploads, "move_within", move)
    monkeypatch.setattr(
        bulk_import_utils.activity_media_crud,
        "create_activity_media",
        create_media,
    )

    await bulk_import_utils.create_activity_media_from_strava_bulk_import(
        7,
        "photo.jpg",
        photo_path,
        Mock(),
    )

    validate.assert_awaited_once()
    move.assert_not_called()
    create_media.assert_not_called()


def test_gear_dictionary_normal(monkeypatch):
    """Smoosh key is built correctly with clean values."""
    mock_user = Mock(id=42)
    monkeypatch.setattr(bulk_import_utils.users_crud, "get_user_by_id", lambda uid, db: mock_user)
    gear_items = [
        _MockGear(gear_id=1, brand="Nike", model="Pegasus", nickname="Fast Shoes"),
    ]
    monkeypatch.setattr(bulk_import_utils.gears_crud, "get_gear_user", lambda uid, db: gear_items)

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result is not None
    assert result["Fast Shoes"] == [1]
    assert result["Nike Pegasus Fast Shoes"] == [1]


def test_gear_dictionary_trailing_whitespace(monkeypatch):
    """Smoosh key strips trailing whitespace from brand/model/nickname."""
    mock_user = Mock(id=42)
    monkeypatch.setattr(bulk_import_utils.users_crud, "get_user_by_id", lambda uid, db: mock_user)
    gear_items = [
        _MockGear(gear_id=2, brand="Nike ", model=" Pegasus ", nickname="Fast Shoes "),
    ]
    monkeypatch.setattr(bulk_import_utils.gears_crud, "get_gear_user", lambda uid, db: gear_items)

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result is not None
    assert "Nike  Pegasus  Fast Shoes " not in result
    assert result["Nike Pegasus Fast Shoes"] == [2]


def test_gear_dictionary_none_fields(monkeypatch):
    """Smoosh key handles None brand/model without TypeError."""
    mock_user = Mock(id=42)
    monkeypatch.setattr(bulk_import_utils.users_crud, "get_user_by_id", lambda uid, db: mock_user)
    gear_items = [
        _MockGear(gear_id=3, brand=None, model=None, nickname="Unbranded"),
    ]
    monkeypatch.setattr(bulk_import_utils.gears_crud, "get_gear_user", lambda uid, db: gear_items)

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result is not None
    assert result["Unbranded"] == [3]


def test_gear_dictionary_leading_whitespace(monkeypatch):
    """Smoosh key strips leading whitespace from brand/model/nickname."""
    mock_user = Mock(id=42)
    monkeypatch.setattr(bulk_import_utils.users_crud, "get_user_by_id", lambda uid, db: mock_user)
    gear_items = [
        _MockGear(gear_id=4, brand=" Nike", model=" Pegasus", nickname=" Pegasus"),
    ]
    monkeypatch.setattr(bulk_import_utils.gears_crud, "get_gear_user", lambda uid, db: gear_items)

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result is not None
    assert result["Nike Pegasus Pegasus"] == [4]


def test_gear_dictionary_no_user(monkeypatch):
    """Returns None when user does not exist."""
    monkeypatch.setattr(bulk_import_utils.users_crud, "get_user_by_id", lambda uid, db: None)

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result is None


def test_gear_dictionary_no_gear(monkeypatch):
    """Returns None when user has no gear."""
    mock_user = Mock(id=42)
    monkeypatch.setattr(bulk_import_utils.users_crud, "get_user_by_id", lambda uid, db: mock_user)
    monkeypatch.setattr(bulk_import_utils.gears_crud, "get_gear_user", lambda uid, db: None)

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result is None


# --- queue_bulk_export_activities_for_import --------------------------------


def _queue_setup(monkeypatch, tmp_path, names):
    """Point the importer at a temp folder with empty files of the given names."""
    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    for name in names:
        (activities_dir / name).write_bytes(b"x")
    monkeypatch.setattr(bulk_import_utils.core_config, "STRAVA_BULK_IMPORT_ACTIVITIES_DIR", str(activities_dir))
    monkeypatch.setattr(bulk_import_utils.core_config, "STRAVA_BULK_IMPORT_MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setattr(bulk_import_utils.file_uploads, "validate_local_file", AsyncMock())
    monkeypatch.setattr(bulk_import_utils.time, "sleep", lambda _s: None)


def _run_queue(db):
    return bulk_import_utils.queue_bulk_export_activities_for_import(
        1, Mock(), db, {}, {"Shoe": [1]}, "2026-10-23T00:00:00+00:00"
    )


def test_one_failing_file_does_not_stop_the_rest(monkeypatch, tmp_path):
    names = ["1.gpx", "2.tcx", "3.gpx"]
    _queue_setup(monkeypatch, tmp_path, names)
    seen: list[str] = []

    async def fake_parse(_user_id, file_path, *_args, **_kwargs):
        name = os.path.basename(file_path)
        seen.append(name)
        if name == "2.tcx":
            # What a TCX without a start time did in the real import.
            raise AttributeError("'NoneType' object has no attribute 'tzinfo'")

    monkeypatch.setattr(bulk_import_utils.activities_utils, "parse_and_store_activity_from_file", fake_parse)
    db = Mock()

    _run_queue(db)

    assert sorted(seen) == sorted(names)
    db.rollback.assert_called_once()


def test_every_file_is_attempted_when_all_succeed(monkeypatch, tmp_path):
    _queue_setup(monkeypatch, tmp_path, ["1.gpx", "2.gpx"])
    seen: list[str] = []

    async def fake_parse(_user_id, file_path, *_args, **_kwargs):
        seen.append(os.path.basename(file_path))

    monkeypatch.setattr(bulk_import_utils.activities_utils, "parse_and_store_activity_from_file", fake_parse)
    db = Mock()

    _run_queue(db)

    assert sorted(seen) == ["1.gpx", "2.gpx"]
    db.rollback.assert_not_called()
