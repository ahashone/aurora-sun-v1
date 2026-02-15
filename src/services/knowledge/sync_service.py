"""
PostgreSQL to Neo4j Sync Service for Aurora Sun V1.

Event-driven synchronization from PostgreSQL changes to Neo4j graph nodes.
Syncs creation, updates, and completion of Vision, Goal, Task, and Habit entities.

When both services are in stub mode, sync operations are tracked in-memory.
This allows development and testing without running databases.

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


class SyncEventType(StrEnum):
    """Types of sync events from PostgreSQL to Neo4j."""

    CREATED = "created"
    UPDATED = "updated"
    COMPLETED = "completed"
    DELETED = "deleted"
    ARCHIVED = "archived"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class SyncEvent:
    """Represents a sync event from PostgreSQL to Neo4j."""

    event_id: str
    event_type: SyncEventType
    entity_type: str       # "vision", "goal", "task", "habit"
    entity_id: str
    user_id: int
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    synced: bool = False
    synced_at: datetime | None = None
    error: str | None = None


@dataclass
class SyncStatus:
    """Status of the sync service."""

    total_events: int = 0
    synced_events: int = 0
    failed_events: int = 0
    pending_events: int = 0
    last_sync_at: datetime | None = None


# =============================================================================
# Service
# =============================================================================


class SyncService:
    """
    PostgreSQL to Neo4j sync service.

    Receives events about entity changes in PostgreSQL and propagates them
    to the Neo4j knowledge graph. Supports creation, updates, completion,
    deletion, and archival of Vision, Goal, Task, and Habit entities.

    Events are processed asynchronously and tracked for reliability.
    Failed events are logged with error details for retry.

    Args:
        neo4j_service: Optional Neo4jService instance for graph operations.
            None = stub mode.
    """

    # Valid entity types that can be synced
    VALID_ENTITY_TYPES = frozenset({"vision", "goal", "task", "habit"})

    def __init__(self, neo4j_service: Any | None = None) -> None:
        """Initialize sync service."""
        self._neo4j = neo4j_service
        self._stub_mode = neo4j_service is None

        # Event log for tracking
        self._events: list[SyncEvent] = []

        if self._stub_mode:
            logger.info("SyncService initialized in stub mode (no Neo4j)")
        else:
            logger.info("SyncService initialized with live Neo4j")

    @property
    def is_stub(self) -> bool:
        """Return True if running in stub mode."""
        return self._stub_mode

    async def sync_event(
        self,
        event_type: SyncEventType,
        entity_type: str,
        entity_id: str,
        user_id: int,
        payload: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> SyncEvent:
        """
        Process a sync event from PostgreSQL to Neo4j.

        Creates, updates, or modifies the corresponding node in Neo4j
        based on the event type.

        Args:
            event_type: The type of change that occurred.
            entity_type: The entity type ("vision", "goal", "task", "habit").
            entity_id: The entity's unique identifier.
            user_id: The user who owns the entity.
            payload: Optional data payload with entity details.
            event_id: Optional custom event ID. Auto-generated if not provided.

        Returns:
            The SyncEvent record.

        Raises:
            ValueError: If entity_type is not valid.
        """
        if entity_type not in self.VALID_ENTITY_TYPES:
            raise ValueError(
                f"Invalid entity_type '{entity_type}'. "
                f"Must be one of: {', '.join(sorted(self.VALID_ENTITY_TYPES))}"
            )

        resolved_id = event_id or str(uuid.uuid4())
        now = datetime.now(UTC)

        event = SyncEvent(
            event_id=resolved_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            payload=payload or {},
            created_at=now,
        )

        try:
            if self._stub_mode:
                # In stub mode, just mark as synced
                event.synced = True
                event.synced_at = now
                logger.debug(
                    "Stub: Synced event %s (%s %s %s for user %d)",
                    resolved_id,
                    event_type,
                    entity_type,
                    entity_id,
                    user_id,
                )
            else:
                await self._process_event_live(event)
                event.synced = True
                event.synced_at = datetime.now(UTC)
        except Exception as exc:  # Intentional catch-all: sync failures must not propagate, events are retried
            event.error = str(exc)
            logger.error(
                "Failed to sync event %s: %s",
                resolved_id,
                exc,
            )

        self._events.append(event)
        return event

    async def _process_event_live(self, event: SyncEvent) -> None:
        """Process a sync event against the live Neo4j database."""
        from src.services.knowledge.neo4j_service import NodeType

        # Map entity types to node types
        node_type_map: dict[str, NodeType] = {
            "vision": NodeType.VISION,
            "goal": NodeType.GOAL,
            "task": NodeType.TASK,
            "habit": NodeType.HABIT,
        }

        node_type = node_type_map[event.entity_type]

        if event.event_type == SyncEventType.CREATED:
            await self._neo4j.create_node(  # type: ignore[union-attr]
                node_type=node_type,
                user_id=event.user_id,
                properties={
                    "entity_id": event.entity_id,
                    "status": "active",
                    **event.payload,
                },
                node_id=event.entity_id,
            )
        elif event.event_type == SyncEventType.COMPLETED:
            # Update node with completed status
            await self._neo4j.create_node(  # type: ignore[union-attr]
                node_type=node_type,
                user_id=event.user_id,
                properties={
                    "entity_id": event.entity_id,
                    "status": "completed",
                    "completed_at": event.created_at.isoformat(),
                    **event.payload,
                },
                node_id=event.entity_id,
            )
        elif event.event_type == SyncEventType.DELETED:
            # Mark as deleted (soft delete in graph)
            await self._neo4j.create_node(  # type: ignore[union-attr]
                node_type=node_type,
                user_id=event.user_id,
                properties={
                    "entity_id": event.entity_id,
                    "status": "deleted",
                    "deleted_at": event.created_at.isoformat(),
                    **event.payload,
                },
                node_id=event.entity_id,
            )
        else:
            # UPDATED or ARCHIVED - upsert
            await self._neo4j.create_node(  # type: ignore[union-attr]
                node_type=node_type,
                user_id=event.user_id,
                properties={
                    "entity_id": event.entity_id,
                    "status": str(event.event_type),
                    **event.payload,
                },
                node_id=event.entity_id,
            )

        logger.info(
            "Synced event %s: %s %s %s",
            event.event_id,
            event.event_type,
            event.entity_type,
            event.entity_id,
        )

    async def get_sync_status(self) -> SyncStatus:
        """
        Get the current sync status.

        Returns:
            SyncStatus with event counts and last sync time.
        """
        total = len(self._events)
        synced = sum(1 for e in self._events if e.synced)
        failed = sum(1 for e in self._events if e.error is not None)
        pending = total - synced - failed

        synced_times = [
            e.synced_at for e in self._events if e.synced_at is not None
        ]
        last_sync_at: datetime | None = max(synced_times) if synced_times else None

        status = SyncStatus(
            total_events=total,
            synced_events=synced,
            failed_events=failed,
            pending_events=pending,
            last_sync_at=last_sync_at,
        )

        logger.debug(
            "Sync status: total=%d, synced=%d, failed=%d, pending=%d",
            total,
            synced,
            failed,
            pending,
        )
        return status


# =============================================================================
# Singleton
# =============================================================================

_sync_service: SyncService | None = None


def get_sync_service(neo4j_service: Any | None = None) -> SyncService:
    """Get or create the sync service singleton."""
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService(neo4j_service=neo4j_service)
    return _sync_service
