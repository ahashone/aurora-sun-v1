"""
Neurostate Services Package for Aurora Sun V1.

This package contains the 6 neurostate intelligence services:
- SensoryStateAssessment: Cumulative sensory load tracking (AU/AH)
- InertiaDetector: Three types of inertia detection (AD/AU/AH)
- BurnoutClassifier: Three types of burnout classification
- MaskingLoadTracker: Exponential double-masking tracking (AH)
- ChannelDominanceDetector: Channel dominance detection (AH)
- EnergyPredictor: Behavioral proxy-based energy prediction

References:
- ARCHITECTURE.md Section 3 (Neurotype Segmentation)
"""

from src.services.neurostate.sensory import (
    SensoryStateAssessment,
    SensoryState,
    ModalityInput,
)

from src.services.neurostate.inertia import (
    InertiaDetector,
    InertiaEventData,
    InertiaDetectionResult,
)

from src.services.neurostate.burnout import (
    BurnoutClassifier,
    BurnoutState,
    BurnoutClassification,
)

from src.services.neurostate.masking import (
    MaskingLoadTracker,
    MaskingLoad,
    MaskingEvent,
)

from src.services.neurostate.channel import (
    ChannelDominanceDetector,
    ChannelStateData,
    ChannelDetectionResult,
)

from src.services.neurostate.energy import (
    EnergyPredictor,
    BehavioralSignals,
    EnergyPrediction,
)


# Re-export all classes
__all__ = [
    # Sensory
    "SensoryStateAssessment",
    "SensoryState",
    "ModalityInput",
    # Inertia
    "InertiaDetector",
    "InertiaEventData",
    "InertiaDetectionResult",
    # Burnout
    "BurnoutClassifier",
    "BurnoutState",
    "BurnoutClassification",
    # Masking
    "MaskingLoadTracker",
    "MaskingLoad",
    "MaskingEvent",
    # Channel
    "ChannelDominanceDetector",
    "ChannelStateData",
    "ChannelDetectionResult",
    # Energy
    "EnergyPredictor",
    "BehavioralSignals",
    "EnergyPrediction",
]
