"""Response models for the tour feedback API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FeedbackOut(BaseModel):
    """The feedback on one tour, or why there is none.

    ``enabled`` is false when no API key is configured: the page then shows
    nothing at all. ``pending`` is true for a short while after import when the
    text is being written on its own, so the page knows to look again.
    """

    enabled: bool
    pending: bool
    text: str | None
    model: str | None
    created_at: datetime | None
