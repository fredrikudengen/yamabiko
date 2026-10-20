"""Get a valid Google Health access token for a user, refreshing it when needed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

import core.config as core_config
import core.cryptography as core_cryptography
import core.logger as core_logger
import google_health.crud as google_health_crud
import google_health.oauth as google_health_oauth

# Refresh a little early so a token never expires in the middle of a sync.
REFRESH_MARGIN = timedelta(minutes=5)


def is_configured() -> bool:
    """True when the OAuth client id and secret are set."""
    settings = core_config.settings
    return bool(settings.GOOGLE_HEALTH_CLIENT_ID and settings.GOOGLE_HEALTH_CLIENT_SECRET)


def redirect_uri() -> str:
    """The redirect URI registered with Google for this server."""
    settings = core_config.settings
    if settings.GOOGLE_HEALTH_REDIRECT_URI:
        return settings.GOOGLE_HEALTH_REDIRECT_URI
    return f"{settings.ENDURAIN_HOST.rstrip('/')}{core_config.ROOT_PATH}/googlehealth/callback"


async def get_valid_access_token(
    user_id: int, db: Session, http: httpx.AsyncClient | None = None, now: datetime | None = None
) -> str | None:
    """A usable access token, or None when the account is not linked.

    Refreshes and stores a new access token when the stored one is near expiry.
    If Google rejects the refresh token (``invalid_grant``: revoked, or expired
    after 7 days in Testing mode) the account is unlinked so the user can link
    again, and None is returned. Other failures (network, 5xx) leave the stored
    tokens alone and also return None, so the next scheduled run retries.
    """
    row = google_health_crud.get_integrations(user_id, db)
    if row is None or not row.googlehealth_refresh_token:
        return None
    if not is_configured():
        core_logger.print_to_log(
            f"User {user_id}: Google Health is linked but the OAuth client is not configured", "warning"
        )
        return None

    now = now or datetime.now(UTC)
    expires = google_health_crud.expires_at(row)
    access_token = core_cryptography.decrypt_token_fernet(row.googlehealth_token)
    if access_token and expires and expires - now > REFRESH_MARGIN:
        return access_token

    refresh_token = core_cryptography.decrypt_token_fernet(row.googlehealth_refresh_token)
    settings = core_config.settings
    try:
        tokens = await google_health_oauth.refresh_access_token(
            refresh_token, settings.GOOGLE_HEALTH_CLIENT_ID, settings.GOOGLE_HEALTH_CLIENT_SECRET, http
        )
    except google_health_oauth.InvalidGrantError:
        core_logger.print_to_log(
            f"User {user_id}: Google Health refresh token is no longer valid; unlinking. The user must link again",
            "warning",
        )
        google_health_crud.unlink(user_id, db)
        return None
    except google_health_oauth.GoogleHealthOAuthError as err:
        core_logger.print_to_log(f"User {user_id}: Could not refresh Google Health token: {err}", "error", exc=err)
        return None

    google_health_crud.store_refreshed_token(user_id, tokens, db)
    return tokens.access_token
