"""
Unit tests for the Review Module.

Tests cover:
- State machine transitions (ACCOMPLISHMENTS -> CHALLENGES -> ENERGY -> REFLECTION -> FORWARD -> DONE)
- Segment-specific reflection prompts (ADHD, Autism, AuDHD, NT)
- GDPR export/delete/freeze/unfreeze
- Task completion check from DailyPlan
- Energy tracking
- Evening workflow auto-trigger
- Edge cases (unknown state, empty input)
- Daily workflow hooks
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.module_context import ModuleContext
from src.core.segment_context import SegmentContext
from src.modules.review import ReviewModule, ReviewStates

# =============================================================================
# Fixtures
# =============================================================================

def _make_ctx(
    segment_code: str = "NT",
    state: str = ReviewStates.ACCOMPLISHMENTS,
    user_id: int = 1,
) -> ModuleContext:
    """Create a ModuleContext for testing."""
    return ModuleContext(
        user_id=user_id,
        segment_context=SegmentContext.from_code(segment_code),  # type: ignore[arg-type]
        state=state,
        session_id="test-session",
        language="en",
        module_name="review",
    )


def _make_mock_db() -> AsyncMock:
    """Create a mock async DB session for testing."""
    mock_db = AsyncMock()
    # Use MagicMock for result so .scalars().all() works synchronously
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result
    return mock_db


@pytest.fixture()
def review_module() -> ReviewModule:
    """Provide a fresh ReviewModule instance with mocked DB session."""
    mock_db = _make_mock_db()
    module = ReviewModule(db_session=mock_db)
    return module


# =============================================================================
# TestReviewStates
# =============================================================================

class TestReviewStates:
    """Test ReviewStates constants."""

    def test_state_values(self) -> None:
        """State values match expected strings."""
        assert ReviewStates.ACCOMPLISHMENTS == "ACCOMPLISHMENTS"
        assert ReviewStates.CHALLENGES == "CHALLENGES"
        assert ReviewStates.ENERGY == "ENERGY"
        assert ReviewStates.REFLECTION == "REFLECTION"
        assert ReviewStates.FORWARD == "FORWARD"
        assert ReviewStates.DONE == "DONE"


# =============================================================================
# TestOnEnter
# =============================================================================

class TestOnEnter:
    """Test ReviewModule.on_enter() for all segments."""

    @pytest.mark.asyncio
    async def test_on_enter_nt(self, review_module: ReviewModule) -> None:
        """NT on_enter returns welcome and starts at ACCOMPLISHMENTS."""
        ctx = _make_ctx("NT")
        response = await review_module.on_enter(ctx)
        assert response.next_state == ReviewStates.ACCOMPLISHMENTS
        assert "review" in response.text.lower() or "accomplish" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_includes_metadata(self, review_module: ReviewModule) -> None:
        """on_enter includes task counts in metadata."""
        ctx = _make_ctx("NT")
        response = await review_module.on_enter(ctx)
        assert "completed_count" in response.metadata
        assert "pending_count" in response.metadata

    @pytest.mark.asyncio
    async def test_on_enter_ad(self, review_module: ReviewModule) -> None:
        """AD on_enter starts review flow."""
        ctx = _make_ctx("AD")
        response = await review_module.on_enter(ctx)
        assert response.next_state == ReviewStates.ACCOMPLISHMENTS

    @pytest.mark.asyncio
    async def test_on_enter_au(self, review_module: ReviewModule) -> None:
        """AU on_enter starts review flow."""
        ctx = _make_ctx("AU")
        response = await review_module.on_enter(ctx)
        assert response.next_state == ReviewStates.ACCOMPLISHMENTS

    @pytest.mark.asyncio
    async def test_on_enter_ah(self, review_module: ReviewModule) -> None:
        """AH on_enter starts review flow."""
        ctx = _make_ctx("AH")
        response = await review_module.on_enter(ctx)
        assert response.next_state == ReviewStates.ACCOMPLISHMENTS


# =============================================================================
# TestStateTransitions
# =============================================================================

class TestStateTransitions:
    """Test full state machine transitions."""

    @pytest.mark.asyncio
    async def test_full_flow_nt(self, review_module: ReviewModule) -> None:
        """Full flow from ACCOMPLISHMENTS to DONE for NT segment."""
        ctx = _make_ctx("NT")
        await review_module.on_enter(ctx)

        # ACCOMPLISHMENTS -> CHALLENGES
        ctx.state = ReviewStates.ACCOMPLISHMENTS
        r = await review_module.handle("I completed my blog post", ctx)
        assert r.next_state == ReviewStates.CHALLENGES

        # CHALLENGES -> ENERGY
        ctx.state = ReviewStates.CHALLENGES
        r = await review_module.handle("I struggled with focus", ctx)
        assert r.next_state == ReviewStates.ENERGY

        # ENERGY -> REFLECTION
        ctx.state = ReviewStates.ENERGY
        r = await review_module.handle("3", ctx)
        assert r.next_state == ReviewStates.REFLECTION

        # REFLECTION -> FORWARD
        ctx.state = ReviewStates.REFLECTION
        r = await review_module.handle("I learned to take breaks", ctx)
        assert r.next_state == ReviewStates.FORWARD

        # FORWARD -> DONE
        ctx.state = ReviewStates.FORWARD
        r = await review_module.handle("Tomorrow I'll start earlier", ctx)
        assert r.is_end_of_flow is True


# =============================================================================
# TestSegmentPrompts
# =============================================================================

class TestSegmentPrompts:
    """Test segment-specific reflection prompts."""

    @pytest.mark.asyncio
    async def test_ad_challenges_prompt(self, review_module: ReviewModule) -> None:
        """AD gets attention-focused challenges prompt."""
        ctx = _make_ctx("AD", state=ReviewStates.CHALLENGES)
        prompt = await review_module._get_segment_prompt(ctx, "challenges")
        assert "attention" in prompt.lower() or "derail" in prompt.lower()

    @pytest.mark.asyncio
    async def test_au_challenges_prompt(self, review_module: ReviewModule) -> None:
        """AU gets sensory/routine challenges prompt."""
        ctx = _make_ctx("AU", state=ReviewStates.CHALLENGES)
        prompt = await review_module._get_segment_prompt(ctx, "challenges")
        assert "sensory" in prompt.lower() or "overwhelm" in prompt.lower()

    @pytest.mark.asyncio
    async def test_ah_challenges_prompt(self, review_module: ReviewModule) -> None:
        """AH gets both attention and sensory challenges prompt."""
        ctx = _make_ctx("AH", state=ReviewStates.CHALLENGES)
        prompt = await review_module._get_segment_prompt(ctx, "challenges")
        assert "attention" in prompt.lower() or "sensory" in prompt.lower()

    @pytest.mark.asyncio
    async def test_ad_energy_prompt(self, review_module: ReviewModule) -> None:
        """AD gets energy spikes prompt."""
        ctx = _make_ctx("AD", state=ReviewStates.ENERGY)
        prompt = await review_module._get_segment_prompt(ctx, "energy")
        assert "spike" in prompt.lower() or "alive" in prompt.lower()

    @pytest.mark.asyncio
    async def test_au_energy_prompt(self, review_module: ReviewModule) -> None:
        """AU gets nervous system/overload prompt."""
        ctx = _make_ctx("AU", state=ReviewStates.ENERGY)
        prompt = await review_module._get_segment_prompt(ctx, "energy")
        assert "nervous system" in prompt.lower() or "overload" in prompt.lower()

    @pytest.mark.asyncio
    async def test_ah_energy_prompt(self, review_module: ReviewModule) -> None:
        """AH gets spoons and channels prompt."""
        ctx = _make_ctx("AH", state=ReviewStates.ENERGY)
        prompt = await review_module._get_segment_prompt(ctx, "energy")
        assert "spoon" in prompt.lower() or "channel" in prompt.lower()


# =============================================================================
# TestAccomplishments
# =============================================================================

class TestAccomplishments:
    """Test accomplishments step."""

    @pytest.mark.asyncio
    async def test_accomplishments_moves_to_challenges(self, review_module: ReviewModule) -> None:
        """ACCOMPLISHMENTS step transitions to CHALLENGES."""
        ctx = _make_ctx("NT", state=ReviewStates.ACCOMPLISHMENTS)
        response = await review_module.handle("I wrote a blog post", ctx)
        assert response.next_state == ReviewStates.CHALLENGES

    @pytest.mark.asyncio
    async def test_accomplishments_stores_metadata(self, review_module: ReviewModule) -> None:
        """ACCOMPLISHMENTS stores user response in metadata."""
        ctx = _make_ctx("NT", state=ReviewStates.ACCOMPLISHMENTS)
        response = await review_module.handle("I wrote a blog post", ctx)
        assert "accomplishments" in response.metadata


# =============================================================================
# TestChallenges
# =============================================================================

class TestChallenges:
    """Test challenges step."""

    @pytest.mark.asyncio
    async def test_challenges_moves_to_energy(self, review_module: ReviewModule) -> None:
        """CHALLENGES step transitions to ENERGY."""
        ctx = _make_ctx("NT", state=ReviewStates.CHALLENGES)
        response = await review_module.handle("I struggled with focus", ctx)
        assert response.next_state == ReviewStates.ENERGY

    @pytest.mark.asyncio
    async def test_challenges_quick_energy_response(self, review_module: ReviewModule) -> None:
        """Quick energy number in CHALLENGES skips to REFLECTION."""
        ctx = _make_ctx("NT", state=ReviewStates.CHALLENGES)
        response = await review_module.handle("3", ctx)
        assert response.next_state == ReviewStates.REFLECTION

    @pytest.mark.asyncio
    async def test_challenges_stores_metadata(self, review_module: ReviewModule) -> None:
        """CHALLENGES stores user response in metadata."""
        ctx = _make_ctx("NT", state=ReviewStates.CHALLENGES)
        response = await review_module.handle("I struggled", ctx)
        assert "challenges" in response.metadata


# =============================================================================
# TestEnergy
# =============================================================================

class TestEnergy:
    """Test energy step."""

    @pytest.mark.asyncio
    async def test_energy_moves_to_reflection(self, review_module: ReviewModule) -> None:
        """ENERGY step transitions to REFLECTION."""
        ctx = _make_ctx("NT", state=ReviewStates.ENERGY)
        response = await review_module.handle("3", ctx)
        assert response.next_state == ReviewStates.REFLECTION

    @pytest.mark.asyncio
    async def test_energy_parses_number(self, review_module: ReviewModule) -> None:
        """ENERGY parses numeric energy value."""
        ctx = _make_ctx("NT", state=ReviewStates.ENERGY)
        response = await review_module.handle("4", ctx)
        assert response.metadata.get("energy_value") == 4

    @pytest.mark.asyncio
    async def test_energy_stores_text_response(self, review_module: ReviewModule) -> None:
        """ENERGY stores non-numeric response."""
        ctx = _make_ctx("NT", state=ReviewStates.ENERGY)
        response = await review_module.handle("I'm feeling drained", ctx)
        assert "energy" in response.metadata


# =============================================================================
# TestReflection
# =============================================================================

class TestReflection:
    """Test reflection step."""

    @pytest.mark.asyncio
    async def test_reflection_moves_to_forward(self, review_module: ReviewModule) -> None:
        """REFLECTION step transitions to FORWARD."""
        ctx = _make_ctx("NT", state=ReviewStates.REFLECTION)
        response = await review_module.handle("I learned to take breaks", ctx)
        assert response.next_state == ReviewStates.FORWARD

    @pytest.mark.asyncio
    async def test_reflection_stores_metadata(self, review_module: ReviewModule) -> None:
        """REFLECTION stores user response in metadata."""
        ctx = _make_ctx("NT", state=ReviewStates.REFLECTION)
        response = await review_module.handle("I learned something", ctx)
        assert "reflection" in response.metadata


# =============================================================================
# TestForward
# =============================================================================

class TestForward:
    """Test forward-looking step."""

    @pytest.mark.asyncio
    async def test_forward_ends_flow(self, review_module: ReviewModule) -> None:
        """FORWARD step ends the flow."""
        ctx = _make_ctx("NT", state=ReviewStates.FORWARD)
        response = await review_module.handle("Tomorrow I'll start earlier", ctx)
        assert response.is_end_of_flow is True

    @pytest.mark.asyncio
    async def test_forward_includes_intention(self, review_module: ReviewModule) -> None:
        """FORWARD includes user's intention in response."""
        ctx = _make_ctx("NT", state=ReviewStates.FORWARD)
        response = await review_module.handle("Tomorrow I'll start earlier", ctx)
        assert "earlier" in response.text.lower()


# =============================================================================
# TestGDPR
# =============================================================================

class TestGDPR:
    """Test GDPR compliance methods."""

    @pytest.mark.asyncio
    async def test_export_returns_dict(self, review_module: ReviewModule) -> None:
        """export_user_data returns expected keys."""
        data = await review_module.export_user_data(user_id=1)
        assert "reviews" in data
        assert "daily_plans" in data

    @pytest.mark.asyncio
    async def test_delete_runs(self, review_module: ReviewModule) -> None:
        """delete_user_data runs without error."""
        await review_module.delete_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_freeze_runs(self, review_module: ReviewModule) -> None:
        """freeze_user_data runs without error."""
        await review_module.freeze_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_unfreeze_runs(self, review_module: ReviewModule) -> None:
        """unfreeze_user_data runs without error."""
        await review_module.unfreeze_user_data(user_id=1)


# =============================================================================
# TestOnExit
# =============================================================================

class TestOnExit:
    """Test session cleanup on module exit."""

    @pytest.mark.asyncio
    async def test_on_exit_runs(self, review_module: ReviewModule) -> None:
        """on_exit runs without error."""
        ctx = _make_ctx("NT", user_id=99)
        await review_module.on_exit(ctx)


# =============================================================================
# TestDailyWorkflowHooks
# =============================================================================

class TestDailyWorkflowHooks:
    """Test daily workflow hooks."""

    def test_hooks_defined(self, review_module: ReviewModule) -> None:
        """Review module defines evening_review hook."""
        hooks = review_module.get_daily_workflow_hooks()
        assert hooks.evening_review is not None
        assert hooks.hook_name == "review"
        assert hooks.priority == 10


# =============================================================================
# TestUnknownState
# =============================================================================

class TestUnknownState:
    """Test handling of unknown states."""

    @pytest.mark.asyncio
    async def test_unknown_state_restarts(self, review_module: ReviewModule) -> None:
        """Unknown state triggers on_enter (restart)."""
        ctx = _make_ctx("NT", state="NONEXISTENT")
        response = await review_module.handle("hello", ctx)
        assert response.next_state == ReviewStates.ACCOMPLISHMENTS


# =============================================================================
# TestModuleIdentity
# =============================================================================

class TestModuleIdentity:
    """Test module identity attributes."""

    def test_name(self, review_module: ReviewModule) -> None:
        """Module name is 'review'."""
        assert review_module.name == "review"

    def test_pillar(self, review_module: ReviewModule) -> None:
        """Module pillar is 'vision_to_task'."""
        assert review_module.pillar == "vision_to_task"

    def test_intents(self, review_module: ReviewModule) -> None:
        """Module has expected intents."""
        assert "review.start" in review_module.intents
        assert "review.accomplishments" in review_module.intents
        assert "review.challenges" in review_module.intents


# =============================================================================
# TestHelperMethods
# =============================================================================

class TestHelperMethods:
    """Test helper methods."""

    def test_t_helper_fallback(self, review_module: ReviewModule) -> None:
        """_t helper falls back to 'en' for invalid language."""
        # Test with invalid language code
        result = review_module._t("xx", "review", "welcome_no_tasks")
        assert isinstance(result, str)
        assert len(result) > 0
