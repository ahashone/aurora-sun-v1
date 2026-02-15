"""
Second Brain Module for Aurora Sun V1.

Upgraded second brain with semantic search, auto-routing, and knowledge graph integration.

Key Features:
- Auto-routing: tasks → planning, goals → goal system, insights → Aurora, ideas → Qdrant
- Semantic search: "What did I think about X last month?" → Qdrant
- Natural language retrieval with time-aware filtering
- Proactive surfacing before planning: "You had 3 ideas about Project X this week"
- Knowledge graph integration: captures → Neo4j nodes linked to goals, motifs, patterns

Reference: ROADMAP.md 3.7 (Second Brain Upgrade)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.gdpr_mixin import GDPRModuleMixin
from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse
from src.lib.encrypted_field import EncryptedFieldDescriptor
from src.lib.encryption import DataClassification
from src.lib.security import sanitize_for_storage
from src.models.base import Base

if TYPE_CHECKING:
    from src.services.knowledge.neo4j_service import Neo4jService
    from src.services.knowledge.qdrant_service import QdrantService


# Content types for classification
ContentType = str  # task | idea | note | insight | question | goal


@dataclass
class CapturedItem:
    """Represents a captured item before routing."""
    original_message: str
    content_type: ContentType
    content: str
    extracted_entities: dict[str, Any]


class SecondBrainEntry(Base):
    """
    Second Brain storage model for captured content.

    Data Classification: SENSITIVE
    - content: Encrypted with AES-256-GCM (personal data)
    """
    __tablename__ = "second_brain_entries"

    # Relationships
    user_relationship = relationship("User", back_populates="second_brain_entries")

    # Columns
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content_type = Column(String(50), nullable=False)  # idea | note | insight | question
    _content_plaintext = Column("content", Text, nullable=False)  # Encrypted storage
    metadata_json = Column(Text, nullable=True)  # Additional metadata (JSON)
    source = Column(String(50), nullable=True)  # capture | voice | search_result
    neo4j_node_id = Column(String(100), nullable=True)  # Link to knowledge graph
    qdrant_point_id = Column(String(100), nullable=True)  # Link to vector store
    created_at = Column(DateTime, nullable=False, default=datetime.now(UTC))

    # Encrypted field (fail-hard, no plaintext fallback)
    content = EncryptedFieldDescriptor(
        plaintext_attr="_content_plaintext",
        field_name="content",
        classification=DataClassification.SENSITIVE,
    )


class SecondBrainState:
    """State machine states for the Second Brain Module."""

    IDLE = "IDLE"
    SEARCH = "SEARCH"
    ROUTE = "ROUTE"
    CONFIRM = "CONFIRM"

    ALL: list[str] = [IDLE, SEARCH, ROUTE, CONFIRM]


class SecondBrainModule(GDPRModuleMixin):
    """
    Second Brain Module with semantic search and knowledge graph integration.

    This module implements:
    - Auto-routing to appropriate destinations
    - Semantic search via Qdrant
    - Knowledge graph integration via Neo4j
    - Proactive surfacing before planning
    - Natural language retrieval with time-aware filtering

    Segment-adaptive behavior:
    - AD (ADHD): Quick capture, minimal friction, proactive surfacing
    - AU (Autism): Structured retrieval, predictable organization
    - AH (AuDHD): Adaptive based on channel, flexible search
    - NT: Standard search and organization
    """

    name = "second_brain"
    intents = [
        "second_brain.search",
        "second_brain.capture",
        "second_brain.retrieve",
        "second_brain.organize",
    ]
    pillar = "second_brain"

    def __init__(
        self,
        neo4j_service: Neo4jService | None = None,
        qdrant_service: QdrantService | None = None,
    ) -> None:
        """Initialize the Second Brain Module."""
        self._neo4j = neo4j_service
        self._qdrant = qdrant_service
        self._state = SecondBrainState.IDLE

    async def on_enter(self, ctx: ModuleContext) -> ModuleResponse:
        """
        Called when user enters the second brain module.

        Provides segment-adaptive welcome message.
        """
        features = ctx.segment_context.features

        if features.routine_anchoring:
            # Autism: Clear, structured
            return ModuleResponse(
                text="Second Brain access. You can search for past notes, ideas, or insights. "
                     "What would you like to find?",
                next_state=SecondBrainState.SEARCH,
            )
        elif features.channel_dominance_enabled:
            # AuDHD: Flexible, adaptive
            return ModuleResponse(
                text="What are you looking for? I can search your notes, ideas, and insights.",
                next_state=SecondBrainState.SEARCH,
            )
        elif features.icnu_enabled:
            # ADHD: Brief, encouraging
            return ModuleResponse(
                text="Let's find what you need! Search your past thoughts, ideas, or notes.",
                next_state=SecondBrainState.SEARCH,
            )
        else:
            # Neurotypical or Custom
            return ModuleResponse(
                text="Search your second brain. What would you like to find?",
                next_state=SecondBrainState.SEARCH,
            )

    async def handle(
        self,
        message: str,
        ctx: ModuleContext,
    ) -> ModuleResponse:
        """
        Handle a second brain request.

        Supports:
        - Semantic search: "What did I think about X last month?"
        - Capture routing: Auto-route to planning/goals/Aurora/Qdrant
        - Natural language retrieval with time-aware filtering
        """
        # Detect if this is a search query or a capture
        if self._is_search_query(message):
            return await self._handle_search(message, ctx)
        else:
            return await self._handle_capture(message, ctx)

    def _is_search_query(self, message: str) -> bool:
        """Detect if the message is a search query."""
        search_keywords = [
            "what did i",
            "when did i",
            "show me",
            "find",
            "search",
            "look for",
            "remember",
            "recall",
        ]
        message_lower = message.lower()
        return any(kw in message_lower for kw in search_keywords)

    async def _handle_search(
        self,
        message: str,
        ctx: ModuleContext,
    ) -> ModuleResponse:
        """
        Handle semantic search via Qdrant.

        Extracts time filters from natural language ("last month", "this week")
        and performs time-aware semantic search.
        """
        # Extract time filter from message
        time_after, time_before = self._extract_time_filter(message)

        if self._qdrant is None:
            # Stub mode: return placeholder
            return ModuleResponse(
                text="Search is not available yet (Qdrant not configured). "
                     "Your query would search for content matching your request.",
                is_end_of_flow=True,
            )

        # TODO: Generate embedding for the search query using an embedding model
        # For now, return a placeholder response
        search_query = self._clean_search_query(message)

        return ModuleResponse(
            text=f"Searching for: '{search_query}' "
                 f"(time range: {time_after} to {time_before})\n\n"
                 "Semantic search will be available once embeddings are configured.",
            is_end_of_flow=True,
        )

    def _extract_time_filter(self, message: str) -> tuple[datetime | None, datetime | None]:
        """
        Extract time filter from natural language.

        Supports:
        - "last month"
        - "this week"
        - "past 3 days"
        - "since January"
        """
        now = datetime.now(UTC)
        message_lower = message.lower()

        if "last month" in message_lower:
            time_after = now - timedelta(days=30)
            time_before = now
        elif "this week" in message_lower:
            time_after = now - timedelta(days=7)
            time_before = now
        elif "past 3 days" in message_lower or "last 3 days" in message_lower:
            time_after = now - timedelta(days=3)
            time_before = now
        elif "today" in message_lower:
            time_after = now.replace(hour=0, minute=0, second=0, microsecond=0)
            time_before = now
        else:
            # No time filter
            time_after = None
            time_before = None

        return time_after, time_before

    def _clean_search_query(self, message: str) -> str:
        """Clean the search query by removing time and search keywords."""
        cleaned = message.strip()

        # Remove search keywords
        search_keywords = [
            "what did i think about",
            "what did i say about",
            "show me",
            "find",
            "search for",
            "look for",
            "remember when",
            "recall",
        ]

        for keyword in search_keywords:
            cleaned = cleaned.lower().replace(keyword, "")

        # Remove time keywords
        time_keywords = [
            "last month",
            "this week",
            "past 3 days",
            "last 3 days",
            "today",
            "yesterday",
        ]

        for keyword in time_keywords:
            cleaned = cleaned.lower().replace(keyword, "")

        return cleaned.strip()

    async def _handle_capture(
        self,
        message: str,
        ctx: ModuleContext,
    ) -> ModuleResponse:
        """
        Handle capture and auto-routing.

        Routes to:
        - task → planning inbox
        - goal → goal system
        - insight → Aurora
        - idea/note → Qdrant + Neo4j
        """
        # Classify content type
        classification = await self._classify_content(message)

        # Sanitize content before storing in Neo4j/Qdrant (injection prevention)
        sanitized_content, was_modified = sanitize_for_storage(
            classification["content"], max_length=10000
        )
        if was_modified:
            import logging
            logging.getLogger(__name__).info(
                "second_brain_content_sanitized user_id=%s content_type=%s",
                ctx.user_id if hasattr(ctx, "user_id") else "unknown",
                classification["type"],
            )
        classification["content"] = sanitized_content

        # Create captured item
        captured = CapturedItem(
            original_message=message,
            content_type=classification["type"],
            content=sanitized_content,
            extracted_entities=classification.get("entities", {}),
        )

        # Route to destination
        await self._route_content(classification["type"], captured, ctx)

        # Return confirmation
        confirmation = self._build_confirmation(
            content_type=classification["type"],
            content=classification["content"],
            segment_context=ctx.segment_context,
        )

        return ModuleResponse(
            text=confirmation,
            is_end_of_flow=True,
            metadata={
                "captured_content_type": classification["type"],
                "captured_content": classification["content"],
            },
        )

    async def _classify_content(self, message: str) -> dict[str, Any]:
        """
        Classify the content type using keyword-based classification.

        In production, this would use an LLM (Haiku) for classification.
        """
        # Keyword-based classification
        content_type = self._keyword_classify(message)

        # Clean up the content
        content = self._clean_content(message, content_type)

        return {
            "type": content_type,
            "content": content,
            "entities": {},
        }

    def _keyword_classify(self, message: str) -> ContentType:
        """Keyword-based classification fallback."""
        message_lower = message.lower()

        # Classification keywords (order matters - more specific first)
        keywords = {
            "question": ["how do", "what is", "why does", "when will", "?"],
            "insight": ["i notice", "i realize", "i'm better", "i work better"],
            "goal": ["my goal", "goal:", "want to", "aim to", "achieve"],
            "idea": ["idea", "thought", "concept", "could", "would be cool", "what if"],
            "task": ["call", "buy", "do", "finish", "submit", "send", "schedule"],
            "note": ["note", "remember", "info", "meeting"],
        }

        for category, kw_list in keywords.items():
            for keyword in kw_list:
                if keyword in message_lower:
                    return category

        # Default to "note"
        return "note"

    def _clean_content(self, message: str, content_type: ContentType) -> str:
        """Clean up content by removing classification prefixes."""
        prefixes = ["task: ", "idea: ", "note: ", "insight: ", "question: ", "goal: "]
        content = message.strip()

        for prefix in prefixes:
            if content.lower().startswith(prefix):
                content = content[len(prefix):]
                break

        return content.strip()

    async def _route_content(
        self,
        content_type: str,
        captured: CapturedItem,
        ctx: ModuleContext,
    ) -> ModuleResponse:
        """
        Route captured content to the appropriate destination.

        Routing rules:
        - task → Planning inbox
        - goal → Goal system
        - insight → Aurora coaching system
        - idea/note/question → Qdrant + Neo4j
        """
        if content_type == "task":
            # Route to Planning Module
            from src.core.side_effects import SideEffect, SideEffectType
            return ModuleResponse(
                text="",
                side_effects=[
                    SideEffect(
                        effect_type=SideEffectType.ADD_TO_PLANNING_INBOX,
                        payload={
                            "content": captured.content,
                            "source": "second_brain",
                        },
                    )
                ],
            )
        elif content_type == "goal":
            # Route to Goal system
            from src.core.side_effects import SideEffect, SideEffectType
            return ModuleResponse(
                text="",
                side_effects=[
                    SideEffect(
                        effect_type=SideEffectType.CREATE_GOAL_FROM_CAPTURE,
                        payload={
                            "title": captured.content,
                            "source": "second_brain",
                        },
                    )
                ],
            )
        elif content_type == "insight":
            # Route to Aurora
            from src.core.side_effects import SideEffect, SideEffectType
            return ModuleResponse(
                text="",
                side_effects=[
                    SideEffect(
                        effect_type=SideEffectType.ROUTE_TO_AURORA,
                        payload={
                            "content_type": content_type,
                            "content": captured.content,
                            "source": "second_brain",
                        },
                    )
                ],
            )
        else:
            # idea/note/question → Qdrant + Neo4j
            from src.core.side_effects import SideEffect, SideEffectType
            return ModuleResponse(
                text="",
                side_effects=[
                    SideEffect(
                        effect_type=SideEffectType.STORE_IN_SECOND_BRAIN,
                        payload={
                            "content_type": content_type,
                            "content": captured.content,
                            "source": "second_brain",
                        },
                    )
                ],
            )

    def _build_confirmation(
        self,
        content_type: ContentType,
        content: str,
        segment_context: Any,
    ) -> str:
        """Build a segment-adaptive confirmation message."""
        features = segment_context.features

        # Truncate long content for confirmation
        display_content = content[:30] + "..." if len(content) > 30 else content

        if features.routine_anchoring:
            # Autism: Clear, structured
            confirmations = {
                "task": f"Task added to planning inbox: '{display_content}'",
                "idea": f"Idea stored in second brain: '{display_content}'",
                "note": f"Note saved: '{display_content}'",
                "insight": f"Insight sent to Aurora: '{display_content}'",
                "question": f"Question saved: '{display_content}'",
                "goal": f"Goal created: '{display_content}'",
            }
        elif features.channel_dominance_enabled:
            # AuDHD: Flexible
            confirmations = {
                "task": f"Task added: '{display_content}'",
                "idea": f"Captured: '{display_content}'",
                "note": f"Noted: '{display_content}'",
                "insight": f"Insight logged: '{display_content}'",
                "question": f"Question saved: '{display_content}'",
                "goal": f"Goal set: '{display_content}'",
            }
        elif features.icnu_enabled:
            # ADHD: Exciting, brief
            confirmations = {
                "task": f"Task added: '{display_content}' - ready when you are!",
                "idea": f"Nice! Idea saved: '{display_content}'",
                "note": f"Got it! '{display_content}'",
                "insight": f"Insight noted: '{display_content}'",
                "question": f"Question captured: '{display_content}'",
                "goal": f"Goal set: '{display_content}' - let's make it happen!",
            }
        else:
            # NT/Default
            confirmations = {
                "task": f"Task captured: '{display_content}'",
                "idea": f"Idea saved: '{display_content}'",
                "note": f"Note stored: '{display_content}'",
                "insight": f"Insight noted: '{display_content}'",
                "question": f"Question captured: '{display_content}'",
                "goal": f"Goal set: '{display_content}'",
            }

        return confirmations.get(content_type, f"Captured: '{display_content}'")

    async def on_exit(self, ctx: ModuleContext) -> None:
        """Called when user exits the second brain module."""
        self._state = SecondBrainState.IDLE

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        """
        Return hooks for the daily workflow.

        planning_enrichment: Proactively surface ideas before planning
        """
        return DailyWorkflowHooks(
            planning_enrichment=self._surface_ideas,
            hook_name="second_brain",
            priority=15,
        )

    async def _surface_ideas(
        self,
        ctx: ModuleContext,
    ) -> dict[str, Any] | None:
        """
        Proactively surface ideas before planning.

        "You had 3 ideas about Project X this week"
        """
        # TODO: Query Qdrant for recent ideas related to current goals
        # For now, return None
        return None

    def _gdpr_data_categories(self) -> dict[str, list[str]]:
        """Declare second brain data categories for GDPR."""
        return {
            "second_brain_entries": ["content", "content_type", "metadata_json"],
            "qdrant_vectors": ["embedding"],
            "neo4j_nodes": ["properties"],
        }


# Export for module registry
__all__ = ["SecondBrainModule", "SecondBrainEntry", "ContentType", "CapturedItem"]
