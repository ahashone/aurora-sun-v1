"""
Aurora Agent for Aurora Sun V1.

The Aurora Agent is the synthesis intelligence layer:
- Weekly cycle: Gather -> Assess -> Synthesize -> Recommend
- Narrative Engine: Story arcs, chapters, daily notes, milestones
- Growth Tracker: 5-dimension trajectory scoring with 3-window comparison
- Milestone Detection: Deterministic detection with segment-specific thresholds
- Coherence Auditor: Vision-Goal-Habit alignment checking
- Proactive Engine: Readiness-based impulse delivery (max 3/week)

Reference: ARCHITECTURE.md Section 5 (Aurora Agent)
"""

from __future__ import annotations

from .agent import AuroraAgent, AuroraState, WorkflowStep
from .coherence import CoherenceAuditor, CoherenceResult, Contradiction, GapType
from .growth import GrowthSummary, GrowthTracker, TrajectoryScore, WindowComparison
from .milestones import (
    MilestoneDetector,
    MilestoneEvent,
    MilestoneType,
)
from .narrative import Chapter, DailyNote, MilestoneCard, NarrativeEngine, StoryArc
from .proactive import ImpulseType, ProactiveEngine, ProactiveImpulse, ReadinessScore

__all__ = [
    # Agent
    "AuroraAgent",
    "AuroraState",
    "WorkflowStep",
    # Narrative
    "NarrativeEngine",
    "StoryArc",
    "Chapter",
    "DailyNote",
    "MilestoneCard",
    # Growth
    "GrowthTracker",
    "TrajectoryScore",
    "WindowComparison",
    "GrowthSummary",
    # Milestones
    "MilestoneDetector",
    "MilestoneEvent",
    "MilestoneType",
    # Coherence
    "CoherenceAuditor",
    "CoherenceResult",
    "Contradiction",
    "GapType",
    # Proactive
    "ProactiveEngine",
    "ReadinessScore",
    "ProactiveImpulse",
    "ImpulseType",
]
