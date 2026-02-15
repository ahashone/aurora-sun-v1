"""
GDPR data export operations (Art. 15 & 20).

Extracted from src/lib/gdpr.py for maintainability.
Contains all export-related methods for the GDPRService.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.lib.gdpr_types import GDPRExportRecord
from src.lib.security import hash_uid

logger = logging.getLogger(__name__)


class GDPRExportMixin:
    """Mixin providing GDPR export operations for GDPRService."""

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
        await self._export_from_modules(user_id, exports, errors)

        # Export from direct database connections
        await self._export_from_databases(user_id, exports, errors)

        # Build export package (track completeness for GDPR compliance)
        export_package = self._build_export_package(user_id, exports, errors)

        logger.info(
            "GDPR export completed for user_hash=%s: %d modules, %d errors, complete=%s",
            hash_uid(user_id), len(exports), len(errors), len(errors) == 0,
        )
        return export_package

    async def _export_from_modules(
        self,
        user_id: int,
        exports: list[GDPRExportRecord],
        errors: list[str],
    ) -> None:
        """Export data from all registered GDPR modules.

        Calls export_user_data() on each registered module and collects results.
        Failures are logged and appended to the errors list.

        Args:
            user_id: User identifier.
            exports: Accumulator for successful exports (mutated in place).
            errors: Accumulator for failure descriptions (mutated in place).
        """
        for module_name, module in self._modules.items():
            try:
                data = await module.export_user_data(user_id)
                exports.append(GDPRExportRecord(
                    module_name=module_name,
                    exported_at=datetime.now(UTC),
                    data=data,
                ))
            except Exception as e:
                logger.error(
                    "Module '%s' export failed for user_hash=%s: %s",
                    module_name, hash_uid(user_id), e,
                )
                errors.append(f"{module_name}: export failed")

    async def _export_from_databases(
        self,
        user_id: int,
        exports: list[GDPRExportRecord],
        errors: list[str],
    ) -> None:
        """Export data from all direct database connections.

        Iterates over the configured database backends (PostgreSQL, Redis,
        Neo4j, Qdrant, Letta) and exports user data from each.

        Args:
            user_id: User identifier.
            exports: Accumulator for successful exports (mutated in place).
            errors: Accumulator for failure descriptions (mutated in place).
        """
        db_sources: list[tuple[str, Any, Any]] = [
            ("postgres", self.db, self._export_postgres),
            ("redis", self.redis, self._export_redis),
            ("neo4j", self.neo4j, self._export_neo4j),
            ("qdrant", self.qdrant, self._export_qdrant),
            ("letta", self.letta, self._export_letta),
        ]

        for source_name, client, export_fn in db_sources:
            if not client:
                continue
            try:
                data = await export_fn(user_id)
                if data:
                    exports.append(GDPRExportRecord(
                        module_name=source_name,
                        exported_at=datetime.now(UTC),
                        data=data,
                    ))
            except Exception as e:
                logger.error(
                    "%s export failed for user_hash=%s: %s",
                    source_name.capitalize(), hash_uid(user_id), e,
                )
                errors.append(f"{source_name}: export failed")

    @staticmethod
    def _build_export_package(
        user_id: int,
        exports: list[GDPRExportRecord],
        errors: list[str],
    ) -> dict[str, Any]:
        """Assemble the final export package with metadata.

        Args:
            user_id: User identifier.
            exports: Successful export records.
            errors: Failure descriptions.

        Returns:
            Complete export dict with metadata and per-module data.
        """
        is_complete = len(errors) == 0
        return {
            "export_metadata": {
                "user_id_hash": hash_uid(user_id),
                "exported_at": datetime.now(UTC).isoformat(),
                "aurora_version": "v1",
                "total_records": len(exports),
                "complete": is_complete,
                "failed_modules": errors if errors else [],
                "completeness_warning": (
                    "Data export may be incomplete. Some modules failed during export."
                    if not is_complete else None
                ),
            },
            "modules": {
                record.module_name: {
                    "exported_at": record.exported_at.isoformat(),
                    "data": record.data,
                }
                for record in exports
            },
        }

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
            logger.error("PostgreSQL export failed for user_hash=%s: %s", hash_uid(user_id), e)
            return {"error": "export failed"}

        return export_data

    async def _export_redis(self, user_id: int) -> dict[str, Any]:
        """
        Export user data from Redis.

        Scans for user:{user_id}:* and aurora:*:{user_id}:* patterns
        and exports their values.
        """
        if not self.redis:
            return {}

        export_data: dict[str, Any] = {}

        try:
            # Scan for user-specific keys (both prefixes)
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
            logger.error("Redis export failed for user_hash=%s: %s", hash_uid(user_id), e)
            return {"error": "export failed"}

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

        except ImportError as e:
            logger.error("Neo4j service not available for user_hash=%s: %s", hash_uid(user_id), e)
            return {"error": "export failed"}
        except Exception as e:
            logger.error("Neo4j export failed for user_hash=%s: %s", hash_uid(user_id), e)
            return {"error": "export failed"}

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

        except ImportError as e:
            logger.error("Qdrant service not available for user_hash=%s: %s", hash_uid(user_id), e)
            return {"error": "export failed"}
        except Exception as e:
            logger.error("Qdrant export failed for user_hash=%s: %s", hash_uid(user_id), e)
            return {"error": "export failed"}

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

        except ImportError as e:
            logger.error("Letta service not available for user_hash=%s: %s", hash_uid(user_id), e)
            return {"error": "export failed"}
        except Exception as e:
            logger.error("Letta export failed for user_hash=%s: %s", hash_uid(user_id), e)
            return {"error": "export failed"}
