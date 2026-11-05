"""
User integrations module for third-party service OAuth management.

This module provides CRUD operations and data models for user
integration settings. The Strava API and Garmin Connect links are gone;
their columns stay in the table.

Exports:
    - CRUD: get_user_integrations_by_user_id, create_user_integrations,
      edit_user_integrations
    - Schemas: UsersIntegrationsBase, UsersIntegrationsCreate,
      UsersIntegrationsRead, UsersIntegrationsUpdate
"""

from .crud import (
    create_user_integrations,
    edit_user_integrations,
    get_user_integrations_by_user_id,
)
from .schema import (
    UsersIntegrationsBase,
    UsersIntegrationsCreate,
    UsersIntegrationsRead,
    UsersIntegrationsUpdate,
)

__all__ = [
    "UsersIntegrationsBase",
    "UsersIntegrationsCreate",
    "UsersIntegrationsRead",
    "UsersIntegrationsUpdate",
    "create_user_integrations",
    "edit_user_integrations",
    "get_user_integrations_by_user_id",
]
