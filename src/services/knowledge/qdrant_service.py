"""
Qdrant Vector Service for Aurora Sun V1.

Vector database wrapper for the Knowledge Layer. Manages:
- Embedding storage and retrieval (captured items, research, coaching traces)
- Semantic search with time-aware filtering
- User-scoped collections (no cross-user leakage)
- GDPR: delete/export user vectors (SW-15)

When client=None (stub mode), all operations succeed with in-memory stubs.
This allows development and testing without a running Qdrant instance.

Reference: ARCHITECTURE.md Section 5 (Knowledge Layer)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.lib.security import hash_uid

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class CollectionName(StrEnum):
    """Named collections in the vector store."""

    CAPTURED_ITEMS = "captured_items"
    RESEARCH_FINDINGS = "research_findings"
    COACHING_TRACES = "coaching_traces"
    USER_NOTES = "user_notes"
    JOURNAL_ENTRIES = "journal_entries"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class EmbeddingResult:
    """Result of storing an embedding."""

    point_id: str
    collection: CollectionName
    user_id: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class SearchResult:
    """A single result from a semantic search."""

    point_id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)
    collection: CollectionName = CollectionName.CAPTURED_ITEMS


@dataclass
class VectorExport:
    """GDPR export: all vectors for a user."""

    user_id: int
    vectors: list[dict[str, Any]]
    exported_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    vector_count: int = 0

    def __post_init__(self) -> None:
        """Set count from data if not provided."""
        if self.vector_count == 0:
            self.vector_count = len(self.vectors)


# =============================================================================
# Stub storage item
# =============================================================================


@dataclass
class _StubPoint:
    """Internal stub storage for a vector point."""

    point_id: str
    collection: CollectionName
    user_id: int
    vector: list[float]
    payload: dict[str, Any]
    created_at: datetime


# =============================================================================
# Service
# =============================================================================


class QdrantService:
    """
    Qdrant vector database service wrapper.

    Manages vector embeddings for semantic search across captured items,
    research findings, coaching traces, and user notes. All vectors are
    user-scoped to prevent cross-user data leakage.

    When client is None (stub mode), all operations succeed with in-memory
    storage for development and testing.

    Args:
        client: Optional Qdrant async client instance. None = stub mode.
    """

    def __init__(self, client: Any | None = None) -> None:
        """Initialize Qdrant service."""
        self._client = client
        self._stub_mode = client is None

        # In-memory stub storage: collection -> list of points
        self._stub_points: dict[CollectionName, list[_StubPoint]] = {
            c: [] for c in CollectionName
        }

        if self._stub_mode:
            logger.info("QdrantService initialized in stub mode (no client)")
        else:
            logger.info("QdrantService initialized with live client")

    @property
    def is_stub(self) -> bool:
        """Return True if running in stub mode."""
        return self._stub_mode

    async def store_embedding(
        self,
        collection: CollectionName,
        user_id: int,
        vector: list[float],
        payload: dict[str, Any] | None = None,
        point_id: str | None = None,
    ) -> EmbeddingResult:
        """
        Store a vector embedding in the specified collection.

        All embeddings are tagged with user_id for scoping and GDPR compliance.

        Args:
            collection: Which collection to store in.
            user_id: The user this embedding belongs to.
            vector: The embedding vector (list of floats).
            payload: Optional metadata payload.
            point_id: Optional custom point ID. Auto-generated if not provided.

        Returns:
            EmbeddingResult with the stored point ID and metadata.
        """
        resolved_id = point_id or str(uuid.uuid4())
        now = datetime.now(UTC)
        resolved_payload = payload or {}
        resolved_payload["user_id"] = user_id
        resolved_payload["created_at"] = now.isoformat()

        if self._stub_mode:
            point = _StubPoint(
                point_id=resolved_id,
                collection=collection,
                user_id=user_id,
                vector=vector,
                payload=resolved_payload,
                created_at=now,
            )
            self._stub_points[collection].append(point)
            logger.debug(
                "Stub: Stored embedding %s in %s for user %d",
                resolved_id,
                collection,
                user_id,
            )
        else:
            await self._store_embedding_live(
                collection, resolved_id, vector, resolved_payload
            )

        return EmbeddingResult(
            point_id=resolved_id,
            collection=collection,
            user_id=user_id,
            created_at=now,
        )

    async def _store_embedding_live(
        self,
        collection: CollectionName,
        point_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        """Store embedding in live Qdrant."""
        from qdrant_client.models import PointStruct  # type: ignore[import-not-found,unused-ignore]

        point = PointStruct(
            id=point_id,
            vector=vector,
            payload=payload,
        )
        await self._client.upsert(  # type: ignore[union-attr]
            collection_name=str(collection),
            points=[point],
        )
        logger.info("Stored embedding %s in %s", point_id, collection)

    async def search_similar(
        self,
        collection: CollectionName,
        user_id: int,
        query_vector: list[float],
        limit: int = 10,
        min_score: float = 0.0,
        time_after: datetime | None = None,
        time_before: datetime | None = None,
    ) -> list[SearchResult]:
        """
        Search for similar vectors, scoped to a specific user.

        Supports time-aware filtering to restrict results to a time window.
        Results are never returned for other users (user-scoped).

        Args:
            collection: Which collection to search.
            user_id: The user to scope the search to.
            query_vector: The query embedding vector.
            limit: Maximum number of results.
            min_score: Minimum similarity score threshold.
            time_after: Only return results created after this time.
            time_before: Only return results created before this time.

        Returns:
            List of SearchResult objects, sorted by similarity score descending.
        """
        if self._stub_mode:
            return self._search_similar_stub(
                collection, user_id, query_vector, limit, min_score,
                time_after, time_before,
            )

        return await self._search_similar_live(
            collection, user_id, query_vector, limit, min_score,
            time_after, time_before,
        )

    def _search_similar_stub(
        self,
        collection: CollectionName,
        user_id: int,
        query_vector: list[float],
        limit: int,
        min_score: float,
        time_after: datetime | None,
        time_before: datetime | None,
    ) -> list[SearchResult]:
        """Search in stub storage using cosine similarity."""
        results: list[SearchResult] = []

        for point in self._stub_points[collection]:
            if point.user_id != user_id:
                continue

            # Time filtering
            if time_after and point.created_at < time_after:
                continue
            if time_before and point.created_at > time_before:
                continue

            # Cosine similarity approximation (dot product for normalized vectors)
            score = self._cosine_similarity(query_vector, point.vector)
            if score < min_score:
                continue

            results.append(
                SearchResult(
                    point_id=point.point_id,
                    score=score,
                    payload=point.payload,
                    collection=collection,
                )
            )

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        logger.debug(
            "Stub: Search in %s for user %d returned %d results",
            collection,
            user_id,
            min(limit, len(results)),
        )
        return results[:limit]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b) or len(a) == 0:
            return 0.0
        dot: float = sum(x * y for x, y in zip(a, b))
        norm_a: float = sum(x * x for x in a) ** 0.5
        norm_b: float = sum(x * x for x in b) ** 0.5
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def _search_similar_live(
        self,
        collection: CollectionName,
        user_id: int,
        query_vector: list[float],
        limit: int,
        min_score: float,
        time_after: datetime | None,
        time_before: datetime | None,
    ) -> list[SearchResult]:
        """Search in live Qdrant with user-scoped filtering."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

        must_conditions: list[FieldCondition] = [
            FieldCondition(key="user_id", match=MatchValue(value=user_id)),
        ]

        if time_after:
            must_conditions.append(
                FieldCondition(
                    key="created_at",
                    range=Range(gte=time_after.isoformat()),  # type: ignore[arg-type]
                )
            )
        if time_before:
            must_conditions.append(
                FieldCondition(
                    key="created_at",
                    range=Range(lte=time_before.isoformat()),  # type: ignore[arg-type]
                )
            )

        search_filter = Filter(must=must_conditions)  # type: ignore[arg-type]

        hits = await self._client.search(  # type: ignore[union-attr]
            collection_name=str(collection),
            query_vector=query_vector,
            query_filter=search_filter,
            limit=limit,
            score_threshold=min_score,
        )

        results: list[SearchResult] = []
        for hit in hits:
            results.append(
                SearchResult(
                    point_id=str(hit.id),
                    score=hit.score,
                    payload=hit.payload or {},
                    collection=collection,
                )
            )

        logger.info("Search in %s for user_hash=%s returned %d results", collection, hash_uid(user_id), len(results))
        return results

    async def delete_user_vectors(self, user_id: int) -> int:
        """
        Delete all vectors for a user across all collections (GDPR Art. 17).

        Args:
            user_id: The user whose vectors to delete.

        Returns:
            Total number of vectors deleted.
        """
        total_deleted = 0

        if self._stub_mode:
            for collection_name in CollectionName:
                before = len(self._stub_points[collection_name])
                self._stub_points[collection_name] = [
                    p for p in self._stub_points[collection_name]
                    if p.user_id != user_id
                ]
                deleted = before - len(self._stub_points[collection_name])
                total_deleted += deleted

            logger.info(
                "Stub: Deleted %d vectors for user %d",
                total_deleted,
                user_id,
            )
            return total_deleted

        return await self._delete_user_vectors_live(user_id)

    async def _delete_user_vectors_live(self, user_id: int) -> int:
        """Delete user vectors from live Qdrant."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        total_deleted = 0
        user_filter = Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        )

        for collection_name in CollectionName:
            await self._client.delete(  # type: ignore[union-attr]
                collection_name=str(collection_name),
                points_selector=user_filter,
            )
            # Qdrant delete returns operation info; we count approximate
            total_deleted += 1  # Approximate count per collection

        logger.info("Deleted vectors for user_hash=%s across all collections", hash_uid(user_id))
        return total_deleted

    async def export_user_vectors(self, user_id: int) -> VectorExport:
        """
        Export all vectors for a user (GDPR Art. 20 data portability).

        Args:
            user_id: The user whose vectors to export.

        Returns:
            VectorExport containing all vector metadata (vectors themselves excluded
            for size, only payloads are included).
        """
        vectors: list[dict[str, Any]] = []

        if self._stub_mode:
            for collection_name in CollectionName:
                for point in self._stub_points[collection_name]:
                    if point.user_id != user_id:
                        continue
                    vectors.append({
                        "point_id": point.point_id,
                        "collection": str(point.collection),
                        "payload": point.payload,
                        "created_at": point.created_at.isoformat(),
                    })
            logger.info(
                "Stub: Exported %d vectors for user %d",
                len(vectors),
                user_id,
            )
        else:
            vectors = await self._export_user_vectors_live(user_id)

        return VectorExport(
            user_id=user_id,
            vectors=vectors,
        )

    async def _export_user_vectors_live(self, user_id: int) -> list[dict[str, Any]]:
        """Export user vectors from live Qdrant."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        vectors: list[dict[str, Any]] = []
        user_filter = Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        )

        for collection_name in CollectionName:
            results = await self._client.scroll(  # type: ignore[union-attr]
                collection_name=str(collection_name),
                scroll_filter=user_filter,
                limit=10000,
            )
            points, _ = results
            for point in points:
                vectors.append({
                    "point_id": str(point.id),
                    "collection": str(collection_name),
                    "payload": point.payload or {},
                })

        logger.info("Exported %d vectors for user_hash=%s", len(vectors), hash_uid(user_id))
        return vectors


# =============================================================================
# Singleton
# =============================================================================

_qdrant_service: QdrantService | None = None


def get_qdrant_service(client: Any | None = None) -> QdrantService:
    """Get or create the Qdrant service singleton."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService(client=client)
    return _qdrant_service
