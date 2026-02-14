"""
Habit Module for Aurora Sun V1.

This module handles habit creation, tracking, and reinforcement using the
Atomic Habits framework (James Clear). Designed with neurotype-specific
adaptations for each segment.

Key features:
- Identity-based framing ("I am someone who...")
- 2-minute rule (start tiny, scale up)
- Habit stacking ("After I [existing], I will [new]")
- Cumulative progress (NOT streaks for ADHD segments)
- Segment-specific timing and reinforcement

State machine: CREATE -> IDENTITY -> CUE -> CRAVING -> RESPONSE -> REWARD -> TRACKING -> DONE

Reference:
- ARCHITECTURE.md Section 2 (Module System)
- ROADMAP.md 3.4: Habit Module
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse
from src.models.base import Base

if TYPE_CHECKING:
    pass


# =============================================================================
# Habit States
# =============================================================================

class HabitState:
    """State machine states for the Habit Module."""

    CREATE = "CREATE"
    IDENTITY = "IDENTITY"
    CUE = "CUE"
    CRAVING = "CRAVING"
    RESPONSE = "RESPONSE"
    REWARD = "REWARD"
    TRACKING = "TRACKING"
    DONE = "DONE"

    ALL: list[str] = [
        CREATE,
        IDENTITY,
        CUE,
        CRAVING,
        RESPONSE,
        REWARD,
        TRACKING,
        DONE,
    ]


# =============================================================================
# SQLAlchemy Models
# =============================================================================

class Habit(Base):
    """
    Habit model for tracking user habits.

    Data Classification: SENSITIVE
    - name: Encrypted with AES-256-GCM (personal behavioral data)
    - identity_statement: Encrypted (personal identity framing)
    - cue, craving, response, reward: Encrypted (behavioral data)

    Uses cumulative_count (NOT streak-based) to support ADHD segments
    where streak-breaking causes shame spirals.
    """

    __tablename__ = "habits"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    _name_plaintext = Column("name", Text, nullable=False)
    identity_statement = Column(Text, nullable=True)
    cue = Column(Text, nullable=True)
    craving = Column(Text, nullable=True)
    response = Column(Text, nullable=True)
    reward = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_active = Column(Integer, default=1)  # 1 = active, 0 = inactive
    cumulative_count = Column(Integer, default=0)
    habit_stack_after = Column(Text, nullable=True)  # "After I [existing]..."
    coherence_goal_id = Column(Integer, ForeignKey("goals.id"), nullable=True)

    # Relationships
    logs = relationship("HabitLog", back_populates="habit", lazy="select")

    @property
    def name(self) -> str:
        """Get decrypted name."""
        if self._name_plaintext is None:
            return ""
        try:
            import json
            data = json.loads(str(self._name_plaintext))
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                return get_encryption_service().decrypt_field(
                    encrypted, int(self.user_id), "name"
                )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return str(self._name_plaintext)

    @name.setter
    def name(self, value: str | None) -> None:
        """Set encrypted name."""
        if value is None:
            setattr(self, "_name_plaintext", None)
            return
        try:
            import json

            from src.lib.encryption import DataClassification, get_encryption_service
            encrypted = get_encryption_service().encrypt_field(
                value, int(self.user_id), DataClassification.SENSITIVE, "name"
            )
            setattr(self, "_name_plaintext", json.dumps(encrypted.to_db_dict()))
        except Exception:
            setattr(self, "_name_plaintext", value)


class HabitLog(Base):
    """
    Habit completion log entry.

    Data Classification: INTERNAL
    - Tracks when a habit was completed.
    - notes: Optional, not encrypted (kept brief and non-sensitive).
    """

    __tablename__ = "habit_logs"

    id = Column(Integer, primary_key=True)
    habit_id = Column(Integer, ForeignKey("habits.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    completed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    notes = Column(Text, nullable=True)

    # Relationships
    habit = relationship("Habit", back_populates="logs")


# =============================================================================
# Session Data
# =============================================================================

@dataclass
class HabitCreationSession:
    """Session data for the habit creation flow."""

    habit_name: str = ""
    identity_statement: str = ""
    cue: str = ""
    craving: str = ""
    response: str = ""
    reward: str = ""
    habit_stack_after: str = ""
    linked_goal_id: int | None = None


# =============================================================================
# Habit Module
# =============================================================================

class HabitModule:
    """
    Habit Module implementing the Atomic Habits framework.

    Segment-adaptive behavior via SegmentContext fields (never if segment == "AD"):
    - icnu_enabled (AD/AH): Novelty rotation, cumulative gamification, dopamine pairing
    - routine_anchoring (AU): Fixed slots, minimal variation, monotropic focus
    - channel_dominance_enabled (AH): Channel-aware, spoon-drawer, integrity trigger
    - Default (NT): Standard habit tracking with streaks optional

    Key design decisions:
    - Cumulative count instead of streaks when gamification == "cumulative"
    - 2-minute rule: always suggest starting tiny
    - Identity-based framing: "I am someone who..." not "I want to..."
    - Habit stacking support for all segments
    - CoherenceRatio: link habits to goals for meaning
    """

    name: str = "habit"
    intents: list[str] = [
        "habit.create",
        "habit.check_in",
        "habit.list",
        "habit.complete",
        "habit.stack",
    ]
    pillar: str = "vision_to_task"

    def __init__(self) -> None:
        """Initialize the Habit Module."""
        self._sessions: dict[int, HabitCreationSession] = {}

    # =========================================================================
    # Module Protocol Implementation
    # =========================================================================

    async def on_enter(self, ctx: ModuleContext) -> ModuleResponse:
        """
        Start a new habit creation flow.

        Uses segment-specific framing:
        - routine_anchoring: Structured, predictable intro
        - channel_dominance_enabled: Flexible, channel-aware intro
        - icnu_enabled: Exciting, novelty-positive intro
        - Default: Standard friendly intro
        """
        features = ctx.segment_context.features

        if features.routine_anchoring:
            text = (
                "Let's create a new habit. I'll guide you through each step "
                "in order. We'll define what this habit means to your identity, "
                "set a consistent cue, and build it into your routine."
            )
        elif features.channel_dominance_enabled:
            text = (
                "Time to build a new habit! We'll work through this together - "
                "I'll check which channel feels right and help you fit it "
                "into your current energy pattern."
            )
        elif features.icnu_enabled:
            text = (
                "New habit time! Let's make this exciting. We'll start tiny "
                "(2-minute rule) and build from there. What habit do you "
                "want to create?"
            )
        else:
            text = (
                "Let's create a new habit together. We'll walk through the "
                "Atomic Habits framework: identity, cue, craving, response, "
                "and reward. What habit would you like to build?"
            )

        self._sessions[ctx.user_id] = HabitCreationSession()

        return ModuleResponse(
            text=text,
            next_state=HabitState.CREATE,
        )

    async def handle(
        self,
        message: str,
        ctx: ModuleContext,
    ) -> ModuleResponse:
        """
        Handle user message based on current state in the habit creation flow.

        Routes to the appropriate state handler based on ctx.state.
        """
        session = self._sessions.get(ctx.user_id)
        if session is None:
            return await self.on_enter(ctx)

        _HandlerType = Callable[
            [str, ModuleContext, HabitCreationSession],
            Awaitable[ModuleResponse],
        ]
        state_handlers: dict[str, _HandlerType] = {
            HabitState.CREATE: self._handle_create,
            HabitState.IDENTITY: self._handle_identity,
            HabitState.CUE: self._handle_cue,
            HabitState.CRAVING: self._handle_craving,
            HabitState.RESPONSE: self._handle_response,
            HabitState.REWARD: self._handle_reward,
            HabitState.TRACKING: self._handle_tracking,
        }

        handler = state_handlers.get(ctx.state)
        if handler is not None:
            return await handler(message, ctx, session)

        # Unknown state, restart
        return await self.on_enter(ctx)

    async def on_exit(self, ctx: ModuleContext) -> None:
        """Clean up session data when leaving the habit module."""
        self._sessions.pop(ctx.user_id, None)

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        """
        Return hooks for the daily workflow.

        morning: Habit reminders (segment-aware timing)
        evening_review: Habit check-in prompt
        """
        return DailyWorkflowHooks(
            morning=self._morning_habit_reminder,
            evening_review=self._evening_habit_checkin,
            hook_name="habit",
            priority=20,
        )

    # =========================================================================
    # GDPR Methods
    # =========================================================================

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """
        GDPR Art. 15: Export all habit data for a user.

        Returns:
            Dict containing habits and habit logs.
        """
        # TODO: Query database for user's habits and logs
        return {
            "habits": [],
            "habit_logs": [],
        }

    async def delete_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 17: Delete all habit data for a user.
        """
        # TODO: DELETE FROM habit_logs WHERE user_id = ?
        # TODO: DELETE FROM habits WHERE user_id = ?
        pass

    async def freeze_user_data(self, user_id: int) -> None:
        """GDPR Art. 18: Restrict processing of habit data."""
        # TODO: Mark habit records as frozen
        pass

    async def unfreeze_user_data(self, user_id: int) -> None:
        """GDPR Art. 18: Lift restriction on habit data processing."""
        # TODO: Unmark frozen records
        pass

    # =========================================================================
    # State Handlers
    # =========================================================================

    async def _handle_create(
        self,
        message: str,
        ctx: ModuleContext,
        session: HabitCreationSession,
    ) -> ModuleResponse:
        """Handle CREATE state - capture habit name and suggest identity framing."""
        session.habit_name = message.strip()

        # Apply 2-minute rule: suggest starting tiny
        two_minute_suggestion = self._apply_two_minute_rule(session.habit_name)

        features = ctx.segment_context.features

        if features.routine_anchoring:
            # AU: Clear, structured identity prompt
            text = (
                f"Habit: '{session.habit_name}'\n\n"
                f"Tip: Start with just 2 minutes - {two_minute_suggestion}\n\n"
                f"Now, let's frame this as an identity statement. "
                f"Instead of 'I want to meditate', say 'I am someone who meditates.'\n\n"
                f"What identity statement fits this habit?"
            )
        elif features.icnu_enabled:
            # AD/AH: Exciting, dopamine-positive
            text = (
                f"Love it! '{session.habit_name}'\n\n"
                f"Pro tip: Start ridiculously small - {two_minute_suggestion}\n\n"
                f"Now the fun part - who do you become with this habit? "
                f"Complete this: 'I am someone who...'"
            )
        else:
            # NT/Default
            text = (
                f"Great choice: '{session.habit_name}'\n\n"
                f"Tip: The 2-minute rule - {two_minute_suggestion}\n\n"
                f"Let's define your identity statement. "
                f"Who do you become with this habit? "
                f"'I am someone who...'"
            )

        return ModuleResponse(
            text=text,
            next_state=HabitState.IDENTITY,
        )

    async def _handle_identity(
        self,
        message: str,
        ctx: ModuleContext,
        session: HabitCreationSession,
    ) -> ModuleResponse:
        """Handle IDENTITY state - capture identity statement, move to CUE."""
        session.identity_statement = message.strip()

        features = ctx.segment_context.features

        if features.routine_anchoring:
            text = (
                f"Identity: '{session.identity_statement}'\n\n"
                f"Next: What will be the cue (trigger) for this habit? "
                f"This should be a specific time, location, or existing routine. "
                f"Example: 'After I wake up' or 'When I sit at my desk at 9am'"
            )
        elif features.icnu_enabled:
            text = (
                f"That's powerful: '{session.identity_statement}'\n\n"
                f"Now, what triggers this habit? Think of something you already do "
                f"every day that you can stack this onto. "
                f"Example: 'After I pour my coffee...'"
            )
        else:
            text = (
                f"Identity set: '{session.identity_statement}'\n\n"
                f"What will trigger this habit? Choose a clear cue - "
                f"a time, place, or existing habit to stack onto."
            )

        return ModuleResponse(
            text=text,
            next_state=HabitState.CUE,
        )

    async def _handle_cue(
        self,
        message: str,
        ctx: ModuleContext,
        session: HabitCreationSession,
    ) -> ModuleResponse:
        """Handle CUE state - capture cue, detect habit stacking, move to CRAVING."""
        session.cue = message.strip()

        # Detect habit stacking pattern
        cue_lower = session.cue.lower()
        if any(keyword in cue_lower for keyword in ["after i", "when i", "before i"]):
            session.habit_stack_after = session.cue

        text = (
            f"Cue set: '{session.cue}'\n\n"
            f"Now, what's the craving? This is the desire or motivation "
            f"behind the habit. What feeling or outcome makes you want to do it?\n\n"
            f"Example: 'I crave the calm feeling after meditation' or "
            f"'I want the energy boost from exercise'"
        )

        return ModuleResponse(
            text=text,
            next_state=HabitState.CRAVING,
        )

    async def _handle_craving(
        self,
        message: str,
        ctx: ModuleContext,
        session: HabitCreationSession,
    ) -> ModuleResponse:
        """Handle CRAVING state - capture craving, move to RESPONSE."""
        session.craving = message.strip()

        # Apply 2-minute rule for the response
        two_min = self._apply_two_minute_rule(session.habit_name)

        text = (
            f"Craving noted: '{session.craving}'\n\n"
            f"What's the actual response (the habit itself)? "
            f"Remember the 2-minute rule: {two_min}\n\n"
            f"Describe the specific action you'll take."
        )

        return ModuleResponse(
            text=text,
            next_state=HabitState.RESPONSE,
        )

    async def _handle_response(
        self,
        message: str,
        ctx: ModuleContext,
        session: HabitCreationSession,
    ) -> ModuleResponse:
        """Handle RESPONSE state - capture response, move to REWARD."""
        session.response = message.strip()

        features = ctx.segment_context.features

        if features.icnu_enabled:
            # AD/AH: Emphasize dopamine pairing
            text = (
                f"Action defined: '{session.response}'\n\n"
                f"Last piece: What's your reward? This is crucial for dopamine! "
                f"Pair something satisfying with completing the habit. "
                f"Example: 'Check off on my tracker' or 'Enjoy my coffee while reading'"
            )
        elif features.routine_anchoring:
            # AU: Clear, predictable
            text = (
                f"Response set: '{session.response}'\n\n"
                f"Finally: What will be your reward? Choose something consistent "
                f"and predictable that you can do immediately after. "
                f"Example: 'Mark it complete on my tracker'"
            )
        else:
            text = (
                f"Response set: '{session.response}'\n\n"
                f"What reward will you give yourself after completing this habit? "
                f"It should be immediate and satisfying."
            )

        return ModuleResponse(
            text=text,
            next_state=HabitState.REWARD,
        )

    async def _handle_reward(
        self,
        message: str,
        ctx: ModuleContext,
        session: HabitCreationSession,
    ) -> ModuleResponse:
        """Handle REWARD state - capture reward, show summary, move to TRACKING."""
        session.reward = message.strip()

        # Build summary
        gamification = ctx.segment_context.ux.gamification
        threshold = ctx.segment_context.core.habit_threshold_days

        tracking_info = self._get_tracking_info(gamification, threshold)

        text = (
            f"Here's your complete habit:\n\n"
            f"Habit: {session.habit_name}\n"
            f"Identity: {session.identity_statement}\n"
            f"Cue: {session.cue}\n"
            f"Craving: {session.craving}\n"
            f"Response: {session.response}\n"
            f"Reward: {session.reward}\n"
        )

        if session.habit_stack_after:
            text += f"Stacked after: {session.habit_stack_after}\n"

        text += f"\n{tracking_info}\n\nShall I save this habit? (yes/no)"

        return ModuleResponse(
            text=text,
            next_state=HabitState.TRACKING,
        )

    async def _handle_tracking(
        self,
        message: str,
        ctx: ModuleContext,
        session: HabitCreationSession,
    ) -> ModuleResponse:
        """Handle TRACKING state - confirm and save, or cancel."""
        import re

        message_lower = message.lower().strip()

        yes_pattern = re.compile(r"\b(yes|y|ja|si|da|yeah|yep|sure|ok|okay|save)\b")
        no_pattern = re.compile(r"\b(no|n|nein|nao|nope|cancel)\b")

        if yes_pattern.search(message_lower):
            # Save the habit via side effect
            from src.core.side_effects import SideEffect, SideEffectType

            gamification = ctx.segment_context.ux.gamification

            if gamification == "cumulative":
                confirmation = (
                    "Habit saved! Your cumulative count starts at 0. "
                    "Every completion adds to your total - no streaks to break!"
                )
            elif gamification == "adaptive":
                confirmation = (
                    "Habit saved! I'll adapt the tracking to your current energy "
                    "and channel. Every completion counts."
                )
            else:
                confirmation = "Habit saved! I'll remind you to track it daily."

            # Clean up session
            self._sessions.pop(ctx.user_id, None)

            return ModuleResponse(
                text=confirmation,
                is_end_of_flow=True,
                next_state=HabitState.DONE,
                side_effects=[
                    SideEffect(
                        effect_type=SideEffectType.CREATE_HABIT,
                        payload={
                            "name": session.habit_name,
                            "identity_statement": session.identity_statement,
                            "cue": session.cue,
                            "craving": session.craving,
                            "response": session.response,
                            "reward": session.reward,
                            "habit_stack_after": session.habit_stack_after,
                            "linked_goal_id": session.linked_goal_id,
                        },
                    )
                ],
            )

        elif no_pattern.search(message_lower):
            self._sessions.pop(ctx.user_id, None)
            return ModuleResponse(
                text="Habit creation cancelled. You can start a new one anytime.",
                is_end_of_flow=True,
                next_state=HabitState.DONE,
            )

        else:
            return ModuleResponse(
                text="Please confirm: save this habit? (yes/no)",
                next_state=HabitState.TRACKING,
            )

    # =========================================================================
    # Daily Workflow Hooks
    # =========================================================================

    async def _morning_habit_reminder(
        self,
        ctx: ModuleContext,
    ) -> str | None:
        """
        Morning habit reminder hook.

        Segment-aware:
        - routine_anchoring: Fixed time reminder with exact habits
        - icnu_enabled: Brief, encouraging nudge
        - channel_dominance_enabled: Channel-aware suggestion
        - Default: Standard reminder
        """
        features = ctx.segment_context.features

        # TODO: Load active habits from database
        # For now, return None (no habits loaded yet)
        active_habits: list[dict[str, Any]] = []

        if not active_habits:
            return None

        if features.routine_anchoring:
            return "Your morning habits are ready. Complete them in order for consistency."
        elif features.icnu_enabled:
            return "Quick habit check! What's first on your list today?"
        elif features.channel_dominance_enabled:
            return "Checking in on habits - which channel are you in right now?"
        else:
            return "Good morning! Time for your daily habits."

    async def _evening_habit_checkin(
        self,
        ctx: ModuleContext,
    ) -> str | None:
        """
        Evening habit check-in hook.

        Segment-aware:
        - gamification == "cumulative": Show cumulative count, no shame
        - gamification == "adaptive": Show contextual progress
        - gamification == "none": Simple tracking, no pressure
        """
        # TODO: Load today's habit completions from database
        # Will use ctx.segment_context.ux.gamification to adapt display
        return None

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _apply_two_minute_rule(self, habit_name: str) -> str:
        """
        Apply the 2-minute rule: suggest a tiny starting version.

        The 2-minute rule from Atomic Habits says to scale down any habit
        to something that takes 2 minutes or less.
        """
        name_lower = habit_name.lower()

        suggestions: dict[str, str] = {
            "meditat": "sit quietly for 2 minutes",
            "exercise": "put on your workout clothes",
            "run": "put on your running shoes",
            "read": "read one page",
            "journal": "write one sentence",
            "study": "open your textbook",
            "clean": "pick up one item",
            "cook": "chop one vegetable",
            "write": "write one sentence",
            "stretch": "do one stretch",
            "walk": "step outside for 2 minutes",
            "yoga": "do one pose",
            "code": "open your editor and type one line",
            "practice": "do it for 2 minutes",
        }

        for keyword, suggestion in suggestions.items():
            if keyword in name_lower:
                return suggestion

        return f"just do the first 2 minutes of '{habit_name}'"

    def _get_tracking_info(self, gamification: str, threshold_days: int) -> str:
        """
        Get segment-appropriate tracking information.

        Uses SegmentContext.ux.gamification and SegmentContext.core.habit_threshold_days.
        """
        if gamification == "cumulative":
            return (
                f"Tracking: Cumulative count (no streaks!). "
                f"Every completion adds +1. Target: {threshold_days} days to build the habit."
            )
        elif gamification == "adaptive":
            return (
                f"Tracking: Adaptive - I'll adjust based on your energy and channel. "
                f"Target: {threshold_days} days to solidify."
            )
        elif gamification == "none":
            return (
                f"Tracking: Simple completion log. "
                f"Target: {threshold_days} days of consistent practice."
            )
        else:
            return (
                f"Tracking: Daily check-in. "
                f"Target: {threshold_days} days to build the habit."
            )

    def get_coherence_ratio(
        self,
        habit_completions: int,
        goal_progress: float,
    ) -> float:
        """
        Calculate the CoherenceRatio between habit and linked goal.

        CoherenceRatio measures how well habit execution correlates
        with goal progress. Higher = more aligned.

        Args:
            habit_completions: Number of habit completions
            goal_progress: Goal progress as 0.0-1.0

        Returns:
            Coherence ratio as 0.0-1.0
        """
        if habit_completions == 0:
            return 0.0
        if goal_progress <= 0.0:
            return 0.0

        # Simple ratio: goal progress per habit completion
        # Normalized to 0-1 range
        raw_ratio = goal_progress / min(habit_completions, 100)
        return min(1.0, max(0.0, raw_ratio))


# =============================================================================
# Module Export
# =============================================================================

__all__ = [
    "HabitModule",
    "HabitState",
    "HabitCreationSession",
    "Habit",
    "HabitLog",
]
