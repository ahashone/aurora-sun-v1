"""
Role-Based Access Control (RBAC) for Aurora Sun V1.

Provides role and permission management for:
- API endpoint access control
- Admin operations
- System-level actions
- Data access restrictions

Roles:
- USER: Regular user (can access own data)
- ADMIN: Administrator (can manage users, view aggregated data)
- SYSTEM: System account (can perform automated operations)

References:
    - ROADMAP.md Phase 4.6 (Production Hardening)
    - ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import Enum
from functools import wraps
from typing import Any, TypeVar

from src.lib.security import hash_uid

logger = logging.getLogger(__name__)


# =============================================================================
# Role and Permission Definitions
# =============================================================================


class Role(Enum):
    """User roles in Aurora Sun V1."""

    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"

    def __str__(self) -> str:
        """String representation."""
        return self.value


class Permission(Enum):
    """Permissions that can be granted to roles."""

    # User data permissions
    READ_OWN_DATA = "read_own_data"
    WRITE_OWN_DATA = "write_own_data"
    DELETE_OWN_DATA = "delete_own_data"

    # Admin permissions
    READ_ALL_USERS = "read_all_users"
    MANAGE_USERS = "manage_users"
    VIEW_AGGREGATED_DATA = "view_aggregated_data"
    MANAGE_SYSTEM_CONFIG = "manage_system_config"

    # System permissions
    AUTOMATED_OPERATIONS = "automated_operations"
    BACKUP_RESTORE = "backup_restore"
    KEY_ROTATION = "key_rotation"

    # Crisis permissions
    OVERRIDE_RATE_LIMITS = "override_rate_limits"
    ACCESS_CRISIS_DATA = "access_crisis_data"

    def __str__(self) -> str:
        """String representation."""
        return self.value


# Role -> Permissions mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.USER: {
        Permission.READ_OWN_DATA,
        Permission.WRITE_OWN_DATA,
        Permission.DELETE_OWN_DATA,
    },
    Role.ADMIN: {
        Permission.READ_OWN_DATA,
        Permission.WRITE_OWN_DATA,
        Permission.DELETE_OWN_DATA,
        Permission.READ_ALL_USERS,
        Permission.MANAGE_USERS,
        Permission.VIEW_AGGREGATED_DATA,
        Permission.MANAGE_SYSTEM_CONFIG,
        Permission.ACCESS_CRISIS_DATA,
    },
    Role.SYSTEM: {
        Permission.AUTOMATED_OPERATIONS,
        Permission.BACKUP_RESTORE,
        Permission.KEY_ROTATION,
        Permission.OVERRIDE_RATE_LIMITS,
        Permission.ACCESS_CRISIS_DATA,
    },
}


# =============================================================================
# Permission Checking
# =============================================================================


def has_permission(role: Role, permission: Permission) -> bool:
    """
    Check if a role has a specific permission.

    Args:
        role: User's role
        permission: Permission to check

    Returns:
        True if role has permission, False otherwise

    Example:
        >>> has_permission(Role.ADMIN, Permission.MANAGE_USERS)
        True
        >>> has_permission(Role.USER, Permission.MANAGE_USERS)
        False
    """
    return permission in ROLE_PERMISSIONS.get(role, set())


def check_permission(
    role: Role,
    permission: Permission,
    raise_on_failure: bool = False,
) -> bool:
    """
    Check permission with optional exception raising.

    Args:
        role: User's role
        permission: Permission to check
        raise_on_failure: If True, raise PermissionDeniedError on failure

    Returns:
        True if permission granted, False otherwise

    Raises:
        PermissionDeniedError: If permission denied and raise_on_failure=True

    Example:
        >>> check_permission(Role.USER, Permission.MANAGE_USERS, raise_on_failure=True)
        PermissionDeniedError: Role 'user' does not have permission 'manage_users'
    """
    has_perm = has_permission(role, permission)

    if not has_perm and raise_on_failure:
        raise PermissionDeniedError(
            f"Role '{role.value}' does not have permission '{permission.value}'"
        )

    return has_perm


def has_any_permission(role: Role, *permissions: Permission) -> bool:
    """
    Check if role has ANY of the specified permissions.

    Args:
        role: User's role
        *permissions: Permissions to check

    Returns:
        True if role has at least one permission

    Example:
        >>> has_any_permission(
        ...     Role.ADMIN,
        ...     Permission.MANAGE_USERS,
        ...     Permission.VIEW_AGGREGATED_DATA
        ... )
        True
    """
    return any(has_permission(role, perm) for perm in permissions)


def has_all_permissions(role: Role, *permissions: Permission) -> bool:
    """
    Check if role has ALL of the specified permissions.

    Args:
        role: User's role
        *permissions: Permissions to check

    Returns:
        True if role has all permissions

    Example:
        >>> has_all_permissions(
        ...     Role.ADMIN,
        ...     Permission.READ_OWN_DATA,
        ...     Permission.MANAGE_USERS
        ... )
        True
    """
    return all(has_permission(role, perm) for perm in permissions)


# =============================================================================
# Decorators for Permission Enforcement
# =============================================================================

F = TypeVar("F", bound=Callable[..., Any])


def _validate_role_from_kwargs(kwargs: dict[str, Any]) -> Role:
    """
    FINDING-015: Validate the role from kwargs.

    SECURITY NOTE: In production, `current_user_role` MUST come from the
    authenticated session/token (e.g., decoded JWT), NOT from caller kwargs
    or user-supplied input. The decorators below read from kwargs as a
    convention for internal function calls, but the caller is responsible
    for setting this from a validated source. Never trust user-supplied role
    values directly.

    Additionally, Role.ADMIN is rejected unless `_internal_request` is True
    in kwargs, which should only be set by the authentication middleware
    after validating an admin session.
    """
    role = kwargs.get("current_user_role")
    if role is None:
        raise PermissionDeniedError(
            "current_user_role not provided to permission-protected function"
        )

    if not isinstance(role, Role):
        raise ValueError(f"Expected Role, got {type(role)}")

    # FINDING-015: Reject Role.ADMIN unless the request is verified as internal/
    # authenticated. In production, this flag must be set by auth middleware only.
    if role == Role.ADMIN and not kwargs.get("_internal_request", False):
        logger.warning(
            "Role.ADMIN rejected: _internal_request flag not set. "
            "Admin role must come from authenticated session."
        )
        raise PermissionDeniedError(
            "Role.ADMIN requires authenticated internal request. "
            "Set _internal_request=True from auth middleware only."
        )

    return role


def require_permission(permission: Permission) -> Callable[[F], F]:
    """
    Decorator to enforce permission requirements.

    FINDING-015: Role is validated via _validate_role_from_kwargs which
    rejects unverified ADMIN claims.

    Args:
        permission: Required permission

    Raises:
        PermissionDeniedError: If user doesn't have permission

    Example:
        >>> @require_permission(Permission.MANAGE_USERS)
        ... async def delete_user(user_id: int, current_user_role: Role):
        ...     # Only admins can call this
        ...     pass
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            role = _validate_role_from_kwargs(kwargs)
            check_permission(role, permission, raise_on_failure=True)
            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            role = _validate_role_from_kwargs(kwargs)
            check_permission(role, permission, raise_on_failure=True)
            return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        else:
            return sync_wrapper  # type: ignore[return-value]

    return decorator


def require_any_permission(*permissions: Permission) -> Callable[[F], F]:
    """
    Decorator to enforce ANY of multiple permissions.

    Args:
        *permissions: Required permissions (user needs at least one)

    Raises:
        PermissionDeniedError: If user doesn't have any required permission

    Example:
        >>> @require_any_permission(
        ...     Permission.MANAGE_USERS,
        ...     Permission.VIEW_AGGREGATED_DATA
        ... )
        ... async def view_user_stats(current_user_role: Role):
        ...     pass
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            role = _validate_role_from_kwargs(kwargs)

            if not has_any_permission(role, *permissions):
                perm_names = [p.value for p in permissions]
                raise PermissionDeniedError(
                    f"Role '{role.value}' does not have any of: {perm_names}"
                )

            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            role = _validate_role_from_kwargs(kwargs)

            if not has_any_permission(role, *permissions):
                perm_names = [p.value for p in permissions]
                raise PermissionDeniedError(
                    f"Role '{role.value}' does not have any of: {perm_names}"
                )

            return func(*args, **kwargs)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        else:
            return sync_wrapper  # type: ignore[return-value]

    return decorator


def require_role(required_role: Role) -> Callable[[F], F]:
    """
    Decorator to enforce specific role requirement.

    FINDING-015: Role is validated via _validate_role_from_kwargs.

    Args:
        required_role: Required role

    Raises:
        PermissionDeniedError: If user doesn't have the role

    Example:
        >>> @require_role(Role.ADMIN)
        ... async def admin_only_endpoint(current_user_role: Role):
        ...     pass
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            current_role = _validate_role_from_kwargs(kwargs)

            if current_role != required_role:
                raise PermissionDeniedError(
                    f"Requires role '{required_role.value}', current role is '{current_role.value}'"
                )

            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            current_role = _validate_role_from_kwargs(kwargs)

            if current_role != required_role:
                raise PermissionDeniedError(
                    f"Requires role '{required_role.value}', current role is '{current_role.value}'"
                )

            return func(*args, **kwargs)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        else:
            return sync_wrapper  # type: ignore[return-value]

    return decorator


# =============================================================================
# Exceptions
# =============================================================================


class PermissionDeniedError(Exception):
    """Raised when a user lacks required permissions."""

    pass


class RoleError(Exception):
    """Raised when there's an error with role assignment/validation."""

    pass


# =============================================================================
# User Role Management
# =============================================================================


def get_user_role(user_id: int, db_session: Any = None) -> Role:
    """
    Get a user's role from the database.

    Args:
        user_id: User ID
        db_session: Database session (if None, returns USER as default)

    Returns:
        User's role (defaults to USER if not found)

    Example:
        >>> role = get_user_role(123, db_session)
        >>> print(role)
        Role.USER
    """
    if db_session is None:
        logger.warning("No database session provided, defaulting to USER role")
        return Role.USER

    try:
        from src.models.user import User

        user = db_session.query(User).filter_by(id=user_id).first()
        if user is None:
            logger.warning("User user_hash=%s not found, defaulting to USER role", hash_uid(user_id))
            return Role.USER

        # Assuming User model has a 'role' field
        if hasattr(user, "role") and user.role:
            return Role(user.role)
        else:
            return Role.USER

    except Exception:
        logger.exception("Error fetching role for user_hash=%s", hash_uid(user_id))
        return Role.USER


def set_user_role(user_id: int, role: Role, db_session: Any) -> None:
    """
    Set a user's role in the database.

    Args:
        user_id: User ID
        role: New role to assign
        db_session: Database session

    Raises:
        RoleError: If role assignment fails

    Example:
        >>> set_user_role(123, Role.ADMIN, db_session)
    """
    if db_session is None:
        raise RoleError("Database session required for role assignment")

    try:
        from src.models.user import User

        user = db_session.query(User).filter_by(id=user_id).first()
        if user is None:
            raise RoleError(f"User {user_id} not found")

        # Set role (assuming User model has a 'role' field)
        if hasattr(user, "role"):
            user.role = role.value
            db_session.commit()
            logger.info("Updated role for user_hash=%s to %s", hash_uid(user_id), role.value)
        else:
            raise RoleError("User model does not have 'role' field")

    except Exception as e:
        db_session.rollback()
        logger.exception("Error setting role for user_hash=%s", hash_uid(user_id))
        raise RoleError(f"Failed to set role: {e}") from e
