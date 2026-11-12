"""The user's heart-rate zone limits (``/api/v1/profile/hr_zones``).

Kept on the server so every device shows the same zones, and so the written
feedback on a tour can use them.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import core.database as core_database
import hr_zones.zones as hr_zones
import users.users.models as users_models

router = APIRouter()

_UserId = Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)]
_Db = Annotated[Session, Depends(core_database.get_db)]
_Validated = Annotated[Callable, Depends(auth_dependencies.validate_access_token)]


class ZoneLimitsOut(BaseModel):
    """The limits in use, and whether they are the defaults."""

    limits: list[int]
    is_default: bool


class ZoneLimitsIn(BaseModel):
    """New limits; ``null`` goes back to the defaults."""

    limits: list[int] | None


def _user(user_id: int, db: Session) -> users_models.Users:
    user = db.get(users_models.Users, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _out(user: users_models.Users) -> ZoneLimitsOut:
    stored = user.hr_zone_limits
    return ZoneLimitsOut(limits=list(hr_zones.limits_of(stored)), is_default=not hr_zones.is_valid(stored))


@router.get("", response_model=ZoneLimitsOut)
def get_zone_limits(_validate_access_token: _Validated, token_user_id: _UserId, db: _Db) -> ZoneLimitsOut:
    """The user's zone limits, or the defaults when none are set."""
    return _out(_user(token_user_id, db))


@router.put("", response_model=ZoneLimitsOut)
def put_zone_limits(
    body: ZoneLimitsIn, _validate_access_token: _Validated, token_user_id: _UserId, db: _Db
) -> ZoneLimitsOut:
    """Store new zone limits, or go back to the defaults with ``null``."""
    if body.limits is not None and not hr_zones.is_valid(body.limits):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"limits must be four whole numbers between {hr_zones.MIN_BPM} and {hr_zones.MAX_BPM}, increasing",
        )
    user = _user(token_user_id, db)
    user.hr_zone_limits = body.limits
    db.commit()
    return _out(user)
