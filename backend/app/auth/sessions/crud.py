"""CRUD operations for user sessions."""

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import CursorResult, delete, select
from sqlalchemy.orm import Session

import auth.sessions.models as auth_sessions_models
import auth.sessions.rotated_refresh_tokens.crud as auth_sessions_rotated_tokens_crud
import auth.sessions.schema as auth_sessions_schema
import core.decorators as core_decorators


@core_decorators.handle_db_errors
def get_user_sessions(
    user_id: int,
    db: Session,
) -> list[auth_sessions_models.UsersSessions]:
    """
    Retrieve all sessions for a user, ordered by creation date.

    Args:
        user_id: The ID of the user whose sessions to retrieve.
        db: SQLAlchemy database session.

    Returns:
        List of session objects, ordered by most recent first.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = (
        select(auth_sessions_models.UsersSessions)
        .where(auth_sessions_models.UsersSessions.user_id == user_id)
        .order_by(auth_sessions_models.UsersSessions.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


@core_decorators.handle_db_errors
def get_session_by_id(
    session_id: str,
    db: Session,
) -> auth_sessions_models.UsersSessions | None:
    """
    Retrieve a user session by ID.

    Args:
        session_id: The unique identifier of the session.
        db: SQLAlchemy database session.

    Returns:
        The session object if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = select(auth_sessions_models.UsersSessions).where(auth_sessions_models.UsersSessions.id == session_id)
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_session_by_id_not_expired(
    session_id: str,
    db: Session,
) -> auth_sessions_models.UsersSessions | None:
    """
    Retrieve a user session by ID if not expired.

    Args:
        session_id: The unique identifier of the session.
        db: SQLAlchemy database session.

    Returns:
        The session object if found and not expired, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = (
        select(auth_sessions_models.UsersSessions)
        .where(auth_sessions_models.UsersSessions.id == session_id)
        .where(auth_sessions_models.UsersSessions.expires_at > datetime.now(UTC))
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def create_session(
    session: auth_sessions_schema.UsersSessionsInternal,
    db: Session,
) -> auth_sessions_models.UsersSessions:
    """
    Create a new user session in the database.

    Args:
        session: The session data to be created.
        db: SQLAlchemy database session.

    Returns:
        The newly created session object.

    Raises:
        HTTPException: If database error occurs.
    """
    db_session = auth_sessions_models.UsersSessions(**session.model_dump())
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session


@core_decorators.handle_db_errors
def edit_session(
    session: auth_sessions_schema.UsersSessionsInternal,
    db: Session,
) -> None:
    """
    Update an existing user session with new field values.

    Args:
        session: Session data with fields to update.
        db: SQLAlchemy database session.

    Raises:
        HTTPException: If session not found (404) or database
            error occurs (500).
    """
    # Get the session from the database
    db_session = get_session_by_id(session.id, db)

    # Check if the session exists
    if not db_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session.id} not found",
        )

    # Update fields dynamically
    session_data = session.model_dump(exclude_unset=True)
    for key, value in session_data.items():
        setattr(db_session, key, value)

    db.commit()
    db.refresh(db_session)


@core_decorators.handle_db_errors
def update_session_csrf_hash(
    session_id: str,
    csrf_token_hash: str,
    db: Session,
) -> None:
    """
    Update only the CSRF token hash on an existing session.

    Used by the in-grace refresh replay path, which mints a fresh
    CSRF token for web clients without rotating the refresh token
    or bumping the rotation count.

    Args:
        session_id: The session to update.
        csrf_token_hash: New HMAC-SHA256 CSRF token hash.
        db: SQLAlchemy database session.

    Raises:
        HTTPException: If session not found (404) or database
            error occurs (500).
    """
    db_session = get_session_by_id(session_id, db)

    if not db_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    db_session.csrf_token_hash = csrf_token_hash
    db.commit()
    db.refresh(db_session)


@core_decorators.handle_db_errors
def delete_session(
    session_id: str,
    user_id: int,
    db: Session,
) -> None:
    """
    Delete a user session and its associated resources.

    Deletes rotated tokens and the session. Used when user
    explicitly logs out a session.

    Args:
        session_id: The unique identifier of the session to
            delete.
        user_id: The ID of the user associated with the session.
        db: SQLAlchemy database session.

    Raises:
        HTTPException: If session not found (404) or database
            error occurs (500).
    """
    # Get the session to retrieve token_family_id before deletion
    stmt = select(auth_sessions_models.UsersSessions).where(
        auth_sessions_models.UsersSessions.id == session_id,
        auth_sessions_models.UsersSessions.user_id == user_id,
    )
    session = db.execute(stmt).scalar_one_or_none()

    # Check if the session was found
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(f"Session {session_id} not found for user {user_id}"),
        )

    # Delete rotated tokens for this session's family
    auth_sessions_rotated_tokens_crud.delete_by_family(session.token_family_id, db)

    # Delete the session
    stmt = delete(auth_sessions_models.UsersSessions).where(
        auth_sessions_models.UsersSessions.id == session_id,
        auth_sessions_models.UsersSessions.user_id == user_id,
    )
    db.execute(stmt)

    db.commit()


@core_decorators.handle_db_errors
def delete_idle_sessions(
    cutoff_time: datetime,
    db: Session,
) -> int:
    """
    Delete sessions exceeding the idle timeout threshold.

    Removes sessions where last_activity_at is older than the
    cutoff time. Used by cleanup scheduler to remove inactive
    sessions.

    Args:
        cutoff_time: Sessions with last_activity_at before this
            time will be deleted.
        db: SQLAlchemy database session.

    Returns:
        Number of sessions deleted.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = delete(auth_sessions_models.UsersSessions).where(
        auth_sessions_models.UsersSessions.last_activity_at < cutoff_time
    )
    result: CursorResult[Any] = db.execute(stmt)
    db.commit()
    return result.rowcount


@core_decorators.handle_db_errors
def delete_sessions_by_family(
    token_family_id: str,
    db: Session,
) -> int:
    """
    Delete all sessions belonging to a token family.

    Used when token reuse is detected to invalidate entire
    session family as security measure.

    Args:
        token_family_id: The family ID to delete sessions for.
        db: SQLAlchemy database session.

    Returns:
        Number of sessions deleted.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = delete(auth_sessions_models.UsersSessions).where(
        auth_sessions_models.UsersSessions.token_family_id == token_family_id
    )
    result: CursorResult[Any] = db.execute(stmt)
    db.commit()
    return result.rowcount


@core_decorators.handle_db_errors
def delete_sessions_by_user(
    user_id: int,
    db: Session,
    commit: bool = True,
    exclude_session_id: str | None = None,
) -> int:
    """
    Delete all sessions for a user.

    Args:
        user_id: The ID of the user whose sessions should be
            deleted.
        db: SQLAlchemy database session.
        commit: Whether to commit the session deletion immediately.
        exclude_session_id: When provided, this session is left
            intact (e.g. the caller's current session so it is
            not logged out by a "revoke other sessions" action).

    Returns:
        Number of sessions deleted.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = delete(auth_sessions_models.UsersSessions).where(auth_sessions_models.UsersSessions.user_id == user_id)
    if exclude_session_id is not None:
        stmt = stmt.where(auth_sessions_models.UsersSessions.id != exclude_session_id)
    result = db.execute(stmt)
    if commit:
        db.commit()
    return result.rowcount
