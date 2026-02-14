"""
Knowledge Layer Services for Aurora Sun V1.

This package provides service wrappers for the Knowledge Layer databases:
- Neo4jService: Graph database for Vision→Goal→Task→Habit hierarchy,
  belief networks, pattern relationships, neurostate trajectories,
  and Aurora narrative ontology.
- QdrantService: Vector database for semantic search over captured items,
  research findings, and coaching traces.
- LettaService: Memory service for 3-tier memory (session, profile, archival)
  and coaching transcript storage.
- SyncService: Event-driven sync from PostgreSQL changes to Neo4j graph nodes.

All services support stub mode (client=None) for development without running databases.
All services include GDPR export/delete methods (SW-15 compliance).

Reference: ARCHITECTURE.md Section 5 (Knowledge Layer)
"""

from __future__ import annotations

from src.services.knowledge.letta_service import (
    LettaService,
    Memory,
    MemoryExport,
    MemoryTier,
    SessionContext,
    get_letta_service,
)
from src.services.knowledge.neo4j_service import (
    GraphNode,
    GraphRelationship,
    Neo4jService,
    NodeType,
    RelationshipType,
    SubgraphExport,
    get_neo4j_service,
)
from src.services.knowledge.qdrant_service import (
    CollectionName,
    EmbeddingResult,
    QdrantService,
    SearchResult,
    VectorExport,
    get_qdrant_service,
)
from src.services.knowledge.sync_service import (
    SyncEvent,
    SyncEventType,
    SyncService,
    SyncStatus,
    get_sync_service,
)

__all__ = [
    # Neo4j
    "Neo4jService",
    "GraphNode",
    "GraphRelationship",
    "NodeType",
    "RelationshipType",
    "SubgraphExport",
    "get_neo4j_service",
    # Qdrant
    "QdrantService",
    "SearchResult",
    "EmbeddingResult",
    "CollectionName",
    "VectorExport",
    "get_qdrant_service",
    # Letta
    "LettaService",
    "Memory",
    "MemoryTier",
    "SessionContext",
    "MemoryExport",
    "get_letta_service",
    # Sync
    "SyncService",
    "SyncEvent",
    "SyncEventType",
    "SyncStatus",
    "get_sync_service",
]
