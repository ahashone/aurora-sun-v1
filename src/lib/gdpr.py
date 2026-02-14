"""
GDPR Compliance Module for Aurora Sun V1.

Implements GDPR data subject rights (Art. 15-22):
- Right to Access (Art. 15): export_user_data()
- Right to Erasure (Art. 17): delete_user_data()
- Right to Restriction (Art. 18): freeze_user_data() / unfreeze_user_data()
- Right to Portability (Art. 20): JSON export format

References:
- ARCHITECTURE.md Section 10: GDPR Compliance
- Data Classification Matrix (Section 10.3)
- Module Protocol (Section 10.5)
- Retention Policy (Section 10.6)
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol

from src.lib.encryption import DataClassification

logger = logging.getLogger(__name__)


class ProcessingRestriction(Enum):
    """
    GDPR Art. 18: Restriction of processing.
    User data can be frozen (restricted) when consent is withdrawn
    but data must be retained for legal obligations.
    """
    ACTIVE = "active"           # Normal processing
    RESTRICTED = "restricted"   # No processing, data retained for legal obligation


@dataclass
class RecordsToDelete:
    """Record identified for deletion due to retention policy expiration."""
    table_name: str
    record_id: int
    classification: DataClassification
    created_at: datetime
    days_since_creation: int
    reason: str


@dataclass
class RetentionPolicyConfig:
    """
    Retention policy configuration per data classification.
    Per ARCHITECTURE.md Section 10.6.

    Default retention:
    - SENSITIVE: 0 days (deleted while account active, immediate cascade on delete)
    - ART_9_SPECIAL: 0 days (deleted while account active, immediate cascade on delete)
    - FINANCIAL: 0 days (deleted while account active, immediate cascade on delete)
    - Consent records: 1825 days (5 years after withdrawal - legal obligation)
    - INTERNAL: No retention limit (anonymized analytics)
    - PUBLIC: No retention limit
    """
    retention_days: dict[DataClassification, int] = field(default_factory=lambda: {
        DataClassification.PUBLIC: -1,           # Indefinite (no retention needed)
        DataClassification.INTERNAL: -1,          # Indefinite (anonymized)
        DataClassification.SENSITIVE: 0,          # Delete while active
        DataClassification.ART_9_SPECIAL: 0,       # Delete while active
        DataClassification.FINANCIAL: 0,          # Delete while active
    })

    # Consent records have special retention: 5 years after withdrawal
    CONSENT_RETENTION_DAYS: int = 1825  # 5 years

    def get_retention_days(self, classification: DataClassification) -> int:
        """Get retention days for a classification. -1 means indefinite."""
        return self.retention_days.get(classification, 0)

    def is_expired(self, classification: DataClassification, created_at: datetime) -> bool:
        """Check if a record has exceeded its retention period."""
        retention = self.get_retention_days(classification)
        if retention == -1:
            return False  # Indefinite retention
        if retention == 0:
            return True  # Delete while active (not stored)

        days_since = (datetime.now(UTC) - created_at).days
        return days_since > retention


class GDPRModuleInterface(Protocol):
    """
    Protocol for GDPR-compliant modules.
    Every module must implement these methods to comply with GDPR.

    Per ARCHITECTURE.md Section 10.5: Module Protocol (Extended)
    """

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """
        GDPR Art. 15 & 20: Export all user data in machine-readable format.
        Called by SW-15 workflow when user requests data export.

        Returns:
            dict: Module-specific user data as JSON-serializable dict
        """
        ...

    async def delete_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 17: Delete all user data (right to be forgotten).
        Called by SW-15 workflow when user requests deletion.

        Must:
        - Delete all records in primary database
        - Delete all vectors in vector store
        - Delete all memories in memory store
        - Delete all Redis keys
        - Mark encryption keys for destruction
        """
        ...

    async def freeze_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 18: Restrict processing of user data.
        Called when user withdraws consent but data must be retained
        for legal obligations (e.g., financial records).

        Must:
        - Set processing_restriction = RESTRICTED
        - Stop all active processing
        - Retain data for legal compliance period
        """
        ...

    async def unfreeze_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 18: Lift restriction on processing.
        Called when user re-consents or restriction reason expires.

        Must:
        - Set processing_restriction = ACTIVE
        - Resume normal processing
        """
        ...


@dataclass
class GDPRExportRecord:
    """Single module's data export for aggregation."""
    module_name: str
    exported_at: datetime
    data: dict[str, Any]


class GDPRService:
    """
    Central GDPR compliance service.
    Coordinates data subject rights across all modules and databases.

    Per ARCHITECTURE.md Section 10.4: SW-15 (GDPR Export/Delete)

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
        logger.info(f"Registered module '{name}' for GDPR operations")

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """
        GDPR Art. 15 & 20: Export all user data in machine-readable JSON format.

        Per SW-15 workflow:
        1. Call export_user_data() on every registered module
        2. Aggregate into single export package
        3. Include: PostgreSQL, Neo4j, Qdrant, Redis, Letta data
        4. Return encrypted package metadata

        Args:
            user_id: User identifier

        Returns:
            dict: Complete user data export with metadata
        """
        exports: list[GDPRExportRecord] = []
        errors: list[str] = []

        # Export from each registered module
        for module_name, module in self._modules.items():
            try:
                data = await module.export_user_data(user_id)
                exports.append(GDPRExportRecord(
                    module_name=module_name,
                    exported_at=datetime.now(UTC),
                    data=data,
                ))
            except Exception as e:
                logger.error(f"Module '{module_name}' export failed: {e}")
                errors.append(f"{module_name}: export failed")

        # Export from direct database connections
        try:
            if self.db:
                pg_data = await self._export_postgres(user_id)
                if pg_data:
                    exports.append(GDPRExportRecord(
                        module_name="postgres",
                        exported_at=datetime.now(UTC),
                        data=pg_data,
                    ))
        except Exception as e:
            logger.error(f"PostgreSQL export failed: {e}")
            errors.append("postgres: export failed")

        try:
            if self.redis:
                redis_data = await self._export_redis(user_id)
                if redis_data:
                    exports.append(GDPRExportRecord(
                        module_name="redis",
                        exported_at=datetime.now(UTC),
                        data=redis_data,
                    ))
        except Exception as e:
            logger.error(f"Redis export failed: {e}")
            errors.append("redis: export failed")

        try:
            if self.neo4j:
                neo4j_data = await self._export_neo4j(user_id)
                if neo4j_data:
                    exports.append(GDPRExportRecord(
                        module_name="neo4j",
                        exported_at=datetime.now(UTC),
                        data=neo4j_data,
                    ))
        except Exception as e:
            logger.error(f"Neo4j export failed: {e}")
            errors.append("neo4j: export failed")

        try:
            if self.qdrant:
                qdrant_data = await self._export_qdrant(user_id)
                if qdrant_data:
                    exports.append(GDPRExportRecord(
                        module_name="qdrant",
                        exported_at=datetime.now(UTC),
                        data=qdrant_data,
                    ))
        except Exception as e:
            logger.error(f"Qdrant export failed: {e}")
            errors.append("qdrant: export failed")

        try:
            if self.letta:
                letta_data = await self._export_letta(user_id)
                if letta_data:
                    exports.append(GDPRExportRecord(
                        module_name="letta",
                        exported_at=datetime.now(UTC),
                        data=letta_data,
                    ))
        except Exception as e:
            logger.error(f"Letta export failed: {e}")
            errors.append("letta: export failed")

        # Build export package
        export_package = {
            "export_metadata": {
                "user_id": user_id,
                "exported_at": datetime.now(UTC).isoformat(),
                "aurora_version": "v1",
                "total_records": len(exports),
                "errors": errors if errors else None,
            },
            "modules": {
                record.module_name: {
                    "exported_at": record.exported_at.isoformat(),
                    "data": record.data,
                }
                for record in exports
            },
        }

        logger.info(f"GDPR export completed for user {user_id}: {len(exports)} modules, {len(errors)} errors")
        return export_package

    async def delete_user_data(self, user_id: int) -> dict[str, Any]:
        """
        GDPR Art. 17: Delete all user data (right to be forgotten).

        Per SW-15 workflow:
        1. Confirmation required (double-confirm for delete)
        2. Call delete_user_data() on every registered module
        3. Delete from PG (cascade), Neo4j, Qdrant, Redis, Letta
        4. Destroy encryption keys
        5. Log audit event (without user data)

        Args:
            user_id: User identifier

        Returns:
            dict: Deletion report with status per component
        """
        deletion_report: dict[str, Any] = {
            "user_id": user_id,
            "deleted_at": datetime.now(UTC).isoformat(),
            "components": {},
        }

        # Delete from each registered module
        for module_name, module in self._modules.items():
            try:
                await module.delete_user_data(user_id)
                deletion_report["components"][module_name] = {"status": "deleted"}
                logger.info(f"Module '{module_name}' data deleted for user {user_id}")
            except Exception as e:
                logger.error(f"Module '{module_name}' deletion failed: {e}")
                deletion_report["components"][module_name] = {"status": "error", "error": "deletion failed"}

        # Delete from PostgreSQL
        try:
            if self.db:
                await self._delete_postgres(user_id)
                deletion_report["components"]["postgres"] = {"status": "deleted"}
        except Exception as e:
            logger.error(f"PostgreSQL deletion failed: {e}")
            deletion_report["components"]["postgres"] = {"status": "error", "error": "operation failed"}

        # Delete from Redis
        try:
            if self.redis:
                await self._delete_redis(user_id)
                deletion_report["components"]["redis"] = {"status": "deleted"}
        except Exception as e:
            logger.error(f"Redis deletion failed: {e}")
            deletion_report["components"]["redis"] = {"status": "error", "error": "operation failed"}

        # Delete from Neo4j
        try:
            if self.neo4j:
                await self._delete_neo4j(user_id)
                deletion_report["components"]["neo4j"] = {"status": "deleted"}
        except Exception as e:
            logger.error(f"Neo4j deletion failed: {e}")
            deletion_report["components"]["neo4j"] = {"status": "error", "error": "operation failed"}

        # Delete from Qdrant
        try:
            if self.qdrant:
                await self._delete_qdrant(user_id)
                deletion_report["components"]["qdrant"] = {"status": "deleted"}
        except Exception as e:
            logger.error(f"Qdrant deletion failed: {e}")
            deletion_report["components"]["qdrant"] = {"status": "error", "error": "operation failed"}

        # Delete from Letta
        try:
            if self.letta:
                await self._delete_letta(user_id)
                deletion_report["components"]["letta"] = {"status": "deleted"}
        except Exception as e:
            logger.error(f"Letta deletion failed: {e}")
            deletion_report["components"]["letta"] = {"status": "error", "error": "operation failed"}

        # Note: Encryption key destruction would be handled by EncryptionService
        # This is logged but not executed here (handled separately for security)

        success = all(
            comp.get("status") == "deleted"
            for comp in deletion_report["components"].values()
        )
        deletion_report["overall_status"] = "success" if success else "partial"

        logger.info(f"GDPR deletion completed for user {user_id}: {deletion_report['overall_status']}")
        return deletion_report

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
                logger.info(f"Module '{module_name}' restricted for user {user_id}")
            except Exception as e:
                logger.error(f"Module '{module_name}' freeze failed: {e}")
                freeze_report["components"][module_name] = {"status": "error", "error": "operation failed"}

        # Set restriction flag in PostgreSQL
        try:
            if self.db:
                await self._set_restriction_flag(user_id, ProcessingRestriction.RESTRICTED)
                freeze_report["components"]["postgres"] = {"status": "restricted"}
        except Exception as e:
            logger.error(f"PostgreSQL restriction failed: {e}")
            freeze_report["components"]["postgres"] = {"status": "error", "error": "operation failed"}

        # Note: Active processing should be stopped by individual modules
        # The freeze_report indicates that processing is now restricted

        logger.info(f"GDPR freeze completed for user {user_id}")
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
                logger.info(f"Module '{module_name}' activated for user {user_id}")
            except Exception as e:
                logger.error(f"Module '{module_name}' unfreeze failed: {e}")
                unfreeze_report["components"][module_name] = {"status": "error", "error": "operation failed"}

        # Remove restriction flag in PostgreSQL
        try:
            if self.db:
                await self._set_restriction_flag(user_id, ProcessingRestriction.ACTIVE)
                unfreeze_report["components"]["postgres"] = {"status": "active"}
        except Exception as e:
            logger.error(f"PostgreSQL unrestriction failed: {e}")
            unfreeze_report["components"]["postgres"] = {"status": "error", "error": "operation failed"}

        logger.info(f"GDPR unfreeze completed for user {user_id}")
        return unfreeze_report

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

        logger.info(f"Retention check found {len(records_to_delete)} records to delete")
        return records_to_delete

    # =========================================================================
    # Private database methods (5-database aggregation implementations)
    # =========================================================================

    async def _export_postgres(self, user_id: int) -> dict[str, Any]:
        """
        Export user data from PostgreSQL.

        Queries all user-related tables and aggregates into a single export.
        Includes: users, sessions, goals, tasks, visions, daily_plans, consent,
        neurostate records, effectiveness data, etc.
        """
        if not self.db:
            return {}

        from sqlalchemy import text

        export_data: dict[str, Any] = {}

        try:
            # Query all tables that have user_id foreign key
            # This is a simplified version - in production, query each table explicitly
            async with self.db.begin() as conn:
                # Get user record
                user_result = await conn.execute(
                    text("SELECT * FROM users WHERE id = :user_id"),
                    {"user_id": user_id}
                )
                user_row = user_result.fetchone()
                if user_row:
                    export_data["user"] = dict(user_row._mapping)

                # Sessions
                sessions = await conn.execute(
                    text("SELECT * FROM sessions WHERE user_id = :user_id ORDER BY created_at DESC"),
                    {"user_id": user_id}
                )
                export_data["sessions"] = [dict(row._mapping) for row in sessions.fetchall()]

                # Goals
                goals = await conn.execute(
                    text("SELECT * FROM goals WHERE user_id = :user_id"),
                    {"user_id": user_id}
                )
                export_data["goals"] = [dict(row._mapping) for row in goals.fetchall()]

                # Tasks
                tasks = await conn.execute(
                    text("SELECT * FROM tasks WHERE user_id = :user_id"),
                    {"user_id": user_id}
                )
                export_data["tasks"] = [dict(row._mapping) for row in tasks.fetchall()]

                # Visions
                visions = await conn.execute(
                    text("SELECT * FROM visions WHERE user_id = :user_id"),
                    {"user_id": user_id}
                )
                export_data["visions"] = [dict(row._mapping) for row in visions.fetchall()]

                # Daily plans
                plans = await conn.execute(
                    text("SELECT * FROM daily_plans WHERE user_id = :user_id ORDER BY date DESC"),
                    {"user_id": user_id}
                )
                export_data["daily_plans"] = [dict(row._mapping) for row in plans.fetchall()]

                # Consent records
                consent = await conn.execute(
                    text("SELECT * FROM consent_records WHERE user_id = :user_id ORDER BY consented_at DESC"),
                    {"user_id": user_id}
                )
                export_data["consent_records"] = [dict(row._mapping) for row in consent.fetchall()]

        except Exception as e:
            logger.error(f"PostgreSQL export failed for user {user_id}: {e}")
            return {"error": str(e)}

        return export_data

    async def _export_redis(self, user_id: int) -> dict[str, Any]:
        """
        Export user data from Redis.

        Scans for all keys matching user:{user_id}:* pattern and exports their values.
        """
        if not self.redis:
            return {}

        export_data: dict[str, Any] = {}

        try:
            # Scan for user-specific keys
            pattern = f"user:{user_id}:*"
            cursor = 0
            keys = []

            while True:
                cursor, partial_keys = await self.redis.scan(cursor, match=pattern, count=100)
                keys.extend(partial_keys)
                if cursor == 0:
                    break

            # Export each key's value
            for key in keys:
                key_type = await self.redis.type(key)

                if key_type == b"string":
                    export_data[key.decode()] = await self.redis.get(key)
                elif key_type == b"hash":
                    export_data[key.decode()] = await self.redis.hgetall(key)
                elif key_type == b"list":
                    export_data[key.decode()] = await self.redis.lrange(key, 0, -1)
                elif key_type == b"set":
                    export_data[key.decode()] = await self.redis.smembers(key)
                elif key_type == b"zset":
                    export_data[key.decode()] = await self.redis.zrange(key, 0, -1, withscores=True)

        except Exception as e:
            logger.error(f"Redis export failed for user {user_id}: {e}")
            return {"error": str(e)}

        return export_data

    async def _export_neo4j(self, user_id: int) -> dict[str, Any]:
        """
        Export user subgraph from Neo4j.

        Calls Neo4jService.export_user_subgraph() which returns all nodes and
        relationships connected to the user.
        """
        if not self.neo4j:
            return {}

        try:
            from src.services.knowledge.neo4j_service import Neo4jService

            neo4j_service = Neo4jService(self.neo4j)
            subgraph = await neo4j_service.export_user_subgraph(user_id)

            return {
                "nodes": subgraph.nodes,
                "relationships": subgraph.relationships,
                "metadata": {
                    "node_count": subgraph.node_count,
                    "relationship_count": subgraph.relationship_count,
                    "exported_at": subgraph.exported_at.isoformat(),
                },
            }

        except Exception as e:
            logger.error(f"Neo4j export failed for user {user_id}: {e}")
            return {"error": str(e)}

    async def _export_qdrant(self, user_id: int) -> dict[str, Any]:
        """
        Export user vectors from Qdrant.

        Calls QdrantService.export_user_vectors() which returns all vectors
        owned by the user across all collections.
        """
        if not self.qdrant:
            return {}

        try:
            from src.services.knowledge.qdrant_service import QdrantService

            qdrant_service = QdrantService(self.qdrant)
            vector_export = await qdrant_service.export_user_vectors(user_id)

            return {
                "vectors": vector_export.vectors,
                "metadata": {
                    "vector_count": vector_export.vector_count,
                    "exported_at": vector_export.exported_at.isoformat(),
                },
            }

        except Exception as e:
            logger.error(f"Qdrant export failed for user {user_id}: {e}")
            return {"error": str(e)}

    async def _export_letta(self, user_id: int) -> dict[str, Any]:
        """
        Export user memories from Letta.

        Calls LettaService.export_user_memories() which returns all coaching
        session transcripts and agent memories.

        IMPORTANT: Decrypts coaching transcripts before export (GDPR Art. 15 requires
        readable format).
        """
        if not self.letta:
            return {}

        try:
            from src.services.knowledge.letta_service import LettaService

            letta_service = LettaService(self.letta)
            memory_export = await letta_service.export_user_memories(user_id)

            return {
                "memories": memory_export.memories,
                "metadata": {
                    "memory_count": memory_export.memory_count,
                    "exported_at": memory_export.exported_at.isoformat(),
                },
            }

        except Exception as e:
            logger.error(f"Letta export failed for user {user_id}: {e}")
            return {"error": str(e)}

    async def _delete_postgres(self, user_id: int) -> None:
        """
        Delete all user data from PostgreSQL (cascade).

        Deletes the user record, which cascades to all related tables via
        foreign key constraints (ON DELETE CASCADE).
        """
        if not self.db:
            return

        from sqlalchemy import text

        try:
            async with self.db.begin() as conn:
                await conn.execute(
                    text("DELETE FROM users WHERE id = :user_id"),
                    {"user_id": user_id}
                )
                # CASCADE constraint will delete:
                # - sessions, goals, tasks, visions, daily_plans, consent_records
                # - neurostate records, effectiveness data, etc.

        except Exception as e:
            logger.error(f"PostgreSQL deletion failed for user {user_id}: {e}")
            raise

    async def _delete_redis(self, user_id: int) -> None:
        """
        Delete all user keys from Redis.

        Scans for user:{user_id}:* pattern and deletes all matching keys.
        """
        if not self.redis:
            return

        try:
            # Scan for user-specific keys
            pattern = f"user:{user_id}:*"
            cursor = 0
            keys = []

            while True:
                cursor, partial_keys = await self.redis.scan(cursor, match=pattern, count=100)
                keys.extend(partial_keys)
                if cursor == 0:
                    break

            # Delete all keys in batch
            if keys:
                await self.redis.delete(*keys)

        except Exception as e:
            logger.error(f"Redis deletion failed for user {user_id}: {e}")
            raise

    async def _delete_neo4j(self, user_id: int) -> None:
        """
        Delete user subgraph from Neo4j.

        Calls Neo4jService.delete_user_subgraph() which deletes the User node
        and all connected nodes/relationships.
        """
        if not self.neo4j:
            return

        try:
            from src.services.knowledge.neo4j_service import Neo4jService

            neo4j_service = Neo4jService(self.neo4j)
            await neo4j_service.delete_user_subgraph(user_id)

        except Exception as e:
            logger.error(f"Neo4j deletion failed for user {user_id}: {e}")
            raise

    async def _delete_qdrant(self, user_id: int) -> None:
        """
        Delete user vectors from Qdrant.

        Calls QdrantService.delete_user_vectors() which deletes all vectors
        owned by the user and verifies no cross-user leakage.
        """
        if not self.qdrant:
            return

        try:
            from src.services.knowledge.qdrant_service import QdrantService

            qdrant_service = QdrantService(self.qdrant)
            await qdrant_service.delete_user_vectors(user_id)

        except Exception as e:
            logger.error(f"Qdrant deletion failed for user {user_id}: {e}")
            raise

    async def _delete_letta(self, user_id: int) -> None:
        """
        Delete user memories from Letta.

        Calls LettaService.delete_user_memories() which:
        - Deletes coaching session transcripts (encrypted)
        - Purges agent memories
        - Marks encryption keys for destruction

        IMPORTANT: Full purge on delete, no recovery possible after this.
        """
        if not self.letta:
            return

        try:
            from src.services.knowledge.letta_service import LettaService

            letta_service = LettaService(self.letta)
            await letta_service.delete_user_memories(user_id)

        except Exception as e:
            logger.error(f"Letta deletion failed for user {user_id}: {e}")
            raise

    async def _set_restriction_flag(
        self, user_id: int, restriction: ProcessingRestriction
    ) -> None:
        """
        Set processing restriction flag in PostgreSQL.

        Updates the users.processing_restriction column to ACTIVE or RESTRICTED.
        """
        if not self.db:
            return

        from sqlalchemy import text

        try:
            async with self.db.begin() as conn:
                await conn.execute(
                    text("UPDATE users SET processing_restriction = :restriction WHERE id = :user_id"),
                    {"restriction": restriction.value, "user_id": user_id}
                )

        except Exception as e:
            logger.error(f"Set restriction flag failed for user {user_id}: {e}")
            raise
