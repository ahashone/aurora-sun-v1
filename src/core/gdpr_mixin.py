"""
GDPR Module Mixin for Aurora Sun V1.

Provides default GDPR method implementations for modules. All modules that handle
user data must implement the 4 GDPR methods (export, delete, freeze, unfreeze).
This mixin provides stub defaults that modules override with their specific logic.

Usage:
    class MyModule(GDPRModuleMixin):
        def _gdpr_data_categories(self) -> dict[str, list[str]]:
            return {"my_table": ["col1", "col2"]}

        async def export_user_data(self, user_id: int) -> dict[str, Any]:
            # Module-specific export logic
            return {"my_data": []}

Reference:
- Module Protocol: src/core/module_protocol.py
- GDPR compliance: src/lib/gdpr.py
- REFACTOR-001: Extract duplicated GDPR methods to mixin
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GDPRModuleMixin:
    """
    Mixin providing default GDPR method implementations for modules.

    Modules inherit from this mixin to get baseline GDPR compliance.
    Override any method for module-specific behavior (e.g., money module
    needs actual decryption in export, actual deletion in delete).

    The mixin provides:
    - export_user_data: Returns empty data categories (override to populate)
    - delete_user_data: No-op stub (override when DB is wired up)
    - freeze_user_data: No-op stub (override when DB is wired up)
    - unfreeze_user_data: No-op stub (override when DB is wired up)
    - _gdpr_data_categories: Override to declare what data this module stores

    Attributes:
        name: Module name (expected from the module class itself)
    """

    # Subclasses must define this (it comes from the module class)
    name: str

    def _gdpr_data_categories(self) -> dict[str, list[str]]:
        """
        Declare what data categories this module stores.

        Override this in your module to declare what tables/collections
        this module manages. Used for audit trails and documentation.

        Returns:
            Dict mapping table/collection name to list of field names.
            Example: {"habits": ["name", "cue", "craving"], "habit_logs": ["notes"]}
        """
        return {}

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """
        GDPR Art. 15: Export all user data from this module.

        Default implementation returns empty dict with keys from
        _gdpr_data_categories. Override for actual DB queries.

        Args:
            user_id: The user's ID

        Returns:
            Dict containing all user data from this module
        """
        categories = self._gdpr_data_categories()
        if categories:
            return {table: [] for table in categories}
        logger.debug(
            "gdpr_export_stub module=%s user_id=%d",
            getattr(self, "name", "unknown"),
            user_id,
        )
        return {}

    async def delete_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 17: Delete all user data from this module.

        Default implementation is a no-op. Override when database
        integration is implemented.

        Args:
            user_id: The user's ID
        """
        logger.debug(
            "gdpr_delete_stub module=%s user_id=%d",
            getattr(self, "name", "unknown"),
            user_id,
        )

    async def freeze_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 18: Restrict processing of user data.

        Data is retained but not processed until unfrozen.
        Default implementation is a no-op.

        Args:
            user_id: The user's ID
        """
        logger.debug(
            "gdpr_freeze_stub module=%s user_id=%d",
            getattr(self, "name", "unknown"),
            user_id,
        )

    async def unfreeze_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 18: Lift restriction of processing.

        Default implementation is a no-op.

        Args:
            user_id: The user's ID
        """
        logger.debug(
            "gdpr_unfreeze_stub module=%s user_id=%d",
            getattr(self, "name", "unknown"),
            user_id,
        )


__all__ = ["GDPRModuleMixin"]
