"""API routes for activity media uploads and management."""

import io
import uuid
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

import activities.activity.crud as activity_crud
import activities.activity.dependencies as activities_dependencies
import activities.activity_media.crud as activity_media_crud
import activities.activity_media.dependencies as activities_media_dependencies
import activities.activity_media.images as activity_media_images
import activities.activity_media.models as activity_media_models
import activities.activity_media.schema as activity_media_schema
import auth.dependencies as auth_dependencies
import core.config as core_config
import core.database as core_database
import core.file_uploads as core_file_uploads

# Define the API router
router = APIRouter()

# Allow-list of safe image extensions for activity media uploads.
_ALLOWED_MEDIA_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"})

# The largest photo that is converted, the same ceiling the upload checks use for images.
_MAX_CONVERTED_BYTES = 20 * 1024 * 1024


def _build_safe_media_filename(activity_id: int, original_name: str | None) -> str:
    """
    Build a path-traversal-safe storage filename for an uploaded media file.

    The original filename is reduced to its basename, sanitized, and its
    extension validated against an allow-list. A random suffix is appended
    to avoid collisions and information disclosure of the original name.

    Args:
        activity_id: ID of the activity the media belongs to.
        original_name: Original ``UploadFile.filename`` value.

    Returns:
        Safe filename of the form ``"{activity_id}_{uuid}{ext}"``.

    Raises:
        HTTPException:
            - 415 Unsupported Media Type: If the extension is not allowed.
    """
    # Strip any directory components (defends against "../", absolute
    # paths, and Windows-style paths that may slip through).
    base_name = PurePosixPath(original_name or "").name
    ext = PurePosixPath(base_name).suffix.lower()

    if ext not in _ALLOWED_MEDIA_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported media file type",
        )

    return f"{activity_id}_{uuid.uuid4().hex}{ext}"


async def _converted_to_jpeg(file: UploadFile, activity_id: int) -> tuple[UploadFile, str]:
    """The upload decoded and re-encoded as JPEG, with a matching stored name.

    Raises:
        HTTPException: 413 when the upload is larger than images may be, 400 when
            it is not a readable photo.
    """
    data = await file.read(_MAX_CONVERTED_BYTES + 1)
    if len(data) > _MAX_CONVERTED_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Photo is too large")
    try:
        jpeg = await run_in_threadpool(activity_media_images.to_jpeg, data)
    except activity_media_images.UnreadablePhotoError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not a readable photo") from err
    name = activity_media_images.jpeg_name(file.filename)
    converted = UploadFile(file=io.BytesIO(jpeg), filename=name, headers=Headers({"content-type": "image/jpeg"}))
    return converted, _build_safe_media_filename(activity_id, name)


def _with_thumbnail(media: activity_media_models.ActivityMedia) -> activity_media_schema.ActivityMedia:
    """The media as the API answers it, with its thumbnail when one has been written."""
    out = activity_media_schema.ActivityMedia.model_validate(media)
    if media.media_path:
        out.thumbnail_path = activity_media_images.existing_thumbnail(media.media_path)
    return out


def _with_thumbnails(media: list[activity_media_models.ActivityMedia]) -> list[activity_media_schema.ActivityMedia]:
    """The media with their thumbnails, writing any that are missing (photos from before thumbnails)."""
    for item in media:
        if item.media_path and activity_media_images.existing_thumbnail(item.media_path) is None:
            activity_media_images.make_thumbnail(item.media_path)
    return [_with_thumbnail(item) for item in media]


@router.get(
    "/activity_id/{activity_id}",
    response_model=list[activity_media_schema.ActivityMedia] | None,
)
async def read_activities_media_user(
    activity_id: int,
    _validate_id: Annotated[Callable, Depends(activities_dependencies.validate_activity_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> list[activity_media_schema.ActivityMedia] | None:
    """
    Retrieve activity media records for an activity owned by the user.

    Args:
        activity_id: Activity ID to fetch media for.
        _validate_id: Activity ID validation dependency.
        _check_scopes: Scope validation dependency.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        List of ActivityMedia records, or None if there are no media or
        the activity is not accessible to the user.
    """
    media = activity_media_crud.get_activity_media(activity_id, token_user_id, db)
    if media is None:
        return None
    return await run_in_threadpool(_with_thumbnails, list(media))


@router.post(
    "/upload/activity_id/{activity_id}",
    response_model=activity_media_schema.ActivityMedia,
    status_code=status.HTTP_201_CREATED,
)
async def upload_media(
    file: UploadFile,
    activity_id: int,
    _validate_id: Annotated[Callable, Depends(activities_dependencies.validate_activity_id)],
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["activities:write"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> activity_media_schema.ActivityMedia:
    """
    Upload an image file to associate with an activity.

    The file is validated by magic-number (not extension) and size limits
    via the centralized image upload helper, stored under the configured
    ``ACTIVITY_MEDIA_DIR``, and registered in the database.

    Args:
        file: Uploaded image file.
        activity_id: Activity ID the media belongs to.
        _validate_id: Activity ID validation dependency.
        _check_scopes: Scope validation dependency.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        The newly created ActivityMedia record.

    Raises:
        HTTPException:
            - 404 Not Found: If the activity is not owned by the user.
            - 400 Bad Request: If image validation fails.
            - 415 Unsupported Media Type: If the extension is rejected.
            - 409 Conflict: If a media with the same path already exists.
            - 500 Internal Server Error: For unexpected I/O or DB errors.
    """
    activity = activity_crud.get_activity_by_id_from_user_id(activity_id, token_user_id, db)
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    new_file_name = _build_safe_media_filename(activity_id, file.filename)

    # HEIC (iPhone) and WebP become JPEG first: browsers other than Safari cannot
    # show HEIC, and the checks below accept JPEG and PNG only. What is checked is
    # then exactly what is stored.
    if activity_media_images.needs_conversion(file.filename):
        file, new_file_name = await _converted_to_jpeg(file, activity_id)

    # SafeUploads validates magic number and size before writing to disk.
    file_path = await core_file_uploads.save_validated_upload(
        file,
        kind=core_file_uploads.UploadKind.IMAGE,
        upload_dir=core_config.settings.ACTIVITY_MEDIA_DIR,
        filename=new_file_name,
    )

    # The grid's small copy; a failure only means the grid loads the full photo.
    await run_in_threadpool(activity_media_images.make_thumbnail, str(file_path))

    try:
        return _with_thumbnail(activity_media_crud.create_activity_media(activity_id, file_path, db))
    except HTTPException:
        # Best-effort cleanup of the orphaned file on DB failure.
        await core_file_uploads.delete_files_by_pattern(core_config.settings.ACTIVITY_MEDIA_DIR, new_file_name)
        raise


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_activity_media(
    media_id: int,
    _validate_id: Annotated[Callable, Depends(activities_media_dependencies.validate_media_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """
    Delete an activity media record and remove its file from disk.

    Args:
        media_id: Activity media ID to delete.
        _validate_id: Media ID validation dependency.
        _check_scopes: Scope validation dependency.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException:
            - 404 Not Found: If the media or owning activity is missing.
            - 403 Forbidden: If the user does not own the activity.
            - 500 Internal Server Error: For database errors.
    """
    activity_media_crud.delete_activity_media(media_id, token_user_id, db)
