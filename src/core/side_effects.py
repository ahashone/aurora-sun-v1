"""
Side Effects for Aurora Sun V1.

Side effects are actions triggered by module responses that the system
executes after responding to the user. They enable modules to interact
with the broader system (database, services, etc.).

Reference: ARCHITECTURE.md Section 2 (Module System)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum
from datetime import datetime
import uuid


class SideEffectType(Enum):
    """Types of side effects that can be executed."""

    # Database operations
    SAVE_TASK = "save_task"
    UPDATE_TASK = "update_task"
    DELETE_TASK = "delete_task"
    SAVE_GOAL = "save_goal"
    UPDATE_GOAL = "update_goal"
    SAVE_VISION = "save_vision"

    # Habit operations
    CREATE_HABIT = "create_habit"
    COMPLETE_HABIT = "complete_habit"
    UPDATE_HABIT_STREAK = "update_habit_streak"

    # Belief operations
    SAVE_BELIEF = "save_belief"
    UPDATE_BELIEF = "update_belief"
    ADD_BELIEF_EVIDENCE = "add_belief_evidence"

    # Transaction operations
    SAVE_TRANSACTION = "save_transaction"
    UPDATE_BUDGET = "update_budget"

    # Capture operations
    SAVE_CAPTURED_ITEM = "save_captured_item"

    # Session operations
    START_SESSION = "start_session"
    END_SESSION = "end_session"
    UPDATE_SESSION = "update_session"

    # Workflow operations
    TRIGGER_DAILY_WORKFLOW = "trigger_daily_workflow"
    TRIGGER_CHECKIN = "trigger_checkin"

    # Aurora operations
    UPDATE_NARRATIVE = "update_narrative"
    TRIGGER_IMPULSE = "trigger_impulse"

    # Notification operations
    SCHEDULE_NOTIFICATION = "schedule_notification"
    CANCEL_NOTIFICATION = "cancel_notification"

    # Custom/Raw side effects
    CUSTOM = "custom"


@dataclass
class SideEffect:
    """A side effect to be executed by the system.

    Side effects are returned in ModuleResponse and executed by the
    Module System after the response is sent to the user.

    Attributes:
        effect_type: The type of side effect
        payload: Data required to execute the effect
        id: Unique identifier for this effect
        created_at: When the effect was created
        priority: Execution priority (lower = earlier)
    """

    effect_type: SideEffectType
    payload: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    priority: int = 0  # Lower = execute first

    def __post_init__(self) -> None:
        """Validate the side effect."""
        if isinstance(self.effect_type, str):
            try:
                self.effect_type = SideEffectType(self.effect_type)
            except ValueError:
                self.effect_type = SideEffectType.CUSTOM

    @classmethod
    def save_task(cls, task_data: Dict[str, Any], priority: int = 0) -> SideEffect:
        """Create a save_task side effect.

        Args:
            task_data: Task data to save
            priority: Execution priority

        Returns:
            SideEffect instance
        """
        return cls(
            effect_type=SideEffectType.SAVE_TASK,
            payload=task_data,
            priority=priority,
        )

    @classmethod
    def complete_habit(cls, habit_id: str, priority: int = 0) -> SideEffect:
        """Create a complete_habit side effect.

        Args:
            habit_id: The habit ID to complete
            priority: Execution priority

        Returns:
            SideEffect instance
        """
        return cls(
            effect_type=SideEffectType.COMPLETE_HABIT,
            payload={"habit_id": habit_id},
            priority=priority,
        )

    @classmethod
    def save_transaction(cls, transaction_data: Dict[str, Any], priority: int = 0) -> SideEffect:
        """Create a save_transaction side effect.

        Args:
            transaction_data: Transaction data to save
            priority: Execution priority

        Returns:
            SideEffect instance
        """
        return cls(
            effect_type=SideEffectType.SAVE_TRANSACTION,
            payload=transaction_data,
            priority=priority,
        )

    @classmethod
    def custom(cls, effect_name: str, payload: Dict[str, Any], priority: int = 0) -> SideEffect:
        """Create a custom side effect.

        Args:
            effect_name: Name of the custom effect
            payload: Effect payload
            priority: Execution priority

        Returns:
            SideEffect instance
        """
        return cls(
            effect_type=SideEffectType.CUSTOM,
            payload={"effect_name": effect_name, **payload},
            priority=priority,
        )


@dataclass
class SideEffectBatch:
    """A batch of side effects to be executed.

    Allows grouping multiple side effects together with metadata.
    """

    effects: list[SideEffect] = field(default_factory=list)
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    source_module: Optional[str] = None
    source_state: Optional[str] = None

    def add(self, effect: SideEffect) -> None:
        """Add a side effect to the batch."""
        self.effects.append(effect)

    def add_save_task(self, task_data: Dict[str, Any]) -> None:
        """Add a save_task effect."""
        self.effects.append(SideEffect.save_task(task_data))

    def add_complete_habit(self, habit_id: str) -> None:
        """Add a complete_habit effect."""
        self.effects.append(SideEffect.complete_habit(habit_id))

    def add_save_transaction(self, transaction_data: Dict[str, Any]) -> None:
        """Add a save_transaction effect."""
        self.effects.append(SideEffect.save_transaction(transaction_data))

    def sort_by_priority(self) -> None:
        """Sort effects by priority (lower = first)."""
        self.effects.sort(key=lambda e: e.priority)

    def is_empty(self) -> bool:
        """Check if batch is empty."""
        return len(self.effects) == 0

    def __len__(self) -> int:
        """Get number of effects in batch."""
        return len(self.effects)


# Side effect executor interface (to be implemented by the system)
class SideEffectExecutor:
    """Interface for executing side effects.

    This is implemented by the Module System to execute
    side effects returned by modules.
    """

    async def execute(self, effect: SideEffect, user_id: int) -> bool:
        """Execute a single side effect.

        Args:
            effect: The side effect to execute
            user_id: The user ID

        Returns:
            True if execution was successful
        """
        raise NotImplementedError

    async def execute_batch(self, batch: SideEffectBatch) -> list[bool]:
        """Execute a batch of side effects.

        Args:
            batch: The batch to execute

        Returns:
            List of success flags for each effect
        """
        batch.sort_by_priority()
        results = []
        for effect in batch.effects:
            success = await self.execute(effect, batch.user_id)
            results.append(success)
        return results
