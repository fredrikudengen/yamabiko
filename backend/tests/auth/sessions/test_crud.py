from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

import auth.sessions.crud as auth_sessions_crud
import auth.sessions.models as _auth_sessions_models
import auth.sessions.models as users_session_models
import auth.sessions.schema as users_session_schema


class TestGetUserSessions:
    """
    Test suite for get_user_sessions function.
    """

    def test_get_user_sessions_success(self, mock_db):
        """
        Test successful retrieval of sessions for a user.
        """
        # Arrange
        user_id = 1
        mock_session1 = MagicMock(spec=users_session_models.UsersSessions)
        mock_session2 = MagicMock(spec=users_session_models.UsersSessions)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            mock_session1,
            mock_session2,
        ]
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.get_user_sessions(user_id, mock_db)

        # Assert
        assert result == [mock_session1, mock_session2]
        mock_db.execute.assert_called_once()

    def test_get_user_sessions_empty(self, mock_db):
        """
        Test retrieval when no sessions exist for user.
        """
        # Arrange
        user_id = 1
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.get_user_sessions(user_id, mock_db)

        # Assert
        assert result == []

    def test_get_user_sessions_db_error(self, mock_db):
        """
        Test exception handling when database error occurs.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            auth_sessions_crud.get_user_sessions(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetSessionById:
    """
    Test suite for get_session_by_id function.
    """

    def test_get_session_by_id_success(self, mock_db):
        """
        Test successful retrieval of session by ID.
        """
        # Arrange
        session_id = "test-session-id"
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.get_session_by_id(session_id, mock_db)

        # Assert
        assert result == mock_session
        mock_db.execute.assert_called_once()

    def test_get_session_by_id_not_found(self, mock_db):
        """
        Test retrieval when session does not exist.
        """
        # Arrange
        session_id = "nonexistent-session"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.get_session_by_id(session_id, mock_db)

        # Assert
        assert result is None

    def test_get_session_by_id_db_error(self, mock_db):
        """
        Test exception handling when database error occurs.
        """
        # Arrange
        session_id = "test-session-id"
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            auth_sessions_crud.get_session_by_id(session_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetSessionByIdNotExpired:
    """
    Test suite for get_session_by_id_not_expired function.
    """

    def test_get_session_by_id_not_expired_success(self, mock_db):
        """
        Test successful retrieval of unexpired session.
        """
        # Arrange
        session_id = "test-session-id"
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.get_session_by_id_not_expired(session_id, mock_db)

        # Assert
        assert result == mock_session
        mock_db.execute.assert_called_once()

    def test_get_session_by_id_not_expired_expired_session(self, mock_db):
        """
        Test retrieval of expired session returns None.
        """
        # Arrange
        session_id = "expired-session-id"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.get_session_by_id_not_expired(session_id, mock_db)

        # Assert
        assert result is None

    def test_get_session_by_id_not_expired_db_error(self, mock_db):
        """
        Test exception handling when database error occurs.
        """
        # Arrange
        session_id = "test-session-id"
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            auth_sessions_crud.get_session_by_id_not_expired(session_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestCreateSession:
    """
    Test suite for create_session function.
    """

    def test_create_session_success(self, mock_db):
        """
        Test successful session creation.
        """
        # Arrange
        now = datetime.now(UTC)
        session_data = users_session_schema.UsersSessionsInternal(
            id="test-session-id",
            user_id=1,
            refresh_token="hashed-token",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=7),
            token_family_id="family-id",
            rotation_count=0,
        )

        mock_db_session = MagicMock(spec=users_session_models.UsersSessions)

        with patch.object(
            _auth_sessions_models,
            "UsersSessions",
            return_value=mock_db_session,
        ):
            # Act
            result = auth_sessions_crud.create_session(session_data, mock_db)

            # Assert
            assert result == mock_db_session
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once()

    def test_create_session_db_error(self, mock_db):
        """
        Test exception handling when database error occurs.
        """
        # Arrange
        now = datetime.now(UTC)
        session_data = users_session_schema.UsersSessionsInternal(
            id="test-session-id",
            user_id=1,
            refresh_token="hashed-token",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=7),
            token_family_id="family-id",
            rotation_count=0,
        )

        mock_db.commit.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            auth_sessions_crud.create_session(session_data, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestEditSession:
    """
    Test suite for edit_session function.
    """

    def test_edit_session_success(self, mock_db):
        """
        Test successful session update.
        """
        # Arrange
        now = datetime.now(UTC)
        session_data = users_session_schema.UsersSessionsInternal(
            id="test-session-id",
            user_id=1,
            refresh_token="new-hashed-token",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=7),
            token_family_id="family-id",
            rotation_count=1,
        )

        mock_db_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_session
        mock_db.execute.return_value = mock_result

        # Act
        auth_sessions_crud.edit_session(session_data, mock_db)

        # Assert
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    def test_edit_session_not_found(self, mock_db):
        """
        Test exception when session not found.
        """
        # Arrange
        now = datetime.now(UTC)
        session_data = users_session_schema.UsersSessionsInternal(
            id="nonexistent-session",
            user_id=1,
            refresh_token="hashed-token",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=7),
            token_family_id="family-id",
            rotation_count=0,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            auth_sessions_crud.edit_session(session_data, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in exc_info.value.detail


class TestDeleteSession:
    """
    Test suite for delete_session function.
    """

    def test_delete_session_success(self, mock_db):
        """
        Test successful session deletion.
        """
        # Arrange
        session_id = "test-session-id"
        user_id = 1
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.token_family_id = "family-id"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        with patch(
            "auth.sessions.crud.auth_sessions_rotated_tokens_crud.delete_by_family",
            return_value=0,
        ):
            # Act
            auth_sessions_crud.delete_session(session_id, user_id, mock_db)

            # Assert
            mock_db.commit.assert_called_once()

    def test_delete_session_not_found(self, mock_db):
        """
        Test exception when session not found.
        """
        # Arrange
        session_id = "nonexistent-session"
        user_id = 1
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            auth_sessions_crud.delete_session(session_id, user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in exc_info.value.detail

    def test_delete_session_calls_rotated_token_cleanup_before_delete(self, mock_db):
        """
        Test that delete_session calls rotated token cleanup
        before executing the session DELETE statement.
        """
        # Arrange
        session_id = "sess-cleanup-order"
        user_id = 7
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.token_family_id = "family-cleanup"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        call_order: list[str] = []

        def record_cleanup(*args, **kwargs):
            call_order.append("cleanup")

        def record_execute(*args, **kwargs):
            call_order.append("execute")
            return mock_result

        mock_db.execute.side_effect = record_execute

        with patch(
            "auth.sessions.crud.auth_sessions_rotated_tokens_crud.delete_by_family",
            side_effect=record_cleanup,
        ):
            # Act
            auth_sessions_crud.delete_session(session_id, user_id, mock_db)

        # Assert — cleanup happens before the DELETE execute
        cleanup_idx = next(i for i, v in enumerate(call_order) if v == "cleanup")
        delete_idx = next(i for i, v in reversed(list(enumerate(call_order))) if v == "execute")
        assert cleanup_idx < delete_idx

    def test_delete_session_commit_failure_raises_http_500(self, mock_db):
        """
        Test that delete_session propagates a SQLAlchemyError
        on commit as an HTTP 500 response.
        """
        # Arrange
        session_id = "sess-commit-fail"
        user_id = 5
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.token_family_id = "family-fail"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        # First execute (SELECT) succeeds; second execute (DELETE)
        # succeeds; commit raises.
        mock_db.execute.return_value = mock_result
        mock_db.commit.side_effect = SQLAlchemyError("commit failed")

        with (
            patch(
                "auth.sessions.crud.auth_sessions_rotated_tokens_crud.delete_by_family",
                return_value=0,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            # Act & Assert
            auth_sessions_crud.delete_session(session_id, user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestDeleteIdleSessions:
    """
    Test suite for delete_idle_sessions function.
    """

    def test_delete_idle_sessions_success(self, mock_db):
        """
        Test successful deletion of idle sessions.
        """
        # Arrange
        cutoff_time = datetime.now(UTC) - timedelta(hours=24)
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.delete_idle_sessions(cutoff_time, mock_db)

        # Assert
        assert result == 5
        mock_db.commit.assert_called_once()

    def test_delete_idle_sessions_none_deleted(self, mock_db):
        """
        Test when no idle sessions exist.
        """
        # Arrange
        cutoff_time = datetime.now(UTC) - timedelta(hours=24)
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.delete_idle_sessions(cutoff_time, mock_db)

        # Assert
        assert result == 0


class TestDeleteSessionsByFamily:
    """
    Test suite for delete_sessions_by_family function.
    """

    def test_delete_sessions_by_family_success(self, mock_db):
        """
        Test successful deletion of sessions by family.
        """
        # Arrange
        token_family_id = "family-id"
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.delete_sessions_by_family(token_family_id, mock_db)

        # Assert
        assert result == 3
        mock_db.commit.assert_called_once()

    def test_delete_sessions_by_family_none_deleted(self, mock_db):
        """
        Test when no sessions exist for family.
        """
        # Arrange
        token_family_id = "nonexistent-family"
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.delete_sessions_by_family(token_family_id, mock_db)

        # Assert
        assert result == 0


class TestDeleteSessionsByUser:
    """
    Test suite for delete_sessions_by_user function.
    """

    def test_delete_sessions_by_user_success(self, mock_db):
        """
        Test successful deletion of all sessions for a user.
        """
        # Arrange
        user_id = 1
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.delete_sessions_by_user(user_id, mock_db)

        # Assert
        assert result == 2
        mock_db.commit.assert_called_once()

    def test_delete_sessions_by_user_none_deleted(self, mock_db):
        """
        Test when the user has no sessions.
        """
        # Arrange
        user_id = 1
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.delete_sessions_by_user(user_id, mock_db)

        # Assert
        assert result == 0

    def test_delete_sessions_by_user_commit_false_does_not_commit(self, mock_db):
        """
        Test that delete_sessions_by_user does not call
        db.commit() when commit=False is passed, allowing the
        caller to manage transaction boundaries.
        """
        # Arrange
        user_id = 9
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.delete_sessions_by_user(user_id, mock_db, commit=False)

        # Assert
        assert result == 3
        mock_db.commit.assert_not_called()


class TestUpdateSessionCsrfHash:
    """
    Test suite for update_session_csrf_hash function.

    This function is used by the in-grace refresh replay path to mint a
    fresh CSRF token hash for web clients without rotating the refresh
    token or bumping the rotation count.
    """

    def test_update_csrf_hash_success(self, mock_db):
        """
        Updates session.csrf_token_hash and commits when session exists.
        """
        # Arrange
        session_id = "test-session-id"
        new_hash = "hmac-sha256-csrf-hash"
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_sessions_crud.update_session_csrf_hash(session_id, new_hash, mock_db)

        # Assert
        assert result is None
        assert mock_session.csrf_token_hash == new_hash
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_session)

    def test_update_csrf_hash_session_not_found_raises_404(self, mock_db):
        """
        Raises HTTP 404 when the session does not exist.
        """
        # Arrange
        session_id = "nonexistent-session"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            auth_sessions_crud.update_session_csrf_hash(session_id, "some-hash", mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert session_id in exc_info.value.detail
        mock_db.commit.assert_not_called()

    def test_update_csrf_hash_db_error_raises_500(self, mock_db):
        """
        Raises HTTP 500 when a SQLAlchemy error occurs.
        """
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("db failure")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            auth_sessions_crud.update_session_csrf_hash("session-id", "hash", mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
