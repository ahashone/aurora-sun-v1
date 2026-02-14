"""
Neo4j Service for Aurora Sun V1.

Graph database wrapper for the Knowledge Layer. Manages:
- Vision→Goal→Task→Habit hierarchy (CONTAINS relationships)
- Belief→BLOCKS→Goal relationships
- Pattern relationship tracking (CORRELATES_WITH, TRIGGERS, PRECEDES)
- Neurostate trajectory storage (temporal state sequences)
- Aurora narrative ontology (StoryArc, Chapter nodes)
- User subgraph export/delete for GDPR (SW-15)

When client=None (stub mode), all operations succeed with in-memory stubs.
This allows development and testing without a running Neo4j instance.

Reference: ARCHITECTURE.md Section 5 (Knowledge Layer)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class NodeType(StrEnum):
    """Types of nodes in the knowledge graph."""

    # Vision-to-Task hierarchy
    VISION = "Vision"
    GOAL = "Goal"
    TASK = "Task"
    HABIT = "Habit"

    # Belief network
    BELIEF = "Belief"

    # Pattern nodes
    PATTERN = "Pattern"
    CYCLE = "Cycle"

    # Neurostate
    NEUROSTATE = "Neurostate"

    # Aurora narrative
    STORY_ARC = "StoryArc"
    CHAPTER = "Chapter"

    # User root
    USER = "User"


class RelationshipType(StrEnum):
    """Types of relationships in the knowledge graph."""

    # Hierarchy
    CONTAINS = "CONTAINS"
    PARENT_OF = "PARENT_OF"
    CHILD_OF = "CHILD_OF"

    # Belief network
    BLOCKS = "BLOCKS"
    SUPPORTS = "SUPPORTS"

    # Pattern relationships
    CORRELATES_WITH = "CORRELATES_WITH"
    TRIGGERS = "TRIGGERS"
    PRECEDES = "PRECEDES"

    # Neurostate
    TRANSITIONS_TO = "TRANSITIONS_TO"

    # Narrative
    HAS_ARC = "HAS_ARC"
    HAS_CHAPTER = "HAS_CHAPTER"
    NEXT_CHAPTER = "NEXT_CHAPTER"

    # Ownership
    OWNS = "OWNS"
    BELONGS_TO = "BELONGS_TO"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class GraphNode:
    """Represents a node in the knowledge graph."""

    node_id: str
    node_type: NodeType
    user_id: int
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class GraphRelationship:
    """Represents a relationship between two nodes."""

    relationship_id: str
    relationship_type: RelationshipType
    source_id: str
    target_id: str
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class SubgraphExport:
    """GDPR export: all nodes and relationships for a user."""

    user_id: int
    nodes: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    exported_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    node_count: int = 0
    relationship_count: int = 0

    def __post_init__(self) -> None:
        """Set counts from data if not provided."""
        if self.node_count == 0:
            self.node_count = len(self.nodes)
        if self.relationship_count == 0:
            self.relationship_count = len(self.relationships)


# =============================================================================
# Service
# =============================================================================


class Neo4jService:
    """
    Neo4j graph database service wrapper.

    Manages the knowledge graph for Aurora Sun V1, including the
    Vision→Goal→Task→Habit hierarchy, belief networks, pattern tracking,
    neurostate trajectories, and narrative ontology.

    When client is None (stub mode), all operations succeed with in-memory
    storage for development and testing.

    Args:
        client: Optional Neo4j async driver instance. None = stub mode.
    """

    def __init__(self, client: Any | None = None) -> None:
        """Initialize Neo4j service."""
        self._client = client
        self._stub_mode = client is None

        # In-memory stub storage
        self._stub_nodes: dict[str, GraphNode] = {}
        self._stub_relationships: dict[str, GraphRelationship] = {}

        if self._stub_mode:
            logger.info("Neo4jService initialized in stub mode (no client)")
        else:
            logger.info("Neo4jService initialized with live client")

    @property
    def is_stub(self) -> bool:
        """Return True if running in stub mode."""
        return self._stub_mode

    async def create_node(
        self,
        node_type: NodeType,
        user_id: int,
        properties: dict[str, Any] | None = None,
        node_id: str | None = None,
    ) -> GraphNode:
        """
        Create a node in the knowledge graph.

        Args:
            node_type: The type of node to create.
            user_id: The user this node belongs to.
            properties: Optional node properties.
            node_id: Optional custom node ID. Auto-generated if not provided.

        Returns:
            The created GraphNode.
        """
        resolved_id = node_id or str(uuid.uuid4())
        now = datetime.now(UTC)

        node = GraphNode(
            node_id=resolved_id,
            node_type=node_type,
            user_id=user_id,
            properties=properties or {},
            created_at=now,
            updated_at=now,
        )

        if self._stub_mode:
            self._stub_nodes[resolved_id] = node
            logger.debug(
                "Stub: Created node %s (type=%s, user=%d)",
                resolved_id,
                node_type,
                user_id,
            )
        else:
            await self._create_node_live(node)

        return node

    async def _create_node_live(self, node: GraphNode) -> None:
        """Create a node in the live Neo4j database."""
        query = (
            f"CREATE (n:{node.node_type} $props) "
            "SET n.node_id = $node_id, n.user_id = $user_id, "
            "n.created_at = $created_at, n.updated_at = $updated_at"
        )
        params = {
            "props": node.properties,
            "node_id": node.node_id,
            "user_id": node.user_id,
            "created_at": node.created_at.isoformat(),
            "updated_at": node.updated_at.isoformat(),
        }
        async with self._client.session() as session:  # type: ignore[union-attr]
            await session.run(query, params)
        logger.info(
            "Created node %s (type=%s, user=%d)",
            node.node_id,
            node.node_type,
            node.user_id,
        )

    async def create_relationship(
        self,
        relationship_type: RelationshipType,
        source_id: str,
        target_id: str,
        properties: dict[str, Any] | None = None,
        relationship_id: str | None = None,
    ) -> GraphRelationship:
        """
        Create a relationship between two nodes.

        Args:
            relationship_type: The type of relationship.
            source_id: Source node ID.
            target_id: Target node ID.
            properties: Optional relationship properties.
            relationship_id: Optional custom ID. Auto-generated if not provided.

        Returns:
            The created GraphRelationship.
        """
        resolved_id = relationship_id or str(uuid.uuid4())
        now = datetime.now(UTC)

        rel = GraphRelationship(
            relationship_id=resolved_id,
            relationship_type=relationship_type,
            source_id=source_id,
            target_id=target_id,
            properties=properties or {},
            created_at=now,
        )

        if self._stub_mode:
            self._stub_relationships[resolved_id] = rel
            logger.debug(
                "Stub: Created relationship %s (%s)-[%s]->(%s)",
                resolved_id,
                source_id,
                relationship_type,
                target_id,
            )
        else:
            await self._create_relationship_live(rel)

        return rel

    async def _create_relationship_live(self, rel: GraphRelationship) -> None:
        """Create a relationship in the live Neo4j database."""
        query = (
            "MATCH (a {node_id: $source_id}), (b {node_id: $target_id}) "
            f"CREATE (a)-[r:{rel.relationship_type} $props]->(b) "
            "SET r.relationship_id = $rel_id, r.created_at = $created_at"
        )
        params = {
            "source_id": rel.source_id,
            "target_id": rel.target_id,
            "props": rel.properties,
            "rel_id": rel.relationship_id,
            "created_at": rel.created_at.isoformat(),
        }
        async with self._client.session() as session:  # type: ignore[union-attr]
            await session.run(query, params)
        logger.info(
            "Created relationship %s: (%s)-[%s]->(%s)",
            rel.relationship_id,
            rel.source_id,
            rel.relationship_type,
            rel.target_id,
        )

    async def query_subgraph(
        self,
        user_id: int,
        node_types: list[NodeType] | None = None,
        relationship_types: list[RelationshipType] | None = None,
        max_depth: int = 3,
    ) -> list[GraphNode]:
        """
        Query a user's subgraph, optionally filtered by node/relationship types.

        Args:
            user_id: The user whose subgraph to query.
            node_types: Optional filter for node types.
            relationship_types: Optional filter for relationship types.
            max_depth: Maximum traversal depth.

        Returns:
            List of matching GraphNode objects.
        """
        if self._stub_mode:
            results: list[GraphNode] = []
            for node in self._stub_nodes.values():
                if node.user_id != user_id:
                    continue
                if node_types and node.node_type not in node_types:
                    continue
                results.append(node)
            logger.debug(
                "Stub: Queried subgraph for user %d, found %d nodes",
                user_id,
                len(results),
            )
            return results

        return await self._query_subgraph_live(
            user_id, node_types, relationship_types, max_depth
        )

    async def _query_subgraph_live(
        self,
        user_id: int,
        node_types: list[NodeType] | None,
        relationship_types: list[RelationshipType] | None,
        max_depth: int,
    ) -> list[GraphNode]:
        """Query subgraph from live Neo4j."""
        # Build Cypher query with optional type filters
        type_filter = ""
        if node_types:
            labels = ":".join(str(nt) for nt in node_types)
            type_filter = f":{labels}"

        query = (
            f"MATCH (n{type_filter} {{user_id: $user_id}}) "
            "RETURN n.node_id AS node_id, labels(n)[0] AS node_type, "
            "n.user_id AS user_id, properties(n) AS props, "
            "n.created_at AS created_at, n.updated_at AS updated_at "
            f"LIMIT {max_depth * 100}"
        )

        results: list[GraphNode] = []
        async with self._client.session() as session:  # type: ignore[union-attr]
            result = await session.run(query, {"user_id": user_id})
            records = await result.data()
            for record in records:
                node = GraphNode(
                    node_id=record["node_id"],
                    node_type=NodeType(record["node_type"]),
                    user_id=record["user_id"],
                    properties=record.get("props", {}),
                )
                results.append(node)

        logger.info("Queried subgraph for user %d, found %d nodes", user_id, len(results))
        return results

    async def export_user_subgraph(self, user_id: int) -> SubgraphExport:
        """
        Export all graph data for a user (GDPR Art. 20 data portability).

        Args:
            user_id: The user whose data to export.

        Returns:
            SubgraphExport containing all nodes and relationships.
        """
        if self._stub_mode:
            nodes = [
                {
                    "node_id": n.node_id,
                    "node_type": str(n.node_type),
                    "properties": n.properties,
                    "created_at": n.created_at.isoformat(),
                    "updated_at": n.updated_at.isoformat(),
                }
                for n in self._stub_nodes.values()
                if n.user_id == user_id
            ]
            user_node_ids = {n.node_id for n in self._stub_nodes.values() if n.user_id == user_id}
            relationships = [
                {
                    "relationship_id": r.relationship_id,
                    "relationship_type": str(r.relationship_type),
                    "source_id": r.source_id,
                    "target_id": r.target_id,
                    "properties": r.properties,
                    "created_at": r.created_at.isoformat(),
                }
                for r in self._stub_relationships.values()
                if r.source_id in user_node_ids or r.target_id in user_node_ids
            ]
            logger.info(
                "Stub: Exported subgraph for user %d (%d nodes, %d relationships)",
                user_id,
                len(nodes),
                len(relationships),
            )
            return SubgraphExport(
                user_id=user_id,
                nodes=nodes,
                relationships=relationships,
            )

        return await self._export_user_subgraph_live(user_id)

    async def _export_user_subgraph_live(self, user_id: int) -> SubgraphExport:
        """Export user subgraph from live Neo4j."""
        nodes_query = (
            "MATCH (n {user_id: $user_id}) "
            "RETURN n.node_id AS node_id, labels(n)[0] AS node_type, "
            "properties(n) AS props, n.created_at AS created_at, "
            "n.updated_at AS updated_at"
        )
        rels_query = (
            "MATCH (a {user_id: $user_id})-[r]->(b) "
            "RETURN r.relationship_id AS rel_id, type(r) AS rel_type, "
            "a.node_id AS source_id, b.node_id AS target_id, "
            "properties(r) AS props, r.created_at AS created_at"
        )

        nodes: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []

        async with self._client.session() as session:  # type: ignore[union-attr]
            result = await session.run(nodes_query, {"user_id": user_id})
            for record in await result.data():
                nodes.append(record)

            result = await session.run(rels_query, {"user_id": user_id})
            for record in await result.data():
                relationships.append(record)

        logger.info(
            "Exported subgraph for user %d (%d nodes, %d relationships)",
            user_id,
            len(nodes),
            len(relationships),
        )
        return SubgraphExport(
            user_id=user_id,
            nodes=nodes,
            relationships=relationships,
        )

    async def delete_user_subgraph(self, user_id: int) -> int:
        """
        Delete all graph data for a user (GDPR Art. 17 right to erasure).

        Deletes all nodes and relationships belonging to the user.

        Args:
            user_id: The user whose data to delete.

        Returns:
            Number of nodes deleted.
        """
        if self._stub_mode:
            user_node_ids = {
                nid
                for nid, n in self._stub_nodes.items()
                if n.user_id == user_id
            }
            # Delete relationships first
            rel_ids_to_delete = [
                rid
                for rid, r in self._stub_relationships.items()
                if r.source_id in user_node_ids or r.target_id in user_node_ids
            ]
            for rid in rel_ids_to_delete:
                del self._stub_relationships[rid]

            # Delete nodes
            for nid in user_node_ids:
                del self._stub_nodes[nid]

            count = len(user_node_ids)
            logger.info(
                "Stub: Deleted subgraph for user %d (%d nodes, %d relationships)",
                user_id,
                count,
                len(rel_ids_to_delete),
            )
            return count

        return await self._delete_user_subgraph_live(user_id)

    async def _delete_user_subgraph_live(self, user_id: int) -> int:
        """Delete user subgraph from live Neo4j."""
        query = (
            "MATCH (n {user_id: $user_id}) "
            "DETACH DELETE n "
            "RETURN count(n) AS deleted_count"
        )
        async with self._client.session() as session:  # type: ignore[union-attr]
            result = await session.run(query, {"user_id": user_id})
            record = await result.single()
            count: int = record["deleted_count"] if record else 0

        logger.info("Deleted subgraph for user %d (%d nodes)", user_id, count)
        return count


# =============================================================================
# Singleton
# =============================================================================

_neo4j_service: Neo4jService | None = None


def get_neo4j_service(client: Any | None = None) -> Neo4jService:
    """Get or create the Neo4j service singleton."""
    global _neo4j_service
    if _neo4j_service is None:
        _neo4j_service = Neo4jService(client=client)
    return _neo4j_service
