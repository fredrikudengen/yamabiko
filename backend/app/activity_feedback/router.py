"""HTTP endpoints for the written feedback on a tour (``/api/v1/feedback``).

Only the owner of a tour reads or writes its feedback. The handlers are plain
``def`` so FastAPI runs them in its thread pool: writing a text waits on the
Claude API for a few seconds.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security, status
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import activity_feedback.client as feedback_client
import activity_feedback.models as feedback_models
import activity_feedback.schema as feedback_schema
import activity_feedback.service as feedback_service
import auth.dependencies as auth_dependencies
import core.database as core_database
import core.logger as core_logger

router = APIRouter()

_Validated = Annotated[Callable, Depends(auth_dependencies.validate_access_token)]
_CanRead = Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])]
_CanWrite = Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])]
_UserId = Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)]
_Db = Annotated[Session, Depends(core_database.get_db)]


def _own_activity(activity_id: int, user_id: int, db: Session) -> activities_models.Activity:
    activity = db.get(activities_models.Activity, activity_id)
    if activity is None or activity.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")
    return activity


def _out(
    activity: activities_models.Activity, stored: feedback_models.ActivityFeedback | None
) -> feedback_schema.FeedbackOut:
    return feedback_schema.FeedbackOut(
        enabled=feedback_client.is_enabled(),
        pending=feedback_service.is_pending(activity, stored is not None),
        text=stored.text if stored else None,
        model=stored.model if stored else None,
        created_at=stored.created_at if stored else None,
    )


@router.get("/activities/{activity_id}", response_model=feedback_schema.FeedbackOut)
def get_activity_feedback(
    activity_id: int, _validate_access_token: _Validated, _check_scopes: _CanRead, token_user_id: _UserId, db: _Db
) -> feedback_schema.FeedbackOut:
    """The stored feedback on one of the user's tours, and whether the feature is on."""
    activity = _own_activity(activity_id, token_user_id, db)
    return _out(activity, feedback_service.get_feedback(activity.id, db))


@router.post("/activities/{activity_id}", response_model=feedback_schema.FeedbackOut)
def write_activity_feedback(
    activity_id: int, _validate_access_token: _Validated, _check_scopes: _CanWrite, token_user_id: _UserId, db: _Db
) -> feedback_schema.FeedbackOut:
    """Write the feedback on a tour now, replacing any earlier text. Costs one API call."""
    activity = _own_activity(activity_id, token_user_id, db)
    if not feedback_client.is_enabled():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Feedback is not configured")
    try:
        stored = feedback_service.generate(activity, db, force=True)
    except feedback_client.FeedbackUnavailableError as err:
        db.rollback()
        core_logger.print_to_log(f"No feedback for activity {activity_id}: {err}", "warning")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"No feedback: {err}") from err
    return _out(activity, stored)
