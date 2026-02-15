"""
GDPR data erasure operations (Art. 17 - Right to be forgotten).

Extracted from src/lib/gdpr.py for maintainability.
Contains single-user and bulk deletion methods for the GDPRService.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.lib.security import hash_uid

logger = logging.getLogger(__name__)


class GDPRErasureMixin:
    """Mixin providing GDPR erasure operations for GDPRService."""

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

        # Track critical database failures separately (GDPR erasure must be complete)
        critical_failures: list[str] = []
        succeeded_components: list[str] = []

        # Delete from each registered module
        for module_name, module in self._modules.items():
            try:
                await module.delete_user_data(user_id)
                deletion_report["components"][module_name] = {"status": "deleted"}
                succeeded_components.append(module_name)
                logger.info("Module '%s' data deleted for user_hash=%s", module_name, hash_uid(user_id))
            except Exception as e:
                logger.error("Module '%s' deletion failed for user_hash=%s: %s", module_name, hash_uid(user_id), e)
                deletion_report["components"][module_name] = {"status": "error", "error": "deletion failed"}

        # Delete from PostgreSQL (CRITICAL)
        try:
            if self.db:
                await self._delete_postgres(user_id)
                deletion_report["components"]["postgres"] = {"status": "deleted"}
                succeeded_components.append("postgres")
        except Exception as e:
            logger.error("PostgreSQL deletion failed for user_hash=%s: %s", hash_uid(user_id), e)
            deletion_report["components"]["postgres"] = {"status": "error", "error": "operation failed"}
            critical_failures.append("postgres")

        # Delete from Redis (CRITICAL)
        try:
            if self.redis:
                await self._delete_redis(user_id)
                deletion_report["components"]["redis"] = {"status": "deleted"}
                succeeded_components.append("redis")
        except Exception as e:
            logger.error("Redis deletion failed for user_hash=%s: %s", hash_uid(user_id), e)
            deletion_report["components"]["redis"] = {"status": "error", "error": "operation failed"}
            critical_failures.append("redis")

        # Delete from Neo4j
        try:
            if self.neo4j:
                await self._delete_neo4j(user_id)
                deletion_report["components"]["neo4j"] = {"status": "deleted"}
                succeeded_components.append("neo4j")
        except Exception as e:
            logger.error("Neo4j deletion failed for user_hash=%s: %s", hash_uid(user_id), e)
            deletion_report["components"]["neo4j"] = {"status": "error", "error": "operation failed"}

        # Delete from Qdrant
        try:
            if self.qdrant:
                await self._delete_qdrant(user_id)
                deletion_report["components"]["qdrant"] = {"status": "deleted"}
                succeeded_components.append("qdrant")
        except Exception as e:
            logger.error("Qdrant deletion failed for user_hash=%s: %s", hash_uid(user_id), e)
            deletion_report["components"]["qdrant"] = {"status": "error", "error": "operation failed"}

        # Delete from Letta
        try:
            if self.letta:
                await self._delete_letta(user_id)
                deletion_report["components"]["letta"] = {"status": "deleted"}
                succeeded_components.append("letta")
        except Exception as e:
            logger.error("Letta deletion failed for user_hash=%s: %s", hash_uid(user_id), e)
            deletion_report["components"]["letta"] = {"status": "error", "error": "operation failed"}

        # Destroy encryption keys (actual key destruction, not just deletion of encrypted data)
        try:
            from src.lib.encryption import get_encryption_service
            encryption_service = get_encryption_service()
            encryption_service.destroy_keys(user_id)
            deletion_report["components"]["encryption_keys"] = {"status": "destroyed"}
            succeeded_components.append("encryption_keys")
            logger.info("Encryption keys destroyed for user_hash=%s", hash_uid(user_id))
        except Exception as e:
            logger.error("Encryption key destruction failed for user_hash=%s: %s", hash_uid(user_id), e)
            deletion_report["components"]["encryption_keys"] = {"status": "error", "error": "key destruction failed"}
            critical_failures.append("encryption_keys")

        # If ANY critical database fails (PostgreSQL, Redis),
        # mark entire operation as FAILED, not "partial"
        all_success = all(
            comp.get("status") in ("deleted", "destroyed")
            for comp in deletion_report["components"].values()
        )
        if all_success:
            deletion_report["overall_status"] = "success"
        elif critical_failures:
            deletion_report["overall_status"] = "failed"
            deletion_report["critical_failures"] = critical_failures
            deletion_report["succeeded_components"] = succeeded_components
            logger.error(
                "GDPR deletion FAILED for user_hash=%s: critical databases failed: %s (succeeded: %s)",
                hash_uid(user_id), critical_failures, succeeded_components,
            )
        else:
            deletion_report["overall_status"] = "partial"
            deletion_report["succeeded_components"] = succeeded_components

        logger.info(
            "GDPR deletion completed for user_hash=%s: %s",
            hash_uid(user_id), deletion_report["overall_status"],
        )
        return deletion_report

    async def bulk_delete_users(self, user_ids: list[int]) -> dict[str, Any]:
        """
        PERF-003: Bulk GDPR delete for multiple users.

        Instead of calling delete_user_data() per user (N+1 pattern),
        this method batches database operations across all users.

        Args:
            user_ids: List of user identifiers to delete

        Returns:
            dict: Bulk deletion report with per-user and aggregate status
        """
        if not user_ids:
            return {"user_count": 0, "results": {}, "overall_status": "success"}

        results: dict[int, dict[str, Any]] = {}
        overall_failures: list[int] = []

        # Phase 1: Batch module deletions (call each module once per user)
        module_errors: dict[int, list[str]] = {uid: [] for uid in user_ids}
        for module_name, module in self._modules.items():
            for uid in user_ids:
                try:
                    await module.delete_user_data(uid)
                except Exception as e:
                    logger.error(
                        "Module '%s' bulk deletion failed for user_hash=%s: %s",
                        module_name, hash_uid(uid), e,
                    )
                    module_errors[uid].append(module_name)

        # Phase 2: Batch database deletions
        # PostgreSQL batch delete (single transaction for all users)
        pg_failed_users: list[int] = []
        if self.db:
            try:
                from sqlalchemy import text
                async with self.db.begin() as conn:
                    for uid in user_ids:
                        await conn.execute(
                            text("DELETE FROM users WHERE id = :user_id"),
                            {"user_id": uid},
                        )
            except Exception as e:
                logger.error("PostgreSQL bulk deletion failed: %s", e)
                pg_failed_users = list(user_ids)

        # Redis batch delete (scan + pipeline delete per user)
        redis_failed_users: list[int] = []
        if self.redis:
            try:
                all_keys: list[Any] = []
                for uid in user_ids:
                    for pattern in [f"user:{uid}:*", f"aurora:*:{uid}:*"]:
                        cursor = 0
                        while True:
                            cursor, partial_keys = await self.redis.scan(
                                cursor, match=pattern, count=100,
                            )
                            all_keys.extend(partial_keys)
                            if cursor == 0:
                                break
                if all_keys:
                    await self.redis.delete(*all_keys)
            except Exception as e:
                logger.error("Redis bulk deletion failed: %s", e)
                redis_failed_users = list(user_ids)

        # Neo4j batch delete
        neo4j_failed_users: list[int] = []
        if self.neo4j:
            for uid in user_ids:
                try:
                    await self._delete_neo4j(uid)
                except Exception as e:
                    logger.error("Neo4j deletion failed for user_hash=%s: %s", hash_uid(uid), e)
                    neo4j_failed_users.append(uid)

        # Qdrant batch delete
        qdrant_failed_users: list[int] = []
        if self.qdrant:
            for uid in user_ids:
                try:
                    await self._delete_qdrant(uid)
                except Exception as e:
                    logger.error("Qdrant deletion failed for user_hash=%s: %s", hash_uid(uid), e)
                    qdrant_failed_users.append(uid)

        # Letta batch delete
        letta_failed_users: list[int] = []
        if self.letta:
            for uid in user_ids:
                try:
                    await self._delete_letta(uid)
                except Exception as e:
                    logger.error("Letta deletion failed for user_hash=%s: %s", hash_uid(uid), e)
                    letta_failed_users.append(uid)

        # Phase 3: Batch encryption key destruction
        encryption_failed_users: list[int] = []
        try:
            from src.lib.encryption import get_encryption_service
            encryption_service = get_encryption_service()
            for uid in user_ids:
                try:
                    encryption_service.destroy_keys(uid)
                except Exception as e:
                    logger.error("Key destruction failed for user_hash=%s: %s", hash_uid(uid), e)
                    encryption_failed_users.append(uid)
        except Exception as e:
            logger.error("Encryption service unavailable for bulk key destruction: %s", e)
            encryption_failed_users = list(user_ids)

        # Phase 4: Build per-user results
        for uid in user_ids:
            critical_failures: list[str] = []
            if uid in pg_failed_users:
                critical_failures.append("postgres")
            if uid in redis_failed_users:
                critical_failures.append("redis")
            if uid in encryption_failed_users:
                critical_failures.append("encryption_keys")

            non_critical_failures: list[str] = list(module_errors[uid])
            if uid in neo4j_failed_users:
                non_critical_failures.append("neo4j")
            if uid in qdrant_failed_users:
                non_critical_failures.append("qdrant")
            if uid in letta_failed_users:
                non_critical_failures.append("letta")

            if critical_failures:
                status = "failed"
                overall_failures.append(uid)
            elif non_critical_failures:
                status = "partial"
            else:
                status = "success"

            results[uid] = {
                "status": status,
                "critical_failures": critical_failures,
                "non_critical_failures": non_critical_failures,
            }

        overall_status = "success"
        if overall_failures:
            overall_status = "failed"
        elif any(r["status"] == "partial" for r in results.values()):
            overall_status = "partial"

        logger.info(
            "GDPR bulk deletion completed: %d users, status=%s",
            len(user_ids), overall_status,
        )
        return {
            "user_count": len(user_ids),
            "results": results,
            "overall_status": overall_status,
            "failed_user_ids": overall_failures,
        }
