"""Minimal client for the Google Health API (v4), the successor of the Fitbit Web API.

Only what the importer needs: list exercises in a date range, and download one
exercise as TCX. The OAuth flow and token refresh live elsewhere; this client
is given a valid access token.

Notes from testing against the real API:

- List filter: ``exercise.interval.civil_start_time >= "YYYY-MM-DD" AND
  exercise.interval.civil_start_time < "YYYY-MM-DD"``. Only ``>=``, ``<`` and
  ``AND`` work. The ``startTime``/``endTime`` examples in the Google
  documentation return 400.
- Rate limit: 300 requests per minute.
- The page size parameter name (``pageSize``) follows Google's list
  conventions and has not been verified against a live response.
"""

from __future__ import annotations

from datetime import date

import httpx

BASE_URL = "https://health.googleapis.com/v4/users/me"
EXERCISE_PATH = "dataTypes/exercise/dataPoints"
PAGE_SIZE = 25
TIMEOUT_S = 30.0
# Hard stop against a pagination loop that never ends.
MAX_PAGES = 40


class GoogleHealthAuthError(Exception):
    """The access token was rejected (expired, revoked or missing scopes)."""


class GoogleHealthClient:
    """Thin async wrapper around the exercise endpoints."""

    def __init__(self, access_token: str, http: httpx.AsyncClient | None = None) -> None:
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._http = http
        self._owns_http = http is None

    async def __aenter__(self) -> GoogleHealthClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=TIMEOUT_S)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError("GoogleHealthClient must be used as an async context manager")
        return self._http

    @staticmethod
    def _check(response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            raise GoogleHealthAuthError(f"Google Health API returned {response.status_code}")
        response.raise_for_status()

    @staticmethod
    def build_filter(start: date, end: date) -> str:
        """Filter for exercises starting on ``start`` up to (not including) ``end``."""
        return (
            f'exercise.interval.civil_start_time >= "{start.isoformat()}" '
            f'AND exercise.interval.civil_start_time < "{end.isoformat()}"'
        )

    async def list_exercises(self, start: date, end: date) -> list[dict]:
        """All exercise data points starting in ``[start, end)``, across pages."""
        data_points: list[dict] = []
        page_token: str | None = None
        for _ in range(MAX_PAGES):
            params = {"filter": self.build_filter(start, end), "pageSize": str(PAGE_SIZE)}
            if page_token:
                params["pageToken"] = page_token
            response = await self._client().get(f"{BASE_URL}/{EXERCISE_PATH}", params=params, headers=self._headers)
            self._check(response)
            body = response.json()
            data_points.extend(body.get("dataPoints") or [])
            page_token = body.get("nextPageToken")
            if not page_token:
                break
        return data_points

    async def download_tcx(self, exercise_id: str) -> bytes:
        """The exercise as a TCX file (per-second position, height, distance and heart rate)."""
        response = await self._client().get(
            f"{BASE_URL}/{EXERCISE_PATH}/{exercise_id}:exportExerciseTcx",
            params={"alt": "media"},
            headers=self._headers,
        )
        self._check(response)
        return response.content
