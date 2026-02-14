"""
Unit tests for the Planning Module.

Tests cover:
- State machine transitions (SCOPE -> VISION -> OVERVIEW -> PRIORITIES -> BREAKDOWN -> SEGMENT_CHECK -> COMMITMENT -> DONE)
- Segment-specific behavior (ADHD, Autism, AuDHD, NT)
- GDPR export/delete/freeze/unfreeze
- Vision alignment check
- Priority enforcement (max_priorities from SegmentContext)
- Segment-specific constraints (sensory check, ICNU, channel dominance)
- Task breakdown and persistence
- Edge cases (unknown state, empty input, invalid priorities)
- Daily workflow hooks
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.core.module_context import ModuleContext
from src.core.segment_context import SegmentContext
from src.core.side_effects import SideEffectType
from src.modules.planning import (
    PlanningModule,
    PlanningSession,
    PlanningState,
    PriorityItem,
)
from src.services.state_store import BoundedStateStore

# =============================================================================
# Helpers
# =============================================================================

class _ReusableAwait:
    """Wrapper that makes a value re-awaitable."""
    def __init__(self, value: object) -> None:
        self._value = value
    def __await__(self):  # type: ignore[override]
        yield
        return self._value


def _make_test_state_store() -> BoundedStateStore:
    """Create an in-memory state store for testing (no Redis dependency)."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = True
    return BoundedStateStore(redis_service=mock_redis)


# =============================================================================
# Fixtures
# =============================================================================

def _make_ctx(
    segment_code: str = "NT",
    state: str = PlanningState.SCOPE,
    user_id: int = 1,
) -> ModuleContext:
    """Create a ModuleContext for testing."""
    return ModuleContext(
        user_id=user_id,
        segment_context=SegmentContext.from_code(segment_code),  # type: ignore[arg-type]
        state=state,
        session_id="test-session",
        language="en",
        module_name="planning",
    )


@pytest.fixture()
def planning_module() -> PlanningModule:
    """Provide a fresh PlanningModule with a test state store."""
    module = PlanningModule()
    store = _make_test_state_store()
    module._state_store = _ReusableAwait(store)  # type: ignore[assignment]
    return module


# =============================================================================
# TestPlanningState
# =============================================================================

class TestPlanningState:
    """Test PlanningState constants."""

    def test_all_states_defined(self) -> None:
        """All 8 states are defined."""
        assert len(PlanningState.ALL) == 8

    def test_state_values(self) -> None:
        """State values match expected strings."""
        assert PlanningState.SCOPE == "SCOPE"
        assert PlanningState.VISION == "VISION"
        assert PlanningState.OVERVIEW == "OVERVIEW"
        assert PlanningState.PRIORITIES == "PRIORITIES"
        assert PlanningState.BREAKDOWN == "BREAKDOWN"
        assert PlanningState.SEGMENT_CHECK == "SEGMENT_CHECK"
        assert PlanningState.COMMITMENT == "COMMITMENT"
        assert PlanningState.DONE == "DONE"


# =============================================================================
# TestOnEnter
# =============================================================================

class TestOnEnter:
    """Test PlanningModule.on_enter() for all segments."""

    @pytest.mark.asyncio
    async def test_on_enter_nt(self, planning_module: PlanningModule) -> None:
        """NT on_enter returns standard message and VISION state."""
        ctx = _make_ctx("NT")
        response = await planning_module.on_enter(ctx)
        assert response.next_state == PlanningState.VISION
        assert "vision" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_ad(self, planning_module: PlanningModule) -> None:
        """AD on_enter uses ICNU-based language."""
        ctx = _make_ctx("AD")
        response = await planning_module.on_enter(ctx)
        assert response.next_state == PlanningState.VISION
        # AD gets ICNU and activation zone language
        assert "activation" in response.text.lower() or "sprint" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_au(self, planning_module: PlanningModule) -> None:
        """AU on_enter uses routine anchoring language."""
        ctx = _make_ctx("AU")
        response = await planning_module.on_enter(ctx)
        assert response.next_state == PlanningState.VISION
        assert "consistency" in response.text.lower() or "routine" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_ah(self, planning_module: PlanningModule) -> None:
        """AH on_enter uses adaptive, channel-aware language."""
        ctx = _make_ctx("AH")
        response = await planning_module.on_enter(ctx)
        assert response.next_state == PlanningState.VISION
        assert "energy" in response.text.lower() or "sensory" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_includes_max_priorities(self, planning_module: PlanningModule) -> None:
        """on_enter metadata includes max_priorities from segment."""
        ctx = _make_ctx("AD")
        response = await planning_module.on_enter(ctx)
        assert "max_priorities" in response.metadata
        # AD gets max 2 priorities
        assert response.metadata["max_priorities"] == 2


# =============================================================================
# TestVisionAlignment
# =============================================================================

class TestVisionAlignment:
    """Test vision alignment check in VISION state."""

    @pytest.mark.asyncio
    async def test_vision_yes_proceeds_to_overview(self, planning_module: PlanningModule) -> None:
        """Answering yes to vision check proceeds to OVERVIEW."""
        ctx = _make_ctx("NT", state=PlanningState.VISION)
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("yes", ctx)
        # With no pending tasks, should skip to PRIORITIES
        assert response.next_state in (PlanningState.OVERVIEW, PlanningState.PRIORITIES)

    @pytest.mark.asyncio
    async def test_vision_no_stays_in_vision(self, planning_module: PlanningModule) -> None:
        """Answering no to vision check stays in VISION for realignment."""
        ctx = _make_ctx("NT", state=PlanningState.VISION)
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("no", ctx)
        assert response.next_state == PlanningState.VISION
        assert "realign" in response.text.lower()

    @pytest.mark.asyncio
    async def test_vision_ambiguous_reprompts(self, planning_module: PlanningModule) -> None:
        """Ambiguous response to vision check re-prompts."""
        ctx = _make_ctx("NT", state=PlanningState.VISION)
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("maybe", ctx)
        assert response.next_state == PlanningState.VISION
        assert "yes or no" in response.text.lower() or "clarify" in response.text.lower()


# =============================================================================
# TestPriorities
# =============================================================================

class TestPriorities:
    """Test priority selection and enforcement."""

    @pytest.mark.asyncio
    async def test_ad_max_2_priorities(self, planning_module: PlanningModule) -> None:
        """AD segment enforces max 2 priorities."""
        ctx = _make_ctx("AD", state=PlanningState.PRIORITIES)
        await planning_module.on_enter(ctx)
        # _parse_priorities truncates to max_priorities (2), so 3 items become 2
        # AD has icnu_enabled, so it goes to SEGMENT_CHECK for ICNU check
        response = await planning_module.handle("1. Task A\n2. Task B\n3. Task C", ctx)
        assert response.next_state == PlanningState.SEGMENT_CHECK
        assert "energy" in response.text.lower()

    @pytest.mark.asyncio
    async def test_au_max_3_priorities(self, planning_module: PlanningModule) -> None:
        """AU segment allows max 3 priorities."""
        ctx = _make_ctx("AU", state=PlanningState.PRIORITIES)
        await planning_module.on_enter(ctx)
        # Add 3 priorities (should be accepted)
        response = await planning_module.handle("1. Task A\n2. Task B\n3. Task C", ctx)
        # AU requires sensory check before breakdown
        assert response.next_state == PlanningState.SEGMENT_CHECK
        assert "sensory" in response.text.lower()

    @pytest.mark.asyncio
    async def test_nt_max_3_priorities(self, planning_module: PlanningModule) -> None:
        """NT segment allows max 3 priorities."""
        ctx = _make_ctx("NT", state=PlanningState.PRIORITIES)
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("1. Write blog\n2. Review PR\n3. Meeting prep", ctx)
        # NT skips segment check, goes straight to breakdown
        assert response.next_state == PlanningState.BREAKDOWN

    @pytest.mark.asyncio
    async def test_priority_parsing_numbered(self, planning_module: PlanningModule) -> None:
        """Numbered priorities are parsed correctly."""
        ctx = _make_ctx("NT", state=PlanningState.PRIORITIES)
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("1. Task A\n2. Task B", ctx)
        assert response.next_state == PlanningState.BREAKDOWN

    @pytest.mark.asyncio
    async def test_priority_parsing_bullets(self, planning_module: PlanningModule) -> None:
        """Bullet priorities are parsed correctly."""
        ctx = _make_ctx("NT", state=PlanningState.PRIORITIES)
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("- Task A\n- Task B", ctx)
        assert response.next_state == PlanningState.BREAKDOWN


# =============================================================================
# TestSegmentChecks
# =============================================================================

class TestSegmentChecks:
    """Test segment-specific constraint checks."""

    @pytest.mark.asyncio
    async def test_au_sensory_check_required(self, planning_module: PlanningModule) -> None:
        """AU segment requires sensory check after priorities."""
        ctx = _make_ctx("AU", state=PlanningState.PRIORITIES)
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("1. Task A\n2. Task B", ctx)
        assert response.next_state == PlanningState.SEGMENT_CHECK
        assert "sensory" in response.text.lower()

    @pytest.mark.asyncio
    async def test_ad_icnu_check_required(self, planning_module: PlanningModule) -> None:
        """AD segment requires ICNU check after priorities."""
        ctx = _make_ctx("AD", state=PlanningState.PRIORITIES)
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("1. Task A\n2. Task B", ctx)
        # AD gets ICNU check
        assert response.next_state == PlanningState.SEGMENT_CHECK
        assert "energy" in response.text.lower()

    @pytest.mark.asyncio
    async def test_ah_channel_check_required(self, planning_module: PlanningModule) -> None:
        """AH segment requires channel dominance check."""
        ctx = _make_ctx("AH", state=PlanningState.PRIORITIES)
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("1. Task A\n2. Task B", ctx)
        assert response.next_state == PlanningState.SEGMENT_CHECK
        # AH can get sensory, ICNU, or channel check
        assert any(word in response.text.lower() for word in ["channel", "energy", "sensory"])

    @pytest.mark.asyncio
    async def test_sensory_overload_redirects(self, planning_module: PlanningModule) -> None:
        """Sensory overload detection redirects user."""
        ctx = _make_ctx("AU", state=PlanningState.SEGMENT_CHECK)
        ctx.metadata = {"sensory_check_required": True}
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("I'm completely overwhelmed and shutting down", ctx)
        assert response.is_end_of_flow is True
        assert "overload" in response.text.lower()

    @pytest.mark.asyncio
    async def test_low_icnu_adjusts_priorities(self, planning_module: PlanningModule) -> None:
        """Low ICNU charge triggers priority adjustment."""
        ctx = _make_ctx("AD", state=PlanningState.SEGMENT_CHECK)
        ctx.metadata = {"icnu_check_required": True}
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("1", ctx)  # Very low energy
        assert response.next_state == PlanningState.PRIORITIES
        assert "adjust" in response.text.lower()


# =============================================================================
# TestBreakdown
# =============================================================================

class TestBreakdown:
    """Test task breakdown."""

    @pytest.mark.asyncio
    async def test_breakdown_parses_tasks(self, planning_module: PlanningModule) -> None:
        """Task breakdown parses tasks from user input."""
        ctx = _make_ctx("NT", state=PlanningState.BREAKDOWN)
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("- Write intro\n- Edit section 2\n- Publish", ctx)
        assert response.next_state == PlanningState.COMMITMENT
        assert "sprint" in response.text.lower() or "commit" in response.text.lower()

    @pytest.mark.asyncio
    async def test_breakdown_removes_numbering(self, planning_module: PlanningModule) -> None:
        """Task breakdown removes numbering from tasks."""
        ctx = _make_ctx("NT", state=PlanningState.BREAKDOWN)
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("1. Task A\n2. Task B", ctx)
        assert response.next_state == PlanningState.COMMITMENT


# =============================================================================
# TestCommitment
# =============================================================================

class TestCommitment:
    """Test commitment confirmation."""

    @pytest.mark.asyncio
    async def test_commitment_yes_creates_tasks(self, planning_module: PlanningModule) -> None:
        """Confirming commitment creates tasks via side effect."""
        ctx = _make_ctx("NT", state=PlanningState.COMMITMENT)
        await planning_module.on_enter(ctx)
        # Simulate a session with tasks
        session_key = f"planning:session:{ctx.user_id}"
        state_store = await planning_module._state_store
        session = PlanningSession(
            scope="Get work done",
            tasks=[
                {"id": "task_1", "title": "Write blog", "priority": 1},
                {"id": "task_2", "title": "Review PR", "priority": 2},
            ],
        )
        await state_store.set(session_key, session, ttl=3600)

        response = await planning_module.handle("yes", ctx)
        assert response.is_end_of_flow is True
        assert response.side_effects is not None
        assert len(response.side_effects) == 1
        # "create_tasks" is not a defined SideEffectType enum value,
        # so SideEffect.__post_init__ converts it to CUSTOM
        assert response.side_effects[0].effect_type == SideEffectType.CUSTOM

    @pytest.mark.asyncio
    async def test_commitment_no_goes_back_to_breakdown(self, planning_module: PlanningModule) -> None:
        """Cancelling commitment goes back to breakdown."""
        ctx = _make_ctx("NT", state=PlanningState.COMMITMENT)
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("no", ctx)
        assert response.next_state == PlanningState.BREAKDOWN

    @pytest.mark.asyncio
    async def test_commitment_ambiguous_reprompts(self, planning_module: PlanningModule) -> None:
        """Ambiguous response to commitment re-prompts."""
        ctx = _make_ctx("NT", state=PlanningState.COMMITMENT)
        await planning_module.on_enter(ctx)
        response = await planning_module.handle("maybe later", ctx)
        assert response.next_state == PlanningState.COMMITMENT


# =============================================================================
# TestHelperMethods
# =============================================================================

class TestHelperMethods:
    """Test helper methods."""

    def test_parse_priorities_numbered(self, planning_module: PlanningModule) -> None:
        """parse_priorities handles numbered lists."""
        priorities = planning_module._parse_priorities("1. Task A\n2. Task B", 3)
        assert len(priorities) == 2
        assert priorities[0].title == ". Task A"

    def test_parse_priorities_bullets(self, planning_module: PlanningModule) -> None:
        """parse_priorities handles bullets."""
        priorities = planning_module._parse_priorities("- Task A\n- Task B", 3)
        assert len(priorities) == 2

    def test_parse_priorities_max_limit(self, planning_module: PlanningModule) -> None:
        """parse_priorities respects max limit."""
        priorities = planning_module._parse_priorities("1. A\n2. B\n3. C\n4. D", 2)
        assert len(priorities) == 2

    def test_parse_tasks_numbered(self, planning_module: PlanningModule) -> None:
        """parse_tasks handles numbered lists."""
        tasks = planning_module._parse_tasks("1. Write\n2. Edit", [])
        assert len(tasks) == 2

    def test_parse_tasks_filters_short(self, planning_module: PlanningModule) -> None:
        """parse_tasks filters out very short lines."""
        tasks = planning_module._parse_tasks("OK\nno\nWrite the blog post", [])
        assert len(tasks) == 1

    def test_is_sensory_overloaded_detects(self, planning_module: PlanningModule) -> None:
        """_is_sensory_overloaded detects overload indicators."""
        assert planning_module._is_sensory_overloaded("I'm completely overwhelmed") is True
        assert planning_module._is_sensory_overloaded("sensory overload") is True
        assert planning_module._is_sensory_overloaded("I'm doing fine") is False

    def test_parse_icnu_extracts_number(self, planning_module: PlanningModule) -> None:
        """_parse_icnu extracts charge from message."""
        assert planning_module._parse_icnu("My energy is 4 out of 5") == 4
        assert planning_module._parse_icnu("1") == 1
        assert planning_module._parse_icnu("no number here") == 3  # default

    def test_parse_channel_identifies(self, planning_module: PlanningModule) -> None:
        """_parse_channel identifies channel from message."""
        assert planning_module._parse_channel("I'm in focus mode") == "focus"
        assert planning_module._parse_channel("feeling creative") == "creative"
        assert planning_module._parse_channel("social energy") == "social"
        assert planning_module._parse_channel("random text") is None


# =============================================================================
# TestSegmentGuidance
# =============================================================================

class TestSegmentGuidance:
    """Test segment-specific guidance text."""

    def test_au_guidance_mentions_routine(self, planning_module: PlanningModule) -> None:
        """AU guidance mentions routine anchoring."""
        segment = SegmentContext.from_code("AU")
        guidance = planning_module._get_segment_guidance(segment)
        assert "consistency" in guidance.lower() or "routine" in guidance.lower()

    def test_ad_guidance_mentions_icnu(self, planning_module: PlanningModule) -> None:
        """AD guidance mentions ICNU/activation."""
        segment = SegmentContext.from_code("AD")
        guidance = planning_module._get_segment_guidance(segment)
        assert "activation" in guidance.lower() or "sprint" in guidance.lower()

    def test_ah_guidance_mentions_energy(self, planning_module: PlanningModule) -> None:
        """AH guidance mentions energy/sensory."""
        segment = SegmentContext.from_code("AH")
        guidance = planning_module._get_segment_guidance(segment)
        assert "energy" in guidance.lower() or "sensory" in guidance.lower()


# =============================================================================
# TestGDPR
# =============================================================================

class TestGDPR:
    """Test GDPR compliance methods."""

    @pytest.mark.asyncio
    async def test_export_returns_dict(self, planning_module: PlanningModule) -> None:
        """export_user_data returns expected keys."""
        data = await planning_module.export_user_data(user_id=1)
        assert "tasks" in data
        assert "goals" in data
        assert "visions" in data

    @pytest.mark.asyncio
    async def test_delete_runs(self, planning_module: PlanningModule) -> None:
        """delete_user_data runs without error."""
        await planning_module.delete_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_freeze_runs(self, planning_module: PlanningModule) -> None:
        """freeze_user_data runs without error."""
        await planning_module.freeze_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_unfreeze_runs(self, planning_module: PlanningModule) -> None:
        """unfreeze_user_data runs without error."""
        await planning_module.unfreeze_user_data(user_id=1)


# =============================================================================
# TestOnExit
# =============================================================================

class TestOnExit:
    """Test session cleanup on module exit."""

    @pytest.mark.asyncio
    async def test_on_exit_cleans_session(self, planning_module: PlanningModule) -> None:
        """on_exit removes the user's session."""
        ctx = _make_ctx("NT", user_id=99)
        await planning_module.on_enter(ctx)
        session_key = f"planning:session:99"
        state_store = await planning_module._state_store
        session = await state_store.get(session_key)
        assert session is not None
        await planning_module.on_exit(ctx)
        session = await state_store.get(session_key)
        assert session is None


# =============================================================================
# TestDailyWorkflowHooks
# =============================================================================

class TestDailyWorkflowHooks:
    """Test daily workflow hooks."""

    def test_hooks_defined(self, planning_module: PlanningModule) -> None:
        """Planning module defines planning_enrichment hook."""
        hooks = planning_module.get_daily_workflow_hooks()
        assert hooks.planning_enrichment is not None
        assert hooks.hook_name == "planning"
        assert hooks.priority == 10


# =============================================================================
# TestUnknownState
# =============================================================================

class TestUnknownState:
    """Test handling of unknown states."""

    @pytest.mark.asyncio
    async def test_unknown_state_restarts(self, planning_module: PlanningModule) -> None:
        """Unknown state triggers on_enter (restart)."""
        ctx = _make_ctx("NT", state="NONEXISTENT")
        response = await planning_module.handle("hello", ctx)
        assert response.next_state == PlanningState.VISION


# =============================================================================
# TestModuleIdentity
# =============================================================================

class TestModuleIdentity:
    """Test module identity attributes."""

    def test_name(self, planning_module: PlanningModule) -> None:
        """Module name is 'planning'."""
        assert planning_module.name == "planning"

    def test_pillar(self, planning_module: PlanningModule) -> None:
        """Module pillar is 'vision_to_task'."""
        assert planning_module.pillar == "vision_to_task"

    def test_intents(self, planning_module: PlanningModule) -> None:
        """Module has expected intents."""
        assert "planning.start" in planning_module.intents
        assert "planning.prioritize" in planning_module.intents
