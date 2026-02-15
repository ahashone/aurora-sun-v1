"""
Planning Module State Machine and Data Structures.

Defines the state machine states and session data structures for the planning flow.

Reference: planning.py (main module)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# Planning Module States
# =============================================================================

class PlanningState:
    """State machine states for the Planning Module."""

    # Initial state - ask what user wants to accomplish
    SCOPE = "SCOPE"

    # Display vision + 90d goals BEFORE task list
    VISION = "VISION"

    # Show existing tasks and pending items
    OVERVIEW = "OVERVIEW"

    # Select priorities (max based on segment)
    PRIORITIES = "PRIORITIES"

    # Break down priorities into tasks
    BREAKDOWN = "BREAKDOWN"

    # Validate against segment constraints
    SEGMENT_CHECK = "SEGMENT_CHECK"

    # Confirm today's commitment
    COMMITMENT = "COMMITMENT"

    # Flow complete
    DONE = "DONE"

    # All states as a list for validation
    ALL = [
        SCOPE,
        VISION,
        OVERVIEW,
        PRIORITIES,
        BREAKDOWN,
        SEGMENT_CHECK,
        COMMITMENT,
        DONE,
    ]


# =============================================================================
# Planning Data Structures
# =============================================================================

@dataclass
class PriorityItem:
    """A priority item selected by the user."""

    id: str
    title: str
    goal_id: int | None = None
    estimated_minutes: int | None = None


@dataclass
class PlanningSession:
    """Session data for the planning flow."""

    # What user wants to accomplish
    scope: str = ""

    # Selected priorities (max based on segment)
    priorities: list[PriorityItem] = field(default_factory=list)

    # Tasks derived from priorities
    tasks: list[dict[str, Any]] = field(default_factory=list)

    # 90d goals for vision alignment
    goals_90d: list[dict[str, Any]] = field(default_factory=list)

    # User's vision
    vision_content: str | None = None

    # User confirmed vision alignment
    vision_aligned: bool = False
