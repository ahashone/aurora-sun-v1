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

from .coaching_engine import (
    ChannelDominance,
    CoachingEngine,
    CoachingResponse,
    get_coaching_engine,
)

# Crisis Safety Net (SW-11)
from .crisis_service import (
    CountryCode,
    CrisisLevel,
    CrisisResponse,
    CrisisService,
    CrisisSignal,
    check_and_handle_crisis,
    get_crisis_service,
)
from .effectiveness import (
    EffectivenessMetrics,
    EffectivenessMetricsResponse,
    EffectivenessReport,
    EffectivenessService,
    InterventionInstance,
    InterventionOutcome,
    InterventionOutcomeData,
    InterventionType,
    SegmentCode,
    VariantComparisonResult,
    VariantExperiment,
    get_effectiveness_service,
)
from .neurostate.burnout import (
    BurnoutClassification,
    BurnoutClassifier,
    BurnoutState,
)
from .neurostate.channel import (
    ChannelDetectionResult,
    ChannelDominanceDetector,
    ChannelStateData,
)
from .neurostate.energy import (
    BehavioralSignals,
    EnergyPrediction,
    EnergyPredictor,
)
from .neurostate.inertia import (
    InertiaDetectionResult,
    InertiaDetector,
    InertiaEventData,
)
from .neurostate.masking import (
    MaskingEvent,
    MaskingLoad,
    MaskingLoadTracker,
)

# Neurostate Services
from .neurostate.sensory import (
    ModalityInput,
    SensoryState,
    SensoryStateAssessment,
)
from .pattern_detection import (
    CycleSeverity,
    CycleType,
    DetectedCycle,
    Intervention,
    PatternDetectionService,
    SignalName,
    get_pattern_detection_service,
)

# Revenue Tracker (Money Pillar)
from .revenue_tracker import (
    EntryType,
    RevenueBalance,
    RevenueCategory,
    RevenueEntry,
    RevenueTracker,
    get_revenue_tracker,
    parse_and_save_revenue,
)
from .tension_engine import (
    FulfillmentType,
    OverrideLevel,
    Quadrant,
    TensionEngine,
    TensionState,
    get_tension_engine,
    get_user_tension,
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
