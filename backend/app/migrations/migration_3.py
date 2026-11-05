"""
Migration 3: back-fill laps, steps, and sets for all activities.

Processes every existing activity from FIT/GPX files or Strava and populates
the laps, workout steps, and sets tables.
"""

import glob
import os

import fitdecode
from sqlalchemy.orm import Session

import activities.activity.crud as activities_crud
import activities.activity.models as activities_models
import activities.activity_file_import.utils_fit as fit_utils
import activities.activity_file_import.utils_gpx as gpx_utils
import activities.activity_laps.crud as activity_laps_crud
import activities.activity_sets.crud as activity_sets_crud
import activities.activity_streams.constants as activity_streams_constants
import activities.activity_streams.crud as activity_streams_crud
import activities.activity_workout_steps.crud as activity_workout_steps_crud
import core.config as core_config
import core.logger as core_logger
import migrations.crud as migrations_crud
from activities.activity_exercise_titles import (
    crud as activity_exercise_titles_crud,
)


def process_migration_3(db: Session) -> None:
    """
    Run migration 3 for all existing activities.

    Args:
        db: Active database session.

    Returns:
        None.

    Raises:
        None — errors are logged; the migration flag is not
        set when any activity fails to process.
    """
    core_logger.print_to_log_and_console("Started migration 3")

    activities_processed_with_no_errors = True

    try:
        activities = activities_crud.get_all_activities_no_serialize(db)
    except Exception as err:
        core_logger.print_to_log_and_console(
            f"Migration 3 - Error fetching activities: {err}",
            "error",
            exc=err,
        )
        return

    if activities:
        for activity in activities:
            try:
                if activity.strava_activity_id is None:
                    # check if activity file exists. Fetching a missing file
                    # from Garmin Connect is gone with the Garmin integration.
                    activity_fit_file_path = find_activity_fit_file(activity.id)
                    processed_dir = core_config.FILES_PROCESSED_DIR
                    activity_gpx_file_path = os.path.join(
                        processed_dir,
                        f"{activity.id}.gpx",
                    )

                    # if .gpx and .fit for activity do not exist, skip
                    if (
                        activity_fit_file_path is None or not os.path.exists(activity_fit_file_path)
                    ) and not os.path.exists(activity_gpx_file_path):
                        core_logger.print_to_log_and_console(
                            f"Migration 3 - Activity {activity.id}"
                            " does not have a file. Will process it"
                            " using activity streams.",
                            "info",
                        )
                        # Process the activity using streams
                        process_activity_using_streams(
                            activity,
                            db,
                        )
                    # if exists, process it
                    else:
                        if activity_fit_file_path is not None and os.path.exists(activity_fit_file_path):
                            # Process the .fit file
                            process_fit_file(
                                activity,
                                activity_fit_file_path,
                                db,
                            )
                        else:
                            # Process the .gpx activity
                            process_activity_using_streams(
                                activity,
                                db,
                            )
                else:
                    # Strava API activities used to fetch their laps from
                    # Strava; with the integration gone they use the streams.
                    process_activity_using_streams(activity, db)
            except Exception as err:
                activities_processed_with_no_errors = False
                core_logger.print_to_log_and_console(
                    f"Migration 3 - Failed to process activity {activity.id}: {err}",
                    "error",
                    exc=err,
                )

    # Mark migration as executed
    if activities_processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(3, db)
        except Exception as err:
            core_logger.print_to_log_and_console(
                f"Migration 3 - Failed to set migration as executed: {err}",
                "error",
                exc=err,
            )
            return
    else:
        core_logger.print_to_log_and_console(
            "Migration 3 failed to process all activities. Will try again later.",
            "error",
        )

    core_logger.print_to_log_and_console("Finished migration 3")


def find_activity_fit_file(activity_id: int) -> str | None:
    """
    Find the FIT file path for a given activity ID.

    Args:
        activity_id: The activity's primary-key ID.

    Returns:
        Absolute path to the FIT file, or None if not found.

    Raises:
        None.
    """
    processed_dir = core_config.FILES_PROCESSED_DIR

    # Try single activity file first
    single_path = os.path.join(processed_dir, f"{activity_id}.fit")
    if os.path.exists(single_path):
        return single_path

    # Then search through multi-activity files
    for filepath in glob.glob(os.path.join(processed_dir, "*.fit")):
        filename = os.path.basename(filepath)
        name_without_ext = os.path.splitext(filename)[0]
        activity_ids = name_without_ext.split("_")

        if str(activity_id) in activity_ids:
            return filepath

    # If not found
    return None


def process_fit_file(
    activity: activities_models.Activity,
    activity_fit_file_path: str,
    db: Session,
) -> None:
    """
    Parse a FIT file and persist its data to the database.

    Args:
        activity: ORM Activity instance.
        activity_fit_file_path: Absolute path to the FIT file.
        db: Active database session.

    Returns:
        None.

    Raises:
        Exception: Re-raised after logging on parse failure.
    """
    # Array to store sessions
    sessions = []

    # Array to store laps
    laps = []

    # Array to store workout steps
    workout_steps = []

    # Array to store exercise titles
    exercises_titles = []

    # Array to store sets
    sets = []

    core_logger.print_to_log_and_console(f"Migration 3 - Activity {activity.id} has a fit file. Will process it.")
    try:
        # Open the FIT file
        with open(activity_fit_file_path, "rb") as fit_file:
            fit_data = fitdecode.FitReader(fit_file)

            # Iterate over FIT messages
            for frame in fit_data:
                if isinstance(frame, fitdecode.FitDataMessage):
                    # Parse session data
                    if frame.name == "session":
                        sessions.append(fit_utils.parse_frame_session(frame))

                    # Parse lap data
                    if frame.name == "lap":
                        laps.append(fit_utils.parse_frame_lap(frame))

                    # Extract workout step data
                    if frame.name == "workout_step":
                        workout_steps.append(fit_utils.parse_frame_workout_step(frame))

                    # Extract exercise title data
                    if frame.name == "exercise_title":
                        exercises_titles.append(fit_utils.parse_frame_exercise_title(frame))

                    # Extract set data
                    if frame.name == "set":
                        sets.append(fit_utils.parse_frame_set(frame))
        # Store data in the database
        store_data_in_db(
            activity,
            sessions,
            laps,
            workout_steps,
            exercises_titles,
            sets,
            db,
        )
    except Exception as err:
        core_logger.print_to_log_and_console(
            f"Migration 3 - Failed to process activity {activity.id} file: {err}",
            "error",
            exc=err,
        )
        raise err


def process_activity_using_streams(
    activity: activities_models.Activity,
    db: Session,
) -> None:
    """
    Build laps from activity streams and persist to the database.

    Args:
        activity: ORM Activity instance.
        db: Active database session.

    Returns:
        None.

    Raises:
        Exception: Re-raised after logging on processing failure.
    """
    core_logger.print_to_log_and_console(f"Migration 3 - Activity {activity.id} has a gpx file. Will process it.")

    try:
        streams = activity_streams_crud.get_activity_streams(activity.id, activity.user_id, db)
        stream_map = {stream.stream_type: stream.stream_waypoints for stream in (streams or [])}

        laps = gpx_utils.generate_activity_laps(
            stream_map.get(activity_streams_constants.STREAM_TYPE_MAP) or [],
            stream_map.get(activity_streams_constants.STREAM_TYPE_ELEVATION) or [],
            stream_map.get(activity_streams_constants.STREAM_TYPE_POWER) or [],
            stream_map.get(activity_streams_constants.STREAM_TYPE_HR) or [],
            stream_map.get(activity_streams_constants.STREAM_TYPE_CADENCE) or [],
            stream_map.get(activity_streams_constants.STREAM_TYPE_SPEED) or [],
        )

        store_data_in_db(activity, [], laps, [], [], [], db)
    except Exception as err:
        core_logger.print_to_log_and_console(
            f"Migration 3 - Failed to process activity {activity.id} file: {err}",
            "error",
            exc=err,
        )
        raise


def store_data_in_db(
    activity: activities_models.Activity,
    sessions: list,
    laps: list,
    workout_steps: list,
    exercises_titles: list,
    sets: list,
    db: Session,
) -> None:
    """
    Persist FIT-file data (laps, steps, sets) to the database.

    Args:
        activity: ORM Activity instance.
        sessions: Parsed session records from the FIT file.
        laps: Parsed lap records from the FIT file.
        workout_steps: Parsed workout-step records.
        exercises_titles: Parsed exercise-title records.
        sets: Parsed set records from the FIT file.
        db: Active database session.

    Returns:
        None.

    Raises:
        None.
    """
    laps_to_store = []
    workout_steps_to_store = workout_steps if workout_steps else []
    exercises_titles_to_store = exercises_titles if exercises_titles else []
    sets_to_store = sets if sets else []

    if sessions and len(sessions) > 1:
        if laps:
            filtered_laps = []  # Temporary list to store filtered laps
            for lap in laps:
                start_time = activity.start_time
                end_time = activity.end_time
                lap_start_time = lap["start_time"]

                if start_time <= lap_start_time <= end_time:
                    # Append the lap to the temporary list
                    core_logger.print_to_log_and_console(
                        f"start_time: {start_time}, lap_start_time: {lap_start_time}, end_time: {end_time}"
                    )
                    filtered_laps.append(lap)

            # Extend laps_to_store with the filtered laps
            laps_to_store.extend(filtered_laps)
    else:
        laps_to_store = laps if laps else []

    # Create activity laps in the database
    if laps_to_store:
        activity_laps_crud.create_activity_laps(laps_to_store, activity.id, db)

    # Create activity workout steps in the database
    if workout_steps_to_store:
        activity_workout_steps_crud.create_activity_workout_steps(workout_steps_to_store, activity.id, db)

    # Create activity exercise titles in the database
    if exercises_titles_to_store:
        activity_exercise_titles_crud.create_activity_exercise_titles(exercises_titles_to_store, db)

    # Create activity sets in the database
    if sets_to_store:
        activity_sets_crud.create_activity_sets(sets_to_store, activity.id, db)

    core_logger.print_to_log_and_console(f"Migration 3 - Activity {activity.id} processed.")
