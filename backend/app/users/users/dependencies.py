"""User-specific request validation dependencies."""

import core.dependencies as core_dependencies


def validate_user_id(user_id: int) -> None:
    """
    Validate that user ID is positive.

    Args:
        user_id: User ID to validate.

    Returns:
        None

    Raises:
        HTTPException: 400 if user ID is invalid (≤ 0).
    """
    core_dependencies.validate_id(identifier=user_id, min_value=0, message="Invalid user ID")
