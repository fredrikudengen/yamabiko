import os

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import core.config as core_config
import core.logger as core_logger
import core.text_imports as core_text_imports
import gears.gear.crud as gears_crud
import gears.gear.schema as gears_schema


def iterate_over_bikes_csv() -> dict:
    """
    Parses a Strava bikes CSV file and returns its contents as a dictionary.

    The function looks for a CSV file specified by configuration settings, reads it, and constructs a dictionary where each key is the "Bike Name" from the CSV, and the value is a dictionary of the bike's attributes as provided in the CSV row.

    Returns:
        dict: A dictionary mapping bike names to their corresponding data from the CSV file.

    Raises:
        HTTPException: If the CSV file is missing, has invalid headers, or cannot be parsed.
    """
    # CSV file location
    bulk_import_dir = core_config.STRAVA_BULK_IMPORT_DIR
    bikes_file_name = core_config.STRAVA_BULK_IMPORT_BIKES_FILE
    bikes_file_path = os.path.join(bulk_import_dir, bikes_file_name)

    # Get file and parse it
    bikes_dict = {}
    try:
        if os.path.isfile(bikes_file_path):
            core_logger.print_to_log_and_console(
                f"{bikes_file_name} exists in the {bulk_import_dir} directory. Starting to process file."
            )
            for row in core_text_imports.read_bounded_csv(bikes_file_path):
                if ("Bike Name" not in row) or ("Bike Brand" not in row) or ("Bike Model" not in row):
                    core_logger.print_to_log_and_console(
                        f"Aborting bikes import: Proper headers not found in {bikes_file_name}.  File should have 'Bike Name', 'Bike Brand', and 'Bike Model'."
                    )
                    raise HTTPException(
                        status_code=status.HTTP_424_FAILED_DEPENDENCY,
                        detail="Invalid file. Proper headers not found in Strava bikes CSV file.",
                    )
                bikes_dict[row["Bike Name"]] = row
            core_logger.print_to_log_and_console(
                f"Strava bike gear csv file parsed and gear dictionary created. File was {len(bikes_dict)} rows long, ignoring header row."
            )
            return bikes_dict
        core_logger.print_to_log_and_console(f"No {bikes_file_name} file located in the {bulk_import_dir} directory.")
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="No Strava bikes CSV file found for import.",
        )
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        core_logger.print_to_log_and_console(f"Error attempting to open {bikes_file_path} file:  {err}", "error")
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Error parsing Strava bikes CSV file.",
        ) from err


def iterate_over_shoes_csv() -> list:
    """
    Parses a Strava shoes CSV file and returns its contents as a list.
    Why a list?  Strava shoes files do not have anything that can be used as a key (unlike Strava bikes files, where nickname is required and unique)

    The function looks for a CSV file specified by configuration settings, reads it, and constructs a list where each item a dictionary of the shoe's attributes as provided in the CSV row.

    Returns:
        list: A list of shoe data obtained from the CSV file.

    Raises:
        HTTPException: If the CSV file is missing, has invalid headers, or cannot be parsed.
    """
    # CSV file location
    bulk_import_dir = core_config.STRAVA_BULK_IMPORT_DIR
    shoesfilename = core_config.STRAVA_BULK_IMPORT_SHOES_FILE
    shoes_file_path = os.path.join(bulk_import_dir, shoesfilename)

    # Get file and parse it
    shoes_list = []  # Using a list for shoes, as there is no unique value to use as a dictionary key like with bikes
    try:
        if os.path.isfile(shoes_file_path):
            core_logger.print_to_log_and_console(
                f"{shoesfilename} exists in the {bulk_import_dir} directory. Starting to process file."
            )
            for row in core_text_imports.read_bounded_csv(shoes_file_path):
                if ("Shoe Name" not in row) or ("Shoe Brand" not in row) or ("Shoe Model" not in row):
                    core_logger.print_to_log_and_console(
                        f"Aborting shoes import: Proper headers not found in {shoesfilename}. File should have 'Shoe Name', 'Shoe Brand', and 'Shoe Model'."
                    )
                    raise HTTPException(
                        status_code=status.HTTP_424_FAILED_DEPENDENCY,
                        detail="Invalid file. Proper headers not found in Strava shoes CSV file.",
                    )
                shoes_list.append(row)
            core_logger.print_to_log_and_console(
                f"Strava {shoesfilename} file parsed and gear dictionary created. File was {len(shoes_list)} rows long, ignoring header row."
            )
            return shoes_list
        core_logger.print_to_log_and_console(f"No {shoesfilename} file located in the {bulk_import_dir} directory.")
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="No Strava shoes CSV file found for import.",
        )
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        core_logger.print_to_log_and_console(f"Error attempting to open {shoes_file_path} file:  {err}", "error")
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Error parsing Strava shoes CSV file.",
        ) from err


def transform_csv_bike_gear_to_schema_gear(bikes_dict: dict, token_user_id: int) -> list[gears_schema.GearCreate]:
    """
    Transforms a dictionary of bike data (parsed from CSV) into a list of Gear schema objects.

    Args:
        bikes_dict (dict): A dictionary where each key is a bike nickname and each value is a dictionary
            containing bike attributes such as "Bike Brand" and "Bike Model".
        token_user_id (int): The user ID to associate with each Gear object.

    Returns:
        list[gears_schema.GearCreate]: A list of Gear schema objects created from the input bike data.
    """
    gears = []
    for bike in bikes_dict:
        new_gear = gears_schema.GearCreate(
            user_id=token_user_id,
            brand=bikes_dict[bike]["Bike Brand"].strip() if bikes_dict[bike]["Bike Brand"] else None,
            model=bikes_dict[bike]["Bike Model"].strip() if bikes_dict[bike]["Bike Model"] else None,
            nickname=bike.strip(),
            gear_type=gears_schema.GearType.BIKE,
            active=True,
            strava_gear_id=None,
        )
        gears.append(new_gear)
    return gears


def transform_csv_shoe_gear_to_schema_gear(
    shoes_list: list, token_user_id: int, db: Session
) -> list[gears_schema.GearCreate]:
    """
    Transforms a list of shoe data (parsed from CSV) into a list of Gear schema objects.
    Renames any name-less shoes to a default name plus a unique number, as Strava allows name-less shoes, but Endurain does not.

    Args:
        shoes_list (list): A list where each row is a single shoe's data, parsed from the strava shoe csv
        token_user_id (int): The user ID to associate with each Gear object.
        db (session): Database session

    Returns:
        list[gears_schema.GearCreate]: A list of Gear schema objects created from the input shoe data.
    """
    gears = []
    newnumber = 1
    shoe_name = ""
    for shoerow in shoes_list:
        # 1 - Check for nameless shoes and add a novel name. Why?  Because Strava allows nameless shoes, but Endurain does not.
        if (
            shoerow["Shoe Name"] is None
            or shoerow["Shoe Name"] == ""
            or shoerow["Shoe Name"].replace("+", " ").strip() == ""
        ):
            # Shoe name is blank or parses to blank; assign a new, non-duplicated name.
            proposed_name_is_already_present = True
            while proposed_name_is_already_present:
                proposed_name = core_config.STRAVA_BULK_IMPORT_SHOES_UNNAMED_SHOE + str(newnumber)
                gear_check = gears_crud.get_gear_user_by_nickname(token_user_id, proposed_name, db)
                if gear_check is not None:
                    newnumber += 1
                else:
                    proposed_name_is_already_present = False
                    shoe_name = proposed_name
                    core_logger.print_to_log_and_console(
                        f"Shoe name was blank, it has been updated to: {proposed_name}"
                    )
                    newnumber += 1  # Iterate the number so the next unnamed shoe does not duplicate this one.
        else:
            # CSV data has a name for the shoe, use CSV's data as the name.
            shoe_name = shoerow["Shoe Name"].strip()

        # 2 - Add (possibly renamed) gear item to the list of gear to be added.
        new_gear = gears_schema.GearCreate(
            user_id=token_user_id,
            brand=shoerow["Shoe Brand"].strip() if shoerow["Shoe Brand"] else None,
            model=shoerow["Shoe Model"].strip() if shoerow["Shoe Model"] else None,
            nickname=shoe_name,
            gear_type=gears_schema.GearType.SHOES,
            active=True,
            strava_gear_id=None,
        )
        gears.append(new_gear)
    return gears
