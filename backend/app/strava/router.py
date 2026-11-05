import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security, status
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import core.database as core_database
import core.logger as core_logger
import strava.bulk_import_utils as strava_bulk_import_utils
import websocket.manager as websocket_manager

# Define the API router
router = APIRouter()

# Define the thread pool executor with 2 workers
executor = ThreadPoolExecutor(max_workers=2)


@router.post("/import/activities", status_code=201)
async def import_activities_and_media_from_strava_export(
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    ws_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
):
    try:
        # Get time of import initiation to pass to function for recording in import_data dictionary, ensuring all activities imported via this bulk import action share an identical import time.
        import_time = datetime.now(UTC).isoformat()
        core_logger.print_to_log_and_console(f"Strava bulk import: Initiated at {import_time}.", "info")

        # Parse activities data from activities.csv into a dictionary
        strava_activities_dict = strava_bulk_import_utils.iterate_over_activities_csv()

        if strava_activities_dict is None:
            core_logger.print_to_log_and_console(
                "ABORTING IMPORT: Aborting strava bulk import due to improperly parsed CSV.", "error"
            )
            return {"Strava import ABORTED due to lack of, or improperly parsed, activities.csv file."}

        # Queue files for processing. The Strava export's gear column is ignored: Yamabiko has no gear.
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            executor,
            partial(
                strava_bulk_import_utils.queue_bulk_export_activities_for_import,
                token_user_id,
                ws_manager,
                db,
                strava_activities_dict,
                import_time,
            ),
        )

        # Log a success message that explains processing will continue elsewhere.
        core_logger.print_to_log_and_console(
            "Strava bulk import initiated. Processing of files will continue in the background."
        )

        # Return a success message
        return {"Strava bulk import initiated. Processing of files will continue in the background."}
    except Exception as err:
        # Log the exception
        core_logger.print_to_log_and_console(f"Error in strava_bulk_import: {err}", "error")
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
