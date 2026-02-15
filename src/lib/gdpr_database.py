"""
GDPR database operations (deletion and restriction flag management).

Extracted from src/lib/gdpr.py for maintainability.
Contains the private database methods used by erasure and restriction mixins.
"""

import logging
from typing import Any

from src.lib.gdpr_types import ProcessingRestriction
from src.lib.security import hash_uid

logger = logging.getLogger(__name__)


class GDPRDatabaseMixin:
    """Mixin providing GDPR database operations for GDPRService."""

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
            logger.error("PostgreSQL deletion failed for user_hash=%s: %s", hash_uid(user_id), e)
            raise

    async def _delete_redis(self, user_id: int) -> None:
        """
        Delete all user keys from Redis.

        Scans for user:{user_id}:* and aurora:*:{user_id}:* patterns
        and deletes all matching keys.
        """
        if not self.redis:
            return

        try:
            # Scan for both user-prefixed and aurora-prefixed keys
            patterns = [
                f"user:{user_id}:*",
                f"aurora:*:{user_id}:*",
            ]
            keys: list[Any] = []

            for pattern in patterns:
                cursor = 0
                while True:
                    cursor, partial_keys = await self.redis.scan(cursor, match=pattern, count=100)
                    keys.extend(partial_keys)
                    if cursor == 0:
                        break

            # Delete all keys in batch
            if keys:
                await self.redis.delete(*keys)

        except Exception as e:
            logger.error("Redis deletion failed for user_hash=%s: %s", hash_uid(user_id), e)
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
            logger.error("Neo4j deletion failed for user_hash=%s: %s", hash_uid(user_id), e)
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
            logger.error("Qdrant deletion failed for user_hash=%s: %s", hash_uid(user_id), e)
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
            logger.error("Letta deletion failed for user_hash=%s: %s", hash_uid(user_id), e)
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
            logger.error("Set restriction flag failed for user_hash=%s: %s", hash_uid(user_id), e)
            raise
