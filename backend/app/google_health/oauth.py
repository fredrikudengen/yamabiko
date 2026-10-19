"""OAuth 2.0 (authorization code flow) for the Google Health API.

Flow: the user's browser is sent to Google's consent page with
``access_type=offline`` and ``prompt=consent`` (so Google returns a refresh
token every time). Google redirects back to the callback with a ``code``,
which is exchanged for an access token (about an hour) and a refresh token.
The access token is renewed from the refresh token when it nears expiry.

Facts from testing against the real API:

- A token that also carries the ``cloud-platform`` scope is rejected with 403
  ``DISALLOWED_OAUTH_SCOPES``. ``include_granted_scopes`` is therefore not set,
  so scopes granted earlier to the same client are not merged in.
- In Testing mode the refresh token expires after 7 days; ``invalid_grant`` on
  refresh means the user has to link again.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - public endpoint, not a secret
SCOPES = (
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.location.readonly",
)
TIMEOUT_S = 30.0


class GoogleHealthOAuthError(Exception):
    """The OAuth exchange failed (bad request, network error or missing scope)."""


class InvalidGrantError(GoogleHealthOAuthError):
    """The refresh token or code is no longer valid; the user must link again."""


@dataclass(frozen=True)
class TokenSet:
    """Tokens from Google. ``refresh_token`` is None on a refresh (Google reuses the old one)."""

    access_token: str
    expires_at: datetime
    refresh_token: str | None
    scope: str


def build_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    """The Google consent URL to send the user's browser to."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _parse_tokens(body: dict, now: datetime) -> TokenSet:
    try:
        access_token = body["access_token"]
        expires_in = int(body.get("expires_in", 3600))
    except (KeyError, TypeError, ValueError) as err:
        raise GoogleHealthOAuthError("Unexpected token response from Google") from err
    return TokenSet(
        access_token=access_token,
        expires_at=now + timedelta(seconds=expires_in),
        refresh_token=body.get("refresh_token"),
        scope=body.get("scope", ""),
    )


async def _post_token(data: dict[str, str], http: httpx.AsyncClient | None) -> TokenSet:
    now = datetime.now(UTC)
    try:
        if http is None:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                response = await client.post(TOKEN_URL, data=data)
        else:
            response = await http.post(TOKEN_URL, data=data)
    except httpx.HTTPError as err:
        raise GoogleHealthOAuthError(f"Could not reach Google: {type(err).__name__}") from err

    if response.status_code != httpx.codes.OK:
        try:
            error = response.json().get("error")
        except ValueError:
            error = None
        if error == "invalid_grant":
            raise InvalidGrantError("Google rejected the grant (expired, revoked or already used)")
        raise GoogleHealthOAuthError(f"Google token endpoint returned {response.status_code} ({error or 'no error'})")
    return _parse_tokens(response.json(), now)


def missing_scopes(granted: str) -> list[str]:
    """Required scopes that are not in the space-separated ``granted`` string."""
    granted_set = set(granted.split())
    return [scope for scope in SCOPES if scope not in granted_set]


async def exchange_code(
    code: str, client_id: str, client_secret: str, redirect_uri: str, http: httpx.AsyncClient | None = None
) -> TokenSet:
    """Exchange the authorization code for tokens.

    Raises:
        GoogleHealthOAuthError: On any failure, or when the user did not grant
            every required scope (Google lets users untick scopes) or Google
            returned no refresh token.
    """
    tokens = await _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        http,
    )
    missing = missing_scopes(tokens.scope)
    if missing:
        raise GoogleHealthOAuthError("Not all required permissions were granted: " + ", ".join(missing))
    if not tokens.refresh_token:
        raise GoogleHealthOAuthError("Google returned no refresh token")
    return tokens


async def refresh_access_token(
    refresh_token: str, client_id: str, client_secret: str, http: httpx.AsyncClient | None = None
) -> TokenSet:
    """Get a new access token from the refresh token.

    Raises:
        InvalidGrantError: When the refresh token is expired or revoked.
    """
    return await _post_token(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        http,
    )
