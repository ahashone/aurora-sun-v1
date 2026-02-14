"""
Masking Load Tracker Service for Aurora Sun V1.

For AuDHD: exponential double-masking cost per context.
As per ARCHITECTURE.md Section 3.5.

References:
- ARCHITECTURE.md Section 3 (Neurotype Segmentation)
- ARCHITECTURE.md Section 3.5 (Masking - AuDHD)
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.neurostate import MaskingLog

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class MaskingLoad:
    """Current masking load for a user."""

    user_id: int
    total_load: float                    # Total cumulative load (0-100)
    context_loads: dict[str, float]       # Load per context
    is_overloaded: bool                  # True if total > 80%
    is_critical: bool                    # True if total > 95%
    recent_events: list                  # Last N masking events


@dataclass
class MaskingEvent:
    """A single masking event."""

    id: int | None = None
    user_id: int = 0
    context: str = ""
    masking_type: str = ""
    load_score: float = 0.0
    duration_minutes: int | None = None
    notes: str | None = None
    logged_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# Service
# =============================================================================

class MaskingLoadTracker:
    """
    Tracks masking behavior and load for AuDHD users.

    Key Principles:
    - AuDHD has EXPONENTIAL double-masking cost
    - Each context accumulates independently
    - Masking in multiple contexts compounds exponentially
    - Recovery requires ceasing masking, not just time

    Masking Types:
    - Social camouflaging
    - Emotional suppression
    - Sensory masking (stim management)
    - Cognitive masking (masking processing differences)
    - Attention masking (hiding hyperfocus/inattention)

    Usage:
        tracker = MaskingLoadTracker(db)
        load = await tracker.track(user_id=123, context="work", masking_behavior="social")
    """

    # Base load scores per masking type
    MASKING_TYPE_BASE_LOAD = {
        "social_camouflaging": 15.0,
        "emotional_suppression": 12.0,
        "sensory_masking": 10.0,
        "cognitive_masking": 12.0,
        "attention_masking": 8.0,
        "speech_masking": 10.0,
        "special_interest_suppression": 8.0,
    }

    # Thresholds
    OVERLOAD_THRESHOLD = 80.0
    CRITICAL_THRESHOLD = 95.0

    # Exponential multiplier for context switching
    CONTEXT_MULTIPLIER = 1.5

    # Maximum contexts to track
    MAX_CONTEXTS = 10

    # Time window for "recent" events (hours)
    RECENT_WINDOW_HOURS = 24

    def __init__(self, db: Session):
        """
        Initialize the masking load tracker.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    async def track(
        self,
        user_id: int,
        context: str,
        masking_behavior: str,
        duration_minutes: int | None = None,
        notes: str | None = None,
    ) -> MaskingLoad:
        """
        Track a masking event and update cumulative load.

        CRITICAL: For AuDHD, masking in multiple contexts has
        EXPONENTIAL cost. Each context adds load, but switching
        contexts multiplies the cost.

        Args:
            user_id: The user's ID
            context: Context of masking (work, social, family, etc.)
            masking_behavior: Type of masking
            duration_minutes: How long masking was maintained
            notes: Optional notes

        Returns:
            Updated MaskingLoad
        """
        # Validate masking type
        if masking_behavior not in self.MASKING_TYPE_BASE_LOAD:
            # Default base load for unknown types
            base_load = 10.0
        else:
            base_load = self.MASKING_TYPE_BASE_LOAD[masking_behavior]

        # Calculate load with duration factor
        if duration_minutes:
            # Longer duration = more load (non-linear)
            duration_factor = 1 + (duration_minutes / 60) * 0.5
            event_load = base_load * duration_factor
        else:
            event_load = base_load

        # Get current context loads
        current_contexts = self._get_context_loads(user_id)

        # Add exponential cost for context switching
        if context in current_contexts:
            # Already masking in this context - add to existing load
            new_context_load = current_contexts[context] + event_load
        else:
            # New context - exponential penalty
            active_contexts = len(current_contexts)
            if active_contexts > 0:
                exponential_penalty = self.CONTEXT_MULTIPLIER ** active_contexts
                event_load *= exponential_penalty
            new_context_load = event_load

        # Cap individual context at 100
        new_context_load = min(100.0, new_context_load)

        # Log the event
        self._log_event(
            user_id=user_id,
            context=context,
            masking_type=masking_behavior,
            load_score=event_load,
            duration_minutes=duration_minutes,
            notes=notes,
        )

        # Return updated load
        return await self.get_current_load(user_id)

    async def get_current_load(
        self,
        user_id: int,
    ) -> MaskingLoad:
        """
        Get the current masking load for a user.

        Args:
            user_id: The user's ID

        Returns:
            Current MaskingLoad
        """
        # Get context loads
        context_loads = self._get_context_loads(user_id)

        # Calculate total (exponential sum)
        total_load = self._calculate_total_load(context_loads)

        # Get recent events
        recent_events = self._get_recent_events(user_id)

        return MaskingLoad(
            user_id=user_id,
            total_load=total_load,
            context_loads=context_loads,
            is_overloaded=total_load > self.OVERLOAD_THRESHOLD,
            is_critical=total_load > self.CRITICAL_THRESHOLD,
            recent_events=recent_events,
        )

    async def reduce_load(
        self,
        user_id: int,
        context: str,
        reduction: float,
    ) -> MaskingLoad:
        """
        Reduce masking load for a context.

        Use when user reports stopping masking in a context.

        Args:
            user_id: The user's ID
            context: Context to reduce
            reduction: Amount to reduce (0-100)

        Returns:
            Updated MaskingLoad
        """
        current = self._get_context_loads(user_id)

        if context in current:
            current[context] = max(0.0, current[context] - reduction)

            # Update database - find most recent event and mark reduction
            # For simplicity, we log a negative event
            self._log_event(
                user_id=user_id,
                context=context,
                masking_type="load_reduction",
                load_score=-reduction,
                duration_minutes=None,
                notes="User-reported load reduction",
            )

        return await self.get_current_load(user_id)

    async def get_recovery_recommendations(
        self,
        user_id: int,
    ) -> list[str]:
        """
        Get masking recovery recommendations.

        Args:
            user_id: The user's ID

        Returns:
            List of recommendations
        """
        load = await self.get_current_load(user_id)
        recommendations = []

        if load.is_critical:
            recommendations.append("CRITICAL: Stop all masking immediately")
            recommendations.append("Find safe space: quiet, dark, no social demands")
            recommendations.append("Do not attempt to mask - this is a safety concern")

        elif load.is_overloaded:
            recommendations.append("Reduce active contexts - pick one to unmask in")
            recommendations.append("Prioritize: which context is safest to unmask?")
            recommendations.append("Schedule recovery time between contexts")

        else:
            # Check for accumulation warning
            if len(load.context_loads) >= 3:
                recommendations.append("Masking across multiple contexts - watch for accumulation")
            else:
                recommendations.append("Current masking load is manageable")

        # Context-specific recommendations
        for ctx, ctx_load in load.context_loads.items():
            if ctx_load > 50:
                recommendations.append(f"High load in '{ctx}' context - consider reducing here")

        return recommendations

    def _get_context_loads(self, user_id: int) -> dict[str, float]:
        """Get current load per context from database."""
        # Sum load scores by context for unresolved masking
        # For simplicity, use recent events to calculate
        recent_time = datetime.now(UTC) - timedelta(hours=self.RECENT_WINDOW_HOURS)

        results = (
            self.db.query(
                MaskingLog.context,
                func.sum(MaskingLog.load_score).label("total")
            )
            .filter(
                MaskingLog.user_id == user_id,
                MaskingLog.logged_at >= recent_time,
            )
            .group_by(MaskingLog.context)
            .all()
        )

        return {ctx: max(0.0, float(total or 0)) for ctx, total in results}

    def _calculate_total_load(self, context_loads: dict[str, float]) -> float:
        """
        Calculate total masking load with exponential cost.

        More contexts = exponentially higher total load.
        """
        if not context_loads:
            return 0.0

        # Sum with exponential penalty for multiple contexts
        active_contexts = len(context_loads)
        base_sum = sum(context_loads.values())

        # Exponential factor: 2 contexts = 1.5x, 3 = 2.25x, etc.
        exponential_factor = 1 + (self.CONTEXT_MULTIPLIER ** (active_contexts - 1) - 1) * 0.5

        return min(100.0, base_sum * exponential_factor)

    def _log_event(
        self,
        user_id: int,
        context: str,
        masking_type: str,
        load_score: float,
        duration_minutes: int | None,
        notes: str | None,
    ) -> MaskingLog:
        """Log a masking event to the database."""
        event = MaskingLog(
            user_id=user_id,
            context=context,
            masking_type=masking_type,
            load_score=load_score,
            duration_minutes=duration_minutes,
            notes=notes,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def _get_recent_events(
        self,
        user_id: int,
        limit: int = 5,
    ) -> list[MaskingLog]:
        """Get recent masking events."""
        recent_time = datetime.now(UTC) - timedelta(hours=self.RECENT_WINDOW_HOURS)

        return (
            self.db.query(MaskingLog)
            .filter(
                MaskingLog.user_id == user_id,
                MaskingLog.logged_at >= recent_time,
            )
            .order_by(MaskingLog.logged_at.desc())
            .limit(limit)
            .all()
        )


__all__ = ["MaskingLoadTracker", "MaskingLoad", "MaskingEvent"]
