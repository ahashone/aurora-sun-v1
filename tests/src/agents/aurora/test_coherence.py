"""
Tests for the Coherence Auditor.

Covers:
- Vision-Goal-Habit coherence scoring
- Contradiction detection
- Gap detection (orphan goals, orphan habits, missing habits)
- Coherence ratio calculation
- Summary generation
- Audit history
- GDPR export/delete
"""

from __future__ import annotations

import pytest

from src.agents.aurora.coherence import (
    CoherenceAuditor,
    CoherenceGap,
    CoherenceResult,
    Contradiction,
    ContradictionSeverity,
    GapType,
)
from src.core.segment_context import SegmentContext


@pytest.fixture()
def auditor() -> CoherenceAuditor:
    """Create a CoherenceAuditor instance."""
    return CoherenceAuditor()


@pytest.fixture()
def nt_ctx() -> SegmentContext:
    return SegmentContext.from_code("NT")


@pytest.fixture()
def ad_ctx() -> SegmentContext:
    return SegmentContext.from_code("AD")


# ============================================================================
# Coherence audit tests
# ============================================================================


class TestAuditCoherence:
    def test_basic_audit(
        self, auditor: CoherenceAuditor, nt_ctx: SegmentContext
    ) -> None:
        result = auditor.audit_coherence(
            user_id=1,
            segment_ctx=nt_ctx,
            vision="Build a sustainable freelance business",
            goals=["Launch website", "Get 5 clients"],
            habits=["Morning planning", "Client outreach"],
            goal_habit_links={
                "Launch website": ["Morning planning"],
                "Get 5 clients": ["Client outreach"],
            },
        )
        assert isinstance(result, CoherenceResult)
        assert result.user_id == 1
        assert 0.0 <= result.coherence_ratio <= 1.0

    def test_perfect_coherence(
        self, auditor: CoherenceAuditor, nt_ctx: SegmentContext
    ) -> None:
        """All goals linked to habits, all habits linked to goals."""
        result = auditor.audit_coherence(
            user_id=1,
            segment_ctx=nt_ctx,
            vision="Be productive",
            goals=["Goal A"],
            habits=["Habit A"],
            goal_habit_links={"Goal A": ["Habit A"]},
        )
        assert result.goal_habit_score == 1.0
        assert len(result.gaps) == 0

    def test_no_data(
        self, auditor: CoherenceAuditor, nt_ctx: SegmentContext
    ) -> None:
        result = auditor.audit_coherence(
            user_id=1, segment_ctx=nt_ctx
        )
        assert result.coherence_ratio == 0.0
        assert result.total_items_audited == 0

    def test_goals_without_habits(
        self, auditor: CoherenceAuditor, nt_ctx: SegmentContext
    ) -> None:
        result = auditor.audit_coherence(
            user_id=1,
            segment_ctx=nt_ctx,
            vision="Success",
            goals=["Goal A", "Goal B"],
            habits=[],
        )
        assert result.goal_habit_score == 0.0
        # Should detect missing habits
        gap_types = {g.gap_type for g in result.gaps}
        assert GapType.MISSING_HABIT in gap_types

    def test_orphan_habits_detected(
        self, auditor: CoherenceAuditor, nt_ctx: SegmentContext
    ) -> None:
        result = auditor.audit_coherence(
            user_id=1,
            segment_ctx=nt_ctx,
            goals=["Goal A"],
            habits=["Habit A", "Orphan Habit"],
            goal_habit_links={"Goal A": ["Habit A"]},
        )
        orphan_gaps = [
            g for g in result.gaps if g.gap_type == GapType.ORPHAN_HABIT
        ]
        assert len(orphan_gaps) == 1
        assert orphan_gaps[0].item == "Orphan Habit"

    def test_missing_habits_detected(
        self, auditor: CoherenceAuditor, nt_ctx: SegmentContext
    ) -> None:
        result = auditor.audit_coherence(
            user_id=1,
            segment_ctx=nt_ctx,
            goals=["Goal without habit"],
            habits=["Some habit"],
            goal_habit_links={},
        )
        missing_gaps = [
            g for g in result.gaps if g.gap_type == GapType.MISSING_HABIT
        ]
        assert len(missing_gaps) == 1

    def test_audit_records_history(
        self, auditor: CoherenceAuditor, nt_ctx: SegmentContext
    ) -> None:
        auditor.audit_coherence(user_id=1, segment_ctx=nt_ctx)
        auditor.audit_coherence(user_id=1, segment_ctx=nt_ctx)
        history = auditor.get_audit_history(user_id=1)
        assert len(history) == 2

    def test_audit_result_to_dict(
        self, auditor: CoherenceAuditor, nt_ctx: SegmentContext
    ) -> None:
        result = auditor.audit_coherence(
            user_id=1, segment_ctx=nt_ctx,
            goals=["A"], habits=["B"],
        )
        d = result.to_dict()
        assert "coherence_ratio" in d
        assert "gaps" in d
        assert "contradictions" in d


# ============================================================================
# Contradiction detection tests
# ============================================================================


class TestFindContradictions:
    def test_no_contradictions(self, auditor: CoherenceAuditor) -> None:
        contradictions = auditor.find_contradictions(
            goals=["Build website", "Learn marketing"],
            habits=["Code daily", "Read marketing books"],
        )
        assert len(contradictions) == 0

    def test_opposing_goals_detected(self, auditor: CoherenceAuditor) -> None:
        contradictions = auditor.find_contradictions(
            goals=["Reduce screen time", "Increase social media presence"],
            habits=[],
        )
        assert len(contradictions) >= 1
        assert contradictions[0].severity == ContradictionSeverity.MEDIUM

    def test_stop_start_contradiction(self, auditor: CoherenceAuditor) -> None:
        contradictions = auditor.find_contradictions(
            goals=["Stop procrastinating", "Start more projects"],
            habits=[],
        )
        assert len(contradictions) >= 1

    def test_contradiction_to_dict(self, auditor: CoherenceAuditor) -> None:
        c = Contradiction(
            item_a="A", item_b="B", description="Conflict",
            severity=ContradictionSeverity.HIGH,
        )
        d = c.to_dict()
        assert d["severity"] == "high"
        assert d["item_a"] == "A"

    def test_contradiction_has_suggestion(self, auditor: CoherenceAuditor) -> None:
        contradictions = auditor.find_contradictions(
            goals=["Reduce workload", "Increase productivity"],
            habits=[],
        )
        if contradictions:
            assert contradictions[0].suggestion != ""


# ============================================================================
# Coherence ratio calculation tests
# ============================================================================


class TestCoherenceRatio:
    def test_perfect_ratio(self, auditor: CoherenceAuditor) -> None:
        ratio = auditor.calculate_coherence_ratio(10, 10)
        assert ratio == 1.0

    def test_zero_ratio(self, auditor: CoherenceAuditor) -> None:
        ratio = auditor.calculate_coherence_ratio(0, 10)
        assert ratio == 0.0

    def test_empty_ratio(self, auditor: CoherenceAuditor) -> None:
        ratio = auditor.calculate_coherence_ratio(0, 0)
        assert ratio == 0.0

    def test_partial_ratio(self, auditor: CoherenceAuditor) -> None:
        ratio = auditor.calculate_coherence_ratio(5, 10)
        assert ratio == 0.5

    def test_ratio_capped_at_1(self, auditor: CoherenceAuditor) -> None:
        ratio = auditor.calculate_coherence_ratio(15, 10)
        assert ratio == 1.0


# ============================================================================
# Summary generation tests
# ============================================================================


class TestSummary:
    def test_high_coherence_summary(
        self, auditor: CoherenceAuditor, nt_ctx: SegmentContext
    ) -> None:
        result = auditor.audit_coherence(
            user_id=1,
            segment_ctx=nt_ctx,
            vision="Be productive",
            goals=["Goal"],
            habits=["Habit"],
            goal_habit_links={"Goal": ["Habit"]},
        )
        assert "well aligned" in result.summary or "aligned" in result.summary.lower()

    def test_low_coherence_summary(
        self, auditor: CoherenceAuditor, nt_ctx: SegmentContext
    ) -> None:
        result = auditor.audit_coherence(
            user_id=1,
            segment_ctx=nt_ctx,
            goals=["Goal A", "Goal B", "Goal C"],
            habits=["Unlinked habit"],
        )
        assert "gap" in result.summary.lower() or "significant" in result.summary.lower()


# ============================================================================
# Gap dataclass tests
# ============================================================================


class TestCoherenceGap:
    def test_gap_to_dict(self) -> None:
        gap = CoherenceGap(
            gap_type=GapType.ORPHAN_HABIT,
            item="Morning walk",
            description="Not linked",
            suggestion="Link it",
        )
        d = gap.to_dict()
        assert d["gap_type"] == "orphan_habit"
        assert d["item"] == "Morning walk"


# ============================================================================
# GDPR tests
# ============================================================================


class TestCoherenceGDPR:
    def test_export(
        self, auditor: CoherenceAuditor, nt_ctx: SegmentContext
    ) -> None:
        auditor.audit_coherence(user_id=1, segment_ctx=nt_ctx)
        data = auditor.export_user_data(user_id=1)
        assert "coherence_audits" in data
        assert len(data["coherence_audits"]) == 1

    def test_delete(
        self, auditor: CoherenceAuditor, nt_ctx: SegmentContext
    ) -> None:
        auditor.audit_coherence(user_id=1, segment_ctx=nt_ctx)
        auditor.delete_user_data(user_id=1)
        data = auditor.export_user_data(user_id=1)
        assert data["coherence_audits"] == []

    def test_export_empty(self, auditor: CoherenceAuditor) -> None:
        data = auditor.export_user_data(user_id=999)
        assert data["coherence_audits"] == []
