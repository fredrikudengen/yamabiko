"""Tests for the users management router endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth.dependencies as auth_dependencies
import core.database as core_database
import users.users.dependencies as users_dependencies


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def auth_app(mock_db):
    app = FastAPI()
    from users.users.router import router

    app.include_router(router, prefix="/users")

    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[core_database.get_db] = lambda: mock_db

    return app


def _make_mock_user(user_id, **overrides):
    """Build a mock user object compatible with UsersRead.model_validate."""
    user = MagicMock()
    user.id = user_id
    user.name = overrides.get("name", f"User {user_id}")
    user.username = overrides.get("username", f"user{user_id}")
    user.email = overrides.get("email", f"user{user_id}@example.com")
    user.city = overrides.get("city")
    user.birthdate = overrides.get("birthdate")
    user.preferred_language = overrides.get("preferred_language", "en")
    user.gender = overrides.get("gender", "unspecified")
    user.units = overrides.get("units", "metric")
    user.height = overrides.get("height")
    user.max_heart_rate = overrides.get("max_heart_rate")
    user.first_day_of_week = overrides.get("first_day_of_week", "monday")
    user.currency = overrides.get("currency", "euro")
    user.photo_path = overrides.get("photo_path")
    user.active = overrides.get("active", True)
    user.access_type = overrides.get("access_type", "regular")
    user.mfa_enabled = overrides.get("mfa_enabled", False)
    user.email_verified = overrides.get("email_verified", True)
    user.pending_admin_approval = overrides.get("pending_admin_approval", False)
    user.external_auth_count = overrides.get("external_auth_count", 0)
    return user


class TestReadUsersId:
    @patch("users.users.router.users_crud.get_user_by_id")
    def test_found(self, mock_get, mock_db, auth_app):
        auth_app.dependency_overrides[users_dependencies.validate_user_id] = lambda: None
        client = TestClient(auth_app)

        mock_get.return_value = _make_mock_user(42, name="ID User")

        response = client.get("/users/id/42")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 42
        assert data["name"] == "ID User"

    @patch("users.users.router.users_crud.get_user_by_id")
    def test_not_found(self, mock_get, mock_db, auth_app):
        auth_app.dependency_overrides[users_dependencies.validate_user_id] = lambda: None
        client = TestClient(auth_app)

        mock_get.return_value = None

        response = client.get("/users/id/999")

        assert response.status_code == 200
        assert response.json() is None
