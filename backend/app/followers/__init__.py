"""
Followers: only the table model is left.

Yamabiko is single-user, so following, follow requests and their API are
gone. The model stays because the table does, and the activity queries still
read it for followers-only visibility.

Exports:
    - Models: Follower (ORM model)
"""

from .models import Follower as FollowerModel

__all__ = [
    "FollowerModel",
]
