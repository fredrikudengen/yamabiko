"""Import of Google Health exercises as Yamabiko activities.

Same shape as ``garmin.activity_utils``: list the exercises in a date range,
skip the ones already stored, download each as TCX, parse it with Endurain's
own parser and store it. After parsing, ``overrides`` corrects distance,
elevation and timer time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

import activities.activity.schema as activities_schema
import activities.activity.utils as activities_utils
import core.config as core_config
import core.file_uploads as file_uploads
import core.logger as core_logger
import google_health.client as google_health_client
import google_health.crud as google_health_crud
import google_health.filters as google_health_filters
import google_health.overrides as google_health_overrides
import websocket.manager as websocket_manager

# The band syncs in batches, sometimes a day or two after the session, and a
# record can exist before the session has finished. Looking back a week and
# skipping what is already stored makes the import catch up on its own.
DEFAULT_LOOKBACK_DAYS = 7


def lookback_range(days: int = DEFAULT_LOOKBACK_DAYS, today: date | None = None) -> tuple[date, date]:
    """Date range ``[start, end)`` that covers the last ``days`` days including today."""
    today = today or datetime.now(UTC).date()
    return today - timedelta(days=days), today + timedelta(days=1)


async def import_exercise(
    data_point: dict,
    tcx_bytes: bytes,
    user_id: int,
    ws_manager: websocket_manager.WebSocketManager,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Store one exercise from its data point (JSON) and TCX bytes."""
    exercise_id = google_health_filters.exercise_id(data_point)
    if exercise_id is None:
        return None

    try:
        tcx_path = await file_uploads.save_validated_bytes(
            tcx_bytes,
            kind=file_uploads.UploadKind.ACTIVITY,
            upload_dir=core_config.settings.FILES_DIR,
            filename=f"googlehealth_{exercise_id}.tcx",
        )
    except Exception as err:
        core_logger.print_to_log(
            f"User {user_id}: Google Health TCX for {exercise_id} failed validation: {type(err).__name__}",
            "warning",
            exc=err,
        )
        return None

    def hook(parsed_info: dict) -> dict:
        return google_health_overrides.apply_google_health_overrides(parsed_info, data_point, str(tcx_path))

    stored = await activities_utils.parse_and_store_activity_from_file(
        token_user_id=user_id,
        file_path=str(tcx_path),
        websocket_manager=ws_manager,
        db=db,
        parsed_info_hook=hook,
    )
    if not stored:
        # The file is only moved out of FILES_DIR on success. Remove it, or the
        # next import would fail on the leftover file.
        core_logger.print_to_log(
            f"User {user_id}: Failed to parse Google Health exercise {exercise_id}; removing its file",
            "warning",
        )
        file_uploads.safe_remove_within(tcx_path, base_dir=core_config.settings.FILES_DIR)
    return stored


async def fetch_and_process_exercises(
    client: google_health_client.GoogleHealthClient,
    start: date,
    end: date,
    user_id: int,
    ws_manager: websocket_manager.WebSocketManager,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Import every new, finished, GPS-recorded exercise starting in ``[start, end)``.

    Raises:
        GoogleHealthAuthError: When the token is rejected; the caller decides
            how to tell the user to link the account again.
    """
    data_points = await client.list_exercises(start, end)

    imported: list[activities_schema.Activity] = []
    for data_point in data_points:
        reason = google_health_filters.skip_reason(data_point)
        exercise_id = google_health_filters.exercise_id(data_point)
        if reason is not None:
            core_logger.print_to_log(f"User {user_id}: Skipping Google Health exercise {exercise_id}: {reason}")
            continue
        if google_health_crud.activity_exists(exercise_id, user_id, db):
            core_logger.print_to_log(f"User {user_id}: Google Health exercise {exercise_id} already stored")
            continue

        try:
            tcx_bytes = await client.download_tcx(exercise_id)
            stored = await import_exercise(data_point, tcx_bytes, user_id, ws_manager, db)
        except google_health_client.GoogleHealthAuthError:
            raise
        except Exception as err:
            core_logger.print_to_log(
                f"User {user_id}: Error importing Google Health exercise {exercise_id}: {err}",
                "error",
                exc=err,
            )
            continue
        if stored:
            imported.extend(stored)

    return imported or None
