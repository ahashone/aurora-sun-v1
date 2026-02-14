"""
Tests for Role-Based Access Control (RBAC).

Test coverage:
- Role and permission definitions
- Permission checking functions
- Decorators for permission enforcement
- User role management
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.infra.rbac import (
    Permission,
    PermissionDeniedError,
    Role,
    RoleError,
    check_permission,
    get_user_role,
    has_all_permissions,
    has_any_permission,
    has_permission,
    require_any_permission,
    require_permission,
    require_role,
    set_user_role,
)

# =============================================================================
# Permission Checking Tests
# =============================================================================


def test_has_permission_user() -> None:
    """Test user role permissions."""
    assert has_permission(Role.USER, Permission.READ_OWN_DATA)
    assert has_permission(Role.USER, Permission.WRITE_OWN_DATA)
    assert not has_permission(Role.USER, Permission.MANAGE_USERS)
    assert not has_permission(Role.USER, Permission.BACKUP_RESTORE)


def test_has_permission_admin() -> None:
    """Test admin role permissions."""
    assert has_permission(Role.ADMIN, Permission.READ_OWN_DATA)
    assert has_permission(Role.ADMIN, Permission.MANAGE_USERS)
    assert has_permission(Role.ADMIN, Permission.VIEW_AGGREGATED_DATA)
    assert not has_permission(Role.ADMIN, Permission.BACKUP_RESTORE)


def test_has_permission_system() -> None:
    """Test system role permissions."""
    assert has_permission(Role.SYSTEM, Permission.AUTOMATED_OPERATIONS)
    assert has_permission(Role.SYSTEM, Permission.BACKUP_RESTORE)
    assert has_permission(Role.SYSTEM, Permission.KEY_ROTATION)
    assert not has_permission(Role.SYSTEM, Permission.READ_OWN_DATA)


def test_check_permission_success() -> None:
    """Test check_permission when permission is granted."""
    result = check_permission(Role.ADMIN, Permission.MANAGE_USERS, raise_on_failure=False)
    assert result is True


def test_check_permission_failure() -> None:
    """Test check_permission when permission is denied."""
    result = check_permission(Role.USER, Permission.MANAGE_USERS, raise_on_failure=False)
    assert result is False


def test_check_permission_raises() -> None:
    """Test check_permission raises PermissionDeniedError."""
    with pytest.raises(PermissionDeniedError):
        check_permission(Role.USER, Permission.MANAGE_USERS, raise_on_failure=True)


def test_has_any_permission() -> None:
    """Test has_any_permission with multiple permissions."""
    assert has_any_permission(
        Role.ADMIN,
        Permission.MANAGE_USERS,
        Permission.VIEW_AGGREGATED_DATA,
    )

    assert not has_any_permission(
        Role.USER,
        Permission.MANAGE_USERS,
        Permission.BACKUP_RESTORE,
    )


def test_has_all_permissions() -> None:
    """Test has_all_permissions with multiple permissions."""
    assert has_all_permissions(
        Role.ADMIN,
        Permission.READ_OWN_DATA,
        Permission.MANAGE_USERS,
    )

    assert not has_all_permissions(
        Role.USER,
        Permission.READ_OWN_DATA,
        Permission.MANAGE_USERS,
    )


# =============================================================================
# Decorator Tests
# =============================================================================


@pytest.mark.asyncio
async def test_require_permission_decorator_async_success() -> None:
    """Test require_permission decorator on async function (success)."""

    @require_permission(Permission.READ_OWN_DATA)
    async def test_func(current_user_role: Role) -> str:
        return "success"

    result = await test_func(current_user_role=Role.USER)
    assert result == "success"


@pytest.mark.asyncio
async def test_require_permission_decorator_async_failure() -> None:
    """Test require_permission decorator on async function (failure)."""

    @require_permission(Permission.MANAGE_USERS)
    async def test_func(current_user_role: Role) -> str:
        return "success"

    with pytest.raises(PermissionDeniedError):
        await test_func(current_user_role=Role.USER)


def test_require_permission_decorator_sync_success() -> None:
    """Test require_permission decorator on sync function (success)."""

    @require_permission(Permission.MANAGE_USERS)
    def test_func(current_user_role: Role, **kwargs: Any) -> str:
        return "success"

    # FINDING-015: Role.ADMIN requires _internal_request=True
    result = test_func(current_user_role=Role.ADMIN, _internal_request=True)
    assert result == "success"


def test_require_permission_decorator_sync_failure() -> None:
    """Test require_permission decorator on sync function (failure)."""

    @require_permission(Permission.MANAGE_USERS)
    def test_func(current_user_role: Role) -> str:
        return "success"

    with pytest.raises(PermissionDeniedError):
        test_func(current_user_role=Role.USER)


@pytest.mark.asyncio
async def test_require_any_permission_decorator_success() -> None:
    """Test require_any_permission decorator (success)."""

    @require_any_permission(Permission.MANAGE_USERS, Permission.VIEW_AGGREGATED_DATA)
    async def test_func(current_user_role: Role, **kwargs: Any) -> str:
        return "success"

    # FINDING-015: Role.ADMIN requires _internal_request=True
    result = await test_func(current_user_role=Role.ADMIN, _internal_request=True)
    assert result == "success"


@pytest.mark.asyncio
async def test_require_any_permission_decorator_failure() -> None:
    """Test require_any_permission decorator (failure)."""

    @require_any_permission(Permission.MANAGE_USERS, Permission.BACKUP_RESTORE)
    async def test_func(current_user_role: Role) -> str:
        return "success"

    with pytest.raises(PermissionDeniedError):
        await test_func(current_user_role=Role.USER)


@pytest.mark.asyncio
async def test_require_role_decorator_success() -> None:
    """Test require_role decorator (success)."""

    @require_role(Role.ADMIN)
    async def test_func(current_user_role: Role, **kwargs: Any) -> str:
        return "admin only"

    # FINDING-015: Role.ADMIN requires _internal_request=True
    result = await test_func(current_user_role=Role.ADMIN, _internal_request=True)
    assert result == "admin only"


@pytest.mark.asyncio
async def test_require_role_decorator_failure() -> None:
    """Test require_role decorator (failure)."""

    @require_role(Role.ADMIN)
    async def test_func(current_user_role: Role) -> str:
        return "admin only"

    with pytest.raises(PermissionDeniedError):
        await test_func(current_user_role=Role.USER)


def test_require_permission_no_role_provided() -> None:
    """Test decorator when current_user_role is not provided."""

    @require_permission(Permission.READ_OWN_DATA)
    def test_func() -> str:
        return "success"

    with pytest.raises(PermissionDeniedError, match="not provided"):
        test_func()


# =============================================================================
# User Role Management Tests
# =============================================================================


def test_get_user_role_no_session() -> None:
    """Test get_user_role with no database session."""
    role = get_user_role(user_id=123, db_session=None)
    assert role == Role.USER


def test_get_user_role_with_session() -> None:
    """Test get_user_role with database session."""
    mock_session = MagicMock()
    mock_user = MagicMock()
    mock_user.role = "admin"
    mock_session.query.return_value.filter_by.return_value.first.return_value = mock_user

    role = get_user_role(user_id=123, db_session=mock_session)
    assert role == Role.ADMIN


def test_get_user_role_user_not_found() -> None:
    """Test get_user_role when user not found."""
    mock_session = MagicMock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None

    role = get_user_role(user_id=999, db_session=mock_session)
    assert role == Role.USER


def test_set_user_role_success() -> None:
    """Test set_user_role successfully."""
    mock_session = MagicMock()
    mock_user = MagicMock()
    mock_user.role = "user"
    mock_session.query.return_value.filter_by.return_value.first.return_value = mock_user

    set_user_role(user_id=123, role=Role.ADMIN, db_session=mock_session)

    assert mock_user.role == "admin"
    mock_session.commit.assert_called_once()


def test_set_user_role_no_session() -> None:
    """Test set_user_role with no session."""
    with pytest.raises(RoleError, match="Database session required"):
        set_user_role(user_id=123, role=Role.ADMIN, db_session=None)


def test_set_user_role_user_not_found() -> None:
    """Test set_user_role when user not found."""
    mock_session = MagicMock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None

    with pytest.raises(RoleError, match="not found"):
        set_user_role(user_id=999, role=Role.ADMIN, db_session=mock_session)


# =============================================================================
# String Representation Tests
# =============================================================================


def test_role_str_representation() -> None:
    """Test Role enum string representation."""
    assert str(Role.USER) == "user"
    assert str(Role.ADMIN) == "admin"
    assert str(Role.SYSTEM) == "system"


def test_permission_str_representation() -> None:
    """Test Permission enum string representation."""
    assert str(Permission.READ_OWN_DATA) == "read_own_data"
    assert str(Permission.MANAGE_USERS) == "manage_users"
