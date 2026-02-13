"""
Module Context for Aurora Sun V1.

The context passed to every module handle/on_enter/on_exit call.
Contains all information the module needs to process user requests.

Reference: ARCHITECTURE.md Section 2 (Module System)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any

from .segment_context import SegmentContext


# Type aliases for clarity
State: TypeAlias = str  # Current state in module's state machine (e.g., "overview", "priorities", "commitment")
SessionId: TypeAlias = str  # Unique session identifier
Language: TypeAlias = str  # ISO 639-1 language code (e.g., "en", "de")


@dataclass
class ModuleContext:
    """Context passed to every module operation.

    This is the interface between the Module System and individual modules.
    Contains all user-specific and session-specific information needed for
    module operations.

    Attributes:
        user_id: The user's unique identifier
        segment_context: The user's segment configuration (AD/AU/AH/NT/CU)
        state: Current state in the module's state machine
        session_id: Unique identifier for this conversation session
        language: ISO 639-1 language code
        module_name: Name of the currently active module
        previous_response: The previous response from the module (for continuity)
        metadata: Additional module-specific metadata
    """

    # Core user/session identifiers
    user_id: int
    segment_context: SegmentContext
    state: str  # Current state in module's state machine
    session_id: str
    language: str
    module_name: str

    # Timing
    started_at: datetime = field(default_factory=lambda: datetime.utcnow())
    last_interaction_at: datetime = field(default_factory=lambda: datetime.utcnow())

    # Continuity
    previous_response: Optional[str] = None
    message_history: list[dict[str, Any]] = field(default_factory=list)

    # Module-specific data
    metadata: dict[str, Any] = field(default_factory=dict)

    # Workflow context
    is_daily_workflow_active: bool = False
    daily_workflow_stage: Optional[str] = None

    # GDPR context
    is_frozen: bool = False  # True if user data processing is restricted (Art. 18)

    def update_interaction(self) -> None:
        """Update the last interaction timestamp."""
        self.last_interaction_at = datetime.utcnow()

    def add_to_history(self, role: str, content: str) -> None:
        """Add a message to the conversation history.

        Args:
            role: "user" or "assistant"
            content: The message content
        """
        self.message_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def get_recent_history(self, count: int = 5) -> list[dict[str, Any]]:
        """Get the most recent messages from history.

        Args:
            count: Number of messages to return

        Returns:
            List of message dicts
        """
        return self.message_history[-count:]


# Import Literal for type hints
from typing import Literal, Any
