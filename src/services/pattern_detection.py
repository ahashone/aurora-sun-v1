"""
Pattern Detection Service for Aurora Sun V1.

Detects destructive behavioral patterns in user data based on
Daily Burden research across neurotype segments.

5 Core Cycles:
- Meta-Spirale: Overthinking about overthinking
- Shiny Object: Constantly starting new things
- Perfectionism: Never finishing due to standards
- Isolation: Withdrawing from support
- Free Work: Unpaid labor consuming energy

Plus 14 signals from Daily Burden research:
- AD (ADHD): Activation deficit, time blindness, RSD, shame accumulation, emotional dysregulation
- AU (Autism): Sensory overload trajectory, masking escalation, inertia frequency, capacity decline
- AH (AuDHD): Double masking cost, channel dominance shifts, spoon budget overspend

Reference:
- knowledge/research/meta-syntheses/meta-synthesis-daily-burden-ad.json
- knowledge/research/meta-syntheses/meta-synthesis-daily-burden-au.json
- knowledge/research/meta-syntheses/meta-synthesis-daily-burden-ah.json

Author: Aurora Sun V1 Team
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.core.segment_context import SegmentContext

# ============================================================================
# Core Cycles (5 Destructive Patterns)
# ============================================================================

class CycleType(StrEnum):
    """The 5 core destructive cycles detected by the service."""

    META_SPIRALE = "meta_spirale"       # Overthinking about overthinking
    SHINY_OBJECT = "shiny_object"       # Constantly starting new things
    PERFECTIONISM = "perfectionism"     # Never finishing due to standards
    ISOLATION = "isolation"              # Withdrawing from support
    FREE_WORK = "free_work"            # Unpaid labor consuming energy


class CycleSeverity(StrEnum):
    """Severity levels for detected cycles."""

    NONE = "none"
    EMERGING = "emerging"     # Early signs, mild concern
    ACTIVE = "active"         # Clear pattern, moderate concern
    SEVERE = "severe"        # entrenched pattern, high concern


@dataclass
class DetectedCycle:
    """A detected destructive cycle in user behavior."""

    cycle_type: CycleType
    severity: CycleSeverity
    confidence: float                    # 0.0 - 1.0
    evidence: list[str] = field(default_factory=list)
    trend: str = "stable"               # "improving", "stable", "worsening"
    first_detected: str | None = None  # ISO date string
    last_detected: str | None = None   # ISO date string


# ============================================================================
# Signal Definitions (14 Daily Burden Signals)
# ============================================================================

class SignalName(StrEnum):
    """14 signals from Daily Burden research."""

    # AD (ADHD) Signals
    MASKING_ESCALATION = "masking_escalation"
    SENSORY_OVERLOAD_TRAJECTORY = "sensory_overload_trajectory"
    INERTIA_FREQUENCY = "inertia_frequency"
    BURNOUT_EARLY_WARNING = "burnout_early_warning"
    TIME_BLINDNESS_SEVERITY = "time_blindness_severity"
    WAITING_MODE_FREQUENCY = "waiting_mode_frequency"
    DEADLINE_DEPENDENCY = "deadline_dependency"
    EMOTIONAL_DYSREGULATION_INTENSITY = "emotional_dysregulation_intensity"
    RSD_ESCALATION = "rsd_escalation"
    SHAME_ACCUMULATION = "shame_accumulation"

    # AU (Autism) Signals
    ENERGY_DEPLETION_RATE = "energy_depletion_rate"
    SPOON_BUDGET_OVERSPEND = "spoon_budget_overspend"
    CAPACITY_DECLINE_TREND = "capacity_decline_trend"
    SOCIAL_BATTERY_DRAIN = "social_battery_drain"
    ISOLATION_TREND = "isolation_trend"
    TRANSITION_TAX = "transition_tax"

    # AH (AuDHD) Signals
    DOUBLE_MASKING_COST = "double_masking_cost"
    CHANNEL_DOMINANCE_SHIFTS = "channel_dominance_shifts"


# Signal metadata for each segment
SIGNAL_METADATA: dict[SignalName, dict[str, Any]] = {
    # AD Signals
    SignalName.MASKING_ESCALATION: {
        "segment": "AD",
        "applicable_segments": ["AD", "AH"],  # AuDHD also experiences ADHD masking
        "category": "compensation_load",
        "description": "Increasing effort to hide ADHD traits over time",
        "research_source": "meta-synthesis-daily-burden-ad.json",
        "finding_id": "HCF-011",
    },
    SignalName.SENSORY_OVERLOAD_TRAJECTORY: {
        "segment": "AD",
        "applicable_segments": ["AD", "AH"],  # Sensory issues in both
        "category": "sensory",
        "description": "Sensory burden accumulating through the day",
        "research_source": "meta-synthesis-daily-burden-ad.json",
        "finding_id": "HCF-018",
    },
    SignalName.INERTIA_FREQUENCY: {
        "segment": "AU",
        "applicable_segments": ["AU", "AH"],  # AuDHD has autistic inertia
        "category": "inertia",
        "description": "Frequency of state-change paralysis",
        "research_source": "meta-synthesis-daily-burden-au.json",
        "finding_id": "HCF-006",
    },
    SignalName.BURNOUT_EARLY_WARNING: {
        "segment": "AD",
        "applicable_segments": ["AD", "AH"],  # ADHD burnout model applies to AuDHD
        "category": "burnout",
        "description": "Early indicators of ADHD burnout (distinct from NT burnout)",
        "research_source": "meta-synthesis-daily-burden-ad.json",
        "finding_id": "HCF-014",
    },
    SignalName.TIME_BLINDNESS_SEVERITY: {
        "segment": "AD",
        "applicable_segments": ["AD", "AH"],  # Time blindness is ADHD trait
        "category": "time_experience",
        "description": "Now vs Not Now binary affecting daily decisions",
        "research_source": "meta-synthesis-daily-burden-ad.json",
        "finding_id": "HCF-003",
    },
    SignalName.WAITING_MODE_FREQUENCY: {
        "segment": "AD",
        "applicable_segments": ["AD", "AU", "AH"],  # All ND segments experience waiting mode
        "category": "time_experience",
        "description": "Anticipatory paralysis before upcoming events",
        "research_source": "meta-synthesis-daily-burden-ad.json",
        "finding_id": "HCF-009",
    },
    SignalName.DEADLINE_DEPENDENCY: {
        "segment": "AD",
        "applicable_segments": ["AD", "AH"],  # Procrastination-sprint is ADHD pattern
        "category": "time_experience",
        "description": "Procrastination-sprint-crash cycles",
        "research_source": "meta-synthesis-daily-burden-ad.json",
        "finding_id": "HCF-012",
    },
    SignalName.EMOTIONAL_DYSREGULATION_INTENSITY: {
        "segment": "AD",
        "applicable_segments": ["AD", "AH"],  # Core ADHD feature
        "category": "emotional_regulation",
        "description": "Intensity of emotional reactions (core ADHD feature)",
        "research_source": "meta-synthesis-daily-burden-ad.json",
        "finding_id": "HCF-004",
    },
    SignalName.RSD_ESCALATION: {
        "segment": "AD",
        "applicable_segments": ["AD", "AH"],  # RSD is ADHD-specific
        "category": "emotional_regulation",
        "description": "Rejection Sensitive Dysphoria patterns",
        "research_source": "meta-synthesis-daily-burden-ad.json",
        "finding_id": "HCF-005",
    },
    SignalName.SHAME_ACCUMULATION: {
        "segment": "AD",
        "applicable_segments": ["AD", "AU", "AH"],  # All ND segments experience shame
        "category": "shame_accumulation",
        "description": "Chronic shame building from accumulated failures",
        "research_source": "meta-synthesis-daily-burden-ad.json",
        "finding_id": "HCF-006",
    },

    # AU Signals
    SignalName.ENERGY_DEPLETION_RATE: {
        "segment": "AU",
        "applicable_segments": ["AU", "AH"],  # Energy management is autism-centric
        "category": "energy_management",
        "description": "Rate of energy resource depletion through day",
        "research_source": "meta-synthesis-daily-burden-au.json",
        "finding_id": "HCF-001",
    },
    SignalName.SPOON_BUDGET_OVERSPEND: {
        "segment": "AU",
        "applicable_segments": ["AU", "AH"],  # Spoon theory for autism + AuDHD
        "category": "energy_management",
        "description": "Exceeding available spoon/energy budget",
        "research_source": "meta-synthesis-daily-burden-au.json",
        "finding_id": "MCF-002",
    },
    SignalName.CAPACITY_DECLINE_TREND: {
        "segment": "AU",
        "applicable_segments": ["AU", "AH"],  # Autism burnout pattern
        "category": "burnout",
        "description": "Long-term decline in available capacity",
        "research_source": "meta-synthesis-daily-burden-au.json",
        "finding_id": "HCF-003",
    },
    SignalName.SOCIAL_BATTERY_DRAIN: {
        "segment": "AU",
        "applicable_segments": ["AU", "AH"],  # Social costs are autism trait
        "category": "social",
        "description": "Social interaction costs and post-interaction processing",
        "research_source": "meta-synthesis-daily-burden-au.json",
        "finding_id": "MCF-012",
    },
    SignalName.ISOLATION_TREND: {
        "segment": "AU",
        "applicable_segments": ["AU", "AH"],  # Autistic withdrawal pattern
        "category": "social",
        "description": "Withdrawing from support connections",
        "research_source": "meta-synthesis-daily-burden-au.json",
        "finding_id": "MCF-012",
    },
    SignalName.TRANSITION_TAX: {
        "segment": "AU",
        "applicable_segments": ["AU", "AH"],  # Task switching cost is autism trait
        "category": "transitions",
        "description": "Excessive energy cost at each activity switch",
        "research_source": "meta-synthesis-daily-burden-au.json",
        "finding_id": "MCF-009",
    },

    # AH Signals (AuDHD-specific, not overlapping)
    SignalName.DOUBLE_MASKING_COST: {
        "segment": "AH",
        "applicable_segments": ["AH"],  # AuDHD-specific
        "category": "masking",
        "description": "Exponential masking cost from hiding both ADHD and autism traits",
        "research_source": "meta-synthesis-daily-burden-ah.json",
        "finding_id": "HCF-005",
    },
    SignalName.CHANNEL_DOMINANCE_SHIFTS: {
        "segment": "AH",
        "applicable_segments": ["AH"],  # AuDHD-specific
        "category": "channel_dominance",
        "description": "Shifts between ADHD-dominant and autism-dominant modes",
        "research_source": "meta-synthesis-daily-burden-ah.json",
        "finding_id": "HCF-004",
    },
}


# ============================================================================
# Intervention Definitions
# ============================================================================

@dataclass
class Intervention:
    """A segment-specific intervention for a detected cycle."""

    cycle_type: CycleType
    segment: str
    intervention_type: str
    title: str
    description: str
    resources: list[str] = field(default_factory=list)
    urgency: str = "normal"            # "low", "normal", "high"
    when_to_escalate: str | None = None


# Segment-specific intervention strategies
INTERVENTIONS: dict[CycleType, dict[str, Intervention]] = {
    CycleType.META_SPIRALE: {
        "AD": Intervention(
            cycle_type=CycleType.META_SPIRALE,
            segment="AD",
            intervention_type="cognitive",
            title="Externalize the Overthinking",
            description=(
                "Meta-spirale (overthinking about overthinking) is common in ADHD. "
                "Try: (1) Write down the thought loop, (2) Set a 2-minute timer to decide, "
                "(3) Body double with someone present."
            ),
            resources=["The Wall of Awful model", "Body doubling"],
            urgency="normal",
        ),
        "AU": Intervention(
            cycle_type=CycleType.META_SPIRALE,
            segment="AU",
            intervention_type="cognitive",
            title="Predictability Reduces Rumination",
            description=(
                "For autistic minds, uncertainty fuels meta-thinking. "
                "Try: (1) Create a clear decision tree, (2) Schedule 'worry time' as a block, "
                "(3) Use literal checklists instead of open questions."
            ),
            resources=["Energy Accounting", "Structured decision frameworks"],
            urgency="normal",
        ),
        "AH": Intervention(
            cycle_type=CycleType.META_SPIRALE,
            segment="AH",
            intervention_type="cognitive",
            title="Bridge the Two Systems",
            description=(
                "AuDHD combines ADHD hyperanalysis with autism need for certainty. "
                "Try: (1) Name which channel is dominant right now, "
                "(2) Match strategy to channel (action for ADHD, structure for AU), "
                "(3) Use 'good enough' instead of 'perfect' criteria."
            ),
            resources=["Channel dominance check", "Flexible structure"],
            urgency="high",
        ),
    },
    CycleType.SHINY_OBJECT: {
        "AD": Intervention(
            cycle_type=CycleType.SHINY_OBJECT,
            segment="AD",
            intervention_type="motivation",
            title="Ride the Wave, Then Commit",
            description=(
                "Novelty-seeking is ADHD neurology, not a flaw. "
                "Try: (1) Use hyperfocus energy on new projects but set a 1-week 'commitment gate', "
                "(2) Create a 'parking lot' for interrupted ideas, "
                "(3) Pair with accountability for completion."
            ),
            resources=["Dopamine menu", "Body doubling for completion"],
            urgency="normal",
        ),
        "AU": Intervention(
            cycle_type=CycleType.SHINY_OBJECT,
            segment="AU",
            intervention_type="motivation",
            title="Special Interests Are Resources",
            description=(
                "Intense focus on interests is autistic strength, not distraction. "
                "Try: (1) Identify how new interest connects to goals, "
                "(2) Use interest as reward for completing less-exciting tasks, "
                "(3) Don't frame it as problem - redirect intentionally."
            ),
            resources=["Special interest leverage", "Interest-based rewards"],
            urgency="low",
        ),
        "AH": Intervention(
            cycle_type=CycleType.SHINY_OBJECT,
            segment="AH",
            intervention_type="motivation",
            title="Channel-Aware Interest Management",
            description=(
                "AuDHD has both novelty drive (ADHD) and depth focus (AU). "
                "Try: (1) During ADHD-dominant phase: quick wins, "
                "(2) During autism-dominant phase: deep work on single project, "
                "(3) Don't fight either - ride the channel."
            ),
            resources=["Channel dominance tracking", "Flexible structure"],
            urgency="normal",
        ),
    },
    CycleType.PERFECTIONISM: {
        "AD": Intervention(
            cycle_type=CycleType.PERFECTIONISM,
            segment="AD",
            intervention_type="emotional",
            title="Done Is Better Than Perfect",
            description=(
                "ADHD perfectionism comes from fear, not high standards. "
                "Try: (1) Set 'good enough' completion criteria before starting, "
                "(2) Use timers to force timeboxing, "
                "(3) Celebrate 'at least started' not just 'finished perfectly'."
            ),
            resources=["Timeboxing", "Shame-free completion tracking"],
            urgency="normal",
        ),
        "AU": Intervention(
            cycle_type=CycleType.PERFECTIONISM,
            segment="AU",
            intervention_type="emotional",
            title="Quality Through Structure",
            description=(
                "Autistic perfectionism often stems from high internal standards and rule-following. "
                "Try: (1) Define 'done' criteria explicitly in advance, "
                "(2) Build in review cycles instead of endless refinement, "
                "(3) Separate 'quality of work' from 'perfectionism anxiety'."
            ),
            resources=["Explicit done criteria", "Review scaffolding"],
            urgency="normal",
        ),
        "AH": Intervention(
            cycle_type=CycleType.PERFECTIONISM,
            segment="AH",
            intervention_type="emotional",
            title="Two Standards, Two Strategies",
            description=(
                "AuDHD perfectionism combines ADHD fear-based perfectionism with AU high standards. "
                "Try: (1) During ADHD mode: focus on starting, not finishing perfectly, "
                "(2) During AU mode: channel high standards into depth work, "
                "(3) Identify which perfectionism is active before intervening."
            ),
            resources=["Channel check", "Dual-strategy approach"],
            urgency="high",
        ),
    },
    CycleType.ISOLATION: {
        "AD": Intervention(
            cycle_type=CycleType.ISOLATION,
            segment="AD",
            intervention_type="social",
            title="Connection Reduces Burden",
            description=(
                "ADHD isolation often stems from shame, RSD, or overwhelm. "
                "Try: (1) Body doubling - just having someone present, "
                "(2) Online ADHD communities for understanding without judgment, "
                "(3) Low-effort connection: voice notes, short messages."
            ),
            resources=["Body doubling", "ADHD community support", "RSD awareness"],
            urgency="high",
        ),
        "AU": Intervention(
            cycle_type=CycleType.ISOLATION,
            segment="AU",
            intervention_type="social",
            title="Quality Over Quantity in Connection",
            description=(
                "Autistic isolation often comes from exhaustion, not disinterest. "
                "Try: (1) Identify which connection types recharge vs drain, "
                "(2) Connect with other autists who don't require masking, "
                "(3) Schedule specific connection times with clear parameters."
            ),
            resources=["Energy accounting", "Autism community", "Structured social time"],
            urgency="high",
        ),
        "AH": Intervention(
            cycle_type=CycleType.ISOLATION,
            segment="AH",
            intervention_type="social",
            title="Navigate the Connection Paradox",
            description=(
                "AuDHD often feels 'not enough' for both communities. "
                "Try: (1) Seek AuDHD-specific communities, "
                "(2) Accept that different channels need different connection types, "
                "(3) Don't let 'not fitting' stop you from reaching out."
            ),
            resources=["AuDHD communities", "Channel-appropriate connection"],
            urgency="high",
        ),
    },
    CycleType.FREE_WORK: {
        "AD": Intervention(
            cycle_type=CycleType.FREE_WORK,
            segment="AD",
            intervention_type="boundary",
            title="Value Your Attention",
            description=(
                "ADHD hyperfocus often goes to others' priorities. "
                "Try: (1) Track where your attention actually goes, "
                "(2) Block time for your own projects, "
                "(3) Learn to say no without over-explaining."
            ),
            resources=["Attention audit", "Priority boundaries"],
            urgency="normal",
        ),
        "AU": Intervention(
            cycle_type=CycleType.FREE_WORK,
            segment="AU",
            intervention_type="boundary",
            title="Protect Your Energy for Your Goals",
            description=(
                "Autistic people often exhaust themselves meeting others' expectations. "
                "Try: (1) Use energy accounting to see where energy goes, "
                "(2) Identify 'shoulds' that aren't actually required, "
                "(3) Practice saying no - it's a valid complete sentence."
            ),
            resources=["Energy accounting", "Boundary setting", "Should audit"],
            urgency="normal",
        ),
        "AH": Intervention(
            cycle_type=CycleType.FREE_WORK,
            segment="AH",
            intervention_type="boundary",
            title="Channel Your Energy Intentionally",
            description=(
                "AuDHD often gives energy away in both ADHD (people-pleasing from RSD) and AU (masking) ways. "
                "Try: (1) Check channel dominance before committing, "
                "(2) During AU mode: protect energy, say no, "
                "(3) During ADHD mode: channel novelty energy toward OWN projects."
            ),
            resources=["Channel check", "Energy allocation", "Spoon drawer"],
            urgency="high",
        ),
    },
}


# ============================================================================
# Signal Detection Configuration
# ============================================================================

# Signal thresholds for severity levels
SIGNAL_THRESHOLDS: dict[SignalName, tuple[float, float]] = {
    # AD Signals (0-1 scale)
    SignalName.MASKING_ESCALATION: (0.3, 0.7),
    SignalName.SENSORY_OVERLOAD_TRAJECTORY: (0.3, 0.7),
    SignalName.BURNOUT_EARLY_WARNING: (0.2, 0.5),
    SignalName.TIME_BLINDNESS_SEVERITY: (0.3, 0.7),
    SignalName.WAITING_MODE_FREQUENCY: (0.3, 0.7),
    SignalName.DEADLINE_DEPENDENCY: (0.3, 0.7),
    SignalName.EMOTIONAL_DYSREGULATION_INTENSITY: (0.3, 0.7),
    SignalName.RSD_ESCALATION: (0.3, 0.6),
    SignalName.SHAME_ACCUMULATION: (0.3, 0.7),

    # AU Signals
    SignalName.INERTIA_FREQUENCY: (0.3, 0.7),
    SignalName.ENERGY_DEPLETION_RATE: (0.3, 0.7),
    SignalName.SPOON_BUDGET_OVERSPEND: (0.3, 0.6),
    SignalName.CAPACITY_DECLINE_TREND: (0.2, 0.5),
    SignalName.SOCIAL_BATTERY_DRAIN: (0.3, 0.7),
    SignalName.ISOLATION_TREND: (0.3, 0.7),
    SignalName.TRANSITION_TAX: (0.3, 0.7),

    # AH Signals
    SignalName.DOUBLE_MASKING_COST: (0.3, 0.6),
    SignalName.CHANNEL_DOMINANCE_SHIFTS: (0.3, 0.7),
}


# ============================================================================
# Pattern Detection Service
# ============================================================================

class PatternDetectionService:
    """
    Detect destructive patterns in user behavior.

    This service analyzes user data to detect:
    1. Core Cycles (5 patterns): Meta-Spirale, Shiny Object, Perfectionism, Isolation, Free Work
    2. Daily Burden Signals (14 signals): Segment-specific indicators of strain

    Each detection includes confidence score and severity level,
    enabling targeted intervention selection.

    Usage:
        service = PatternDetectionService()
        cycles = await service.detect_cycles(user_id=123, recent_data={...})
        intervention = await service.get_intervention(cycle=detected_cycle, segment="AD")
        signal_score = await service.detect_signal(user_id=123, signal_name="masking_escalation")
    """

    def __init__(self) -> None:
        """Initialize the Pattern Detection Service."""
        # In production, this would connect to database/Redis
        self._cycle_history: dict[int, list[DetectedCycle]] = {}
        self._signal_history: dict[int, dict[SignalName, list[float]]] = {}

    async def detect_cycles(
        self,
        user_id: int,
        recent_data: dict[str, Any],
    ) -> list[DetectedCycle]:
        """
        Detect all 5 core destructive cycles from user data.

        Analyzes behavioral patterns to identify which cycles are active
        and at what severity level.

        Args:
            user_id: The user's unique identifier
            recent_data: Dictionary containing recent user data points:
                - task_completion_rate: float (0-1)
                - new_starts_count: int
                - abandoned_tasks_count: int
                - social_interactions_count: int
                - time_in_social: float (hours)
                - unpaid_work_hours: float
                - overthinking_indicators: list[str]
                - perfectionism_evidence: list[str]
                - isolation_evidence: list[str]
                - energy_trend: str ("improving", "stable", "declining")
                - completion_patterns: list[dict]
                - etc.

        Returns:
            List of DetectedCycle objects, one for each of the 5 core cycles.
            Severity will be NONE if the cycle is not detected.
        """
        detected_cycles: list[DetectedCycle] = []

        # Extract relevant data points with defaults
        task_completion_rate = recent_data.get("task_completion_rate", 0.5)
        new_starts = recent_data.get("new_starts_count", 0)
        abandoned_tasks = recent_data.get("abandoned_tasks_count", 0)
        social_interactions = recent_data.get("social_interactions_count", 0)
        unpaid_work_hours = recent_data.get("unpaid_work_hours", 0.0)
        overthinking_indicators = recent_data.get("overthinking_indicators", [])
        perfectionism_evidence = recent_data.get("perfectionism_evidence", [])
        isolation_evidence = recent_data.get("isolation_evidence", [])

        # 1. Detect META_SPIRALE (overthinking about overthinking)
        meta_spirale_severity = CycleSeverity.NONE
        if overthinking_indicators:
            if len(overthinking_indicators) >= 3:
                meta_spirale_severity = CycleSeverity.SEVERE
            elif len(overthinking_indicators) >= 1:
                meta_spirale_severity = CycleSeverity.EMERGING

        detected_cycles.append(DetectedCycle(
            cycle_type=CycleType.META_SPIRALE,
            severity=meta_spirale_severity,
            confidence=0.8 if meta_spirale_severity != CycleSeverity.NONE else 0.0,
            evidence=overthinking_indicators[:3],
            trend="stable",
        ))

        # 2. Detect SHINY_OBJECT (constantly starting new things)
        shiny_object_severity = CycleSeverity.NONE
        if new_starts > 0 and abandoned_tasks > 0:
            abandonment_ratio = abandoned_tasks / (new_starts + abandoned_tasks)
            if abandonment_ratio > 0.7:
                shiny_object_severity = CycleSeverity.SEVERE
            elif abandonment_ratio > 0.5:
                shiny_object_severity = CycleSeverity.ACTIVE
            elif abandonment_ratio > 0.3:
                shiny_object_severity = CycleSeverity.EMERGING

        detected_cycles.append(DetectedCycle(
            cycle_type=CycleType.SHINY_OBJECT,
            severity=shiny_object_severity,
            confidence=0.85 if shiny_object_severity != CycleSeverity.NONE else 0.0,
            evidence=[f"Started {new_starts} new, abandoned {abandoned_tasks}"],
            trend="stable",
        ))

        # 3. Detect PERFECTIONISM (never finishing due to standards)
        perfectionism_severity = CycleSeverity.NONE
        if perfectionism_evidence:
            if len(perfectionism_evidence) >= 3:
                perfectionism_severity = CycleSeverity.SEVERE
            elif len(perfectionism_evidence) >= 1:
                perfectionism_severity = CycleSeverity.EMERGING
        elif task_completion_rate < 0.3 and abandoned_tasks > 3:
            # Infer from behavior if explicit evidence missing
            perfectionism_severity = CycleSeverity.ACTIVE

        detected_cycles.append(DetectedCycle(
            cycle_type=CycleType.PERFECTIONISM,
            severity=perfectionism_severity,
            confidence=0.75 if perfectionism_severity != CycleSeverity.NONE else 0.0,
            evidence=perfectionism_evidence[:3],
            trend="stable",
        ))

        # 4. Detect ISOLATION (withdrawing from support)
        isolation_severity = CycleSeverity.NONE
        if isolation_evidence:
            if len(isolation_evidence) >= 3:
                isolation_severity = CycleSeverity.SEVERE
            elif len(isolation_evidence) >= 1:
                isolation_severity = CycleSeverity.EMERGING
        elif social_interactions < 2:  # Low social interaction
            isolation_severity = CycleSeverity.ACTIVE

        detected_cycles.append(DetectedCycle(
            cycle_type=CycleType.ISOLATION,
            severity=isolation_severity,
            confidence=0.8 if isolation_severity != CycleSeverity.NONE else 0.0,
            evidence=isolation_evidence[:3] + [f"Social interactions: {social_interactions}"],
            trend="stable",
        ))

        # 5. Detect FREE_WORK (unpaid labor consuming energy)
        free_work_severity = CycleSeverity.NONE
        if unpaid_work_hours > 0:
            if unpaid_work_hours > 20:
                free_work_severity = CycleSeverity.SEVERE
            elif unpaid_work_hours > 10:
                free_work_severity = CycleSeverity.ACTIVE
            elif unpaid_work_hours > 5:
                free_work_severity = CycleSeverity.EMERGING

        detected_cycles.append(DetectedCycle(
            cycle_type=CycleType.FREE_WORK,
            severity=free_work_severity,
            confidence=0.9 if free_work_severity != CycleSeverity.NONE else 0.0,
            evidence=[f"Unpaid work: {unpaid_work_hours} hours"],
            trend="stable",
        ))

        # Store history
        self._cycle_history[user_id] = detected_cycles

        return detected_cycles

    async def get_intervention(
        self,
        cycle: DetectedCycle,
        segment_context: SegmentContext,
    ) -> Intervention | None:
        """
        Return a segment-specific intervention for a detected cycle.

        Different segments require different approaches to the same cycle.
        Uses SegmentContext features to determine which intervention approach.

        Args:
            cycle: The detected cycle to get intervention for
            segment_context: The user's SegmentContext

        Returns:
            Intervention object tailored to the segment, or None if cycle is not active
        """
        # Don't intervene if cycle is not active
        if cycle.severity == CycleSeverity.NONE:
            return None

        # Derive intervention key from SegmentContext features
        features = segment_context.features
        if features.channel_dominance_enabled:
            intervention_key = "AH"
        elif features.routine_anchoring:
            intervention_key = "AU"
        elif features.icnu_enabled:
            intervention_key = "AD"
        else:
            # NT/CU fallback to AD-style interventions
            intervention_key = "AD"

        # Get intervention for cycle type and segment
        if cycle.cycle_type in INTERVENTIONS:
            segment_interventions = INTERVENTIONS[cycle.cycle_type]
            if intervention_key in segment_interventions:
                return segment_interventions[intervention_key]

        # Fallback: return AD intervention if segment-specific not found
        if cycle.cycle_type in INTERVENTIONS:
            return INTERVENTIONS[cycle.cycle_type].get("AD")

        return None

    async def detect_signal(
        self,
        user_id: int,
        signal_name: SignalName,
    ) -> float:
        """
        Detect a specific signal from the 14 Daily Burden signals.

        Returns a score (0.0 - 1.0) indicating the severity/presence
        of the signal in the user's recent data.

        Args:
            user_id: The user's unique identifier
            signal_name: The name of the signal to detect

        Returns:
            Signal intensity score (0.0 = not present, 1.0 = maximum)
        """
        # Get signal metadata
        metadata = SIGNAL_METADATA.get(signal_name)
        if not metadata:
            return 0.0

        # In production, this would query actual user data
        # For now, return 0.0 as placeholder
        # Real implementation would analyze:
        # - Activity patterns
        # - Energy logs
        # - Communication patterns
        # - Task completion data
        # - Self-reported data

        # Initialize history if needed
        if user_id not in self._signal_history:
            self._signal_history[user_id] = {}
        if signal_name not in self._signal_history[user_id]:
            self._signal_history[user_id][signal_name] = []

        # Default score (would be calculated from data in production)
        default_score = 0.0

        return default_score

    async def get_signal_severity(
        self,
        signal_name: SignalName,
        score: float,
    ) -> CycleSeverity:
        """
        Determine severity level from signal score.

        Args:
            signal_name: The signal being evaluated
            score: The calculated signal intensity (0-1)

        Returns:
            Severity level based on thresholds
        """
        thresholds = SIGNAL_THRESHOLDS.get(signal_name, (0.3, 0.7))

        if score >= thresholds[1]:
            return CycleSeverity.SEVERE
        elif score >= thresholds[0]:
            return CycleSeverity.ACTIVE
        elif score > 0:
            return CycleSeverity.EMERGING
        else:
            return CycleSeverity.NONE

    async def get_signals_for_segment(
        self,
        segment_context: SegmentContext,
    ) -> list[SignalName]:
        """
        Get all relevant signals for a segment based on SegmentContext.

        Uses SegmentContext.features to determine which signals are relevant:
        - For CU (Custom): returns all signals (user decides)
        - For NT (Neurotypical): returns empty list (minimal tracking)
        - For AD/AU/AH: returns signals based on applicable_segments metadata

        Args:
            segment_context: The user's SegmentContext

        Returns:
            List of SignalName values relevant to this segment
        """
        segment_code = segment_context.core.code

        # CU (Custom) gets all signals - user decides
        if segment_code == "CU":
            return list(SIGNAL_METADATA.keys())

        # NT (Neurotypical) gets minimal/no signals
        if segment_code == "NT":
            return []

        # For AD/AU/AH: filter by applicable_segments
        relevant_signals = []
        for signal, metadata in SIGNAL_METADATA.items():
            applicable_segments = metadata.get("applicable_segments", [])
            if segment_code in applicable_segments:
                relevant_signals.append(signal)

        return relevant_signals

    async def get_cycle_summary(
        self,
        user_id: int,
    ) -> dict[str, Any]:
        """
        Get a summary of all detected cycles for a user.

        Args:
            user_id: The user's unique identifier

        Returns:
            Dictionary with cycle detection summary
        """
        cycles = self._cycle_history.get(user_id, [])

        active_cycles = [
            {
                "cycle": c.cycle_type.value,
                "severity": c.severity.value,
                "confidence": c.confidence,
            }
            for c in cycles
            if c.severity != CycleSeverity.NONE
        ]

        return {
            "user_id": user_id,
            "total_cycles": len(cycles),
            "active_cycles": len(active_cycles),
            "cycles": active_cycles,
        }


# ============================================================================
# Module-level singleton for easy access
# ============================================================================

_pattern_detection_service: PatternDetectionService | None = None


def get_pattern_detection_service() -> PatternDetectionService:
    """
    Get the singleton PatternDetectionService instance.

    Returns:
        The global PatternDetectionService instance
    """
    global _pattern_detection_service
    if _pattern_detection_service is None:
        _pattern_detection_service = PatternDetectionService()
    return _pattern_detection_service
