"""Writing, storing and reading the feedback on a tour."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import activity_feedback.client as feedback_client
import activity_feedback.facts as feedback_facts
import activity_feedback.models as feedback_models
import core.logger as core_logger
from core.database import SessionLocal

# How long after import a tour without a text counts as "being written", so the
# page knows to look again. The call itself takes a few seconds.
PENDING_WINDOW = timedelta(minutes=2)

# One at a time: an import of many files should not open many API calls at once.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="activity-feedback")


def get_feedback(activity_id: int, db: Session) -> feedback_models.ActivityFeedback | None:
    """The stored text for a tour, if one has been written."""
    return db.get(feedback_models.ActivityFeedback, activity_id)


def is_pending(activity: activities_models.Activity, has_text: bool) -> bool:
    """Whether a text is on its way for a tour that was just imported."""
    if has_text or not feedback_client.auto_enabled() or activity.created_at is None:
        return False
    created = activity.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return datetime.now(UTC) - created < PENDING_WINDOW


def generate(
    activity: activities_models.Activity, db: Session, *, force: bool = False
) -> feedback_models.ActivityFeedback:
    """Write the feedback for a tour and store it, replacing any earlier text.

    Args:
        activity: The tour.
        db: Database session.
        force: Ask the model even when a text for exactly these facts is stored.

    Returns:
        The stored feedback.

    Raises:
        FeedbackUnavailableError: When the model gave no usable text; nothing is changed.
    """
    facts: dict[str, Any] = feedback_facts.build_facts(activity, db)
    digest = feedback_client.facts_hash(facts)
    stored = get_feedback(activity.id, db)
    if stored is not None and stored.facts_hash == digest and not force:
        return stored

    text = feedback_client.write_feedback(facts)
    if stored is None:
        stored = feedback_models.ActivityFeedback(activity_id=activity.id)
        db.add(stored)
    stored.text = text
    stored.model = feedback_client.MODEL
    stored.facts_hash = digest
    stored.facts = facts
    stored.created_at = datetime.now(UTC)
    db.commit()
    return stored


def _generate_in_background(activity_id: int) -> None:
    """Write the text for a new tour on its own session; never raises."""
    try:
        with SessionLocal() as db:
            activity = db.get(activities_models.Activity, activity_id)
            if activity is not None:
                generate(activity, db)
    except feedback_client.FeedbackUnavailableError as err:
        core_logger.print_to_log(f"No feedback for activity {activity_id}: {err}", "warning")
    except Exception as err:
        core_logger.print_to_log(
            f"Writing feedback for activity {activity_id} failed: {type(err).__name__}", "error", exc=err
        )


def write_after_import(activity_id: int) -> None:
    """Queue a text for a tour that was just stored; returns at once and never raises.

    Does nothing unless a key is set and ``ACTIVITY_FEEDBACK_AUTO`` is on. Call it
    after the segment times and map cells are in, since the text builds on them.
    The import never waits for the API, and an API failure is only logged.
    """
    if not feedback_client.auto_enabled():
        return
    try:
        _executor.submit(_generate_in_background, activity_id)
    except RuntimeError as err:  # the pool is shutting down with the process
        core_logger.print_to_log(f"Could not queue feedback for activity {activity_id}: {err}", "warning")
