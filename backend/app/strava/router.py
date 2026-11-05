import asyncio
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security, status
from sqlalchemy.orm import Session

import activities.activity.utils as activities_utils
import auth.dependencies as auth_dependencies
import core.config as core_config
import core.database as core_database
import core.logger as core_logger
import gears.gear.crud as gears_crud
import strava.bulk_import_utils as strava_bulk_import_utils
import strava.gear_utils as strava_gear_utils
import websocket.manager as websocket_manager

# Define the API router
router = APIRouter()

# Define the thread pool executor with 2 workers
executor = ThreadPoolExecutor(max_workers=2)


@router.post("/import/bikes", status_code=201)
async def import_bikes_from_strava_export(
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    try:
        # Log beginning of bike import
        core_logger.print_to_log("Entering bike importing function")

        # Get bikes from Strava export CSV file
        bikes_dict = strava_gear_utils.iterate_over_bikes_csv()

        # Transform bikes dict to list of Gear schema objects
        if bikes_dict:
            bikes = strava_gear_utils.transform_csv_bike_gear_to_schema_gear(bikes_dict, token_user_id)

            # Add bikes to the database
            if bikes:
                gears_crud.create_multiple_gears(bikes, token_user_id, db)

        # Define variables for moving the bikes file
        processed_dir = core_config.FILES_PROCESSED_DIR
        bulk_import_dir = core_config.STRAVA_BULK_IMPORT_DIR
        bikes_file_name = core_config.STRAVA_BULK_IMPORT_BIKES_FILE
        bikes_file_path = os.path.join(bulk_import_dir, bikes_file_name)

        # Move the bikes file to the processed directory
        activities_utils.move_file(processed_dir, bikes_file_name, bikes_file_path)
        core_logger.print_to_log_and_console(f"{bikes_file_name} moved to: {processed_dir}.")

        # Log completion of bike import
        core_logger.print_to_log_and_console("Bike import complete.")
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log_and_console(f"Error in import_bikes_from_strava_export: {err}", "error")
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.post("/import/shoes", status_code=201)
async def import_shoes_from_strava_export(
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    try:
        # Log beginning of shoe import
        core_logger.print_to_log("Entering shoe importing function")

        # Get shoes from Strava export CSV file
        shoes_list = strava_gear_utils.iterate_over_shoes_csv()

        core_logger.print_to_log_and_console("Shoe list created.", "debug")

        # Transform shoes list to list of Gear schema objects
        if shoes_list:
            shoes = strava_gear_utils.transform_csv_shoe_gear_to_schema_gear(shoes_list, token_user_id, db)

            core_logger.print_to_log_and_console("Shoe list converted to schema gear.", "debug")

            # Add shoes to the database
            if shoes:
                gears_crud.create_multiple_gears(shoes, token_user_id, db)

        core_logger.print_to_log_and_console("Shoes added to db.", "debug")

        # Define variables for moving the shoes file
        processed_dir = core_config.FILES_PROCESSED_DIR
        bulk_import_dir = core_config.STRAVA_BULK_IMPORT_DIR
        shoes_file_name = core_config.STRAVA_BULK_IMPORT_SHOES_FILE
        shoes_file_path = os.path.join(bulk_import_dir, shoes_file_name)

        # Move the shoes file to the processed directory and log it.
        activities_utils.move_file(processed_dir, shoes_file_name, shoes_file_path)
        core_logger.print_to_log_and_console(f"{shoes_file_name} moved to: {processed_dir}.")

        # Log completion of shoe import
        core_logger.print_to_log_and_console("Shoe import complete.")
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log_and_console(f"Error in import_shoes_from_strava_export: {err}", "error")
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


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

        # Create gear list here, so it does not have to be done separately for every single activity that is imported (AND because Strava has a wacked format for shoe naming in their export)
        users_existing_gear_nickname_to_id = strava_bulk_import_utils.create_gear_dictionary_for_bulk_import(
            token_user_id, db
        )

        # Queue files for processing.
        if users_existing_gear_nickname_to_id:
            loop = asyncio.get_event_loop()
            loop.run_in_executor(
                executor,
                partial(
                    strava_bulk_import_utils.queue_bulk_export_activities_for_import,
                    token_user_id,
                    ws_manager,
                    db,
                    strava_activities_dict,
                    users_existing_gear_nickname_to_id,
                    import_time,
                ),
            )

            # Log a success message that explains processing will continue elsewhere.
            core_logger.print_to_log_and_console(
                "Strava bulk import initiated. Processing of files will continue in the background."
            )
        else:
            core_logger.print_to_log_and_console(
                "ABORTING IMPORT: Aborting strava bulk import due to failure in creating gear nickname to id dictionary.",
                "error",
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
