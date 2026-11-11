"""ORM model for the written feedback on an activity."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class ActivityFeedback(Base):
    """
    The feedback text written for one activity (at most one per activity).

    The text describes the tour as the numbers stood when it was written: a
    faster tour later does not change it. ``facts`` is exactly what the model
    was given, so a text can always be checked against its numbers.

    Attributes:
        activity_id: The activity the text is about.
        text: The feedback, plain text.
        model: The model that wrote it.
        facts_hash: Hash of the facts, prompt and model the text was made from.
        facts: The facts the model was given.
        created_at: When the text was written.
    """

    __tablename__ = "activity_feedback"

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Activity the feedback is about",
    )
    text: Mapped[str] = mapped_column(Text, nullable=False, comment="The feedback, plain text")
    model: Mapped[str] = mapped_column(String(100), nullable=False, comment="Model that wrote the text")
    facts_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="Hash of facts, prompt and model")
    facts: Mapped[dict] = mapped_column(JSON, nullable=False, comment="The facts the model was given")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
