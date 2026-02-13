"""
Services for Aurora Sun V1.

This package contains the core services that power the Aurora coaching system.

Services:
    - TensionEngine: Maps users to quadrants (Sonne vs Erde)
    - CoachingEngine: Inline coaching with segment-specific protocols

Reference: ARCHITECTURE.md Section 4 (Intelligence Layer)
"""

from .tension_engine import (
    TensionEngine,
    TensionState,
    Quadrant,
    OverrideLevel,
    FulfillmentType,
    get_tension_engine,
    get_user_tension,
)

from .coaching_engine import (
    CoachingEngine,
    CoachingResponse,
    ChannelDominance,
    get_coaching_engine,
)


__all__ = [
    # Tension Engine
    "TensionEngine",
    "TensionState",
    "Quadrant",
    "OverrideLevel",
    "FulfillmentType",
    "get_tension_engine",
    "get_user_tension",
    # Coaching Engine
    "CoachingEngine",
    "CoachingResponse",
    "ChannelDominance",
    "get_coaching_engine",
]
