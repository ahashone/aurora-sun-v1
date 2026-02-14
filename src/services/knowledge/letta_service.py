"""
Letta Memory Service for Aurora Sun V1.

Memory service wrapper for the Knowledge Layer. Manages:
- 3-tier memory: short-term session, long-term profile, archival history
- Coaching transcript storage (encrypted, ART_9_SPECIAL classification)
- GDPR: export/delete all user memories (SW-15)

When client=None (stub mode), all operations succeed with in-memory stubs.
This allows development and testing without a running Letta instance.

Reference: ARCHITECTURE.md Section 5 (Knowledge Layer)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.lib.encryption import DataClassification
from src.lib.security import hash_uid

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class MemoryTier(StrEnum):
    """Memory tier classification."""

    SESSION = "session"          # Short-term: current conversation context
    PROFILE = "profile"          # Long-term: user preferences, patterns, segment info
    ARCHIVAL = "archival"        # Historical: coaching transcripts, past sessions


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class Memory:
    """Represents a single memory entry."""

    memory_id: str
    tier: MemoryTier
    user_id: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    classification: DataClassification = DataClassification.SENSITIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    session_id: str | None = None


@dataclass
class SessionContext:
    """Aggregated context for a user's current session."""

    user_id: int
    session_id: str
    memories: list[Memory]
    profile_summary: str = ""
    recent_topics: list[str] = field(default_factory=list)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class MemoryExport:
    """GDPR export: all memories for a user."""

    user_id: int
    memories: list[dict[str, Any]]
    exported_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    memory_count: int = 0

    def __post_init__(self) -> None:
        """Set count from data if not provided."""
        if self.memory_count == 0:
            self.memory_count = len(self.memories)


# =============================================================================
# Service
# =============================================================================


class LettaService:
    """
    Letta memory service wrapper.

    Manages the 3-tier memory system for Aurora Sun V1:
    - SESSION: Short-term context for the current conversation.
    - PROFILE: Long-term user preferences, discovered patterns, segment info.
    - ARCHIVAL: Historical coaching transcripts and past session summaries.

    Coaching transcripts are classified as ART_9_SPECIAL (health data)
    and must be encrypted at rest.

    When client is None (stub mode), all operations succeed with in-memory
    storage for development and testing.

    Args:
        client: Optional Letta client instance. None = stub mode.
    """

    def __init__(self, client: Any | None = None) -> None:
        """Initialize Letta service."""
        self._client = client
        self._stub_mode = client is None

        # In-memory stub storage: user_id -> list of memories
        self._stub_memories: dict[int, list[Memory]] = {}

        if self._stub_mode:
            logger.info("LettaService initialized in stub mode (no client)")
        else:
            logger.info("LettaService initialized with live client")

    @property
    def is_stub(self) -> bool:
        """Return True if running in stub mode."""
        return self._stub_mode

    async def store_memory(
        self,
        tier: MemoryTier,
        user_id: int,
        content: str,
        metadata: dict[str, Any] | None = None,
        classification: DataClassification = DataClassification.SENSITIVE,
        session_id: str | None = None,
        memory_id: str | None = None,
    ) -> Memory:
        """
        Store a memory in the specified tier.

        Coaching transcripts and health-related data should use
        ART_9_SPECIAL classification for proper encryption.

        Args:
            tier: Which memory tier to store in.
            user_id: The user this memory belongs to.
            content: The memory content text.
            metadata: Optional metadata dictionary.
            classification: Data classification for encryption.
            session_id: Optional session ID for SESSION-tier memories.
            memory_id: Optional custom memory ID. Auto-generated if not provided.

        Returns:
            The stored Memory object.
        """
        resolved_id = memory_id or str(uuid.uuid4())
        now = datetime.now(UTC)

        memory = Memory(
            memory_id=resolved_id,
            tier=tier,
            user_id=user_id,
            content=content,
            metadata=metadata or {},
            classification=classification,
            created_at=now,
            updated_at=now,
            session_id=session_id,
        )

        if self._stub_mode:
            self._stub_memories.setdefault(user_id, []).append(memory)
            logger.debug(
                "Stub: Stored memory %s (tier=%s, user=%d, classification=%s)",
                resolved_id,
                tier,
                user_id,
                classification.value,
            )
        else:
            await self._store_memory_live(memory)

        return memory

    async def _store_memory_live(self, memory: Memory) -> None:
        """Store memory in live Letta service."""
        # Letta client API for memory creation
        await self._client.create_memory(  # type: ignore[union-attr]
            user_id=str(memory.user_id),
            content=memory.content,
            metadata={
                "tier": str(memory.tier),
                "classification": memory.classification.value,
                "session_id": memory.session_id,
                "memory_id": memory.memory_id,
                **(memory.metadata),
            },
        )
        logger.info(
            "Stored memory %s (tier=%s, user=%d)",
            memory.memory_id,
            memory.tier,
            memory.user_id,
        )

    async def recall_memories(
        self,
        user_id: int,
        tier: MemoryTier | None = None,
        query: str | None = None,
        limit: int = 20,
        session_id: str | None = None,
    ) -> list[Memory]:
        """
        Recall memories for a user, optionally filtered by tier and query.

        Args:
            user_id: The user whose memories to recall.
            tier: Optional tier filter.
            query: Optional search query for semantic matching.
            limit: Maximum number of memories to return.
            session_id: Optional session ID filter (for SESSION tier).

        Returns:
            List of Memory objects, most recent first.
        """
        if self._stub_mode:
            return self._recall_memories_stub(user_id, tier, query, limit, session_id)

        return await self._recall_memories_live(user_id, tier, query, limit, session_id)

    def _recall_memories_stub(
        self,
        user_id: int,
        tier: MemoryTier | None,
        query: str | None,
        limit: int,
        session_id: str | None,
    ) -> list[Memory]:
        """Recall memories from stub storage."""
        user_memories = self._stub_memories.get(user_id, [])

        results: list[Memory] = []
        for memory in user_memories:
            if tier and memory.tier != tier:
                continue
            if session_id and memory.session_id != session_id:
                continue
            if query and query.lower() not in memory.content.lower():
                continue
            results.append(memory)

        # Most recent first
        results.sort(key=lambda m: m.created_at, reverse=True)
        logger.debug(
            "Stub: Recalled %d memories for user %d (tier=%s)",
            min(limit, len(results)),
            user_id,
            tier,
        )
        return results[:limit]

    async def _recall_memories_live(
        self,
        user_id: int,
        tier: MemoryTier | None,
        query: str | None,
        limit: int,
        session_id: str | None,
    ) -> list[Memory]:
        """Recall memories from live Letta service."""
        filters: dict[str, Any] = {"user_id": str(user_id)}
        if tier:
            filters["tier"] = str(tier)
        if session_id:
            filters["session_id"] = session_id

        if query:
            results = await self._client.search_memory(  # type: ignore[union-attr]
                user_id=str(user_id),
                query=query,
                limit=limit,
                filters=filters,
            )
        else:
            results = await self._client.list_memories(  # type: ignore[union-attr]
                user_id=str(user_id),
                limit=limit,
                filters=filters,
            )

        memories: list[Memory] = []
        for item in results:
            meta = item.get("metadata", {})
            memories.append(
                Memory(
                    memory_id=meta.get("memory_id", str(uuid.uuid4())),
                    tier=MemoryTier(meta.get("tier", "archival")),
                    user_id=user_id,
                    content=item.get("content", ""),
                    metadata=meta,
                    classification=DataClassification(
                        meta.get("classification", "sensitive")
                    ),
                    session_id=meta.get("session_id"),
                )
            )

        logger.info("Recalled %d memories for user_hash=%s", len(memories), hash_uid(user_id))
        return memories

    async def get_session_context(
        self,
        user_id: int,
        session_id: str,
        include_profile: bool = True,
        max_session_memories: int = 50,
    ) -> SessionContext:
        """
        Get aggregated context for a user's current session.

        Combines session memories with profile information for
        the coaching agents to use as context.

        Args:
            user_id: The user ID.
            session_id: The current session ID.
            include_profile: Whether to include PROFILE tier memories.
            max_session_memories: Maximum session memories to include.

        Returns:
            SessionContext with session memories and profile summary.
        """
        # Get session memories
        session_memories = await self.recall_memories(
            user_id=user_id,
            tier=MemoryTier.SESSION,
            session_id=session_id,
            limit=max_session_memories,
        )

        profile_summary = ""
        recent_topics: list[str] = []

        if include_profile:
            profile_memories = await self.recall_memories(
                user_id=user_id,
                tier=MemoryTier.PROFILE,
                limit=10,
            )
            if profile_memories:
                profile_summary = "; ".join(
                    m.content[:100] for m in profile_memories[:5]
                )
                for mem in profile_memories:
                    topics = mem.metadata.get("topics", [])
                    if isinstance(topics, list):
                        recent_topics.extend(str(t) for t in topics)

        return SessionContext(
            user_id=user_id,
            session_id=session_id,
            memories=session_memories,
            profile_summary=profile_summary,
            recent_topics=recent_topics[:20],
        )

    async def export_user_memories(self, user_id: int) -> MemoryExport:
        """
        Export all memories for a user (GDPR Art. 20 data portability).

        Args:
            user_id: The user whose memories to export.

        Returns:
            MemoryExport containing all memory data.
        """
        if self._stub_mode:
            user_memories = self._stub_memories.get(user_id, [])
            memories_data = [
                {
                    "memory_id": m.memory_id,
                    "tier": str(m.tier),
                    "content": m.content,
                    "metadata": m.metadata,
                    "classification": m.classification.value,
                    "created_at": m.created_at.isoformat(),
                    "updated_at": m.updated_at.isoformat(),
                    "session_id": m.session_id,
                }
                for m in user_memories
            ]
            logger.info(
                "Stub: Exported %d memories for user %d",
                len(memories_data),
                user_id,
            )
            return MemoryExport(user_id=user_id, memories=memories_data)

        return await self._export_user_memories_live(user_id)

    async def _export_user_memories_live(self, user_id: int) -> MemoryExport:
        """Export user memories from live Letta service."""
        all_memories = await self._client.list_memories(  # type: ignore[union-attr]
            user_id=str(user_id),
            limit=100000,
        )
        memories_data: list[dict[str, Any]] = []
        for item in all_memories:
            memories_data.append({
                "content": item.get("content", ""),
                "metadata": item.get("metadata", {}),
            })

        logger.info("Exported %d memories for user_hash=%s", len(memories_data), hash_uid(user_id))
        return MemoryExport(user_id=user_id, memories=memories_data)

    async def delete_user_memories(self, user_id: int) -> int:
        """
        Delete all memories for a user (GDPR Art. 17 right to erasure).

        Args:
            user_id: The user whose memories to delete.

        Returns:
            Number of memories deleted.
        """
        if self._stub_mode:
            user_memories = self._stub_memories.pop(user_id, [])
            count = len(user_memories)
            logger.info(
                "Stub: Deleted %d memories for user %d",
                count,
                user_id,
            )
            return count

        return await self._delete_user_memories_live(user_id)

    async def _delete_user_memories_live(self, user_id: int) -> int:
        """Delete user memories from live Letta service."""
        result = await self._client.delete_user_memories(  # type: ignore[union-attr]
            user_id=str(user_id),
        )
        count: int = result.get("deleted_count", 0) if isinstance(result, dict) else 0
        logger.info("Deleted %d memories for user_hash=%s", count, hash_uid(user_id))
        return count


# =============================================================================
# Singleton
# =============================================================================

_letta_service: LettaService | None = None


def get_letta_service(client: Any | None = None) -> LettaService:
    """Get or create the Letta service singleton."""
    global _letta_service
    if _letta_service is None:
        _letta_service = LettaService(client=client)
    return _letta_service
