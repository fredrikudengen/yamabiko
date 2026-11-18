"""Turning uploaded photos into something every browser shows, and small copies for the grid.

* **HEIC and WebP become JPEG.** Phones save HEIC, which only Safari shows, and
  the upload checks accept JPEG and PNG only. The photo is decoded, turned the
  right way up from its EXIF orientation, and re-encoded as JPEG *before* the
  usual checks, so what is checked is also what is stored.
* **Thumbnails.** Next to each photo, ``<name>.thumb.jpg``: at most
  ``THUMBNAIL_SIZE`` pixels on the long side, for the photo grid. A photo
  stored before thumbnails existed gets one the first time it is listed.
"""

from __future__ import annotations

import io
from pathlib import Path, PurePosixPath

import pillow_heif
from PIL import Image, ImageOps

pillow_heif.register_heif_opener()

# Formats a browser may not show, converted to JPEG on upload.
CONVERTED_EXTENSIONS: frozenset[str] = frozenset({".heic", ".heif", ".webp"})

# Long side of a thumbnail, in pixels: sharp in a grid cell on a phone's screen.
THUMBNAIL_SIZE = 640
THUMBNAIL_QUALITY = 80
CONVERTED_QUALITY = 90
THUMBNAIL_SUFFIX = ".thumb.jpg"

# Pillow refuses images above this many pixels, against decompression bombs.
Image.MAX_IMAGE_PIXELS = 80_000_000


class UnreadablePhotoError(ValueError):
    """The upload is not a photo that can be read."""


def needs_conversion(filename: str | None) -> bool:
    """Whether an upload is in a format that is turned into JPEG first."""
    return PurePosixPath(filename or "").suffix.lower() in CONVERTED_EXTENSIONS


def _rgb(image: Image.Image) -> Image.Image:
    """The image the right way up, without transparency, ready for JPEG."""
    upright = ImageOps.exif_transpose(image) or image
    if upright.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", upright.size, (255, 255, 255))
        rgba = upright.convert("RGBA")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return upright.convert("RGB")


def to_jpeg(data: bytes) -> bytes:
    """A photo in any format Pillow reads (with HEIC), as JPEG, the right way up.

    Raises:
        UnreadablePhotoError: When the bytes are not a readable photo.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            out = io.BytesIO()
            _rgb(image).save(out, format="JPEG", quality=CONVERTED_QUALITY, optimize=True)
    except (OSError, ValueError, Image.DecompressionBombError) as err:
        raise UnreadablePhotoError(str(err)) from err
    return out.getvalue()


def jpeg_name(filename: str | None) -> str:
    """The upload's name with a ``.jpg`` extension instead of its own."""
    path = PurePosixPath(PurePosixPath(filename or "photo").name)
    return f"{path.stem or 'photo'}.jpg"


def thumbnail_path_for(media_path: str) -> str:
    """Where a photo's thumbnail is kept: next to it, ``<name>.thumb.jpg``."""
    path = Path(media_path)
    return str(path.with_name(path.stem + THUMBNAIL_SUFFIX))


def make_thumbnail(media_path: str) -> str | None:
    """Write the thumbnail for a stored photo; ``None`` when the photo cannot be read.

    Never raises: a missing thumbnail only means the grid loads the full photo.
    """
    target = thumbnail_path_for(media_path)
    try:
        with Image.open(media_path) as image:
            small = _rgb(image)
            small.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE))
            small.save(target, format="JPEG", quality=THUMBNAIL_QUALITY, optimize=True)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    return target


def existing_thumbnail(media_path: str) -> str | None:
    """The thumbnail's path when it has been written, else ``None``."""
    target = thumbnail_path_for(media_path)
    return target if Path(target).is_file() else None
