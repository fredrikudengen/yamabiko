"""Database lookups specific to Google Health imports."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import core.cryptography as core_cryptography
import google_health.oauth as google_health_oauth
import users.users_integrations.models as integrations_models


def activity_exists(googlehealth_activity_id: str, user_id: int, db: Session) -> bool:
    """True when the user already has an activity imported from this exercise."""
    stmt = select(activities_models.Activity.id).where(
        activities_models.Activity.user_id == user_id,
        activities_models.Activity.googlehealth_activity_id == googlehealth_activity_id,
    )
    return db.execute(stmt).first() is not None


# --- OAuth state and token storage (columns on users_integrations) ----------


def get_integrations(user_id: int, db: Session) -> integrations_models.UsersIntegrations | None:
    """The user's integrations row, or None."""
    stmt = select(integrations_models.UsersIntegrations).where(integrations_models.UsersIntegrations.user_id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def _get_or_create_integrations(user_id: int, db: Session) -> integrations_models.UsersIntegrations:
    row = get_integrations(user_id, db)
    if row is None:
        row = integrations_models.UsersIntegrations(user_id=user_id)
        db.add(row)
        db.flush()
    return row


def get_integrations_by_state(state: str, db: Session) -> integrations_models.UsersIntegrations | None:
    """The row waiting for the OAuth callback with this ``state``, or None."""
    if not state:
        return None
    stmt = select(integrations_models.UsersIntegrations).where(
        integrations_models.UsersIntegrations.googlehealth_state == state
    )
    return db.execute(stmt).scalar_one_or_none()


def set_state(user_id: int, state: str | None, db: Session) -> None:
    """Store (or clear) the one-time ``state`` for a link attempt."""
    row = _get_or_create_integrations(user_id, db)
    row.googlehealth_state = state
    db.commit()


def link(user_id: int, tokens: google_health_oauth.TokenSet, db: Session) -> None:
    """Store tokens (encrypted) after a successful code exchange and clear the state."""
    row = _get_or_create_integrations(user_id, db)
    row.googlehealth_token = core_cryptography.encrypt_token_fernet(tokens.access_token)
    row.googlehealth_refresh_token = core_cryptography.encrypt_token_fernet(tokens.refresh_token)
    row.googlehealth_token_expires_at = tokens.expires_at
    row.googlehealth_state = None
    db.commit()


def store_refreshed_token(user_id: int, tokens: google_health_oauth.TokenSet, db: Session) -> None:
    """Store a refreshed access token. Google normally keeps the same refresh token."""
    row = _get_or_create_integrations(user_id, db)
    row.googlehealth_token = core_cryptography.encrypt_token_fernet(tokens.access_token)
    row.googlehealth_token_expires_at = tokens.expires_at
    if tokens.refresh_token:
        row.googlehealth_refresh_token = core_cryptography.encrypt_token_fernet(tokens.refresh_token)
    db.commit()


def unlink(user_id: int, db: Session) -> None:
    """Forget every Google Health token and state for the user."""
    row = get_integrations(user_id, db)
    if row is None:
        return
    row.googlehealth_state = None
    row.googlehealth_token = None
    row.googlehealth_refresh_token = None
    row.googlehealth_token_expires_at = None
    db.commit()


def linked_user_ids(db: Session) -> list[int]:
    """Users that have a refresh token stored."""
    stmt = select(integrations_models.UsersIntegrations.user_id).where(
        integrations_models.UsersIntegrations.googlehealth_refresh_token.is_not(None)
    )
    return list(db.execute(stmt).scalars())


def expires_at(row: integrations_models.UsersIntegrations) -> datetime | None:
    """Expiry as an aware datetime (SQLite drops the timezone on read)."""
    value = row.googlehealth_token_expires_at
    if value is not None and value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value
