"""
Tension Engine for Aurora Sun V1.

Maps users to quadrants based on Sonne (energy/fulfillment) vs Erde (grounding/action).
Used by CoachingEngine to determine coaching approach.

Reference: ARCHITECTURE.md Section 4 (Tension Engine + Fulfillment)
Reference: SW-3, SW-11, SW-12
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Literal, TypeAlias

# Quadrant levels (0-1 scale)
TensionLevel: TypeAlias = Literal[0, 1]


class Quadrant(StrEnum):
    """Four quadrants based on Sonne vs Erde axes."""

    SWEET_SPOT = "SWEET_SPOT"   # HIGH sonne + HIGH erde: Reinforce
    AVOIDANCE = "AVOIDANCE"      # HIGH sonne + LOW erde: Cycle breaker
    BURNOUT = "BURNOUT"          # LOW sonne + HIGH erde: Recovery intervention
    CRISIS = "CRISIS"            # LOW sonne + LOW erde: Safety first


# Override hierarchy (safety-critical interventions override everything)
OverrideLevel = Literal["SAFETY", "GROUNDING", "ALIGNMENT", "OPTIMIZATION"]

OVERRIDE_HIERARCHY: list[OverrideLevel] = [
    "SAFETY",       # Crisis, burnout, health -> overrides everything
    "GROUNDING",    # Must act, not just think -> overrides alignment
    "ALIGNMENT",    # Fulfillment -> overrides optimization
    "OPTIMIZATION", # Efficiency -> lowest priority
]


# Fulfillment types (distinguishes genuine engagement from avoidance patterns)
FulfillmentType = Literal["GENUINE", "PSEUDO", "DUTY"]


class TensionState:
    """Current tension state for a user.

    Tracks the user's position in the Sonne/Erde space and provides
    methods for quadrant determination and override detection.
    """

    def __init__(
        self,
        sonne: float,  # 0-1: Energy/fulfillment
        erde: float,   # 0-1: Grounding/action
        user_id: int,
    ):
        """Initialize tension state.

        Args:
            sonne: Energy/fulfillment level (0=low, 1=high)
            erde: Grounding/action level (0=low, 1=high)
            user_id: User identifier
        """
        self.user_id = user_id
        self.sonne = max(0.0, min(1.0, sonne))
        self.erde = max(0.0, min(1.0, erde))

    @property
    def quadrant(self) -> Quadrant:
        """Determine the current quadrant based on Sonne and Erde levels."""
        if self.sonne >= 0.5 and self.erde >= 0.5:
            return Quadrant.SWEET_SPOT
        elif self.sonne >= 0.5 and self.erde < 0.5:
            return Quadrant.AVOIDANCE
        elif self.sonne < 0.5 and self.erde >= 0.5:
            return Quadrant.BURNOUT
        else:
            return Quadrant.CRISIS

    def needs_activation(self) -> bool:
        """Check if user needs activation protocol (not burnout or crisis).

        Returns:
            True if user is in SWEET_SPOT or AVOIDANCE quadrants
        """
        return self.quadrant in (Quadrant.SWEET_SPOT, Quadrant.AVOIDANCE)

    def needs_recovery(self) -> bool:
        """Check if user needs recovery protocol (burnout or crisis).

        Returns:
            True if user is in BURNOUT or CRISIS quadrants
        """
        return self.quadrant in (Quadrant.BURNOUT, Quadrant.CRISIS)

    def is_crisis(self) -> bool:
        """Check if user is in crisis state.

        Returns:
            True if user is in CRISIS quadrant
        """
        return self.quadrant == Quadrant.CRISIS

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "user_id": self.user_id,
            "sonne": self.sonne,
            "erde": self.erde,
            "quadrant": self.quadrant.value,
        }


class TensionEngine:
    """Engine for mapping users to tension quadrants.

    The Tension Engine determines the user's current state in the
    Sonne (energy/fulfillment) vs Erde (grounding/action) space
    and provides the quadrant classification for coaching decisions.

    Usage:
        engine = TensionEngine()
        state = engine.get_state(user_id=123)
        quadrant = state.quadrant

    Quadrant-based coaching:
        - SWEET_SPOT: Reinforce, no coaching needed
        - AVOIDANCE: Cycle breaker protocol
        - BURNOUT: SW-12 (Burnout Redirect)
        - CRISIS: SW-11 (Crisis Override)
    """

    def __init__(self) -> None:
        """Initialize the Tension Engine."""
        # In-memory cache of user tension states
        self._states: dict[int, TensionState] = {}
        # Redis service for persistence
        from src.services.redis_service import get_redis_service
        self._redis = get_redis_service()

    async def get_state(self, user_id: int) -> TensionState:
        """Get the current tension state for a user.

        Args:
            user_id: The user's unique identifier

        Returns:
            TensionState with current Sonne/Erde levels and quadrant
        """
        # Check in-memory cache first
        if user_id in self._states:
            return self._states[user_id]

        # Try loading from Redis
        redis_key = f"tension:{user_id}"
        redis_data = await self._redis.get(redis_key)

        if redis_data:
            try:
                data = json.loads(redis_data)
                state = TensionState(
                    sonne=data["sonne"],
                    erde=data["erde"],
                    user_id=user_id,
                )
                # Cache in memory
                self._states[user_id] = state
                return state
            except (json.JSONDecodeError, KeyError):
                # Fall through to default
                pass

        # Default to neutral state (0.5, 0.5)
        state = TensionState(sonne=0.5, erde=0.5, user_id=user_id)
        self._states[user_id] = state
        return state

    async def update_state(
        self,
        user_id: int,
        sonne: float | None = None,
        erde: float | None = None,
    ) -> TensionState:
        """Update the tension state for a user.

        Args:
            user_id: The user's unique identifier
            sonne: New energy/fulfillment level (None = no change)
            erde: New grounding/action level (None = no change)

        Returns:
            Updated TensionState
        """
        current = await self.get_state(user_id)

        new_sonne = sonne if sonne is not None else current.sonne
        new_erde = erde if erde is not None else current.erde

        new_state = TensionState(
            sonne=new_sonne,
            erde=new_erde,
            user_id=user_id,
        )

        # Update in-memory cache
        self._states[user_id] = new_state

        # Persist to Redis with 24-hour TTL
        redis_key = f"tension:{user_id}"
        redis_data = {"sonne": new_sonne, "erde": new_erde}
        await self._redis.set(redis_key, redis_data, ttl=86400)

        return new_state

    async def determine_override_level(
        self,
        user_id: int,
        burnout_severity: float = 0.0,
        crisis_detected: bool = False,
    ) -> OverrideLevel:
        """Determine the current override level based on safety signals.

        Args:
            user_id: The user's unique identifier
            burnout_severity: Burnout severity (0-1), 0 = no burnout
            crisis_detected: Whether a crisis has been detected

        Returns:
            The appropriate override level (SAFETY, GROUNDING, ALIGNMENT, or OPTIMIZATION)
        """
        # Crisis always takes highest priority
        if crisis_detected:
            return "SAFETY"

        # Burnout severity > 0.6 also triggers safety override
        if burnout_severity > 0.6:
            return "SAFETY"

        # Check tension quadrant for grounding vs alignment
        state = await self.get_state(user_id)

        if state.erde < 0.3:
            # Low grounding/action → needs grounding override
            return "GROUNDING"

        if state.sonne < 0.3:
            # Low energy/fulfillment → needs alignment override
            return "ALIGNMENT"

        return "OPTIMIZATION"

    async def should_activate(
        self,
        user_id: int,
        burnout_severity: float = 0.0,
    ) -> bool:
        """Determine if activation coaching should be applied.

        Args:
            user_id: The user's unique identifier
            burnout_severity: Current burnout severity (0-1)

        Returns:
            True if activation is appropriate, False if recovery is needed
        """
        # If burnout is emerging or active, don't activate
        if burnout_severity > 0.3:
            return False

        state = await self.get_state(user_id)
        return state.needs_activation()

    async def detect_quadrant_shift(
        self,
        user_id: int,
        previous_quadrant: Quadrant,
    ) -> Quadrant | None:
        """Detect if user has shifted quadrants.

        Args:
            user_id: The user's unique identifier
            previous_quadrant: The previous quadrant state

        Returns:
            New quadrant if shifted, None if unchanged
        """
        current = await self.get_state(user_id)
        current_quadrant = current.quadrant

        if current_quadrant != previous_quadrant:
            return current_quadrant
        return None

    def determine_fulfillment_type(
        self,
        activity_level: float,
        energy_change: float,
        results_achieved: bool,
    ) -> FulfillmentType:
        """Determine the type of engagement based on behavioral signals.

        Args:
            activity_level: Current activity/effort level (0-1)
            energy_change: Change in energy after activity (-1 to 1)
            results_achieved: Whether meaningful results were produced

        Returns:
            Fulfillment type: GENUINE, PSEUDO, or DUTY
        """
        if results_achieved and energy_change > 0:
            # Activity + energy rises + results = genuine engagement
            return "GENUINE"
        elif activity_level > 0.3 and not results_achieved:
            # Activity + energy rises + NO results = flow as avoidance
            return "PSEUDO"
        elif results_achieved and energy_change < -0.3:
            # Results + energy drain = duty/burnout path
            return "DUTY"
        else:
            # Default to duty if ambiguous
            return "DUTY"


# Module-level singleton for easy access
_tension_engine: TensionEngine | None = None


def get_tension_engine() -> TensionEngine:
    """Get the singleton TensionEngine instance.

    Returns:
        The global TensionEngine instance
    """
    global _tension_engine
    if _tension_engine is None:
        _tension_engine = TensionEngine()
    return _tension_engine


async def get_user_tension(user_id: int) -> TensionState:
    """Convenience function to get a user's tension state.

    Args:
        user_id: The user's unique identifier

    Returns:
        The user's current TensionState
    """
    engine = get_tension_engine()
    return await engine.get_state(user_id)
