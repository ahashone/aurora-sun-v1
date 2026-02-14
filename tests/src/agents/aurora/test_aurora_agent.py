"""
Tests for the Aurora Agent (main orchestrator).

Covers:
- Weekly cycle: Gather -> Assess -> Synthesize -> Recommend
- Individual methods: generate_chapter, check_milestones, assess_growth
- Error handling in workflow steps
- State transitions
- GDPR export/delete
- Segment-specific behavior across workflow
"""

from __future__ import annotations

import pytest

from src.agents.aurora.agent import (
    AuroraAgent,
    AuroraState,
    WorkflowStep,
)
from src.agents.aurora.coherence import CoherenceAuditor
from src.agents.aurora.growth import GrowthTracker
from src.agents.aurora.milestones import MilestoneDetector, MilestoneType
from src.agents.aurora.narrative import NarrativeEngine
from src.agents.aurora.proactive import ProactiveEngine
from src.core.segment_context import SegmentContext


@pytest.fixture()
def agent() -> AuroraAgent:
    """Create an AuroraAgent instance."""
    return AuroraAgent()


@pytest.fixture()
def nt_ctx() -> SegmentContext:
    return SegmentContext.from_code("NT")


@pytest.fixture()
def ad_ctx() -> SegmentContext:
    return SegmentContext.from_code("AD")


@pytest.fixture()
def au_ctx() -> SegmentContext:
    return SegmentContext.from_code("AU")


@pytest.fixture()
def ah_ctx() -> SegmentContext:
    return SegmentContext.from_code("AH")


# ============================================================================
# AuroraState tests
# ============================================================================


class TestAuroraState:
    def test_default_state(self) -> None:
        state = AuroraState()
        assert state.current_step == WorkflowStep.GATHER
        assert state.user_id == 0
        assert state.milestones == []
        assert state.errors == []

    def test_state_to_dict(self) -> None:
        state = AuroraState(user_id=1)
        d = state.to_dict()
        assert d["user_id"] == 1
        assert d["current_step"] == "gather"
        assert d["milestones_count"] == 0


# ============================================================================
# WorkflowStep tests
# ============================================================================


class TestWorkflowStep:
    def test_all_steps(self) -> None:
        steps = list(WorkflowStep)
        assert WorkflowStep.GATHER in steps
        assert WorkflowStep.ASSESS in steps
        assert WorkflowStep.SYNTHESIZE in steps
        assert WorkflowStep.RECOMMEND in steps
        assert WorkflowStep.ERROR in steps
        assert WorkflowStep.COMPLETE in steps


# ============================================================================
# Weekly cycle tests
# ============================================================================


class TestWeeklyCycle:
    @pytest.mark.asyncio()
    async def test_full_cycle_completes(
        self, agent: AuroraAgent, nt_ctx: SegmentContext
    ) -> None:
        state = await agent.run_weekly_cycle(
            user_id=1,
            segment_ctx=nt_ctx,
            vision="Be productive",
            goals=["Goal A"],
            habits=["Habit A"],
            goal_habit_links={"Goal A": ["Habit A"]},
        )
        assert state.current_step == WorkflowStep.COMPLETE
        assert state.user_id == 1
        assert state.errors == []

    @pytest.mark.asyncio()
    async def test_cycle_with_milestones(
        self, agent: AuroraAgent, nt_ctx: SegmentContext
    ) -> None:
        state = await agent.run_weekly_cycle(
            user_id=1,
            segment_ctx=nt_ctx,
            achieved_goals=["Launch MVP"],
            habit_streaks={"journaling": 25},
        )
        assert len(state.milestones) >= 1
        types = {m.milestone_type for m in state.milestones}
        assert MilestoneType.GOAL_ACHIEVED in types

    @pytest.mark.asyncio()
    async def test_cycle_generates_chapter(
        self, agent: AuroraAgent, nt_ctx: SegmentContext
    ) -> None:
        state = await agent.run_weekly_cycle(
            user_id=1,
            segment_ctx=nt_ctx,
            week_number=3,
        )
        assert state.chapter is not None
        assert state.chapter.week_number == 3

    @pytest.mark.asyncio()
    async def test_cycle_generates_growth_summary(
        self, agent: AuroraAgent, nt_ctx: SegmentContext
    ) -> None:
        state = await agent.run_weekly_cycle(
            user_id=1, segment_ctx=nt_ctx
        )
        assert state.growth_summary is not None
        assert state.growth_summary.user_id == 1

    @pytest.mark.asyncio()
    async def test_cycle_calculates_readiness(
        self, agent: AuroraAgent, nt_ctx: SegmentContext
    ) -> None:
        state = await agent.run_weekly_cycle(
            user_id=1, segment_ctx=nt_ctx
        )
        assert state.readiness is not None

    @pytest.mark.asyncio()
    async def test_cycle_with_empty_data(
        self, agent: AuroraAgent, nt_ctx: SegmentContext
    ) -> None:
        state = await agent.run_weekly_cycle(
            user_id=1, segment_ctx=nt_ctx
        )
        assert state.current_step == WorkflowStep.COMPLETE
        assert state.errors == []

    @pytest.mark.asyncio()
    async def test_cycle_adhd_segment(
        self, agent: AuroraAgent, ad_ctx: SegmentContext
    ) -> None:
        state = await agent.run_weekly_cycle(
            user_id=1,
            segment_ctx=ad_ctx,
            habit_streaks={"exercise": 21},
        )
        assert state.current_step == WorkflowStep.COMPLETE
        # ADHD 21-day threshold should trigger
        habit_milestones = [
            m for m in state.milestones
            if m.milestone_type == MilestoneType.HABIT_ESTABLISHED
        ]
        assert len(habit_milestones) == 1

    @pytest.mark.asyncio()
    async def test_cycle_autism_segment_14d_habit(
        self, agent: AuroraAgent, au_ctx: SegmentContext
    ) -> None:
        state = await agent.run_weekly_cycle(
            user_id=1,
            segment_ctx=au_ctx,
            habit_streaks={"reading": 14},
        )
        habit_milestones = [
            m for m in state.milestones
            if m.milestone_type == MilestoneType.HABIT_ESTABLISHED
        ]
        assert len(habit_milestones) == 1  # 14 days is enough for AU


# ============================================================================
# Individual method tests
# ============================================================================


class TestGenerateChapter:
    @pytest.mark.asyncio()
    async def test_generate_chapter(
        self, agent: AuroraAgent, nt_ctx: SegmentContext
    ) -> None:
        chapter = await agent.generate_chapter(
            user_id=1, segment_ctx=nt_ctx, week_number=5
        )
        assert chapter.week_number == 5
        assert chapter.user_id == 1

    @pytest.mark.asyncio()
    async def test_generate_chapter_with_milestones(
        self, agent: AuroraAgent, nt_ctx: SegmentContext
    ) -> None:
        from src.agents.aurora.milestones import MilestoneEvent
        ms = MilestoneEvent(
            user_id=1,
            milestone_type=MilestoneType.GOAL_ACHIEVED,
            title="Test Goal",
            description="Completed",
        )
        chapter = await agent.generate_chapter(
            user_id=1, segment_ctx=nt_ctx,
            week_number=1, milestones=[ms],
        )
        assert len(chapter.milestones) == 1


class TestCheckMilestones:
    @pytest.mark.asyncio()
    async def test_check_milestones(
        self, agent: AuroraAgent, nt_ctx: SegmentContext
    ) -> None:
        milestones = await agent.check_milestones(
            user_id=1,
            segment_ctx=nt_ctx,
            achieved_goals=["Goal A"],
        )
        assert len(milestones) == 1


class TestAssessGrowth:
    @pytest.mark.asyncio()
    async def test_assess_growth(
        self, agent: AuroraAgent, nt_ctx: SegmentContext
    ) -> None:
        summary = await agent.assess_growth(user_id=1, segment_ctx=nt_ctx)
        assert summary.user_id == 1
        assert summary.narrative != ""


# ============================================================================
# Constructor tests
# ============================================================================


class TestAuroraAgentInit:
    def test_default_initialization(self) -> None:
        agent = AuroraAgent()
        assert isinstance(agent.narrative, NarrativeEngine)
        assert isinstance(agent.growth, GrowthTracker)
        assert isinstance(agent.milestones, MilestoneDetector)
        assert isinstance(agent.coherence, CoherenceAuditor)
        assert isinstance(agent.proactive, ProactiveEngine)

    def test_custom_engines(self) -> None:
        narrative = NarrativeEngine()
        growth = GrowthTracker()
        agent = AuroraAgent(
            narrative_engine=narrative,
            growth_tracker=growth,
        )
        assert agent.narrative is narrative
        assert agent.growth is growth


# ============================================================================
# GDPR tests
# ============================================================================


class TestAuroraAgentGDPR:
    @pytest.mark.asyncio()
    async def test_export_user_data(
        self, agent: AuroraAgent, nt_ctx: SegmentContext
    ) -> None:
        await agent.run_weekly_cycle(
            user_id=1,
            segment_ctx=nt_ctx,
            achieved_goals=["Goal A"],
        )
        data = agent.export_user_data(user_id=1)
        assert "narrative" in data
        assert "growth" in data
        assert "milestones" in data
        assert "coherence" in data
        assert "proactive" in data

    @pytest.mark.asyncio()
    async def test_delete_user_data(
        self, agent: AuroraAgent, nt_ctx: SegmentContext
    ) -> None:
        await agent.run_weekly_cycle(
            user_id=1,
            segment_ctx=nt_ctx,
            achieved_goals=["Goal A"],
        )
        agent.delete_user_data(user_id=1)
        data = agent.export_user_data(user_id=1)
        assert data["milestones"]["milestones"] == []
        assert data["growth"]["trajectory_scores"] == []
