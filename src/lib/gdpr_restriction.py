"""
GDPR processing restriction operations (Art. 18).

Extracted from src/lib/gdpr.py for maintainability.
Contains freeze/unfreeze and restriction flag management for the GDPRService.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.lib.gdpr_types import ProcessingRestriction
from src.lib.security import hash_uid

logger = logging.getLogger(__name__)


class GDPRRestrictionMixin:
    """Mixin providing GDPR restriction operations for GDPRService."""

    async def freeze_user_data(self, user_id: int) -> dict[str, Any]:
        """
        GDPR Art. 18: Restrict processing of user data.

        Called when user withdraws consent but data must be retained
        for legal obligations (e.g., financial records required for taxes).

        Args:
            user_id: User identifier

        Returns:
            dict: Freeze report with status per component
        """
        freeze_report: dict[str, Any] = {
            "user_id": user_id,
            "restriction": ProcessingRestriction.RESTRICTED.value,
            "frozen_at": datetime.now(UTC).isoformat(),
            "components": {},
        }

        # Freeze in each registered module
        for module_name, module in self._modules.items():
            try:
                await module.freeze_user_data(user_id)
                freeze_report["components"][module_name] = {"status": "restricted"}
                logger.info("Module '%s' restricted for user_hash=%s", module_name, hash_uid(user_id))
            except Exception as e:
                logger.error("Module '%s' freeze failed for user_hash=%s: %s", module_name, hash_uid(user_id), e)
                freeze_report["components"][module_name] = {"status": "error", "error": "operation failed"}

        # Set restriction flag in PostgreSQL
        try:
            if self.db:
                await self._set_restriction_flag(user_id, ProcessingRestriction.RESTRICTED)
                freeze_report["components"]["postgres"] = {"status": "restricted"}
        except Exception as e:
            logger.error("PostgreSQL restriction failed for user_hash=%s: %s", hash_uid(user_id), e)
            freeze_report["components"]["postgres"] = {"status": "error", "error": "operation failed"}

        # Note: Active processing should be stopped by individual modules
        # The freeze_report indicates that processing is now restricted

        logger.info("GDPR freeze completed for user_hash=%s", hash_uid(user_id))
        return freeze_report

    async def unfreeze_user_data(self, user_id: int) -> dict[str, Any]:
        """
        GDPR Art. 18: Lift restriction on processing.

        Called when user re-consents or when the legal obligation
        that required retention has expired.

        Args:
            user_id: User identifier

        Returns:
            dict: Unfreeze report with status per component
        """
        unfreeze_report: dict[str, Any] = {
            "user_id": user_id,
            "restriction": ProcessingRestriction.ACTIVE.value,
            "unfrozen_at": datetime.now(UTC).isoformat(),
            "components": {},
        }

        # Unfreeze in each registered module
        for module_name, module in self._modules.items():
            try:
                await module.unfreeze_user_data(user_id)
                unfreeze_report["components"][module_name] = {"status": "active"}
                logger.info("Module '%s' activated for user_hash=%s", module_name, hash_uid(user_id))
            except Exception as e:
                logger.error("Module '%s' unfreeze failed for user_hash=%s: %s", module_name, hash_uid(user_id), e)
                unfreeze_report["components"][module_name] = {"status": "error", "error": "operation failed"}

        # Remove restriction flag in PostgreSQL
        try:
            if self.db:
                await self._set_restriction_flag(user_id, ProcessingRestriction.ACTIVE)
                unfreeze_report["components"]["postgres"] = {"status": "active"}
        except Exception as e:
            logger.error("PostgreSQL unrestriction failed for user_hash=%s: %s", hash_uid(user_id), e)
            unfreeze_report["components"]["postgres"] = {"status": "error", "error": "operation failed"}

        logger.info("GDPR unfreeze completed for user_hash=%s", hash_uid(user_id))
        return unfreeze_report
