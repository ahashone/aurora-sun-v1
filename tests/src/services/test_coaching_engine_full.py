"""
Tests for the Full Coaching Engine.

Covers:
- Coach method (full workflow)
- Intent routing
- Context enrichment
- 4-tier fallback (optimized artifact -> dspy -> pydantic_ai -> placeholder)
- Segment-specific coaching signatures (AD, AU, AH, NT, CU)
- Memory storage
- GDPR export/delete
"""

from __future__ import annotations

import pytest

from src.core.segment_context import SegmentContext
from src.services.coaching_engine_full import (
    CoachingContext,
    CoachingIntent,
    CoachingResult,
    CoachingStep,
    CoachingTier,
    FullCoachingEngine,
)


@pytest.fixture()
def engine() -> FullCoachingEngine:
    """Create a FullCoachingEngine instance."""
    return FullCoachingEngine()


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


@pytest.fixture()
def cu_ctx() -> SegmentContext:
    return SegmentContext.from_code("CU")


# ============================================================================
# Coach method (full workflow) tests
# ============================================================================


class TestCoach:
    @pytest.mark.asyncio()
    async def test_coach_basic(
        self, engine: FullCoachingEngine, nt_ctx: SegmentContext
    ) -> None:
        result = await engine.coach(
            user_id=1,
            message="I need help planning my day",
            segment_ctx=nt_ctx,
        )
        assert isinstance(result, CoachingResult)
        assert result.text != ""
        assert result.step_completed == CoachingStep.END

    @pytest.mark.asyncio()
    async def test_coach_stuck_intent(
        self, engine: FullCoachingEngine, nt_ctx: SegmentContext
    ) -> None:
        result = await engine.coach(
            user_id=1,
            message="I'm stuck and can't start anything",
            segment_ctx=nt_ctx,
        )
        assert result.intent == CoachingIntent.STUCK

    @pytest.mark.asyncio()
    async def test_coach_planning_intent(
        self, engine: FullCoachingEngine, nt_ctx: SegmentContext
    ) -> None:
        result = await engine.coach(
            user_id=1,
            message="Help me plan my priorities",
            segment_ctx=nt_ctx,
        )
        assert result.intent == CoachingIntent.PLANNING

    @pytest.mark.asyncio()
    async def test_coach_reflection_intent(
        self, engine: FullCoachingEngine, nt_ctx: SegmentContext
    ) -> None:
        result = await engine.coach(
            user_id=1,
            message="Let me review how my day went",
            segment_ctx=nt_ctx,
        )
        assert result.intent == CoachingIntent.REFLECTION

    @pytest.mark.asyncio()
    async def test_coach_energy_intent(
        self, engine: FullCoachingEngine, nt_ctx: SegmentContext
    ) -> None:
        result = await engine.coach(
            user_id=1,
            message="I'm feeling exhausted and tired",
            segment_ctx=nt_ctx,
        )
        assert result.intent == CoachingIntent.ENERGY_CHECK

    @pytest.mark.asyncio()
    async def test_coach_stores_memory(
        self, engine: FullCoachingEngine, nt_ctx: SegmentContext
    ) -> None:
        result = await engine.coach(user_id=1, message="Test", segment_ctx=nt_ctx)
        assert result is not None
        data = engine.export_user_data(1)
        assert len(data["coaching_interactions"]) == 1

    @pytest.mark.asyncio()
    async def test_coach_context_enriched(
        self, engine: FullCoachingEngine, nt_ctx: SegmentContext
    ) -> None:
        result = await engine.coach(
            user_id=1, message="Hello", segment_ctx=nt_ctx
        )
        assert result.context_enriched is True
        assert result.knowledge_applied is True
        assert result.memory_stored is True


# ============================================================================
# Intent routing tests
# ============================================================================


class TestRouteContext:
    def test_route_stuck(self, engine: FullCoachingEngine) -> None:
        ctx = CoachingContext(message="I'm stuck and frozen")
        ctx = engine.route_context(ctx)
        assert ctx.intent == CoachingIntent.STUCK

    def test_route_planning(self, engine: FullCoachingEngine) -> None:
        ctx = CoachingContext(message="Help me plan today")
        ctx = engine.route_context(ctx)
        assert ctx.intent == CoachingIntent.PLANNING

    def test_route_reflection(self, engine: FullCoachingEngine) -> None:
        ctx = CoachingContext(message="Let me reflect on what I learned")
        ctx = engine.route_context(ctx)
        assert ctx.intent == CoachingIntent.REFLECTION

    def test_route_motivation(self, engine: FullCoachingEngine) -> None:
        ctx = CoachingContext(message="I need some motivation")
        ctx = engine.route_context(ctx)
        assert ctx.intent == CoachingIntent.MOTIVATION

    def test_route_accountability(self, engine: FullCoachingEngine) -> None:
        ctx = CoachingContext(message="Check my progress")
        ctx = engine.route_context(ctx)
        assert ctx.intent == CoachingIntent.ACCOUNTABILITY

    def test_route_energy(self, engine: FullCoachingEngine) -> None:
        ctx = CoachingContext(message="I'm exhausted and have no energy")
        ctx = engine.route_context(ctx)
        assert ctx.intent == CoachingIntent.ENERGY_CHECK

    def test_route_general(self, engine: FullCoachingEngine) -> None:
        ctx = CoachingContext(message="Hello world")
        ctx = engine.route_context(ctx)
        assert ctx.intent == CoachingIntent.GENERAL

    def test_route_case_insensitive(self, engine: FullCoachingEngine) -> None:
        ctx = CoachingContext(message="I'M STUCK!")
        ctx = engine.route_context(ctx)
        assert ctx.intent == CoachingIntent.STUCK


# ============================================================================
# Context enrichment tests
# ============================================================================


class TestEnrichContext:
    def test_enrich_adds_metadata(
        self, engine: FullCoachingEngine, nt_ctx: SegmentContext
    ) -> None:
        ctx = CoachingContext(
            message="Test", segment_ctx=nt_ctx
        )
        ctx = engine.enrich_context(ctx)
        assert "burnout_model" in ctx.metadata
        assert "inertia_type" in ctx.metadata

    def test_enrich_adhd_metadata(
        self, engine: FullCoachingEngine, ad_ctx: SegmentContext
    ) -> None:
        ctx = CoachingContext(
            message="Test", segment_ctx=ad_ctx
        )
        ctx = engine.enrich_context(ctx)
        assert ctx.metadata["burnout_model"] == "boom_bust"
        assert ctx.metadata["inertia_type"] == "activation_deficit"

    def test_enrich_autism_metadata(
        self, engine: FullCoachingEngine, au_ctx: SegmentContext
    ) -> None:
        ctx = CoachingContext(
            message="Test", segment_ctx=au_ctx
        )
        ctx = engine.enrich_context(ctx)
        assert ctx.metadata["burnout_model"] == "overload_shutdown"
        assert ctx.metadata["sensory_accumulation"] is True

    def test_enrich_no_segment(
        self, engine: FullCoachingEngine
    ) -> None:
        ctx = CoachingContext(message="Test")
        ctx = engine.enrich_context(ctx)
        assert "burnout_model" not in ctx.metadata


# ============================================================================
# 4-tier fallback tests
# ============================================================================


class TestFallbackTiers:
    @pytest.mark.asyncio()
    async def test_tier1_optimized_artifact(
        self, engine: FullCoachingEngine, nt_ctx: SegmentContext
    ) -> None:
        """Tier 1 should work for all segment/intent combos."""
        ctx = CoachingContext(
            message="stuck", segment_ctx=nt_ctx,
            intent=CoachingIntent.STUCK,
        )
        result = CoachingResult()
        result = await engine.generate_coaching_response(ctx, result)
        assert result.tier_used == CoachingTier.OPTIMIZED_ARTIFACT
        assert result.text != ""

    @pytest.mark.asyncio()
    async def test_tier4_placeholder_fallback(
        self, engine: FullCoachingEngine
    ) -> None:
        """Without segment context, falls to placeholder (tier 4)."""
        ctx = CoachingContext(
            message="stuck", intent=CoachingIntent.STUCK
        )
        result = CoachingResult()
        result = await engine.generate_coaching_response(ctx, result)
        assert result.tier_used == CoachingTier.PLACEHOLDER
        assert result.text != ""


# ============================================================================
# Segment-specific coaching signatures tests
# ============================================================================


class TestSegmentSignatures:
    @pytest.mark.asyncio()
    async def test_adhd_stuck_signature(
        self, engine: FullCoachingEngine, ad_ctx: SegmentContext
    ) -> None:
        result = await engine.coach(
            user_id=1, message="I'm stuck", segment_ctx=ad_ctx
        )
        # ADHD stuck response should mention spark, sprint, or interest
        assert any(word in result.text.lower() for word in ["spark", "sprint", "interesting", "novel"])

    @pytest.mark.asyncio()
    async def test_autism_stuck_signature(
        self, engine: FullCoachingEngine, au_ctx: SegmentContext
    ) -> None:
        result = await engine.coach(
            user_id=1, message="I'm stuck", segment_ctx=au_ctx
        )
        # Autism stuck response should mention step by step, break down
        assert any(word in result.text.lower() for word in ["step", "break", "identify"])

    @pytest.mark.asyncio()
    async def test_audhd_stuck_signature(
        self, engine: FullCoachingEngine, ah_ctx: SegmentContext
    ) -> None:
        result = await engine.coach(
            user_id=1, message="I'm stuck", segment_ctx=ah_ctx
        )
        # AuDHD should mention checking in, can't start vs too much
        assert any(word in result.text.lower() for word in ["check", "start", "too much"])

    @pytest.mark.asyncio()
    async def test_nt_planning_signature(
        self, engine: FullCoachingEngine, nt_ctx: SegmentContext
    ) -> None:
        result = await engine.coach(
            user_id=1, message="Help me plan today", segment_ctx=nt_ctx
        )
        assert "priorities" in result.text.lower() or "plan" in result.text.lower()

    @pytest.mark.asyncio()
    async def test_adhd_energy_check(
        self, engine: FullCoachingEngine, ad_ctx: SegmentContext
    ) -> None:
        result = await engine.coach(
            user_id=1, message="How's my energy?", segment_ctx=ad_ctx
        )
        assert "RED" in result.text or "YELLOW" in result.text or "GREEN" in result.text

    @pytest.mark.asyncio()
    async def test_audhd_energy_check(
        self, engine: FullCoachingEngine, ah_ctx: SegmentContext
    ) -> None:
        result = await engine.coach(
            user_id=1, message="How's my energy?", segment_ctx=ah_ctx
        )
        assert "spoon" in result.text.lower() or "channel" in result.text.lower()

    @pytest.mark.asyncio()
    async def test_all_segments_have_signatures(
        self, engine: FullCoachingEngine
    ) -> None:
        """All 5 segments should have coaching signatures."""
        from src.services.coaching_engine_full import COACHING_SIGNATURES
        for code in ("AD", "AU", "AH", "NT", "CU"):
            assert code in COACHING_SIGNATURES
            sigs = COACHING_SIGNATURES[code]
            for intent in CoachingIntent:
                assert intent.value in sigs, f"Missing {intent.value} for {code}"


# ============================================================================
# CoachingContext tests
# ============================================================================


class TestCoachingContext:
    def test_to_dict(self, nt_ctx: SegmentContext) -> None:
        ctx = CoachingContext(
            user_id=1,
            message="Test",
            segment_ctx=nt_ctx,
            intent=CoachingIntent.PLANNING,
        )
        d = ctx.to_dict()
        assert d["user_id"] == 1
        assert d["intent"] == "planning"
        assert d["segment_code"] == "NT"

    def test_to_dict_no_segment(self) -> None:
        ctx = CoachingContext(message="Test")
        d = ctx.to_dict()
        assert d["segment_code"] is None


# ============================================================================
# CoachingResult tests
# ============================================================================


class TestCoachingResult:
    def test_to_dict(self) -> None:
        result = CoachingResult(
            text="Hello",
            tier_used=CoachingTier.OPTIMIZED_ARTIFACT,
            confidence=0.85,
        )
        d = result.to_dict()
        assert d["text"] == "Hello"
        assert d["tier_used"] == "optimized_artifact"
        assert d["confidence"] == 0.85


# ============================================================================
# GDPR tests
# ============================================================================


class TestCoachingEngineGDPR:
    @pytest.mark.asyncio()
    async def test_export(
        self, engine: FullCoachingEngine, nt_ctx: SegmentContext
    ) -> None:
        await engine.coach(user_id=1, message="Test", segment_ctx=nt_ctx)
        data = engine.export_user_data(1)
        assert "coaching_interactions" in data
        assert len(data["coaching_interactions"]) == 1

    @pytest.mark.asyncio()
    async def test_delete(
        self, engine: FullCoachingEngine, nt_ctx: SegmentContext
    ) -> None:
        await engine.coach(user_id=1, message="Test", segment_ctx=nt_ctx)
        engine.delete_user_data(1)
        data = engine.export_user_data(1)
        assert data["coaching_interactions"] == []

    def test_export_empty(self, engine: FullCoachingEngine) -> None:
        data = engine.export_user_data(999)
        assert data["coaching_interactions"] == []

    @pytest.mark.asyncio()
    async def test_memory_limit(
        self, engine: FullCoachingEngine, nt_ctx: SegmentContext
    ) -> None:
        """Memory should be capped at 100 interactions."""
        for i in range(105):
            await engine.coach(
                user_id=1, message=f"Message {i}", segment_ctx=nt_ctx
            )
        data = engine.export_user_data(1)
        assert len(data["coaching_interactions"]) == 100
