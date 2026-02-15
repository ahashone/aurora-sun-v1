"""
Coherence Auditor for Aurora Agent.

Checks alignment between a user's vision, goals, and habits:
- Vision-Goal coherence: Do goals serve the vision?
- Goal-Habit coherence: Do habits support the goals?
- Vision-Habit coherence: Do daily actions align with long-term vision?
- Contradiction detection: Conflicting goals, habits that undermine goals
- Gap detection: Missing habits for goals, goals without vision alignment

The coherence auditor runs as part of the weekly cycle and produces
actionable insights for the user (always framed as proposals, never mandates).

Reference: ARCHITECTURE.md Section 5 (Aurora Agent - Coherence Auditor)
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.core.segment_context import SegmentContext

# Maximum number of users in the in-memory audit history cache
_AUDIT_HISTORY_MAXLEN = 1000

# Common stop words removed from keyword overlap scoring
_STOP_WORDS: frozenset[str] = frozenset(
    {"a", "the", "and", "or", "to", "for", "my", "i"}
)

# Coherence summary thresholds
_COHERENCE_HIGH_THRESHOLD = 0.8  # Vision/goals/habits well aligned
_COHERENCE_MODERATE_THRESHOLD = 0.5  # Moderate alignment

# Coherence sub-score weights (must sum to 1.0)
_WEIGHT_VISION_GOAL = 0.35
_WEIGHT_GOAL_HABIT = 0.40
_WEIGHT_VISION_HABIT = 0.25


class GapType(StrEnum):
    """Types of coherence gaps."""

    VISION_GOAL = "vision_goal"         # Goal doesn't serve vision
    GOAL_HABIT = "goal_habit"           # No habit supports this goal
    VISION_HABIT = "vision_habit"       # Habit doesn't align with vision
    ORPHAN_GOAL = "orphan_goal"         # Goal with no vision connection
    ORPHAN_HABIT = "orphan_habit"       # Habit with no goal connection
    MISSING_HABIT = "missing_habit"     # Goal needs a supporting habit


class ContradictionSeverity(StrEnum):
    """Severity of detected contradictions."""

    LOW = "low"           # Minor misalignment, may be intentional
    MEDIUM = "medium"     # Notable conflict worth surfacing
    HIGH = "high"         # Direct contradiction requiring attention


@dataclass
class Contradiction:
    """A detected contradiction between user intentions.

    Contradictions are conflicts between goals, habits, or
    the overall vision. They are surfaced as observations,
    never judgments.
    """

    contradiction_id: str = field(
        default_factory=lambda: uuid.uuid4().hex[:12]
    )
    item_a: str = ""       # First conflicting item
    item_b: str = ""       # Second conflicting item
    description: str = ""  # Human-readable description
    severity: ContradictionSeverity = ContradictionSeverity.LOW
    suggestion: str = ""   # Proposed resolution (always optional)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "contradiction_id": self.contradiction_id,
            "item_a": self.item_a,
            "item_b": self.item_b,
            "description": self.description,
            "severity": self.severity.value,
            "suggestion": self.suggestion,
            "metadata": self.metadata,
        }


@dataclass
class CoherenceGap:
    """A detected gap in the vision-goal-habit chain."""

    gap_id: str = field(
        default_factory=lambda: uuid.uuid4().hex[:12]
    )
    gap_type: GapType = GapType.ORPHAN_GOAL
    item: str = ""          # The item with the gap
    description: str = ""   # Human-readable description
    suggestion: str = ""    # Proposed action

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "gap_id": self.gap_id,
            "gap_type": self.gap_type.value,
            "item": self.item,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass
class CoherenceResult:
    """Result of a coherence audit.

    Contains scores, gaps, and contradictions.
    """

    user_id: int = 0
    coherence_ratio: float = 0.0  # 0.0-1.0 overall coherence
    vision_goal_score: float = 0.0
    goal_habit_score: float = 0.0
    vision_habit_score: float = 0.0
    gaps: list[CoherenceGap] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    total_items_audited: int = 0
    aligned_items: int = 0
    summary: str = ""
    audited_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "user_id": self.user_id,
            "coherence_ratio": self.coherence_ratio,
            "vision_goal_score": self.vision_goal_score,
            "goal_habit_score": self.goal_habit_score,
            "vision_habit_score": self.vision_habit_score,
            "gaps": [g.to_dict() for g in self.gaps],
            "contradictions": [c.to_dict() for c in self.contradictions],
            "total_items_audited": self.total_items_audited,
            "aligned_items": self.aligned_items,
            "summary": self.summary,
            "audited_at": self.audited_at,
            "metadata": self.metadata,
        }


class CoherenceAuditor:
    """Coherence Auditor for Aurora Agent.

    Checks alignment between vision, goals, and habits.
    Detects contradictions and gaps. Always proposes, never mandates.

    Usage:
        auditor = CoherenceAuditor()
        result = auditor.audit_coherence(
            user_id=1,
            segment_ctx=ctx,
            vision="Build a sustainable freelance business",
            goals=["Launch website", "Get 5 clients"],
            habits=["Morning planning", "Client outreach"],
        )
    """

    def __init__(self) -> None:
        """Initialize the coherence auditor."""
        # In-memory storage (production: PostgreSQL)
        # Bounded to _AUDIT_HISTORY_MAXLEN users to prevent unbounded growth
        self._audit_history: OrderedDict[int, list[CoherenceResult]] = OrderedDict()

    def audit_coherence(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
        vision: str = "",
        goals: list[str] | None = None,
        habits: list[str] | None = None,
        goal_habit_links: dict[str, list[str]] | None = None,
    ) -> CoherenceResult:
        """Run a full coherence audit.

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context
            vision: The user's declared vision
            goals: List of goal names
            habits: List of habit names
            goal_habit_links: Dict mapping goal_name -> list of supporting habits

        Returns:
            CoherenceResult with scores, gaps, and contradictions
        """
        goals = goals or []
        habits = habits or []
        goal_habit_links = goal_habit_links or {}

        # Calculate sub-scores
        vision_goal_score = self._score_vision_goal(vision, goals)
        goal_habit_score = self._score_goal_habit(goals, habits, goal_habit_links)
        vision_habit_score = self._score_vision_habit(vision, habits)

        # Detect gaps
        gaps = self._detect_gaps(vision, goals, habits, goal_habit_links)

        # Detect contradictions
        contradictions = self.find_contradictions(goals, habits)

        # Calculate overall coherence
        total_items = len(goals) + len(habits)
        aligned = self._count_aligned(
            goals, habits, goal_habit_links, vision
        )

        coherence_ratio = (
            aligned / total_items if total_items > 0 else 0.0
        )

        # Overall score is weighted average of sub-scores
        if vision and goals and habits:
            overall = (
                vision_goal_score * _WEIGHT_VISION_GOAL
                + goal_habit_score * _WEIGHT_GOAL_HABIT
                + vision_habit_score * _WEIGHT_VISION_HABIT
            )
            coherence_ratio = max(coherence_ratio, overall)

        summary = self._generate_summary(
            coherence_ratio, gaps, contradictions, segment_ctx
        )

        result = CoherenceResult(
            user_id=user_id,
            coherence_ratio=round(coherence_ratio, 4),
            vision_goal_score=round(vision_goal_score, 4),
            goal_habit_score=round(goal_habit_score, 4),
            vision_habit_score=round(vision_habit_score, 4),
            gaps=gaps,
            contradictions=contradictions,
            total_items_audited=total_items,
            aligned_items=aligned,
            summary=summary,
        )

        # Record audit
        self._record_audit(user_id, result)

        return result

    def find_contradictions(
        self,
        goals: list[str],
        habits: list[str],
    ) -> list[Contradiction]:
        """Find contradictions between goals and habits.

        In production, this would use semantic similarity
        and LLM-based reasoning. For now, uses heuristic rules.

        Args:
            goals: List of goal names
            habits: List of habit names

        Returns:
            List of detected Contradiction objects
        """
        contradictions: list[Contradiction] = []

        # Heuristic: check for opposing goals
        opposition_pairs = [
            ("reduce", "increase"),
            ("stop", "start"),
            ("less", "more"),
            ("avoid", "pursue"),
            ("simplify", "expand"),
        ]

        for i, goal_a in enumerate(goals):
            for goal_b in goals[i + 1 :]:
                for word_a, word_b in opposition_pairs:
                    a_lower = goal_a.lower()
                    b_lower = goal_b.lower()
                    if (
                        (word_a in a_lower and word_b in b_lower)
                        or (word_b in a_lower and word_a in b_lower)
                    ):
                        contradictions.append(
                            Contradiction(
                                item_a=goal_a,
                                item_b=goal_b,
                                description=(
                                    f"Goals '{goal_a}' and '{goal_b}' "
                                    "may be in conflict."
                                ),
                                severity=ContradictionSeverity.MEDIUM,
                                suggestion=(
                                    "Consider whether both goals can coexist, "
                                    "or if one should be prioritized."
                                ),
                            )
                        )

        return contradictions

    def calculate_coherence_ratio(
        self,
        aligned_items: int,
        total_items: int,
    ) -> float:
        """Calculate the coherence ratio.

        Args:
            aligned_items: Number of aligned items
            total_items: Total number of items audited

        Returns:
            Coherence ratio (0.0-1.0)
        """
        if total_items == 0:
            return 0.0
        return min(1.0, max(0.0, aligned_items / total_items))

    def get_audit_history(
        self, user_id: int
    ) -> list[CoherenceResult]:
        """Get audit history for a user.

        Args:
            user_id: The user's unique identifier

        Returns:
            List of CoherenceResult objects
        """
        return self._audit_history.get(user_id, [])

    def export_user_data(self, user_id: int) -> dict[str, Any]:
        """GDPR export for coherence data.

        Args:
            user_id: The user's unique identifier

        Returns:
            All coherence data for the user
        """
        history = self._audit_history.get(user_id, [])
        return {
            "coherence_audits": [r.to_dict() for r in history],
        }

    def delete_user_data(self, user_id: int) -> None:
        """GDPR delete for coherence data.

        Args:
            user_id: The user's unique identifier
        """
        self._audit_history.pop(user_id, None)

    @staticmethod
    def _score_keyword_alignment(
        reference: str, items: list[str]
    ) -> float:
        """Score alignment between a reference text and a list of items.

        Uses keyword overlap heuristic (stop words excluded).
        In production, this would use semantic similarity.

        Args:
            reference: The reference text (e.g., vision statement)
            items: List of items to compare against (e.g., goals or habits)

        Returns:
            Score 0.0-1.0 (fraction of items with keyword overlap)
        """
        if not reference or not items:
            return 0.0

        ref_words = set(reference.lower().split())
        aligned_count = 0
        for item in items:
            item_words = set(item.lower().split())
            overlap = ref_words & item_words
            overlap -= _STOP_WORDS
            if overlap:
                aligned_count += 1

        return aligned_count / len(items)

    def _score_vision_goal(
        self, vision: str, goals: list[str]
    ) -> float:
        """Score vision-goal alignment.

        Args:
            vision: The user's vision statement
            goals: List of goal names

        Returns:
            Score 0.0-1.0
        """
        return self._score_keyword_alignment(vision, goals)

    def _score_goal_habit(
        self,
        goals: list[str],
        habits: list[str],
        links: dict[str, list[str]],
    ) -> float:
        """Score goal-habit alignment.

        Goals with linked habits score higher than orphan goals.

        Args:
            goals: List of goal names
            habits: List of habit names
            links: Dict mapping goal_name -> list of supporting habits

        Returns:
            Score 0.0-1.0
        """
        if not goals:
            return 0.0

        linked_goals = 0
        for goal in goals:
            if goal in links and links[goal]:
                # Verify linked habits actually exist
                valid_links = [
                    h for h in links[goal] if h in habits
                ]
                if valid_links:
                    linked_goals += 1

        return linked_goals / len(goals)

    def _score_vision_habit(
        self, vision: str, habits: list[str]
    ) -> float:
        """Score vision-habit alignment.

        Args:
            vision: The user's vision statement
            habits: List of habit names

        Returns:
            Score 0.0-1.0
        """
        return self._score_keyword_alignment(vision, habits)

    def _detect_gaps(
        self,
        vision: str,
        goals: list[str],
        habits: list[str],
        links: dict[str, list[str]],
    ) -> list[CoherenceGap]:
        """Detect coherence gaps.

        Args:
            vision: The user's vision statement
            goals: List of goal names
            habits: List of habit names
            links: Dict mapping goal_name -> supporting habits

        Returns:
            List of CoherenceGap objects
        """
        gaps: list[CoherenceGap] = []

        # Check for orphan goals (no linked habits)
        for goal in goals:
            linked = links.get(goal, [])
            valid = [h for h in linked if h in habits]
            if not valid:
                gaps.append(
                    CoherenceGap(
                        gap_type=GapType.MISSING_HABIT,
                        item=goal,
                        description=(
                            f"Goal '{goal}' has no supporting habits."
                        ),
                        suggestion=(
                            f"Consider adding a daily or weekly habit "
                            f"that moves you toward '{goal}'."
                        ),
                    )
                )

        # Check for orphan habits (not linked to any goal)
        all_linked_habits: set[str] = set()
        for habit_list in links.values():
            all_linked_habits.update(habit_list)

        for habit in habits:
            if habit not in all_linked_habits:
                gaps.append(
                    CoherenceGap(
                        gap_type=GapType.ORPHAN_HABIT,
                        item=habit,
                        description=(
                            f"Habit '{habit}' is not linked to any goal."
                        ),
                        suggestion=(
                            f"Consider which goal '{habit}' supports, "
                            f"or whether it is still needed."
                        ),
                    )
                )

        return gaps

    def _count_aligned(
        self,
        goals: list[str],
        habits: list[str],
        links: dict[str, list[str]],
        vision: str,
    ) -> int:
        """Count aligned items.

        Args:
            goals: List of goal names
            habits: List of habit names
            links: Dict mapping goal_name -> supporting habits
            vision: The user's vision statement

        Returns:
            Number of aligned items
        """
        aligned = 0

        # Count goals linked to habits
        for goal in goals:
            linked = links.get(goal, [])
            valid = [h for h in linked if h in habits]
            if valid:
                aligned += 1

        # Count habits linked to goals
        all_linked: set[str] = set()
        for habit_list in links.values():
            all_linked.update(habit_list)
        for habit in habits:
            if habit in all_linked:
                aligned += 1

        return aligned

    def _generate_summary(
        self,
        ratio: float,
        gaps: list[CoherenceGap],
        contradictions: list[Contradiction],
        segment_ctx: SegmentContext,
    ) -> str:
        """Generate a human-readable summary.

        Args:
            ratio: Overall coherence ratio
            gaps: Detected gaps
            contradictions: Detected contradictions
            segment_ctx: The user's segment context

        Returns:
            Summary string
        """
        parts: list[str] = []

        if ratio >= _COHERENCE_HIGH_THRESHOLD:
            parts.append(
                "Your vision, goals, and habits are well aligned."
            )
        elif ratio >= _COHERENCE_MODERATE_THRESHOLD:
            parts.append(
                "There is moderate alignment between your vision, "
                "goals, and habits."
            )
        else:
            parts.append(
                "There are significant gaps between your vision, "
                "goals, and daily habits."
            )

        if gaps:
            parts.append(f"Found {len(gaps)} gap(s) to address.")

        if contradictions:
            parts.append(
                f"Found {len(contradictions)} potential contradiction(s)."
            )

        if not gaps and not contradictions:
            parts.append("No gaps or contradictions found.")

        return " ".join(parts)

    def _record_audit(
        self, user_id: int, result: CoherenceResult
    ) -> None:
        """Record an audit result (bounded LRU cache).

        Args:
            user_id: The user's unique identifier
            result: The audit result to record
        """
        if user_id not in self._audit_history:
            if len(self._audit_history) >= _AUDIT_HISTORY_MAXLEN:
                self._audit_history.popitem(last=False)
            self._audit_history[user_id] = []
        else:
            self._audit_history.move_to_end(user_id)
        self._audit_history[user_id].append(result)
