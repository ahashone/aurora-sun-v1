"""
Tests for the Proactive Engine.

Covers:
- ReadinessScore calculation
- Weekly impulse limit (max 3)
- Boom-bust detection for ADHD (burnout_model = "boom_bust")
- Admin-approved impulse types
- Impulse queueing and delivery
- Timing and energy factors
- Segment-specific behavior
- GDPR export/delete
"""

from __future__ import annotations

import pytest

from src.agents.aurora.proactive import (
    MAX_IMPULSES_PER_WEEK,
    ImpulseType,
    ProactiveEngine,
    ProactiveImpulse,
    ReadinessScore,
)
from src.core.segment_context import SegmentContext


@pytest.fixture()
def engine() -> ProactiveEngine:
    """Create a ProactiveEngine instance."""
    return ProactiveEngine()


@pytest.fixture()
def ad_ctx() -> SegmentContext:
    return SegmentContext.from_code("AD")


@pytest.fixture()
def au_ctx() -> SegmentContext:
    return SegmentContext.from_code("AU")


@pytest.fixture()
def ah_ctx() -> SegmentContext:
    return SegmentContext.from_code("AH")


@pytest.fixture()
def nt_ctx() -> SegmentContext:
    return SegmentContext.from_code("NT")


# ============================================================================
# ReadinessScore tests
# ============================================================================


class TestReadinessScore:
    def test_default_score(self) -> None:
        score = ReadinessScore()
        assert score.score == 0.0
        assert not score.should_send

    def test_to_dict(self) -> None:
        score = ReadinessScore(score=0.7, should_send=True, reason="Ready")
        d = score.to_dict()
        assert d["score"] == 0.7
        assert d["should_send"] is True


# ============================================================================
# calculate_readiness tests
# ============================================================================


class TestCalculateReadiness:
    def test_good_conditions(
        self, engine: ProactiveEngine, nt_ctx: SegmentContext
    ) -> None:
        """Good energy, moderate engagement, reasonable timing."""
        readiness = engine.calculate_readiness(
            user_id=1,
            segment_ctx=nt_ctx,
            current_energy=0.7,
            hours_since_last_interaction=6.0,
            interactions_this_week=5,
            current_hour=14,
        )
        assert readiness.should_send is True
        assert readiness.score > 0.45

    def test_night_time_reduces_readiness(
        self, engine: ProactiveEngine, nt_ctx: SegmentContext
    ) -> None:
        """Late night should block impulses."""
        readiness = engine.calculate_readiness(
            user_id=1,
            segment_ctx=nt_ctx,
            current_energy=0.8,
            hours_since_last_interaction=6.0,
            interactions_this_week=5,
            current_hour=23,
        )
        assert readiness.should_send is False

    def test_early_morning_reduces_readiness(
        self, engine: ProactiveEngine, nt_ctx: SegmentContext
    ) -> None:
        readiness = engine.calculate_readiness(
            user_id=1,
            segment_ctx=nt_ctx,
            current_energy=0.8,
            hours_since_last_interaction=6.0,
            interactions_this_week=5,
            current_hour=3,
        )
        assert readiness.should_send is False

    def test_very_recent_interaction_reduces(
        self, engine: ProactiveEngine, nt_ctx: SegmentContext
    ) -> None:
        readiness = engine.calculate_readiness(
            user_id=1,
            segment_ctx=nt_ctx,
            current_energy=0.7,
            hours_since_last_interaction=0.5,
            interactions_this_week=5,
            current_hour=14,
        )
        # Very recent interaction = low timing factor
        assert readiness.timing_factor < 0.2

    def test_low_energy_reduces_readiness(
        self, engine: ProactiveEngine, nt_ctx: SegmentContext
    ) -> None:
        readiness = engine.calculate_readiness(
            user_id=1,
            segment_ctx=nt_ctx,
            current_energy=0.1,
            hours_since_last_interaction=6.0,
            interactions_this_week=5,
            current_hour=14,
        )
        assert readiness.energy_factor == 0.1

    def test_weekly_limit_blocks(
        self, engine: ProactiveEngine, nt_ctx: SegmentContext
    ) -> None:
        """After 3 deliveries this week, should not send more."""
        # Simulate 3 deliveries
        for i in range(3):
            impulse = engine.queue_impulse(
                user_id=1,
                impulse_type=ImpulseType.ENERGY_REMINDER,
                content=f"Reminder {i}",
            )
            assert impulse is not None
            engine.deliver_impulse(1, impulse.impulse_id)

        readiness = engine.calculate_readiness(
            user_id=1,
            segment_ctx=nt_ctx,
            current_energy=0.9,
            hours_since_last_interaction=6.0,
            interactions_this_week=5,
            current_hour=14,
        )
        assert readiness.should_send is False
        assert "Weekly limit" in readiness.reason

    def test_boom_bust_detection_adhd(
        self, engine: ProactiveEngine, ad_ctx: SegmentContext
    ) -> None:
        """ADHD users: high energy + high activity = boom-bust risk."""
        readiness = engine.calculate_readiness(
            user_id=1,
            segment_ctx=ad_ctx,
            current_energy=0.9,
            hours_since_last_interaction=6.0,
            interactions_this_week=15,
            current_hour=14,
        )
        assert readiness.boom_bust_risk >= 0.5

    def test_no_boom_bust_risk_autism(
        self, engine: ProactiveEngine, au_ctx: SegmentContext
    ) -> None:
        """Autism users: no boom-bust model."""
        readiness = engine.calculate_readiness(
            user_id=1,
            segment_ctx=au_ctx,
            current_energy=0.9,
            hours_since_last_interaction=6.0,
            interactions_this_week=15,
            current_hour=14,
        )
        assert readiness.boom_bust_risk == 0.0

    def test_partial_boom_bust_audhd(
        self, engine: ProactiveEngine, ah_ctx: SegmentContext
    ) -> None:
        """AuDHD: partial boom-bust risk from three_type burnout model."""
        readiness = engine.calculate_readiness(
            user_id=1,
            segment_ctx=ah_ctx,
            current_energy=0.9,
            hours_since_last_interaction=6.0,
            interactions_this_week=15,
            current_hour=14,
        )
        assert readiness.boom_bust_risk > 0.0


# ============================================================================
# should_send_impulse tests
# ============================================================================


class TestShouldSendImpulse:
    def test_should_send_true(
        self, engine: ProactiveEngine, nt_ctx: SegmentContext
    ) -> None:
        result = engine.should_send_impulse(
            user_id=1,
            segment_ctx=nt_ctx,
            current_energy=0.7,
            hours_since_last_interaction=8.0,
            interactions_this_week=5,
            current_hour=14,
        )
        assert result is True

    def test_should_send_false_night(
        self, engine: ProactiveEngine, nt_ctx: SegmentContext
    ) -> None:
        result = engine.should_send_impulse(
            user_id=1,
            segment_ctx=nt_ctx,
            current_energy=0.7,
            hours_since_last_interaction=8.0,
            interactions_this_week=5,
            current_hour=2,
        )
        assert result is False


# ============================================================================
# Impulse queue tests
# ============================================================================


class TestImpulseQueue:
    def test_queue_approved_type(self, engine: ProactiveEngine) -> None:
        impulse = engine.queue_impulse(
            user_id=1,
            impulse_type=ImpulseType.ENERGY_REMINDER,
            content="How is your energy?",
        )
        assert impulse is not None
        assert impulse.impulse_type == ImpulseType.ENERGY_REMINDER

    def test_queue_unapproved_type(self, engine: ProactiveEngine) -> None:
        """Non-approved types should be rejected."""
        # BURNOUT_WARNING is not in default approved types
        engine_restricted = ProactiveEngine(
            approved_types=frozenset({ImpulseType.ENERGY_REMINDER})
        )
        impulse = engine_restricted.queue_impulse(
            user_id=1,
            impulse_type=ImpulseType.BURNOUT_WARNING,
            content="Warning",
        )
        assert impulse is None

    def test_get_pending_sorted_by_priority(
        self, engine: ProactiveEngine
    ) -> None:
        engine.queue_impulse(1, ImpulseType.ENERGY_REMINDER, "Low", priority=1)
        engine.queue_impulse(1, ImpulseType.VISION_REFRESHER, "High", priority=5)
        engine.queue_impulse(1, ImpulseType.GROWTH_INSIGHT, "Medium", priority=3)
        pending = engine.get_pending_impulses(1)
        assert len(pending) == 3
        assert pending[0].priority == 5
        assert pending[1].priority == 3
        assert pending[2].priority == 1

    def test_deliver_impulse(self, engine: ProactiveEngine) -> None:
        impulse = engine.queue_impulse(
            1, ImpulseType.ENERGY_REMINDER, "Test"
        )
        assert impulse is not None
        delivered = engine.deliver_impulse(1, impulse.impulse_id)
        assert delivered is not None
        assert delivered.delivered_at is not None

    def test_deliver_removes_from_pending(
        self, engine: ProactiveEngine
    ) -> None:
        impulse = engine.queue_impulse(
            1, ImpulseType.ENERGY_REMINDER, "Test"
        )
        assert impulse is not None
        engine.deliver_impulse(1, impulse.impulse_id)
        pending = engine.get_pending_impulses(1)
        assert len(pending) == 0

    def test_deliver_nonexistent(self, engine: ProactiveEngine) -> None:
        result = engine.deliver_impulse(1, "nonexistent")
        assert result is None

    def test_priority_clamped(self, engine: ProactiveEngine) -> None:
        impulse = engine.queue_impulse(
            1, ImpulseType.ENERGY_REMINDER, "Test", priority=10
        )
        assert impulse is not None
        assert impulse.priority == 5

    def test_priority_clamped_low(self, engine: ProactiveEngine) -> None:
        impulse = engine.queue_impulse(
            1, ImpulseType.ENERGY_REMINDER, "Test", priority=-5
        )
        assert impulse is not None
        assert impulse.priority == 1


# ============================================================================
# Admin-approved types tests
# ============================================================================


class TestApprovedTypes:
    def test_default_approved_types(self, engine: ProactiveEngine) -> None:
        approved = engine.get_approved_types()
        assert ImpulseType.ENERGY_REMINDER in approved
        assert ImpulseType.VISION_REFRESHER in approved
        assert ImpulseType.MILESTONE_CELEBRATION in approved

    def test_custom_approved_types(self) -> None:
        custom = frozenset({ImpulseType.PATTERN_ALERT})
        engine = ProactiveEngine(approved_types=custom)
        assert ImpulseType.PATTERN_ALERT in engine.get_approved_types()
        assert ImpulseType.ENERGY_REMINDER not in engine.get_approved_types()

    def test_max_impulses_per_week_constant(self) -> None:
        assert MAX_IMPULSES_PER_WEEK == 3


# ============================================================================
# ProactiveImpulse tests
# ============================================================================


class TestProactiveImpulse:
    def test_to_dict(self) -> None:
        impulse = ProactiveImpulse(
            user_id=1,
            impulse_type=ImpulseType.GROWTH_INSIGHT,
            content="You grew!",
        )
        d = impulse.to_dict()
        assert d["impulse_type"] == "growth_insight"
        assert d["content"] == "You grew!"
        assert d["delivered_at"] is None


# ============================================================================
# GDPR tests
# ============================================================================


class TestProactiveGDPR:
    def test_export(self, engine: ProactiveEngine) -> None:
        engine.queue_impulse(1, ImpulseType.ENERGY_REMINDER, "Test")
        data = engine.export_user_data(1)
        assert "impulse_queue" in data
        assert len(data["impulse_queue"]) == 1

    def test_delete(self, engine: ProactiveEngine) -> None:
        engine.queue_impulse(1, ImpulseType.ENERGY_REMINDER, "Test")
        engine.delete_user_data(1)
        data = engine.export_user_data(1)
        assert data["impulse_queue"] == []
        assert data["delivery_log"] == []

    def test_export_empty(self, engine: ProactiveEngine) -> None:
        data = engine.export_user_data(999)
        assert data["impulse_queue"] == []
        assert data["delivery_log"] == []
