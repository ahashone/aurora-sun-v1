"""
Unit tests for the Future Letter Module.

Tests cover:
- State machine transitions (SETTING -> LIFE_NOW -> LOOKING_BACK -> CHALLENGES -> WISDOM -> DONE)
- Segment-specific prompts (ADHD, Autism, AuDHD, NT)
- GDPR export/delete/freeze/unfreeze
- Time horizon parsing (5/10/20 years)
- Letter compilation
- Key insights extraction
- Vision anchoring side effects
- Edge cases (unknown state, invalid time horizon)
- Daily workflow hooks
"""

from __future__ import annotations

import pytest

from src.core.module_context import ModuleContext
from src.core.segment_context import SegmentContext
from src.core.side_effects import SideEffectType
from src.modules.future_letter import (
    FutureLetterModule,
    FutureLetterSession,
    FutureLetterState,
)
from src.services.state_store import BoundedStateStore

# =============================================================================
# Helpers
# =============================================================================

class _ReusableAwait:
    """Wrapper that makes a coroutine result re-awaitable."""
    def __init__(self, value: object) -> None:
        self._value = value
    def __await__(self):  # type: ignore[override]
        yield
        return self._value


def _make_test_state_store() -> BoundedStateStore:
    """Create an in-memory state store for testing (no Redis dependency)."""
    from unittest.mock import AsyncMock
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
    state: str = FutureLetterState.SETTING,
    user_id: int = 1,
) -> ModuleContext:
    """Create a ModuleContext for testing."""
    return ModuleContext(
        user_id=user_id,
        segment_context=SegmentContext.from_code(segment_code),  # type: ignore[arg-type]
        state=state,
        session_id="test-session",
        language="en",
        module_name="future_letter",
    )


@pytest.fixture()
def future_letter_module() -> FutureLetterModule:
    """Provide a fresh FutureLetterModule with a test state store."""
    module = FutureLetterModule()
    # Close the old coroutine to prevent "coroutine never awaited" warnings
    old_coro = module._state_store
    if hasattr(old_coro, "close"):
        old_coro.close()
    store = _make_test_state_store()
    # Replace the coroutine with a re-awaitable wrapper so multiple
    # awaits in the module methods work correctly in tests
    module._state_store = _ReusableAwait(store)  # type: ignore[assignment]
    return module


# =============================================================================
# TestFutureLetterState
# =============================================================================

class TestFutureLetterState:
    """Test FutureLetterState constants."""

    def test_all_states_defined(self) -> None:
        """All 6 states are defined."""
        assert len(FutureLetterState.ALL) == 6

    def test_state_values(self) -> None:
        """State values match expected strings."""
        assert FutureLetterState.SETTING == "SETTING"
        assert FutureLetterState.LIFE_NOW == "LIFE_NOW"
        assert FutureLetterState.LOOKING_BACK == "LOOKING_BACK"
        assert FutureLetterState.CHALLENGES == "CHALLENGES"
        assert FutureLetterState.WISDOM == "WISDOM"
        assert FutureLetterState.DONE == "DONE"


# =============================================================================
# TestOnEnter
# =============================================================================

class TestOnEnter:
    """Test FutureLetterModule.on_enter() for all segments."""

    @pytest.mark.asyncio
    async def test_on_enter_nt(self, future_letter_module: FutureLetterModule) -> None:
        """NT on_enter returns welcome and SETTING state."""
        ctx = _make_ctx("NT")
        response = await future_letter_module.on_enter(ctx)
        assert response.next_state == FutureLetterState.SETTING
        assert "future" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_ad(self, future_letter_module: FutureLetterModule) -> None:
        """AD on_enter uses exciting language."""
        ctx = _make_ctx("AD")
        response = await future_letter_module.on_enter(ctx)
        assert response.next_state == FutureLetterState.SETTING
        assert "exciting" in response.text.lower() or "imagine" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_au(self, future_letter_module: FutureLetterModule) -> None:
        """AU on_enter uses clear, structured language."""
        ctx = _make_ctx("AU")
        response = await future_letter_module.on_enter(ctx)
        assert response.next_state == FutureLetterState.SETTING
        assert "time" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_ah(self, future_letter_module: FutureLetterModule) -> None:
        """AH on_enter uses adaptive language."""
        ctx = _make_ctx("AH")
        response = await future_letter_module.on_enter(ctx)
        assert response.next_state == FutureLetterState.SETTING

    @pytest.mark.asyncio
    async def test_on_enter_includes_metadata(
        self, future_letter_module: FutureLetterModule,
    ) -> None:
        """on_enter includes time horizon options in metadata."""
        ctx = _make_ctx("NT")
        response = await future_letter_module.on_enter(ctx)
        assert "time_horizon_options" in response.metadata
        assert response.metadata["time_horizon_options"] == [5, 10, 20]


# =============================================================================
# TestStateTransitions
# =============================================================================

class TestStateTransitions:
    """Test full state machine transitions."""

    @pytest.mark.asyncio
    async def test_full_flow_nt(self, future_letter_module: FutureLetterModule) -> None:
        """Full flow from SETTING to DONE for NT segment."""
        ctx = _make_ctx("NT")
        await future_letter_module.on_enter(ctx)

        # SETTING -> LIFE_NOW
        ctx.state = FutureLetterState.SETTING
        r = await future_letter_module.handle("10 years", ctx)
        assert r.next_state == FutureLetterState.LIFE_NOW

        # LIFE_NOW -> LOOKING_BACK
        ctx.state = FutureLetterState.LIFE_NOW
        r = await future_letter_module.handle("I'm building my career", ctx)
        assert r.next_state == FutureLetterState.LOOKING_BACK

        # LOOKING_BACK -> CHALLENGES
        ctx.state = FutureLetterState.LOOKING_BACK
        r = await future_letter_module.handle("This was the foundation", ctx)
        assert r.next_state == FutureLetterState.CHALLENGES

        # CHALLENGES -> WISDOM
        ctx.state = FutureLetterState.CHALLENGES
        r = await future_letter_module.handle("I learned to be patient", ctx)
        assert r.next_state == FutureLetterState.WISDOM

        # WISDOM -> DONE
        ctx.state = FutureLetterState.WISDOM
        r = await future_letter_module.handle("Trust the process", ctx)
        assert r.is_end_of_flow is True
        assert r.side_effects is not None
        assert len(r.side_effects) == 1
        assert r.side_effects[0].effect_type == SideEffectType.CUSTOM


# =============================================================================
# TestTimeHorizonParsing
# =============================================================================

class TestTimeHorizonParsing:
    """Test time horizon parsing."""

    def test_parse_5_years(self, future_letter_module: FutureLetterModule) -> None:
        """Parse '5 years' correctly."""
        result = future_letter_module._parse_time_horizon("5 years")
        assert result == 5

    def test_parse_10_years(self, future_letter_module: FutureLetterModule) -> None:
        """Parse '10 years' correctly."""
        result = future_letter_module._parse_time_horizon("10 years")
        assert result == 10

    def test_parse_20_years(self, future_letter_module: FutureLetterModule) -> None:
        """Parse '20 years' correctly."""
        result = future_letter_module._parse_time_horizon("20 years")
        assert result == 20

    def test_parse_just_number(self, future_letter_module: FutureLetterModule) -> None:
        """Parse just '5' correctly."""
        result = future_letter_module._parse_time_horizon("5")
        assert result == 5

    def test_parse_word_five(self, future_letter_module: FutureLetterModule) -> None:
        """Parse word 'five' correctly."""
        result = future_letter_module._parse_time_horizon("five")
        assert result == 5

    def test_parse_word_ten(self, future_letter_module: FutureLetterModule) -> None:
        """Parse word 'ten' correctly."""
        result = future_letter_module._parse_time_horizon("ten")
        assert result == 10

    def test_parse_word_twenty(self, future_letter_module: FutureLetterModule) -> None:
        """Parse word 'twenty' correctly."""
        result = future_letter_module._parse_time_horizon("twenty")
        assert result == 20

    def test_parse_invalid_returns_none(self, future_letter_module: FutureLetterModule) -> None:
        """Invalid input returns None."""
        result = future_letter_module._parse_time_horizon("invalid")
        assert result is None

    def test_parse_ambiguous_prefers_20(self, future_letter_module: FutureLetterModule) -> None:
        """Ambiguous '5 or 20' prefers 20."""
        result = future_letter_module._parse_time_horizon("5 or 20")
        assert result == 20


# =============================================================================
# TestSetting
# =============================================================================

class TestSetting:
    """Test SETTING state handler."""

    @pytest.mark.asyncio
    async def test_setting_valid_proceeds(self, future_letter_module: FutureLetterModule) -> None:
        """Valid time horizon proceeds to LIFE_NOW."""
        ctx = _make_ctx("NT", state=FutureLetterState.SETTING)
        await future_letter_module.on_enter(ctx)
        response = await future_letter_module.handle("10", ctx)
        assert response.next_state == FutureLetterState.LIFE_NOW
        assert "10 years" in response.text

    @pytest.mark.asyncio
    async def test_setting_invalid_reprompts(
        self, future_letter_module: FutureLetterModule,
    ) -> None:
        """Invalid time horizon re-prompts."""
        ctx = _make_ctx("NT", state=FutureLetterState.SETTING)
        await future_letter_module.on_enter(ctx)
        response = await future_letter_module.handle("invalid", ctx)
        assert response.next_state == FutureLetterState.SETTING
        assert "didn't catch" in response.text.lower()


# =============================================================================
# TestLifeNow
# =============================================================================

class TestLifeNow:
    """Test LIFE_NOW state handler."""

    @pytest.mark.asyncio
    async def test_life_now_proceeds(self, future_letter_module: FutureLetterModule) -> None:
        """LIFE_NOW proceeds to LOOKING_BACK."""
        ctx = _make_ctx("NT", state=FutureLetterState.LIFE_NOW)
        await future_letter_module.on_enter(ctx)
        # Set time horizon
        session_key = f"future_letter:session:{ctx.user_id}"
        state_store = await future_letter_module._state_store
        session = FutureLetterSession(time_horizon=10)
        await state_store.set(session_key, session, ttl=86400)

        response = await future_letter_module.handle("I'm building my career", ctx)
        assert response.next_state == FutureLetterState.LOOKING_BACK


# =============================================================================
# TestLookingBack
# =============================================================================

class TestLookingBack:
    """Test LOOKING_BACK state handler."""

    @pytest.mark.asyncio
    async def test_looking_back_proceeds(self, future_letter_module: FutureLetterModule) -> None:
        """LOOKING_BACK proceeds to CHALLENGES."""
        ctx = _make_ctx("NT", state=FutureLetterState.LOOKING_BACK)
        await future_letter_module.on_enter(ctx)
        response = await future_letter_module.handle("This was the foundation", ctx)
        assert response.next_state == FutureLetterState.CHALLENGES


# =============================================================================
# TestChallenges
# =============================================================================

class TestChallenges:
    """Test CHALLENGES state handler."""

    @pytest.mark.asyncio
    async def test_challenges_proceeds(self, future_letter_module: FutureLetterModule) -> None:
        """CHALLENGES proceeds to WISDOM."""
        ctx = _make_ctx("NT", state=FutureLetterState.CHALLENGES)
        await future_letter_module.on_enter(ctx)
        response = await future_letter_module.handle("I learned to be patient", ctx)
        assert response.next_state == FutureLetterState.WISDOM


# =============================================================================
# TestWisdom
# =============================================================================

class TestWisdom:
    """Test WISDOM state handler."""

    @pytest.mark.asyncio
    async def test_wisdom_ends_flow(self, future_letter_module: FutureLetterModule) -> None:
        """WISDOM ends the flow."""
        ctx = _make_ctx("NT", state=FutureLetterState.WISDOM)
        await future_letter_module.on_enter(ctx)
        # Set up session
        session_key = f"future_letter:session:{ctx.user_id}"
        state_store = await future_letter_module._state_store
        session = FutureLetterSession(
            time_horizon=10,
            life_now="Building career",
            looking_back="Foundation",
            challenges="Patience",
        )
        await state_store.set(session_key, session, ttl=86400)

        response = await future_letter_module.handle("Trust the process", ctx)
        assert response.is_end_of_flow is True

    @pytest.mark.asyncio
    async def test_wisdom_creates_side_effect(
        self, future_letter_module: FutureLetterModule,
    ) -> None:
        """WISDOM creates vision_anchor side effect."""
        ctx = _make_ctx("NT", state=FutureLetterState.WISDOM)
        await future_letter_module.on_enter(ctx)
        session_key = f"future_letter:session:{ctx.user_id}"
        state_store = await future_letter_module._state_store
        session = FutureLetterSession(
            time_horizon=10,
            life_now="Building career",
            looking_back="Foundation",
            challenges="Patience",
        )
        await state_store.set(session_key, session, ttl=86400)

        response = await future_letter_module.handle("Trust the process", ctx)
        assert response.side_effects is not None
        assert len(response.side_effects) == 1
        assert response.side_effects[0].effect_type == SideEffectType.CUSTOM


# =============================================================================
# TestLetterCompilation
# =============================================================================

class TestLetterCompilation:
    """Test letter compilation."""

    def test_compile_letter(self, future_letter_module: FutureLetterModule) -> None:
        """_compile_letter creates formatted letter."""
        session = FutureLetterSession(
            time_horizon=10,
            life_now="Building my career",
            looking_back="This was the foundation",
            challenges="I learned to be patient",
            wisdom="Trust the process",
        )
        letter = future_letter_module._compile_letter(session)
        assert "Dear Future Me" in letter
        assert "10 years ago" in letter
        assert "Building my career" in letter
        assert "This was the foundation" in letter
        assert "I learned to be patient" in letter
        assert "Trust the process" in letter


# =============================================================================
# TestKeyInsightsExtraction
# =============================================================================

class TestKeyInsightsExtraction:
    """Test key insights extraction."""

    def test_extract_key_insights(self, future_letter_module: FutureLetterModule) -> None:
        """_extract_key_insights extracts first sentences."""
        session = FutureLetterSession(
            time_horizon=10,
            life_now="Building my career. It's challenging but rewarding.",
            looking_back="This was the foundation. Everything grew from here.",
            challenges="I learned to be patient. It was hard at first.",
            wisdom="Trust the process. Everything works out.",
        )
        insights = future_letter_module._extract_key_insights(session)
        assert len(insights) > 0
        assert any("Building my career" in insight for insight in insights)


# =============================================================================
# TestSegmentPrompts
# =============================================================================

class TestSegmentPrompts:
    """Test segment-specific prompts."""

    def test_ad_setting_prompt(self, future_letter_module: FutureLetterModule) -> None:
        """AD gets exciting setting prompt."""
        segment = SegmentContext.from_code("AD")
        prompt = future_letter_module._get_segment_prompt(segment, "setting")
        assert "exciting" in prompt.lower() or "imagine" in prompt.lower()

    def test_au_setting_prompt(self, future_letter_module: FutureLetterModule) -> None:
        """AU gets clear, structured setting prompt."""
        segment = SegmentContext.from_code("AU")
        prompt = future_letter_module._get_segment_prompt(segment, "setting")
        assert "time" in prompt.lower()

    def test_ah_challenges_prompt(self, future_letter_module: FutureLetterModule) -> None:
        """AH gets attention/sensory challenges prompt."""
        segment = SegmentContext.from_code("AH")
        prompt = future_letter_module._get_segment_prompt(segment, "challenges")
        assert "attention" in prompt.lower() or "sensory" in prompt.lower()


# =============================================================================
# TestGDPR
# =============================================================================

class TestGDPR:
    """Test GDPR compliance methods."""

    @pytest.mark.asyncio
    async def test_export_returns_dict(self, future_letter_module: FutureLetterModule) -> None:
        """export_user_data returns expected keys."""
        data = await future_letter_module.export_user_data(user_id=1)
        assert "future_letters" in data

    @pytest.mark.asyncio
    async def test_delete_runs(self, future_letter_module: FutureLetterModule) -> None:
        """delete_user_data runs without error."""
        await future_letter_module.delete_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_freeze_runs(self, future_letter_module: FutureLetterModule) -> None:
        """freeze_user_data runs without error."""
        await future_letter_module.freeze_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_unfreeze_runs(self, future_letter_module: FutureLetterModule) -> None:
        """unfreeze_user_data runs without error."""
        await future_letter_module.unfreeze_user_data(user_id=1)


# =============================================================================
# TestOnExit
# =============================================================================

class TestOnExit:
    """Test session cleanup on module exit."""

    @pytest.mark.asyncio
    async def test_on_exit_cleans_session(self, future_letter_module: FutureLetterModule) -> None:
        """on_exit removes the user's session."""
        ctx = _make_ctx("NT", user_id=99)
        await future_letter_module.on_enter(ctx)
        session_key = "future_letter:session:99"
        state_store = await future_letter_module._state_store
        session = await state_store.get(session_key)
        assert session is not None
        await future_letter_module.on_exit(ctx)
        session = await state_store.get(session_key)
        assert session is None


# =============================================================================
# TestDailyWorkflowHooks
# =============================================================================

class TestDailyWorkflowHooks:
    """Test daily workflow hooks."""

    def test_hooks_defined(self, future_letter_module: FutureLetterModule) -> None:
        """Future letter module defines hooks."""
        hooks = future_letter_module.get_daily_workflow_hooks()
        assert hooks.hook_name == "future_letter"
        assert hooks.priority == 50


# =============================================================================
# TestUnknownState
# =============================================================================

class TestUnknownState:
    """Test handling of unknown states."""

    @pytest.mark.asyncio
    async def test_unknown_state_restarts(self, future_letter_module: FutureLetterModule) -> None:
        """Unknown state triggers on_enter (restart)."""
        ctx = _make_ctx("NT", state="NONEXISTENT")
        response = await future_letter_module.handle("hello", ctx)
        assert response.next_state == FutureLetterState.SETTING


# =============================================================================
# TestModuleIdentity
# =============================================================================

class TestModuleIdentity:
    """Test module identity attributes."""

    def test_name(self, future_letter_module: FutureLetterModule) -> None:
        """Module name is 'future_letter'."""
        assert future_letter_module.name == "future_letter"

    def test_pillar(self, future_letter_module: FutureLetterModule) -> None:
        """Module pillar is 'vision_to_task'."""
        assert future_letter_module.pillar == "vision_to_task"

    def test_intents(self, future_letter_module: FutureLetterModule) -> None:
        """Module has expected intents."""
        assert "future_letter.start" in future_letter_module.intents
        assert "future_letter.write" in future_letter_module.intents
