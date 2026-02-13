"""
Services for Aurora Sun V1.

This package contains the core services that power the Aurora coaching system.

Services:
    - TensionEngine: Maps users to quadrants (Sonne vs Erde)
    - CoachingEngine: Inline coaching with segment-specific protocols
    - Neurostate Services (6):
        - SensoryStateAssessment: Cumulative sensory load (AU/AH)
        - InertiaDetector: Three inertia types (AD/AU/AH)
        - BurnoutClassifier: Three burnout types
        - MaskingLoadTracker: Exponential double-masking (AH)
        - ChannelDominanceDetector: Channel dominance (AH)
        - EnergyPredictor: Behavioral proxy prediction

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

from .pattern_detection import (
    PatternDetectionService,
    CycleType,
    CycleSeverity,
    DetectedCycle,
    SignalName,
    Intervention,
    get_pattern_detection_service,
)

# Neurostate Services
from .neurostate.sensory import (
    SensoryStateAssessment,
    SensoryState,
    ModalityInput,
)

from .neurostate.inertia import (
    InertiaDetector,
    InertiaEventData,
    InertiaDetectionResult,
)

from .neurostate.burnout import (
    BurnoutClassifier,
    BurnoutState,
    BurnoutClassification,
)

from .neurostate.masking import (
    MaskingLoadTracker,
    MaskingLoad,
    MaskingEvent,
)

from .neurostate.channel import (
    ChannelDominanceDetector,
    ChannelStateData,
    ChannelDetectionResult,
)

from .neurostate.energy import (
    EnergyPredictor,
    BehavioralSignals,
    EnergyPrediction,
)

from .effectiveness import (
    EffectivenessService,
    InterventionType,
    InterventionOutcome,
    SegmentCode,
    InterventionInstance,
    EffectivenessMetrics,
    VariantExperiment,
    EffectivenessMetricsResponse,
    VariantComparisonResult,
    InterventionOutcomeData,
    EffectivenessReport,
    get_effectiveness_service,
)

# Revenue Tracker (Money Pillar)
from .revenue_tracker import (
    RevenueTracker,
    RevenueEntry,
    RevenueBalance,
    RevenueCategory,
    EntryType,
    get_revenue_tracker,
    parse_and_save_revenue,
)

# Crisis Safety Net (SW-11)
from .crisis_service import (
    CrisisService,
    CrisisLevel,
    CrisisSignal,
    CrisisResponse,
    CountryCode,
    get_crisis_service,
    check_and_handle_crisis,
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
    # Pattern Detection
    "PatternDetectionService",
    "CycleType",
    "CycleSeverity",
    "DetectedCycle",
    "SignalName",
    "Intervention",
    "get_pattern_detection_service",
    # Neurostate Services
    "SensoryStateAssessment",
    "SensoryState",
    "ModalityInput",
    "InertiaDetector",
    "InertiaEventData",
    "InertiaDetectionResult",
    "BurnoutClassifier",
    "BurnoutState",
    "BurnoutClassification",
    "MaskingLoadTracker",
    "MaskingLoad",
    "MaskingEvent",
    "ChannelDominanceDetector",
    "ChannelStateData",
    "ChannelDetectionResult",
    "EnergyPredictor",
    "BehavioralSignals",
    "EnergyPrediction",
    # Effectiveness Service
    "EffectivenessService",
    "InterventionType",
    "InterventionOutcome",
    "SegmentCode",
    "InterventionInstance",
    "EffectivenessMetrics",
    "VariantExperiment",
    "EffectivenessMetricsResponse",
    "VariantComparisonResult",
    "InterventionOutcomeData",
    "EffectivenessReport",
    "get_effectiveness_service",
    # Revenue Tracker
    "RevenueTracker",
    "RevenueEntry",
    "RevenueBalance",
    "RevenueCategory",
    "EntryType",
    "get_revenue_tracker",
    "parse_and_save_revenue",
    # Crisis Service
    "CrisisService",
    "CrisisLevel",
    "CrisisSignal",
    "CrisisResponse",
    "CountryCode",
    "get_crisis_service",
    "check_and_handle_crisis",
]
