"""CRUD operations for user integrations."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import users.users_integrations.models as user_integrations_models
import users.users_integrations.schema as user_integrations_schema

# Private internal helpers


def _transform_users_integrations(
    users: user_integrations_models.UsersIntegrations,
) -> user_integrations_schema.UsersIntegrationsRead:
    """
    Transform a user integrations instance to a Pydantic schema.

    Args:
        users: The user integrations ORM instance.

    Returns:
        The user integrations as a schema.
    """
    return user_integrations_schema.UsersIntegrationsRead.model_validate(users)


@core_decorators.handle_db_errors
def _get_user_integrations_model_by_user_id_or_404(
    user_id: int, db: Session
) -> user_integrations_models.UsersIntegrations:
    """
    Retrieve integrations for a specific user.

    Args:
        user_id: The ID of the user to fetch integrations for.
        db: SQLAlchemy database session.

    Returns:
        The UsersIntegrations ORM model for the user.

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database query fails.
    """
    # Get the user integrations by the user id
    stmt = select(user_integrations_models.UsersIntegrations).where(
        user_integrations_models.UsersIntegrations.user_id == user_id
    )
    db_user_integrations = db.execute(stmt).scalar_one_or_none()

    if not db_user_integrations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User integrations not found",
        )

    return db_user_integrations


# Public CRUD functions


@core_decorators.handle_db_errors
def get_user_integrations_by_user_id(
    user_id: int, db: Session
) -> user_integrations_schema.UsersIntegrationsRead | None:
    """
    Retrieve integrations for a specific user.

    Args:
        user_id: The ID of the user to fetch integrations for.
        db: SQLAlchemy database session.

    Returns:
        The UsersIntegrationsRead schema for the user.

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database query fails.
    """
    # Get the user integrations by the user id
    stmt = select(user_integrations_models.UsersIntegrations).where(
        user_integrations_models.UsersIntegrations.user_id == user_id
    )
    user_integrations = db.execute(stmt).scalar_one_or_none()
    return _transform_users_integrations(user_integrations) if user_integrations else None


@core_decorators.handle_db_errors
def create_user_integrations(user_id: int, db: Session) -> user_integrations_schema.UsersIntegrationsRead:
    """
    Create integration settings for a user.

    Args:
        user_id: The ID of the user to create integrations for.
        db: SQLAlchemy database session.

    Returns:
        The created UsersIntegrationsRead schema.

    Raises:
        HTTPException: 409 error if integrations already exist.
        HTTPException: 500 error if database operation fails.
    """
    try:
        # Create a new user integrations with model defaults
        user_integrations = user_integrations_models.UsersIntegrations(
            user_id=user_id,
        )

        # Add the user integrations to the database
        db.add(user_integrations)
        db.commit()
        db.refresh(user_integrations)

        # Return the user integrations
        return _transform_users_integrations(user_integrations)
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Integrations already exist for this user",
        ) from integrity_error


@core_decorators.handle_db_errors
def edit_user_integrations(
    user_integrations: user_integrations_schema.UsersIntegrationsUpdate,
    user_id: int,
    db: Session,
) -> user_integrations_schema.UsersIntegrationsRead:
    """
    Update user integration settings.

    Args:
        user_integrations: Schema with fields to update.
        user_id: The ID of the user to update.
        db: SQLAlchemy database session.

    Returns:
        The updated UsersIntegrations model.

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database operation fails.
    """
    # Get the user integrations from the database
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Get fields to update
    user_integrations_data = user_integrations.model_dump(exclude_unset=True, exclude={"user_id", "id"})
    # Update fields dynamically
    for key, value in user_integrations_data.items():
        setattr(db_user_integrations, key, value)

    # Commit the transaction
    db.commit()
    db.refresh(db_user_integrations)
    return _transform_users_integrations(db_user_integrations)
