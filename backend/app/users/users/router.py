"""Looking up a user from the authenticated app.

Yamabiko is single-user: user administration (list, search, create, edit,
approve, password, photo, delete, identity-provider links) is gone. What is
left is the lookup the activity pages use to show an activity's owner.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security, status
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import core.database as core_database
import users.users.crud as users_crud
import users.users.dependencies as users_dependencies
import users.users.schema as users_schema

# Define the API router
router = APIRouter()


@router.get(
    "/id/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=users_schema.UsersRead | None,
)
def read_users_id(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> users_schema.UsersRead | None:
    """
    Get user by ID.

    Args:
        user_id: User ID to retrieve.
        _validate_id: User ID validation dependency.
        _check_scopes: Authorization check.
        db: Database session dependency.

    Returns:
        User if found, None otherwise.
    """
    return users_crud.get_user_by_id(user_id, db)
