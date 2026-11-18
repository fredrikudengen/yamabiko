"""Tests for turning uploaded photos into JPEG and for the grid's thumbnails."""

import io
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

import activities.activity_media.images as images
from activities.activity_media.schema import ActivityMedia


def _photo(fmt: str, size=(1200, 800), mode="RGB", orientation: int | None = None) -> bytes:
    image = Image.new(mode, size, (200, 30, 30) if mode == "RGB" else (200, 30, 30, 128))
    out = io.BytesIO()
    if orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = orientation
        image.save(out, format=fmt, exif=exif)
    else:
        image.save(out, format=fmt)
    return out.getvalue()


class TestConversion:
    def test_heic_from_a_phone_becomes_jpeg(self):
        jpeg = images.to_jpeg(_photo("HEIF"))

        with Image.open(io.BytesIO(jpeg)) as image:
            assert image.format == "JPEG"
            assert image.size == (1200, 800)

    def test_a_transparent_webp_becomes_jpeg_on_white(self):
        jpeg = images.to_jpeg(_photo("WEBP", mode="RGBA"))

        with Image.open(io.BytesIO(jpeg)) as image:
            assert image.format == "JPEG"
            assert image.mode == "RGB"

    def test_the_photo_is_turned_the_right_way_up(self):
        # Orientation 6: the camera was turned; the stored pixels are on their side.
        jpeg = images.to_jpeg(_photo("JPEG", size=(1200, 800), orientation=6))

        with Image.open(io.BytesIO(jpeg)) as image:
            assert image.size == (800, 1200)

    def test_something_that_is_not_a_photo_is_refused(self):
        with pytest.raises(images.UnreadablePhotoError):
            images.to_jpeg(b"ftypheic but not really a photo")

    @pytest.mark.parametrize(
        ("name", "expected"),
        [("IMG_0001.HEIC", "IMG_0001.jpg"), ("../../etc/x.heif", "x.jpg"), (None, "photo.jpg"), (".webp", ".webp.jpg")],
    )
    def test_the_stored_name_gets_a_jpg_extension(self, name, expected):
        assert images.jpeg_name(name) == expected

    @pytest.mark.parametrize(
        ("name", "converted"), [("a.HEIC", True), ("a.heif", True), ("a.webp", True), ("a.jpg", False)]
    )
    def test_only_formats_browsers_may_not_show_are_converted(self, name, converted):
        assert images.needs_conversion(name) is converted


class TestThumbnails:
    def test_a_thumbnail_is_small_upright_and_next_to_the_photo(self, tmp_path):
        photo = tmp_path / "7_abc.jpg"
        photo.write_bytes(_photo("JPEG", size=(4000, 3000), orientation=6))

        thumbnail = images.make_thumbnail(str(photo))

        assert thumbnail == str(tmp_path / "7_abc.thumb.jpg")
        with Image.open(thumbnail) as image:
            assert max(image.size) == images.THUMBNAIL_SIZE
            assert image.size[1] > image.size[0]  # upright: portrait after orientation 6
        assert images.existing_thumbnail(str(photo)) == thumbnail

    def test_a_photo_that_cannot_be_read_gets_no_thumbnail(self, tmp_path):
        broken = tmp_path / "broken.jpg"
        broken.write_bytes(b"not an image")

        assert images.make_thumbnail(str(broken)) is None
        assert images.existing_thumbnail(str(broken)) is None


@pytest.fixture
def media_dir(tmp_path):
    with patch("core.config.settings.ACTIVITY_MEDIA_DIR", str(tmp_path)):
        yield tmp_path


def _client(mock_db):
    import activities.activity_media.router as router
    import auth.dependencies as auth_deps
    import core.database as core_db

    app = FastAPI()
    app.include_router(router.router, prefix="/activities_media")
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return TestClient(app)


class TestUpload:
    @patch("activities.activity_media.router.activity_crud.get_activity_by_id_from_user_id")
    @patch("activities.activity_media.router.activity_media_crud.create_activity_media")
    def test_a_heic_upload_is_stored_as_a_checked_jpeg_with_a_thumbnail(
        self, mock_create, mock_get_activity, mock_db, media_dir
    ):
        mock_get_activity.return_value = object()
        mock_create.side_effect = lambda activity_id, path, db: ActivityMedia(
            id=1, activity_id=activity_id, media_path=str(path), media_type=1
        )

        response = _client(mock_db).post(
            "/activities_media/upload/activity_id/7",
            files={"file": ("IMG_0001.HEIC", _photo("HEIF"), "image/heic")},
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["media_path"].endswith(".jpg")
        assert body["thumbnail_path"].endswith(".thumb.jpg")
        stored = sorted(p.name for p in media_dir.iterdir())
        assert len(stored) == 2
        assert all(name.startswith("7_") and name.endswith(".jpg") for name in stored)

    @patch("activities.activity_media.router.activity_crud.get_activity_by_id_from_user_id")
    @patch("activities.activity_media.router.activity_media_crud.create_activity_media")
    def test_a_heic_that_is_not_a_photo_is_refused(self, mock_create, mock_get_activity, mock_db, media_dir):
        mock_get_activity.return_value = object()

        response = _client(mock_db).post(
            "/activities_media/upload/activity_id/7",
            files={"file": ("IMG_0001.HEIC", b"not a photo", "image/heic")},
        )

        assert response.status_code == 400
        mock_create.assert_not_called()
        assert list(media_dir.iterdir()) == []


class TestListing:
    @patch("activities.activity_media.router.activity_media_crud.get_activity_media")
    def test_a_photo_from_before_thumbnails_gets_one_when_listed(self, mock_get, mock_db, media_dir):
        photo = media_dir / "7_old.jpg"
        photo.write_bytes(_photo("JPEG"))
        mock_get.return_value = [ActivityMedia(id=1, activity_id=7, media_path=str(photo), media_type=1)]

        (item,) = _client(mock_db).get("/activities_media/activity_id/7").json()

        assert item["thumbnail_path"] == str(media_dir / "7_old.thumb.jpg")
        assert (media_dir / "7_old.thumb.jpg").is_file()
