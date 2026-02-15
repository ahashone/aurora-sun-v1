"""
GDPR Compliance Module for Aurora Sun V1.

Facade module that re-exports all GDPR functionality from sub-modules.
This file preserves the public API -- all existing imports continue to work.

Implements GDPR data subject rights (Art. 15-22):
- Right to Access (Art. 15): export_user_data()
- Right to Erasure (Art. 17): delete_user_data()
- Right to Restriction (Art. 18): freeze_user_data() / unfreeze_user_data()
- Right to Portability (Art. 20): JSON export format

Sub-modules:
- gdpr_types.py: Enums, dataclasses, protocols, constants
- gdpr_export.py: Export operations (Art. 15 & 20)
- gdpr_erasure.py: Deletion operations (Art. 17)
- gdpr_restriction.py: Freeze/unfreeze operations (Art. 18)
- gdpr_database.py: Private database methods (delete, restriction flags)

References:
- ARCHITECTURE.md Section 10: GDPR Compliance
- Data Classification Matrix (Section 10.3)
- Module Protocol (Section 10.5)
- Retention Policy (Section 10.6)
"""

import logging
from typing import Any

from src.lib.encryption import DataClassification
from src.lib.gdpr_database import GDPRDatabaseMixin
from src.lib.gdpr_erasure import GDPRErasureMixin
from src.lib.gdpr_export import GDPRExportMixin
from src.lib.gdpr_restriction import GDPRRestrictionMixin
from src.lib.gdpr_types import (
    RETENTION_INDEFINITE,
    GDPRExportRecord,
    GDPRModuleInterface,
    ProcessingRestriction,
    RecordsToDelete,
    RetentionPolicyConfig,
)

logger = logging.getLogger(__name__)

# Re-export all public names so `from src.lib.gdpr import X` still works
__all__ = [
    "DataClassification",
    "GDPRExportRecord",
    "GDPRModuleInterface",
    "GDPRService",
    "ProcessingRestriction",
    "RecordsToDelete",
    "RETENTION_INDEFINITE",
    "RetentionPolicyConfig",
]


class GDPRService(
    GDPRExportMixin,
    GDPRErasureMixin,
    GDPRRestrictionMixin,
    GDPRDatabaseMixin,
):
    """
    Central GDPR compliance service.
    Coordinates data subject rights across all modules and databases.

    Per ARCHITECTURE.md Section 10.4: SW-15 (GDPR Export/Delete)

    Composed from mixins:
    - GDPRExportMixin: export_user_data, _export_from_modules, _export_from_databases,
      _build_export_package, _export_postgres/redis/neo4j/qdrant/letta
    - GDPRErasureMixin: delete_user_data, bulk_delete_users
    - GDPRRestrictionMixin: freeze_user_data, unfreeze_user_data
    - GDPRDatabaseMixin: _delete_postgres/redis/neo4j/qdrant/letta, _set_restriction_flag

    Usage:
        gdpr_service = GDPRService(
            db_pool=pool,
            redis=redis_client,
            neo4j_driver=driver,
            qdrant_client=qdrant,
            letta_client=letta,
        )

        # Export all user data
        export = await gdpr_service.export_user_data(user_id=123)

        # Delete all user data
        await gdpr_service.delete_user_data(user_id=123)

        # Restrict processing (Art. 18)
        await gdpr_service.freeze_user_data(user_id=123)

        # Check retention policy
        to_delete = await gdpr_service.check_retention()
    """

    def __init__(
        self,
        db_pool: Any = None,
        redis: Any = None,
        neo4j_driver: Any = None,
        qdrant_client: Any = None,
        letta_client: Any = None,
        retention_policy: RetentionPolicyConfig | None = None,
    ):
        """
        Initialize GDPR service with database connections.

        Args:
            db_pool: PostgreSQL async pool
            redis: Redis async client
            neo4j_driver: Neo4j async driver
            qdrant_client: Qdrant client
            letta_client: Letta client
            retention_policy: Custom retention policy (uses default if None)
        """
        self.db = db_pool
        self.redis = redis
        self.neo4j = neo4j_driver
        self.qdrant = qdrant_client
        self.letta = letta_client
        self.retention_policy = retention_policy or RetentionPolicyConfig()
        self._modules: dict[str, GDPRModuleInterface] = {}

    def register_module(self, name: str, module: GDPRModuleInterface) -> None:
        """
        Register a module for GDPR operations.

        Args:
            name: Module name (used in export)
            module: Module implementing GDPRModuleInterface
        """
        self._modules[name] = module
        logger.info("Registered module '%s' for GDPR operations", name)

    async def check_retention(self) -> list[RecordsToDelete]:
        """
        Check retention policy and identify records to delete.

        Per ARCHITECTURE.md Section 10.6:
        - Active user data: retained while account active
        - Deleted user data: 0 days (immediate cascade delete)
        - Consent records: 5 years after withdrawal (legal obligation)
        - Anonymized analytics: indefinite
        - Backup data: 30 days rolling (auto-purged)

        Returns:
            list[RecordsToDelete]: Records that have exceeded retention
        """
        records_to_delete: list[RecordsToDelete] = []

        # This would query the database for records approaching retention limits
        # Implementation depends on specific table structures
        # Placeholder implementation - actual query would depend on schema

        logger.info("Retention check found %d records to delete", len(records_to_delete))
        return records_to_delete
