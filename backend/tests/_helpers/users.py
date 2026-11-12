"""A complete user row for tests that need one in a real database."""

import users.users.models as users_models


def make_user(**extra) -> users_models.Users:
    """User 7 with every required column set; ``extra`` sets or overrides columns."""
    return users_models.Users(
        id=7,
        name="Fredrik",
        username="fredrik",
        email="f@example.com",
        preferred_language="nb",
        gender="unspecified",
        units="metric",
        access_type="regular",
        active=True,
        first_day_of_week="monday",
        currency="euro",
        email_verified=True,
        pending_admin_approval=False,
        **extra,
    )
