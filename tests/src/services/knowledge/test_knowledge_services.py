"""
Tests for Knowledge Layer Services.

Tests cover all four knowledge layer services in stub mode:
- Neo4jService: Graph node/relationship CRUD, subgraph query, GDPR export/delete
- QdrantService: Embedding storage, semantic search, user scoping, GDPR export/delete
- LettaService: 3-tier memory, session context, GDPR export/delete
- SyncService: Event-driven sync, status tracking, validation

All tests run in stub mode (client=None) since databases are not available in dev.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.lib.encryption import DataClassification
from src.services.knowledge.letta_service import (
    LettaService,
    MemoryTier,
)
from src.services.knowledge.neo4j_service import (
    Neo4jService,
    NodeType,
    RelationshipType,
)
from src.services.knowledge.qdrant_service import (
    CollectionName,
    QdrantService,
)
from src.services.knowledge.sync_service import (
    SyncEventType,
    SyncService,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def neo4j_service() -> Neo4jService:
    """Create a Neo4jService in stub mode."""
    return Neo4jService(client=None)


@pytest.fixture
def qdrant_service() -> QdrantService:
    """Create a QdrantService in stub mode."""
    return QdrantService(client=None)


@pytest.fixture
def letta_service() -> LettaService:
    """Create a LettaService in stub mode."""
    return LettaService(client=None)


@pytest.fixture
def sync_service() -> SyncService:
    """Create a SyncService in stub mode."""
    return SyncService(neo4j_service=None)


# =============================================================================
# Neo4j Service Tests
# =============================================================================


class TestNeo4jService:
    """Tests for the Neo4j graph database service."""

    def test_stub_mode_initialization(self, neo4j_service: Neo4jService) -> None:
        """Service initializes in stub mode when client is None."""
        assert neo4j_service.is_stub is True

    def test_live_mode_flag(self) -> None:
        """Service reports not stub when client is provided."""
        service = Neo4jService(client="mock_client")
        assert service.is_stub is False

    @pytest.mark.asyncio
    async def test_create_node(self, neo4j_service: Neo4jService) -> None:
        """Create a node and verify it is stored."""
        node = await neo4j_service.create_node(
            node_type=NodeType.VISION,
            user_id=1,
            properties={"title": "Build Aurora Sun"},
        )

        assert node.node_id is not None
        assert node.node_type == NodeType.VISION
        assert node.user_id == 1
        assert node.properties["title"] == "Build Aurora Sun"
        assert node.created_at is not None

    @pytest.mark.asyncio
    async def test_create_node_with_custom_id(self, neo4j_service: Neo4jService) -> None:
        """Create a node with a custom ID."""
        node = await neo4j_service.create_node(
            node_type=NodeType.GOAL,
            user_id=1,
            node_id="custom-goal-1",
        )
        assert node.node_id == "custom-goal-1"

    @pytest.mark.asyncio
    async def test_create_relationship(self, neo4j_service: Neo4jService) -> None:
        """Create a relationship between two nodes."""
        vision = await neo4j_service.create_node(
            node_type=NodeType.VISION, user_id=1, node_id="v1"
        )
        goal = await neo4j_service.create_node(
            node_type=NodeType.GOAL, user_id=1, node_id="g1"
        )

        rel = await neo4j_service.create_relationship(
            relationship_type=RelationshipType.CONTAINS,
            source_id=vision.node_id,
            target_id=goal.node_id,
            properties={"weight": 1.0},
        )

        assert rel.relationship_id is not None
        assert rel.relationship_type == RelationshipType.CONTAINS
        assert rel.source_id == "v1"
        assert rel.target_id == "g1"
        assert rel.properties["weight"] == 1.0

    @pytest.mark.asyncio
    async def test_create_belief_blocks_goal(self, neo4j_service: Neo4jService) -> None:
        """Create a Belief BLOCKS Goal relationship."""
        belief = await neo4j_service.create_node(
            node_type=NodeType.BELIEF,
            user_id=1,
            properties={"text": "I am not good enough"},
        )
        goal = await neo4j_service.create_node(
            node_type=NodeType.GOAL,
            user_id=1,
            properties={"title": "Launch product"},
        )

        rel = await neo4j_service.create_relationship(
            relationship_type=RelationshipType.BLOCKS,
            source_id=belief.node_id,
            target_id=goal.node_id,
        )
        assert rel.relationship_type == RelationshipType.BLOCKS

    @pytest.mark.asyncio
    async def test_create_narrative_nodes(self, neo4j_service: Neo4jService) -> None:
        """Create StoryArc and Chapter narrative nodes."""
        arc = await neo4j_service.create_node(
            node_type=NodeType.STORY_ARC,
            user_id=1,
            properties={"title": "Journey to Focus"},
        )
        chapter = await neo4j_service.create_node(
            node_type=NodeType.CHAPTER,
            user_id=1,
            properties={"title": "The First Step", "order": 1},
        )

        rel = await neo4j_service.create_relationship(
            relationship_type=RelationshipType.HAS_CHAPTER,
            source_id=arc.node_id,
            target_id=chapter.node_id,
        )

        assert arc.node_type == NodeType.STORY_ARC
        assert chapter.node_type == NodeType.CHAPTER
        assert rel.relationship_type == RelationshipType.HAS_CHAPTER

    @pytest.mark.asyncio
    async def test_query_subgraph(self, neo4j_service: Neo4jService) -> None:
        """Query a user's subgraph returns their nodes only."""
        await neo4j_service.create_node(
            node_type=NodeType.VISION, user_id=1, properties={"title": "User 1 Vision"}
        )
        await neo4j_service.create_node(
            node_type=NodeType.GOAL, user_id=1, properties={"title": "User 1 Goal"}
        )
        await neo4j_service.create_node(
            node_type=NodeType.VISION, user_id=2, properties={"title": "User 2 Vision"}
        )

        nodes = await neo4j_service.query_subgraph(user_id=1)
        assert len(nodes) == 2
        assert all(n.user_id == 1 for n in nodes)

    @pytest.mark.asyncio
    async def test_query_subgraph_with_type_filter(self, neo4j_service: Neo4jService) -> None:
        """Query subgraph filtered by node type."""
        await neo4j_service.create_node(node_type=NodeType.VISION, user_id=1)
        await neo4j_service.create_node(node_type=NodeType.GOAL, user_id=1)
        await neo4j_service.create_node(node_type=NodeType.TASK, user_id=1)

        nodes = await neo4j_service.query_subgraph(
            user_id=1, node_types=[NodeType.VISION, NodeType.GOAL]
        )
        assert len(nodes) == 2
        assert all(n.node_type in (NodeType.VISION, NodeType.GOAL) for n in nodes)

    @pytest.mark.asyncio
    async def test_query_subgraph_empty_user(self, neo4j_service: Neo4jService) -> None:
        """Query subgraph for nonexistent user returns empty list."""
        nodes = await neo4j_service.query_subgraph(user_id=999)
        assert nodes == []

    @pytest.mark.asyncio
    async def test_export_user_subgraph(self, neo4j_service: Neo4jService) -> None:
        """Export all graph data for a user."""
        v = await neo4j_service.create_node(
            node_type=NodeType.VISION, user_id=1, node_id="v1"
        )
        g = await neo4j_service.create_node(
            node_type=NodeType.GOAL, user_id=1, node_id="g1"
        )
        await neo4j_service.create_relationship(
            relationship_type=RelationshipType.CONTAINS,
            source_id=v.node_id,
            target_id=g.node_id,
        )

        export = await neo4j_service.export_user_subgraph(user_id=1)
        assert export.user_id == 1
        assert export.node_count == 2
        assert export.relationship_count == 1
        assert export.exported_at is not None

    @pytest.mark.asyncio
    async def test_export_user_subgraph_empty(self, neo4j_service: Neo4jService) -> None:
        """Export for nonexistent user returns empty export."""
        export = await neo4j_service.export_user_subgraph(user_id=999)
        assert export.node_count == 0
        assert export.relationship_count == 0

    @pytest.mark.asyncio
    async def test_delete_user_subgraph(self, neo4j_service: Neo4jService) -> None:
        """Delete all graph data for a user."""
        await neo4j_service.create_node(
            node_type=NodeType.VISION, user_id=1, node_id="v1"
        )
        await neo4j_service.create_node(
            node_type=NodeType.GOAL, user_id=1, node_id="g1"
        )
        await neo4j_service.create_relationship(
            relationship_type=RelationshipType.CONTAINS,
            source_id="v1",
            target_id="g1",
        )

        deleted = await neo4j_service.delete_user_subgraph(user_id=1)
        assert deleted == 2

        # Verify data is gone
        nodes = await neo4j_service.query_subgraph(user_id=1)
        assert nodes == []

    @pytest.mark.asyncio
    async def test_delete_user_subgraph_preserves_other_users(
        self, neo4j_service: Neo4jService
    ) -> None:
        """Deleting one user's data does not affect other users."""
        await neo4j_service.create_node(node_type=NodeType.VISION, user_id=1)
        await neo4j_service.create_node(node_type=NodeType.VISION, user_id=2)

        await neo4j_service.delete_user_subgraph(user_id=1)

        nodes_1 = await neo4j_service.query_subgraph(user_id=1)
        nodes_2 = await neo4j_service.query_subgraph(user_id=2)
        assert len(nodes_1) == 0
        assert len(nodes_2) == 1

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user(self, neo4j_service: Neo4jService) -> None:
        """Deleting nonexistent user returns 0."""
        deleted = await neo4j_service.delete_user_subgraph(user_id=999)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_all_node_types(self, neo4j_service: Neo4jService) -> None:
        """All NodeType enum values can be used to create nodes."""
        for node_type in NodeType:
            node = await neo4j_service.create_node(
                node_type=node_type, user_id=1
            )
            assert node.node_type == node_type

    @pytest.mark.asyncio
    async def test_all_relationship_types(self, neo4j_service: Neo4jService) -> None:
        """All RelationshipType enum values can be used to create relationships."""
        n1 = await neo4j_service.create_node(node_type=NodeType.USER, user_id=1, node_id="n1")
        n2 = await neo4j_service.create_node(node_type=NodeType.USER, user_id=1, node_id="n2")

        for rel_type in RelationshipType:
            rel = await neo4j_service.create_relationship(
                relationship_type=rel_type,
                source_id=n1.node_id,
                target_id=n2.node_id,
            )
            assert rel.relationship_type == rel_type


# =============================================================================
# Qdrant Service Tests
# =============================================================================


class TestQdrantService:
    """Tests for the Qdrant vector database service."""

    def test_stub_mode_initialization(self, qdrant_service: QdrantService) -> None:
        """Service initializes in stub mode when client is None."""
        assert qdrant_service.is_stub is True

    @pytest.mark.asyncio
    async def test_store_embedding(self, qdrant_service: QdrantService) -> None:
        """Store an embedding and verify the result."""
        result = await qdrant_service.store_embedding(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            vector=[0.1, 0.2, 0.3],
            payload={"text": "My first note"},
        )

        assert result.point_id is not None
        assert result.collection == CollectionName.CAPTURED_ITEMS
        assert result.user_id == 1
        assert result.created_at is not None

    @pytest.mark.asyncio
    async def test_store_embedding_custom_id(self, qdrant_service: QdrantService) -> None:
        """Store an embedding with custom point ID."""
        result = await qdrant_service.store_embedding(
            collection=CollectionName.USER_NOTES,
            user_id=1,
            vector=[0.5, 0.5],
            point_id="custom-point-1",
        )
        assert result.point_id == "custom-point-1"

    @pytest.mark.asyncio
    async def test_search_similar_returns_results(self, qdrant_service: QdrantService) -> None:
        """Search returns matching results for the same user."""
        await qdrant_service.store_embedding(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            vector=[1.0, 0.0, 0.0],
            payload={"text": "Focus techniques"},
        )
        await qdrant_service.store_embedding(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            vector=[0.9, 0.1, 0.0],
            payload={"text": "Concentration methods"},
        )

        results = await qdrant_service.search_similar(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            query_vector=[1.0, 0.0, 0.0],
            limit=5,
        )

        assert len(results) == 2
        # First result should be the exact match
        assert results[0].score > results[1].score

    @pytest.mark.asyncio
    async def test_search_user_scoping(self, qdrant_service: QdrantService) -> None:
        """Search only returns results for the requesting user."""
        await qdrant_service.store_embedding(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            vector=[1.0, 0.0],
            payload={"text": "User 1 data"},
        )
        await qdrant_service.store_embedding(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=2,
            vector=[1.0, 0.0],
            payload={"text": "User 2 data"},
        )

        results = await qdrant_service.search_similar(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            query_vector=[1.0, 0.0],
        )

        assert len(results) == 1
        assert results[0].payload["text"] == "User 1 data"

    @pytest.mark.asyncio
    async def test_search_min_score_filter(self, qdrant_service: QdrantService) -> None:
        """Search respects minimum score threshold."""
        await qdrant_service.store_embedding(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            vector=[1.0, 0.0],
        )
        await qdrant_service.store_embedding(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            vector=[0.0, 1.0],
        )

        results = await qdrant_service.search_similar(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            query_vector=[1.0, 0.0],
            min_score=0.5,
        )

        # Only the first vector should match with score > 0.5
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_limit(self, qdrant_service: QdrantService) -> None:
        """Search respects the limit parameter."""
        for i in range(5):
            await qdrant_service.store_embedding(
                collection=CollectionName.CAPTURED_ITEMS,
                user_id=1,
                vector=[1.0, float(i) / 10.0],
            )

        results = await qdrant_service.search_similar(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            query_vector=[1.0, 0.0],
            limit=2,
        )

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_empty_collection(self, qdrant_service: QdrantService) -> None:
        """Search on empty collection returns empty list."""
        results = await qdrant_service.search_similar(
            collection=CollectionName.COACHING_TRACES,
            user_id=1,
            query_vector=[1.0, 0.0],
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_search_time_filtering(self, qdrant_service: QdrantService) -> None:
        """Search respects time-based filtering."""
        service = qdrant_service

        # Store an embedding
        await service.store_embedding(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            vector=[1.0, 0.0],
        )

        # Search with time_after in the future should return nothing
        future_time = datetime.now(UTC) + timedelta(hours=1)
        results = await service.search_similar(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            query_vector=[1.0, 0.0],
            time_after=future_time,
        )
        assert results == []

        # Search with time_before in the past should return nothing
        past_time = datetime.now(UTC) - timedelta(hours=1)
        results = await service.search_similar(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            query_vector=[1.0, 0.0],
            time_before=past_time,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_delete_user_vectors(self, qdrant_service: QdrantService) -> None:
        """Delete all vectors for a user across collections."""
        await qdrant_service.store_embedding(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            vector=[1.0, 0.0],
        )
        await qdrant_service.store_embedding(
            collection=CollectionName.COACHING_TRACES,
            user_id=1,
            vector=[0.0, 1.0],
        )
        await qdrant_service.store_embedding(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=2,
            vector=[1.0, 1.0],
        )

        deleted = await qdrant_service.delete_user_vectors(user_id=1)
        assert deleted == 2

        # Verify user 1 data is gone
        results = await qdrant_service.search_similar(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            query_vector=[1.0, 0.0],
        )
        assert results == []

        # Verify user 2 data still exists
        results = await qdrant_service.search_similar(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=2,
            query_vector=[1.0, 1.0],
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_export_user_vectors(self, qdrant_service: QdrantService) -> None:
        """Export all vectors for a user."""
        await qdrant_service.store_embedding(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=1,
            vector=[1.0, 0.0],
            payload={"text": "note 1"},
        )
        await qdrant_service.store_embedding(
            collection=CollectionName.USER_NOTES,
            user_id=1,
            vector=[0.0, 1.0],
            payload={"text": "note 2"},
        )

        export = await qdrant_service.export_user_vectors(user_id=1)
        assert export.user_id == 1
        assert export.vector_count == 2
        assert export.exported_at is not None

    @pytest.mark.asyncio
    async def test_export_nonexistent_user(self, qdrant_service: QdrantService) -> None:
        """Export for nonexistent user returns empty export."""
        export = await qdrant_service.export_user_vectors(user_id=999)
        assert export.vector_count == 0

    @pytest.mark.asyncio
    async def test_all_collections(self, qdrant_service: QdrantService) -> None:
        """All CollectionName values can be used."""
        for collection in CollectionName:
            result = await qdrant_service.store_embedding(
                collection=collection,
                user_id=1,
                vector=[1.0],
            )
            assert result.collection == collection

    def test_cosine_similarity_identical(self) -> None:
        """Cosine similarity of identical vectors is 1.0."""
        sim = QdrantService._cosine_similarity([1.0, 0.0], [1.0, 0.0])
        assert abs(sim - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self) -> None:
        """Cosine similarity of orthogonal vectors is 0.0."""
        sim = QdrantService._cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert abs(sim) < 1e-6

    def test_cosine_similarity_opposite(self) -> None:
        """Cosine similarity of opposite vectors is -1.0."""
        sim = QdrantService._cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        assert abs(sim + 1.0) < 1e-6

    def test_cosine_similarity_empty(self) -> None:
        """Cosine similarity of empty vectors is 0.0."""
        sim = QdrantService._cosine_similarity([], [])
        assert sim == 0.0

    def test_cosine_similarity_different_lengths(self) -> None:
        """Cosine similarity of different length vectors is 0.0."""
        sim = QdrantService._cosine_similarity([1.0], [1.0, 0.0])
        assert sim == 0.0

    def test_cosine_similarity_zero_vector(self) -> None:
        """Cosine similarity with zero vector is 0.0."""
        sim = QdrantService._cosine_similarity([0.0, 0.0], [1.0, 0.0])
        assert sim == 0.0


# =============================================================================
# Letta Service Tests
# =============================================================================


class TestLettaService:
    """Tests for the Letta memory service."""

    def test_stub_mode_initialization(self, letta_service: LettaService) -> None:
        """Service initializes in stub mode when client is None."""
        assert letta_service.is_stub is True

    @pytest.mark.asyncio
    async def test_store_memory(self, letta_service: LettaService) -> None:
        """Store a memory and verify it is stored."""
        memory = await letta_service.store_memory(
            tier=MemoryTier.SESSION,
            user_id=1,
            content="User mentioned they prefer morning routines",
            metadata={"topics": ["routine", "morning"]},
        )

        assert memory.memory_id is not None
        assert memory.tier == MemoryTier.SESSION
        assert memory.user_id == 1
        assert memory.content == "User mentioned they prefer morning routines"
        assert memory.classification == DataClassification.SENSITIVE

    @pytest.mark.asyncio
    async def test_store_memory_art9_classification(self, letta_service: LettaService) -> None:
        """Store coaching transcript with ART_9_SPECIAL classification."""
        memory = await letta_service.store_memory(
            tier=MemoryTier.ARCHIVAL,
            user_id=1,
            content="Coaching session transcript: discussed burnout symptoms",
            classification=DataClassification.ART_9_SPECIAL,
        )

        assert memory.classification == DataClassification.ART_9_SPECIAL

    @pytest.mark.asyncio
    async def test_store_memory_with_session_id(self, letta_service: LettaService) -> None:
        """Store a memory with session ID."""
        memory = await letta_service.store_memory(
            tier=MemoryTier.SESSION,
            user_id=1,
            content="Session context",
            session_id="session-123",
        )
        assert memory.session_id == "session-123"

    @pytest.mark.asyncio
    async def test_recall_memories(self, letta_service: LettaService) -> None:
        """Recall memories returns stored memories."""
        await letta_service.store_memory(
            tier=MemoryTier.SESSION,
            user_id=1,
            content="First memory",
        )
        await letta_service.store_memory(
            tier=MemoryTier.SESSION,
            user_id=1,
            content="Second memory",
        )

        memories = await letta_service.recall_memories(user_id=1)
        assert len(memories) == 2

    @pytest.mark.asyncio
    async def test_recall_memories_by_tier(self, letta_service: LettaService) -> None:
        """Recall memories filtered by tier."""
        await letta_service.store_memory(
            tier=MemoryTier.SESSION, user_id=1, content="Session memory"
        )
        await letta_service.store_memory(
            tier=MemoryTier.PROFILE, user_id=1, content="Profile memory"
        )
        await letta_service.store_memory(
            tier=MemoryTier.ARCHIVAL, user_id=1, content="Archival memory"
        )

        session_memories = await letta_service.recall_memories(
            user_id=1, tier=MemoryTier.SESSION
        )
        assert len(session_memories) == 1
        assert session_memories[0].tier == MemoryTier.SESSION

        profile_memories = await letta_service.recall_memories(
            user_id=1, tier=MemoryTier.PROFILE
        )
        assert len(profile_memories) == 1
        assert profile_memories[0].tier == MemoryTier.PROFILE

    @pytest.mark.asyncio
    async def test_recall_memories_by_session_id(self, letta_service: LettaService) -> None:
        """Recall memories filtered by session ID."""
        await letta_service.store_memory(
            tier=MemoryTier.SESSION,
            user_id=1,
            content="Session A memory",
            session_id="session-a",
        )
        await letta_service.store_memory(
            tier=MemoryTier.SESSION,
            user_id=1,
            content="Session B memory",
            session_id="session-b",
        )

        memories = await letta_service.recall_memories(
            user_id=1, session_id="session-a"
        )
        assert len(memories) == 1
        assert memories[0].content == "Session A memory"

    @pytest.mark.asyncio
    async def test_recall_memories_with_query(self, letta_service: LettaService) -> None:
        """Recall memories filtered by text query."""
        await letta_service.store_memory(
            tier=MemoryTier.SESSION, user_id=1, content="Discussed morning routine"
        )
        await letta_service.store_memory(
            tier=MemoryTier.SESSION, user_id=1, content="Talked about exercise"
        )

        memories = await letta_service.recall_memories(
            user_id=1, query="morning"
        )
        assert len(memories) == 1
        assert "morning" in memories[0].content

    @pytest.mark.asyncio
    async def test_recall_memories_user_scoping(self, letta_service: LettaService) -> None:
        """Recall memories only returns memories for the requesting user."""
        await letta_service.store_memory(
            tier=MemoryTier.SESSION, user_id=1, content="User 1 memory"
        )
        await letta_service.store_memory(
            tier=MemoryTier.SESSION, user_id=2, content="User 2 memory"
        )

        memories = await letta_service.recall_memories(user_id=1)
        assert len(memories) == 1
        assert memories[0].content == "User 1 memory"

    @pytest.mark.asyncio
    async def test_recall_memories_limit(self, letta_service: LettaService) -> None:
        """Recall memories respects the limit parameter."""
        for i in range(10):
            await letta_service.store_memory(
                tier=MemoryTier.SESSION, user_id=1, content=f"Memory {i}"
            )

        memories = await letta_service.recall_memories(user_id=1, limit=3)
        assert len(memories) == 3

    @pytest.mark.asyncio
    async def test_recall_memories_most_recent_first(self, letta_service: LettaService) -> None:
        """Recalled memories are sorted most recent first."""
        await letta_service.store_memory(
            tier=MemoryTier.SESSION, user_id=1, content="First"
        )
        await letta_service.store_memory(
            tier=MemoryTier.SESSION, user_id=1, content="Second"
        )

        memories = await letta_service.recall_memories(user_id=1)
        # Most recent should be first (Second was stored after First)
        assert memories[0].created_at >= memories[1].created_at

    @pytest.mark.asyncio
    async def test_get_session_context(self, letta_service: LettaService) -> None:
        """Get aggregated session context."""
        await letta_service.store_memory(
            tier=MemoryTier.SESSION,
            user_id=1,
            content="Current session note",
            session_id="sess-1",
        )
        await letta_service.store_memory(
            tier=MemoryTier.PROFILE,
            user_id=1,
            content="User prefers structure",
            metadata={"topics": ["preferences", "structure"]},
        )

        context = await letta_service.get_session_context(
            user_id=1, session_id="sess-1"
        )

        assert context.user_id == 1
        assert context.session_id == "sess-1"
        assert len(context.memories) == 1
        assert context.profile_summary != ""
        assert context.retrieved_at is not None

    @pytest.mark.asyncio
    async def test_get_session_context_without_profile(self, letta_service: LettaService) -> None:
        """Get session context without including profile."""
        await letta_service.store_memory(
            tier=MemoryTier.SESSION,
            user_id=1,
            content="Session note",
            session_id="sess-1",
        )

        context = await letta_service.get_session_context(
            user_id=1, session_id="sess-1", include_profile=False
        )

        assert context.profile_summary == ""
        assert context.recent_topics == []

    @pytest.mark.asyncio
    async def test_export_user_memories(self, letta_service: LettaService) -> None:
        """Export all memories for a user."""
        await letta_service.store_memory(
            tier=MemoryTier.SESSION, user_id=1, content="Session data"
        )
        await letta_service.store_memory(
            tier=MemoryTier.PROFILE, user_id=1, content="Profile data"
        )
        await letta_service.store_memory(
            tier=MemoryTier.ARCHIVAL, user_id=1, content="Archival data"
        )

        export = await letta_service.export_user_memories(user_id=1)
        assert export.user_id == 1
        assert export.memory_count == 3
        assert export.exported_at is not None

    @pytest.mark.asyncio
    async def test_export_nonexistent_user(self, letta_service: LettaService) -> None:
        """Export for nonexistent user returns empty export."""
        export = await letta_service.export_user_memories(user_id=999)
        assert export.memory_count == 0

    @pytest.mark.asyncio
    async def test_delete_user_memories(self, letta_service: LettaService) -> None:
        """Delete all memories for a user."""
        await letta_service.store_memory(
            tier=MemoryTier.SESSION, user_id=1, content="Memory 1"
        )
        await letta_service.store_memory(
            tier=MemoryTier.PROFILE, user_id=1, content="Memory 2"
        )
        await letta_service.store_memory(
            tier=MemoryTier.SESSION, user_id=2, content="Other user"
        )

        deleted = await letta_service.delete_user_memories(user_id=1)
        assert deleted == 2

        # Verify user 1 data is gone
        memories = await letta_service.recall_memories(user_id=1)
        assert memories == []

        # Verify user 2 data still exists
        memories = await letta_service.recall_memories(user_id=2)
        assert len(memories) == 1

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user(self, letta_service: LettaService) -> None:
        """Delete for nonexistent user returns 0."""
        deleted = await letta_service.delete_user_memories(user_id=999)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_all_memory_tiers(self, letta_service: LettaService) -> None:
        """All MemoryTier values can be used to store memories."""
        for tier in MemoryTier:
            memory = await letta_service.store_memory(
                tier=tier, user_id=1, content=f"Tier: {tier}"
            )
            assert memory.tier == tier


# =============================================================================
# Sync Service Tests
# =============================================================================


class TestSyncService:
    """Tests for the PostgreSQL to Neo4j sync service."""

    def test_stub_mode_initialization(self, sync_service: SyncService) -> None:
        """Service initializes in stub mode when neo4j_service is None."""
        assert sync_service.is_stub is True

    @pytest.mark.asyncio
    async def test_sync_created_event(self, sync_service: SyncService) -> None:
        """Sync a creation event."""
        event = await sync_service.sync_event(
            event_type=SyncEventType.CREATED,
            entity_type="vision",
            entity_id="v-1",
            user_id=1,
            payload={"title": "My Vision"},
        )

        assert event.event_id is not None
        assert event.event_type == SyncEventType.CREATED
        assert event.entity_type == "vision"
        assert event.entity_id == "v-1"
        assert event.user_id == 1
        assert event.synced is True
        assert event.error is None

    @pytest.mark.asyncio
    async def test_sync_updated_event(self, sync_service: SyncService) -> None:
        """Sync an update event."""
        event = await sync_service.sync_event(
            event_type=SyncEventType.UPDATED,
            entity_type="goal",
            entity_id="g-1",
            user_id=1,
            payload={"title": "Updated Goal"},
        )

        assert event.event_type == SyncEventType.UPDATED
        assert event.synced is True

    @pytest.mark.asyncio
    async def test_sync_completed_event(self, sync_service: SyncService) -> None:
        """Sync a completion event."""
        event = await sync_service.sync_event(
            event_type=SyncEventType.COMPLETED,
            entity_type="task",
            entity_id="t-1",
            user_id=1,
        )

        assert event.event_type == SyncEventType.COMPLETED
        assert event.synced is True

    @pytest.mark.asyncio
    async def test_sync_deleted_event(self, sync_service: SyncService) -> None:
        """Sync a deletion event."""
        event = await sync_service.sync_event(
            event_type=SyncEventType.DELETED,
            entity_type="habit",
            entity_id="h-1",
            user_id=1,
        )

        assert event.event_type == SyncEventType.DELETED
        assert event.synced is True

    @pytest.mark.asyncio
    async def test_sync_archived_event(self, sync_service: SyncService) -> None:
        """Sync an archival event."""
        event = await sync_service.sync_event(
            event_type=SyncEventType.ARCHIVED,
            entity_type="goal",
            entity_id="g-2",
            user_id=1,
        )

        assert event.event_type == SyncEventType.ARCHIVED
        assert event.synced is True

    @pytest.mark.asyncio
    async def test_sync_invalid_entity_type(self, sync_service: SyncService) -> None:
        """Sync with invalid entity type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid entity_type"):
            await sync_service.sync_event(
                event_type=SyncEventType.CREATED,
                entity_type="invalid_type",
                entity_id="x-1",
                user_id=1,
            )

    @pytest.mark.asyncio
    async def test_sync_all_valid_entity_types(self, sync_service: SyncService) -> None:
        """All valid entity types can be synced."""
        for entity_type in SyncService.VALID_ENTITY_TYPES:
            event = await sync_service.sync_event(
                event_type=SyncEventType.CREATED,
                entity_type=entity_type,
                entity_id=f"id-{entity_type}",
                user_id=1,
            )
            assert event.synced is True

    @pytest.mark.asyncio
    async def test_sync_custom_event_id(self, sync_service: SyncService) -> None:
        """Sync event with custom event ID."""
        event = await sync_service.sync_event(
            event_type=SyncEventType.CREATED,
            entity_type="vision",
            entity_id="v-1",
            user_id=1,
            event_id="custom-event-1",
        )
        assert event.event_id == "custom-event-1"

    @pytest.mark.asyncio
    async def test_get_sync_status_empty(self, sync_service: SyncService) -> None:
        """Get status with no events."""
        status = await sync_service.get_sync_status()

        assert status.total_events == 0
        assert status.synced_events == 0
        assert status.failed_events == 0
        assert status.pending_events == 0
        assert status.last_sync_at is None

    @pytest.mark.asyncio
    async def test_get_sync_status_after_events(self, sync_service: SyncService) -> None:
        """Get status after processing events."""
        await sync_service.sync_event(
            event_type=SyncEventType.CREATED,
            entity_type="vision",
            entity_id="v-1",
            user_id=1,
        )
        await sync_service.sync_event(
            event_type=SyncEventType.UPDATED,
            entity_type="goal",
            entity_id="g-1",
            user_id=1,
        )

        status = await sync_service.get_sync_status()
        assert status.total_events == 2
        assert status.synced_events == 2
        assert status.failed_events == 0
        assert status.pending_events == 0
        assert status.last_sync_at is not None

    @pytest.mark.asyncio
    async def test_all_event_types(self, sync_service: SyncService) -> None:
        """All SyncEventType values can be used."""
        for event_type in SyncEventType:
            event = await sync_service.sync_event(
                event_type=event_type,
                entity_type="task",
                entity_id=f"t-{event_type}",
                user_id=1,
            )
            assert event.event_type == event_type


# =============================================================================
# Integration Tests
# =============================================================================


class TestKnowledgeLayerIntegration:
    """Integration tests across knowledge layer services."""

    @pytest.mark.asyncio
    async def test_full_gdpr_export_flow(
        self,
        neo4j_service: Neo4jService,
        qdrant_service: QdrantService,
        letta_service: LettaService,
    ) -> None:
        """Full GDPR export across all knowledge services."""
        user_id = 42

        # Store data in each service
        await neo4j_service.create_node(
            node_type=NodeType.VISION,
            user_id=user_id,
            properties={"title": "My Vision"},
        )
        await qdrant_service.store_embedding(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=user_id,
            vector=[1.0, 0.0],
        )
        await letta_service.store_memory(
            tier=MemoryTier.SESSION,
            user_id=user_id,
            content="Session data",
        )

        # Export from each service
        graph_export = await neo4j_service.export_user_subgraph(user_id)
        vector_export = await qdrant_service.export_user_vectors(user_id)
        memory_export = await letta_service.export_user_memories(user_id)

        assert graph_export.node_count == 1
        assert vector_export.vector_count == 1
        assert memory_export.memory_count == 1

    @pytest.mark.asyncio
    async def test_full_gdpr_delete_flow(
        self,
        neo4j_service: Neo4jService,
        qdrant_service: QdrantService,
        letta_service: LettaService,
    ) -> None:
        """Full GDPR deletion across all knowledge services."""
        user_id = 42

        # Store data in each service
        await neo4j_service.create_node(
            node_type=NodeType.VISION,
            user_id=user_id,
            properties={"title": "My Vision"},
        )
        await qdrant_service.store_embedding(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=user_id,
            vector=[1.0, 0.0],
        )
        await letta_service.store_memory(
            tier=MemoryTier.SESSION,
            user_id=user_id,
            content="Session data",
        )

        # Delete from each service
        graph_deleted = await neo4j_service.delete_user_subgraph(user_id)
        vector_deleted = await qdrant_service.delete_user_vectors(user_id)
        memory_deleted = await letta_service.delete_user_memories(user_id)

        assert graph_deleted == 1
        assert vector_deleted == 1
        assert memory_deleted == 1

        # Verify all data is gone
        nodes = await neo4j_service.query_subgraph(user_id)
        results = await qdrant_service.search_similar(
            collection=CollectionName.CAPTURED_ITEMS,
            user_id=user_id,
            query_vector=[1.0, 0.0],
        )
        memories = await letta_service.recall_memories(user_id)

        assert nodes == []
        assert results == []
        assert memories == []

    @pytest.mark.asyncio
    async def test_sync_then_query(self, sync_service: SyncService) -> None:
        """Sync an event and verify status reflects it."""
        await sync_service.sync_event(
            event_type=SyncEventType.CREATED,
            entity_type="vision",
            entity_id="v-1",
            user_id=1,
            payload={"title": "My Vision"},
        )

        status = await sync_service.get_sync_status()
        assert status.total_events == 1
        assert status.synced_events == 1
