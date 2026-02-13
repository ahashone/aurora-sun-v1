"""
Segment Context for Aurora Sun V1.

SegmentContext wraps every interaction as a cross-cutting concern.
Modules receive the right config, framing, and constraints via this context.

Reference: ARCHITECTURE.md Section 3 (Neurotype Segmentation)

Key principle: Modules NEVER check `if segment == "AD"`.
They use fields from SegmentContext instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias


# Internal segment codes (used in code, NOT user-facing)
WorkingStyleCode: TypeAlias = Literal["AD", "AU", "AH", "NT", "CU"]

# User-facing display names
SEGMENT_DISPLAY_NAMES: dict[WorkingStyleCode, str] = {
    "AD": "ADHD",
    "AU": "Autism",
    "AH": "AuDHD",
    "NT": "Neurotypical",
    "CU": "Custom",
}


@dataclass
class SegmentCore:
    """Core segment configuration (read-only for modules)."""

    code: WorkingStyleCode  # AD | AU | AH | NT | CU (internal only)
    display_name: str  # "ADHD" | "Autism" | "AuDHD" | ... (user-facing)
    max_priorities: int  # 2 (AD) | 3 (AU/AH/NT)
    sprint_minutes: int  # 25 (AD) | 45 (AU) | 35 (AH) | 40 (NT)
    habit_threshold_days: int  # 21 (AD/AH/NT) | 14 (AU)


@dataclass
class SegmentUX:
    """UX-related segment configuration."""

    energy_check_type: str  # simple | sensory_cognitive | spoon_drawer
    gamification: str  # cumulative | none | adaptive
    notification_strategy: str  # interval | exact_time | semi_predictable | standard
    money_steps: int  # 3 (AD) | 7 (AU) | 5-8 (AH) | 4 (NT)


@dataclass
class NeurostateConfig:
    """Neurostate-related configuration (for NeurostateService)."""

    burnout_model: str  # boom_bust (AD) | overload_shutdown (AU) | three_type (AH)
    inertia_type: str  # activation_deficit (AD) | autistic_inertia (AU) | double_block (AH)
    masking_model: str  # neurotypical (AD) | social (AU) | double_exponential (AH)
    energy_assessment: str  # self_report (AD) | behavioral_proxy (AU) | composite (AH)
    sensory_accumulation: bool  # True for AU/AH -- sensory load does NOT habituate
    interoception_reliability: str  # moderate (AD) | low (AU) | very_low (AH) | high (NT)
    waiting_mode_vulnerability: str  # high (AD) | high (AU) | extreme (AH)


@dataclass
class SegmentFeatures:
    """Feature flags per segment."""

    icnu_enabled: bool  # True for AD/AH only
    spoon_drawer_enabled: bool  # True for AH only
    channel_dominance_enabled: bool  # True for AH only
    integrity_trigger_enabled: bool  # True for AH only
    sensory_check_required: bool  # True for AU/AH
    routine_anchoring: bool  # True for AU


@dataclass
class SegmentContext:
    """Full segment context for a user.

    Split into 4 sub-objects to avoid a God Object.
    Modules access only the sub-object they need.
    """

    core: SegmentCore
    ux: SegmentUX
    neuro: NeurostateConfig
    features: SegmentFeatures

    @classmethod
    def from_code(cls, code: WorkingStyleCode) -> SegmentContext:
        """Create SegmentContext from a working style code.

        This is the primary factory method. Use this to get the
        appropriate context for a user's segment.

        Args:
            code: The user's segment code (AD, AU, AH, NT, CU)

        Returns:
            Fully configured SegmentContext
        """
        return _SEGMENT_CONTEXTS[code]


# Pre-configured segment contexts
# These are the canonical configurations for each segment
SegmentCore_configs: dict[WorkingStyleCode, SegmentCore] = {
    "AD": SegmentCore(
        code="AD",
        display_name="ADHD",
        max_priorities=2,
        sprint_minutes=25,
        habit_threshold_days=21,
    ),
    "AU": SegmentCore(
        code="AU",
        display_name="Autism",
        max_priorities=3,
        sprint_minutes=45,
        habit_threshold_days=14,
    ),
    "AH": SegmentCore(
        code="AH",
        display_name="AuDHD",
        max_priorities=3,
        sprint_minutes=35,
        habit_threshold_days=21,
    ),
    "NT": SegmentCore(
        code="NT",
        display_name="Neurotypical",
        max_priorities=3,
        sprint_minutes=40,
        habit_threshold_days=21,
    ),
    "CU": SegmentCore(
        code="CU",
        display_name="Custom",
        max_priorities=3,
        sprint_minutes=40,
        habit_threshold_days=21,
    ),
}

SegmentUX_configs: dict[WorkingStyleCode, SegmentUX] = {
    "AD": SegmentUX(
        energy_check_type="simple",
        gamification="cumulative",
        notification_strategy="interval",
        money_steps=3,
    ),
    "AU": SegmentUX(
        energy_check_type="sensory_cognitive",
        gamification="none",
        notification_strategy="exact_time",
        money_steps=7,
    ),
    "AH": SegmentUX(
        energy_check_type="spoon_drawer",
        gamification="adaptive",
        notification_strategy="semi_predictable",
        money_steps=6,
    ),
    "NT": SegmentUX(
        energy_check_type="simple",
        gamification="none",
        notification_strategy="standard",
        money_steps=4,
    ),
    "CU": SegmentUX(
        energy_check_type="simple",
        gamification="none",
        notification_strategy="standard",
        money_steps=4,
    ),
}

NeurostateConfig_configs: dict[WorkingStyleCode, NeurostateConfig] = {
    "AD": NeurostateConfig(
        burnout_model="boom_bust",
        inertia_type="activation_deficit",
        masking_model="neurotypical",
        energy_assessment="self_report",
        sensory_accumulation=False,
        interoception_reliability="moderate",
        waiting_mode_vulnerability="high",
    ),
    "AU": NeurostateConfig(
        burnout_model="overload_shutdown",
        inertia_type="autistic_inertia",
        masking_model="social",
        energy_assessment="behavioral_proxy",
        sensory_accumulation=True,
        interoception_reliability="low",
        waiting_mode_vulnerability="high",
    ),
    "AH": NeurostateConfig(
        burnout_model="three_type",
        inertia_type="double_block",
        masking_model="double_exponential",
        energy_assessment="composite",
        sensory_accumulation=True,
        interoception_reliability="very_low",
        waiting_mode_vulnerability="extreme",
    ),
    "NT": NeurostateConfig(
        burnout_model="standard",
        inertia_type="none",
        masking_model="none",
        energy_assessment="self_report",
        sensory_accumulation=False,
        interoception_reliability="high",
        waiting_mode_vulnerability="low",
    ),
    "CU": NeurostateConfig(
        burnout_model="standard",
        inertia_type="none",
        masking_model="none",
        energy_assessment="self_report",
        sensory_accumulation=False,
        interoception_reliability="high",
        waiting_mode_vulnerability="low",
    ),
}

SegmentFeatures_configs: dict[WorkingStyleCode, SegmentFeatures] = {
    "AD": SegmentFeatures(
        icnu_enabled=True,
        spoon_drawer_enabled=False,
        channel_dominance_enabled=False,
        integrity_trigger_enabled=False,
        sensory_check_required=False,
        routine_anchoring=False,
    ),
    "AU": SegmentFeatures(
        icnu_enabled=False,
        spoon_drawer_enabled=False,
        channel_dominance_enabled=False,
        integrity_trigger_enabled=False,
        sensory_check_required=True,
        routine_anchoring=True,
    ),
    "AH": SegmentFeatures(
        icnu_enabled=True,
        spoon_drawer_enabled=True,
        channel_dominance_enabled=True,
        integrity_trigger_enabled=True,
        sensory_check_required=True,
        routine_anchoring=False,
    ),
    "NT": SegmentFeatures(
        icnu_enabled=False,
        spoon_drawer_enabled=False,
        channel_dominance_enabled=False,
        integrity_trigger_enabled=False,
        sensory_check_required=False,
        routine_anchoring=False,
    ),
    "CU": SegmentFeatures(
        icnu_enabled=False,
        spoon_drawer_enabled=False,
        channel_dominance_enabled=False,
        integrity_trigger_enabled=False,
        sensory_check_required=False,
        routine_anchoring=False,
    ),
}

# Pre-built contexts for each segment
_SEGMENT_CONTEXTS: dict[WorkingStyleCode, SegmentContext] = {
    code: SegmentContext(
        core=SegmentCore_configs[code],
        ux=SegmentUX_configs[code],
        neuro=NeurostateConfig_configs[code],
        features=SegmentFeatures_configs[code],
    )
    for code in ("AD", "AU", "AH", "NT", "CU")
}
