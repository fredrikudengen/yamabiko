"""HTTP endpoints for linking a Google Health account and triggering a sync.

Linking: the logged-in user calls ``POST /auth-url`` and opens the returned URL
in a browser. Google redirects the browser to ``GET /callback`` (no login
cookie needed; the one-time ``state`` identifies the user, as with Strava),
where the code is exchanged for tokens.
"""

import secrets
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Security, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import core.config as core_config
import core.database as core_database
import core.logger as core_logger
import google_health.activity_utils as google_health_activity_utils
import google_health.crud as google_health_crud
import google_health.oauth as google_health_oauth
import google_health.token_utils as google_health_token_utils
import websocket.manager as websocket_manager

router = APIRouter()

# Where the browser goes after the Google consent screen. The path is relative, so it
# resolves against the host the callback was opened on (the redirect URI's host).
SETTINGS_REDIRECT = "/settings/integrations?googlehealth="

_PAGE = (
    "<!doctype html><html lang='no'><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Yamabiko</title><body style='font-family:sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem'>"
    "<h1>{title}</h1><p>{message}</p></body></html>"
)


def _page(title: str, message: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(_PAGE.format(title=title, message=message), status_code=status_code)


@router.get("/status")
async def googlehealth_status(
    _validate_access_token: Annotated[Callable, Depends(auth_dependencies.validate_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """Whether the OAuth client is configured and whether this user is linked. Never returns tokens."""
    row = google_health_crud.get_integrations(token_user_id, db)
    expires = google_health_crud.expires_at(row) if row else None
    return {
        "configured": google_health_token_utils.is_configured(),
        "linked": bool(row and row.googlehealth_refresh_token),
        "access_token_expires_at": expires.isoformat() if expires else None,
        "redirect_uri": google_health_token_utils.redirect_uri(),
    }


@router.post("/auth-url")
async def googlehealth_auth_url(
    _validate_access_token: Annotated[Callable, Depends(auth_dependencies.validate_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """Start linking: returns the Google consent URL to open in a browser."""
    if not google_health_token_utils.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GOOGLE_HEALTH_CLIENT_ID and GOOGLE_HEALTH_CLIENT_SECRET are not set",
        )
    state = secrets.token_urlsafe(32)
    google_health_crud.set_state(token_user_id, state, db)
    url = google_health_oauth.build_auth_url(
        core_config.settings.GOOGLE_HEALTH_CLIENT_ID, google_health_token_utils.redirect_uri(), state
    )
    return {"url": url}


@router.get("/callback", response_model=None)
async def googlehealth_callback(
    db: Annotated[Session, Depends(core_database.get_db)],
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> HTMLResponse | RedirectResponse:
    """Where Google sends the browser after consent; sends it on to the settings page."""
    row = google_health_crud.get_integrations_by_state(state or "", db)
    if row is None:
        return _page("Ugyldig forespørsel", "Ukjent eller allerede brukt state. Start koblingen på nytt.", 400)
    user_id = row.user_id

    # The state is single-use, whatever happens next.
    google_health_crud.set_state(user_id, None, db)

    if error or not code:
        return RedirectResponse(SETTINGS_REDIRECT + "denied", status_code=status.HTTP_303_SEE_OTHER)

    settings = core_config.settings
    try:
        tokens = await google_health_oauth.exchange_code(
            code,
            settings.GOOGLE_HEALTH_CLIENT_ID,
            settings.GOOGLE_HEALTH_CLIENT_SECRET,
            google_health_token_utils.redirect_uri(),
        )
    except google_health_oauth.GoogleHealthOAuthError as err:
        core_logger.print_to_log(f"User {user_id}: Google Health linking failed: {err}", "error", exc=err)
        reason = "scopes" if "permissions" in str(err) else "error"
        return RedirectResponse(SETTINGS_REDIRECT + reason, status_code=status.HTTP_303_SEE_OTHER)

    google_health_crud.link(user_id, tokens, db)
    core_logger.print_to_log(f"User {user_id}: Google Health linked")
    return RedirectResponse(SETTINGS_REDIRECT + "linked", status_code=status.HTTP_303_SEE_OTHER)


@router.delete("/link", status_code=status.HTTP_204_NO_CONTENT)
async def googlehealth_unlink(
    _validate_access_token: Annotated[Callable, Depends(auth_dependencies.validate_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """Forget the stored tokens. (Access can also be revoked in the Google account settings.)"""
    google_health_crud.unlink(token_user_id, db)


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def googlehealth_sync(
    _validate_access_token: Annotated[Callable, Depends(auth_dependencies.validate_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    ws_manager: Annotated[websocket_manager.WebSocketManager, Depends(websocket_manager.get_websocket_manager)],
    db: Annotated[Session, Depends(core_database.get_db)],
    background_tasks: BackgroundTasks,
    days: int = google_health_activity_utils.DEFAULT_LOOKBACK_DAYS,
):
    """Import new exercises from the last ``days`` days in the background."""
    row = google_health_crud.get_integrations(token_user_id, db)
    if not (row and row.googlehealth_refresh_token):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Google Health is not linked")
    days = max(1, min(days, 60))
    background_tasks.add_task(_sync_in_background, token_user_id, days, ws_manager)
    return {"detail": f"Google Health sync of the last {days} days started"}


async def _sync_in_background(user_id: int, days: int, ws_manager: websocket_manager.WebSocketManager) -> None:
    # The request's session is closed when the response is sent, so use a new one.
    with core_database.SessionLocal() as db:
        await google_health_activity_utils.sync_user(user_id, days, ws_manager, db)
