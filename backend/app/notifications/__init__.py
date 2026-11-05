"""
Notifications: only the table model is left.

Yamabiko has no notifications; the API, the creation helpers and the
constants are gone. The model stays because the table does.

Exports:
    - Models: Notification (ORM model)
"""

from .models import Notification as NotificationModel

__all__ = [
    "NotificationModel",
]
