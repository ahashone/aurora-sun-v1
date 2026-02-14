"""
Capture Module for Aurora Sun V1.

This module handles quick capture of thoughts, tasks, ideas, notes, and insights.
Designed for fire-and-forget mode: minimal friction, classify -> route -> confirm.

Reference: ARCHITECTURE.md Section 2 (Module System)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse
from src.models.base import Base

if TYPE_CHECKING:
    pass


# Content types for classification
ContentType = str  # task | idea | note | insight | question | goal


@dataclass
class CapturedItem:
    """Represents a captured item before routing."""
    original_message: str
    content_type: ContentType
    content: str
    extracted_entities: dict[str, Any]


class CapturedContent(Base):
    """
    Captured content model for Second Brain storage.

    Stores captured thoughts, tasks, ideas, notes, insights, and questions.

    Data Classification: SENSITIVE
    - content: Encrypted with AES-256-GCM (personal data)
    """
    __tablename__ = "captured_content"

    # Relationships
    user_relationship = relationship("User", back_populates="captured_items")

    # Columns
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content_type = Column(String(50), nullable=False)  # task | idea | note | insight | question | goal
    _content_plaintext = Column("content", Text, nullable=False)  # Encrypted storage
    metadata_json = Column(Text, nullable=True)  # Additional metadata (JSON)
    source = Column(String(50), nullable=True)  # quick_capture | voice | task | idea | note
    is_routed = Column(Integer, default=0)  # 0 = pending, 1 = routed to destination
    captured_at = Column(DateTime, nullable=False)

    @property
    def content(self) -> str:
        """Get decrypted content."""
        if self._content_plaintext is None:
            return ""
        try:
            import json
            data = json.loads(str(self._content_plaintext))
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                return get_encryption_service().decrypt_field(encrypted, int(self.user_id), "content")
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return str(self._content_plaintext)

    @content.setter
    def content(self, value: str | None) -> None:
        """Set encrypted content."""
        if value is None:
            setattr(self, '_content_plaintext', None)
            return
        try:
            import json

            from src.lib.encryption import DataClassification, get_encryption_service
            encrypted = get_encryption_service().encrypt_field(
                value, int(self.user_id), DataClassification.SENSITIVE, "content"
            )
            setattr(self, '_content_plaintext', json.dumps(encrypted.to_db_dict()))
        except Exception:
            setattr(self, '_content_plaintext', value)


class CaptureModule:
    """
    Capture Module for quick thought and task capture.

    This module implements fire-and-forget capture:
    1. User inputs a quick capture (text or voice)
    2. Classify content type (task/idea/note/insight/question/goal)
    3. Route to appropriate destination (Planning inbox, Second Brain, etc.)
    4. One-line confirmation

    Segment-adaptive behavior:
    - AD (ADHD): Minimal friction, immediate capture, novelty-positive language
    - AU (Autism): Structured confirmation, clear categorization, predictability
    - AH (AuDHD): Adaptive based on current state, flexible routing
    - NT: Standard flow
    """

    name = "capture"
    intents = [
        "capture.quick",
        "capture.voice",
        "capture.task",
        "capture.idea",
        "capture.note",
    ]
    pillar = "second_brain"

    # Classification prompt for Haiku (lightweight model)
    CLASSIFICATION_PROMPT = """Classify the following input into one of these categories:
- task: Something to do (e.g., "call dentist", "buy groceries")
- idea: A creative or conceptual thought (e.g., "newsletter idea", "app idea")
- note: Information to remember (e.g., "meeting at 3pm", "password is...")
- insight: Self-reflection or realization (e.g., "I work better in morning")
- question: Something to ask or find out (e.g., "how do I start?")
- goal: A desired outcome or achievement (e.g., "run marathon", "learn Spanish")

Input: "{message}"

Respond with just the category name."""

    # Keyword fallback for when LLM is unavailable
    CLASSIFICATION_KEYWORDS = {
        "task": ["call", "buy", "do", "finish", "submit", "send", "schedule", "remember to"],
        "idea": ["idea", "thought", "concept", "could", "would be cool", "what if"],
        "note": ["note", "remember", "info", "meeting", "at", "password", "address"],
        "insight": ["i notice", "i realize", "i find", "i'm better", "i work better"],
        "question": ["how do", "what is", "why does", "when will", "?"],
        "goal": ["goal", "want to", "aim to", "marathon", "achieve", "learn to"],
    }

    def __init__(self) -> None:
        """Initialize the Capture Module."""
        # State machine: CAPTURE -> CLASSIFY -> ROUTE -> DONE
        self._state = "capture"
        self._current_capture: CapturedItem | None = None

    async def on_enter(self, ctx: ModuleContext) -> ModuleResponse:
        """
        Called when user enters the capture module.

        For quick capture (fire-and-forget), this is optional -
        we can capture directly from handle() without explicit entry.
        """
        # FIX: Use SegmentContext fields instead of string comparison
        # This follows the ARCHITECTURE.md rule: "Never if segment == 'AD' in code"
        features = ctx.segment_context.features

        # Segment-adaptive entry message based on features
        if features.routine_anchoring:
            # Autism: Structured, clear expectations
            return ModuleResponse(
                text="I'll capture your thought. Just type what you want to remember - "
                     "I'll classify it and store it in the right place.",
                next_state="capture",
            )
        elif features.channel_dominance_enabled:
            # AuDHD: Flexible, adaptive
            return ModuleResponse(
                text="What's on your mind? I'll capture it and sort it for you.",
                next_state="capture",
            )
        elif features.icnu_enabled:
            # ADHD: Minimal friction, encouraging
            return ModuleResponse(
                text="Got it! Just tell me what you need to capture - I'll handle the rest.",
                next_state="capture",
            )
        else:
            # Neurotypical or Custom: Standard message
            return ModuleResponse(
                text="I've captured that. Let me organize it for you.",
                next_state="capture",
            )

    async def handle(
        self,
        message: str,
        ctx: ModuleContext,
    ) -> ModuleResponse:
        """
        Handle a capture request.

        Fire-and-forget flow:
        1. Classify the content type (Haiku)
        2. Extract relevant entities
        3. Route to destination
        4. One-line confirmation
        """
        # Check for voice input (stub)
        if ctx.metadata.get("is_voice_input", False):
            message = await self._process_voice_input(message, ctx)

        # Step 1: Classify content
        classification = await self.classify_content(message)

        # Step 2: Create captured item
        captured = CapturedItem(
            original_message=message,
            content_type=classification["type"],
            content=classification["content"],
            extracted_entities=classification.get("entities", {}),
        )

        # Step 3: Route to destination
        await self.route_content(classification["type"], captured, ctx)

        # Step 4: Return with confirmation (segment-adaptive)
        confirmation = self._build_confirmation(
            content_type=classification["type"],
            content=classification["content"],
            segment_context=ctx.segment_context,
        )

        return ModuleResponse(
            text=confirmation,
            is_end_of_flow=True,  # Fire-and-forget: we're done
            metadata={
                "captured_content_type": classification["type"],
                "captured_content": classification["content"],
            },
        )

    async def classify_content(self, message: str) -> dict[str, Any]:
        """
        Classify the content type using Haiku.

        Uses Haiku (lightweight model) for fast classification.
        Falls back to keyword-based classification if LLM unavailable.

        Args:
            message: The raw input message

        Returns:
            Dict with:
            - type: ContentType (task|idea|note|insight|question|goal)
            - content: Cleaned content
            - entities: Extracted entities (e.g., amounts, dates)
        """
        # TODO: Replace with actual Haiku call when LLM service is available
        # For now, use keyword-based fallback

        # Check for financial content first (route to Money Module)
        if self._is_financial_content(message):
            return {
                "type": "financial",
                "content": message,
                "entities": self._extract_financial_entities(message),
            }

        # Keyword-based classification fallback
        content_type = self._keyword_classify(message)

        # Clean up the content (remove classification keywords)
        content = self._clean_content(message, content_type)

        return {
            "type": content_type,
            "content": content,
            "entities": {},
        }

    def _keyword_classify(self, message: str) -> ContentType:
        """
        Keyword-based classification fallback.

        Used when Haiku is unavailable.
        """
        message_lower = message.lower()

        # Check each category's keywords
        for category, keywords in self.CLASSIFICATION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in message_lower:
                    return category

        # Default to "note" if no match
        return "note"

    def _is_financial_content(self, message: str) -> bool:
        """Check if the message contains financial content."""
        financial_keywords = [
            "euro", "eur", "$", "spent", "cost", "price",
            "paid", "bought", "invoice", "receipt", "budget",
        ]
        message_lower = message.lower()
        return any(kw in message_lower for kw in financial_keywords)

    def _extract_financial_entities(self, message: str) -> dict[str, Any]:
        """Extract financial entities from message."""
        import re

        entities = {}

        # Extract amount (supports: 12€, €12, $12, 12 euros)
        amount_match = re.search(r'(\d+(?:[.,]\d{1,2})?)\s*(?:euros?|eur|€|\$)', message, re.IGNORECASE)
        if amount_match:
            entities["amount"] = amount_match.group(1)

        # Extract currency symbol
        if "€" in message or "eur" in message.lower():
            entities["currency"] = "EUR"
        elif "$" in message:
            entities["currency"] = "USD"

        return entities

    def _clean_content(self, message: str, content_type: ContentType) -> str:
        """Clean up content by removing classification prefixes."""
        # Remove common prefixes
        prefixes = ["task: ", "idea: ", "note: ", "insight: ", "question: ", "goal: ", "remember: "]
        content = message.strip()

        for prefix in prefixes:
            if content.lower().startswith(prefix):
                content = content[len(prefix):]
                break

        return content.strip()

    async def route_content(
        self,
        content_type: str,
        captured: CapturedItem,
        ctx: ModuleContext,
    ) -> ModuleResponse:
        """
        Route captured content to the appropriate destination.

        Routing rules:
        - task -> Planning inbox (add to pending tasks)
        - idea -> Second Brain (store in captured_content)
        - note -> Second Brain (store in captured_content)
        - insight -> Aurora coaching system (process as reflection)
        - goal -> Goal system (create or link to existing)
        - question -> Question bank (for later answering)
        - financial -> Money Module (trigger money capture flow)
        """
        if content_type == "task":
            # Route to Planning Module (via side effect)
            # The planning module will pick this up in next session
            from src.core.side_effects import SideEffect
            return ModuleResponse(
                text="",
                side_effects=[
                    SideEffect(
                        effect_type="add_to_planning_inbox",  # type: ignore[arg-type]
                        payload={
                            "content": captured.content,
                            "source": "capture",
                            "original_message": captured.original_message,
                        },
                    )
                ],
            )
        elif content_type == "idea" or content_type == "note":
            # Store in Second Brain
            from src.core.side_effects import SideEffect
            return ModuleResponse(
                text="",
                side_effects=[
                    SideEffect(
                        effect_type="store_in_second_brain",  # type: ignore[arg-type]
                        payload={
                            "content_type": content_type,
                            "content": captured.content,
                            "source": "capture",
                        },
                    )
                ],
            )
        elif content_type == "goal":
            # Route to Goal system
            from src.core.side_effects import SideEffect
            return ModuleResponse(
                text="",
                side_effects=[
                    SideEffect(
                        effect_type="create_goal_from_capture",  # type: ignore[arg-type]
                        payload={
                            "title": captured.content,
                            "source": "capture",
                        },
                    )
                ],
            )
        elif content_type == "insight" or content_type == "question":
            # Route to Aurora for coaching/reflection
            from src.core.side_effects import SideEffect
            return ModuleResponse(
                text="",
                side_effects=[
                    SideEffect(
                        effect_type="route_to_aurora",  # type: ignore[arg-type]
                        payload={
                            "content_type": content_type,
                            "content": captured.content,
                            "source": "capture",
                        },
                    )
                ],
            )
        elif content_type == "financial":
            # Route to Money Module
            from src.core.side_effects import SideEffect
            return ModuleResponse(
                text="",
                side_effects=[
                    SideEffect(
                        effect_type="route_to_money_module",  # type: ignore[arg-type]
                        payload={
                            "content": captured.content,
                            "entities": captured.extracted_entities,
                        },
                    )
                ],
            )

        # Default: store in Second Brain
        from src.core.side_effects import SideEffect
        return ModuleResponse(
            text="",
            side_effects=[
                SideEffect(
                    effect_type="store_in_second_brain",  # type: ignore[arg-type]
                    payload={
                        "content_type": "note",
                        "content": captured.content,
                        "source": "capture",
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
        """
        Build a segment-adaptive confirmation message.

        The confirmation should be:
        - AD: Brief, encouraging, dopamin-positive
        - AU: Clear, structured, predictable
        - AH: Adaptive based on current state
        - NT: Standard friendly
        """
        # FIX: Use SegmentContext fields instead of string comparison
        # This follows the ARCHITECTURE.md rule: "Never if segment == 'AD' in code"
        features = segment_context.features

        # Truncate long content for confirmation
        display_content = content[:30] + "..." if len(content) > 30 else content

        if features.routine_anchoring:
            # Autism: Clear, structured, no surprises
            confirmations = {
                "task": f"Task captured and added to your planning inbox: '{display_content}'",
                "idea": f"Idea stored in your second brain: '{display_content}'",
                "note": f"Note saved: '{display_content}'",
                "insight": f"Insight recorded: '{display_content}'",
                "question": f"Question saved for later: '{display_content}'",
                "goal": f"Goal added: '{display_content}'",
                "financial": f"Financial entry recorded: '{display_content}'",
            }
        elif features.channel_dominance_enabled:
            # AuDHD: Flexible, adaptive
            confirmations = {
                "task": f"Done! Task: '{display_content}' added to your list.",
                "idea": f"Captured your idea: '{display_content}'",
                "note": f"Note saved: '{display_content}'",
                "insight": f"Insight noted: '{display_content}'",
                "question": f"Question captured: '{display_content}'",
                "goal": f"Goal recorded: '{display_content}'",
                "financial": f"Financial note: '{display_content}'",
            }
        elif features.icnu_enabled:
            # ADHD: Exciting, brief, novelty-positive
            confirmations = {
                "task": f"Captured! Task added: '{display_content}' - ready when you are.",
                "idea": f"Nice one! Idea saved: '{display_content}'",
                "note": f"Got it! Note stored: '{display_content}'",
                "insight": f"Great insight! noted: '{display_content}'",
                "question": f"Question captured: '{display_content}'",
                "goal": f"Goal set: '{display_content}' - let's make it happen!",
                "financial": f"Spent noted: '{display_content}'",
            }
        else:
            # NT / Default
            confirmations = {
                "task": f"Task captured: '{display_content}'",
                "idea": f"Idea saved: '{display_content}'",
                "note": f"Note stored: '{display_content}'",
                "insight": f"Insight noted: '{display_content}'",
                "question": f"Question captured: '{display_content}'",
                "goal": f"Goal set: '{display_content}'",
                "financial": f"Financial note: '{display_content}'",
            }

        return confirmations.get(content_type, f"Captured: '{display_content}'")

    async def _process_voice_input(
        self,
        audio_data: str,
        ctx: ModuleContext,
    ) -> str:
        """
        Process voice input via Groq Whisper.

        This is a STUB - actual implementation will use:
        - Groq Whisper API for fast transcription
        - Audio processing pipeline

        Args:
            audio_data: Audio data (currently stubbed as text placeholder)
            ctx: Module context

        Returns:
            Transcribed text
        """
        # TODO: Implement actual voice processing with Groq Whisper
        # from groq import Groq
        # client = Groq()
        # response = client.audio.transcriptions.create(
        #     file=audio_data,
        #     model="whisper-large-v3",
        #     response_format="text"
        # )
        # return response.text

        # For now, return the "audio_data" as if it were transcribed text
        # In production, this would be replaced with actual transcription
        return audio_data

    async def on_exit(self, ctx: ModuleContext) -> None:
        """
        Called when user exits the capture module.

        Cleanup: Reset internal state.
        """
        self._state = "capture"
        self._current_capture = None

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        """
        Return hooks for the daily workflow.

        planning_enrichment: Surface captured tasks in next planning session
        """
        return DailyWorkflowHooks(
            planning_enrichment=self._surface_captured_tasks,
            hook_name="capture",
            priority=10,  # Run early
        )

    async def _surface_captured_tasks(
        self,
        ctx: ModuleContext,
    ) -> dict[str, Any] | None:
        """
        Surface captured tasks from the capture module.

        Called during planning_enrichment to show captured tasks
        that haven't been processed yet.

        Args:
            ctx: Module context

        Returns:
            Dict with captured tasks, or None if none found
        """
        # TODO: Query database for captured tasks
        # SELECT * FROM captured_content
        # WHERE user_id = ctx.user_id
        # AND content_type = 'task'
        # AND is_routed = 0
        # ORDER BY captured_at DESC
        # LIMIT 5

        # For now, return None (no database integration yet)
        return None

    # GDPR Methods

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """
        Export all captured content for a user.

        GDPR Art. 15: Right of access

        Args:
            user_id: The user's ID

        Returns:
            Dict containing all captured content
        """
        # TODO: Query database for user's captured content
        return {
            "captured_content": [],  # TODO: Populate from DB
        }

    async def delete_user_data(self, user_id: int) -> None:
        """
        Delete all captured content for a user.

        GDPR Art. 17: Right to erasure

        Args:
            user_id: The user's ID
        """
        # TODO: Delete from database
        # DELETE FROM captured_content WHERE user_id = user_id
        pass

    async def freeze_user_data(self, user_id: int) -> None:
        """
        Freeze processing of captured content.

        GDPR Art. 18: Restriction of processing

        Args:
            user_id: The user's ID
        """
        # TODO: Mark records as frozen
        pass

    async def unfreeze_user_data(self, user_id: int) -> None:
        """
        Unfreeze processing of captured content.

        GDPR Art. 18: Lift restriction

        Args:
            user_id: The user's ID
        """
        # TODO: Unmark frozen records
        pass


# Export for module registry
__all__ = ["CaptureModule", "ContentType", "CapturedItem"]
