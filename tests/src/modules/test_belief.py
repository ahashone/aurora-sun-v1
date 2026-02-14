"""
Unit tests for the Limiting Beliefs Module.

Tests cover:
- State machine transitions (SURFACE -> IDENTIFY -> EVIDENCE_FOR -> EVIDENCE_AGAINST -> CHALLENGE -> REFRAME -> TRACK -> DONE)
- Segment-specific behavior (ADHD, Autism, AuDHD, NT)
- GDPR export/delete/freeze/unfreeze
- Model creation (Belief, BeliefEvidence)
- Helper methods (classify_belief, parse_evidence, ContradictionIndex)
- Edge cases (unknown state, empty input, empowering beliefs)
- Daily workflow hooks
"""

from __future__ import annotations

import pytest

from src.core.module_context import ModuleContext
from src.core.segment_context import SegmentContext
from src.modules.belief import (
    Belief,
    BeliefEvidence,
    BeliefModule,
    BeliefSession,
    BeliefState,
)

# =============================================================================
# Fixtures
# =============================================================================

def _make_ctx(
    segment_code: str = "NT",
    state: str = BeliefState.SURFACE,
    user_id: int = 1,
) -> ModuleContext:
    """Create a ModuleContext for testing."""
    return ModuleContext(
        user_id=user_id,
        segment_context=SegmentContext.from_code(segment_code),  # type: ignore[arg-type]
        state=state,
        session_id="test-session",
        language="en",
        module_name="belief",
    )


@pytest.fixture()
def belief_module() -> BeliefModule:
    """Provide a fresh BeliefModule instance."""
    return BeliefModule()


# =============================================================================
# TestBeliefState
# =============================================================================

class TestBeliefState:
    """Test BeliefState constants."""

    def test_all_states_defined(self) -> None:
        """All 8 states are defined."""
        assert len(BeliefState.ALL) == 8

    def test_state_values(self) -> None:
        """State values match expected strings."""
        assert BeliefState.SURFACE == "SURFACE"
        assert BeliefState.IDENTIFY == "IDENTIFY"
        assert BeliefState.EVIDENCE_FOR == "EVIDENCE_FOR"
        assert BeliefState.EVIDENCE_AGAINST == "EVIDENCE_AGAINST"
        assert BeliefState.CHALLENGE == "CHALLENGE"
        assert BeliefState.REFRAME == "REFRAME"
        assert BeliefState.TRACK == "TRACK"
        assert BeliefState.DONE == "DONE"


# =============================================================================
# TestOnEnter
# =============================================================================

class TestOnEnter:
    """Test BeliefModule.on_enter() for all segments."""

    @pytest.mark.asyncio
    async def test_on_enter_nt(self, belief_module: BeliefModule) -> None:
        """NT on_enter returns standard message and SURFACE state."""
        ctx = _make_ctx("NT")
        response = await belief_module.on_enter(ctx)
        assert response.next_state == BeliefState.SURFACE
        assert "belief" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_ad(self, belief_module: BeliefModule) -> None:
        """AD on_enter uses engaging language."""
        ctx = _make_ctx("AD")
        response = await belief_module.on_enter(ctx)
        assert response.next_state == BeliefState.SURFACE
        assert "challenge" in response.text.lower() or "powerful" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_au(self, belief_module: BeliefModule) -> None:
        """AU on_enter uses structured language."""
        ctx = _make_ctx("AU")
        response = await belief_module.on_enter(ctx)
        assert response.next_state == BeliefState.SURFACE
        assert "structured" in response.text.lower() or "process" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_ah(self, belief_module: BeliefModule) -> None:
        """AH on_enter references energy/pace."""
        ctx = _make_ctx("AH")
        response = await belief_module.on_enter(ctx)
        assert response.next_state == BeliefState.SURFACE
        assert "pace" in response.text.lower() or "energy" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_creates_session(self, belief_module: BeliefModule) -> None:
        """on_enter creates a session for the user."""
        ctx = _make_ctx("NT", user_id=42)
        await belief_module.on_enter(ctx)
        assert 42 in belief_module._sessions


# =============================================================================
# TestStateTransitions
# =============================================================================

class TestStateTransitions:
    """Test full state machine transitions."""

    @pytest.mark.asyncio
    async def test_full_flow_nt(self, belief_module: BeliefModule) -> None:
        """Full flow from SURFACE to TRACK for NT segment."""
        ctx = _make_ctx("NT")
        await belief_module.on_enter(ctx)

        # SURFACE -> IDENTIFY (limiting belief)
        ctx.state = BeliefState.SURFACE
        r = await belief_module.handle("I can't succeed at anything", ctx)
        assert r.next_state == BeliefState.IDENTIFY

        # IDENTIFY -> EVIDENCE_FOR
        ctx.state = BeliefState.IDENTIFY
        r = await belief_module.handle("yes, let's explore this", ctx)
        assert r.next_state == BeliefState.EVIDENCE_FOR

        # EVIDENCE_FOR -> EVIDENCE_AGAINST
        ctx.state = BeliefState.EVIDENCE_FOR
        r = await belief_module.handle("I failed my exam\nI got rejected from a job", ctx)
        assert r.next_state == BeliefState.EVIDENCE_AGAINST

        # EVIDENCE_AGAINST -> CHALLENGE
        ctx.state = BeliefState.EVIDENCE_AGAINST
        r = await belief_module.handle("I graduated university\nI got my current job", ctx)
        assert r.next_state == BeliefState.CHALLENGE
        assert "contradiction" in r.text.lower() or "index" in r.text.lower()

        # CHALLENGE -> REFRAME
        ctx.state = BeliefState.CHALLENGE
        r = await belief_module.handle("I realize I have both successes and failures", ctx)
        assert r.next_state == BeliefState.REFRAME

        # REFRAME -> TRACK
        ctx.state = BeliefState.REFRAME
        r = await belief_module.handle("I can succeed when I apply consistent effort", ctx)
        assert r.next_state == BeliefState.TRACK
        assert "save" in r.text.lower()

    @pytest.mark.asyncio
    async def test_track_confirm_saves(self, belief_module: BeliefModule) -> None:
        """Confirming in TRACK saves the belief and ends flow."""
        ctx = _make_ctx("NT", state=BeliefState.TRACK)
        belief_module._sessions[ctx.user_id] = BeliefSession(
            belief_text="I can't do this",
            belief_type="limiting",
            evidence_for=["failed once"],
            evidence_against=["succeeded twice"],
            reframe="I can learn and improve",
        )
        r = await belief_module.handle("yes", ctx)
        assert r.is_end_of_flow is True
        assert r.next_state == BeliefState.DONE
        assert r.side_effects is not None
        assert len(r.side_effects) == 1

    @pytest.mark.asyncio
    async def test_track_cancel(self, belief_module: BeliefModule) -> None:
        """Cancelling in TRACK ends flow without side effects."""
        ctx = _make_ctx("NT", state=BeliefState.TRACK)
        belief_module._sessions[ctx.user_id] = BeliefSession(belief_text="Test")
        r = await belief_module.handle("no", ctx)
        assert r.is_end_of_flow is True
        assert r.side_effects is None

    @pytest.mark.asyncio
    async def test_track_ambiguous_reprompts(self, belief_module: BeliefModule) -> None:
        """Ambiguous input in TRACK re-prompts."""
        ctx = _make_ctx("NT", state=BeliefState.TRACK)
        belief_module._sessions[ctx.user_id] = BeliefSession(belief_text="Test")
        r = await belief_module.handle("maybe", ctx)
        assert r.next_state == BeliefState.TRACK


# =============================================================================
# TestEmpoweringBelief
# =============================================================================

class TestEmpoweringBelief:
    """Test handling of empowering beliefs."""

    @pytest.mark.asyncio
    async def test_empowering_belief_detected(self, belief_module: BeliefModule) -> None:
        """Empowering beliefs are detected and offered alternative flow."""
        ctx = _make_ctx("NT", state=BeliefState.SURFACE)
        belief_module._sessions[ctx.user_id] = BeliefSession()
        r = await belief_module.handle("I am capable of great things", ctx)
        assert "positive" in r.text.lower() or "empowering" in r.text.lower()


# =============================================================================
# TestContradictionIndex
# =============================================================================

class TestContradictionIndex:
    """Test ContradictionIndex calculation."""

    def test_zero_evidence(self) -> None:
        """Zero total evidence returns 0.0."""
        assert BeliefModule.calculate_contradiction_index(0, 0) == 0.0

    def test_only_supporting(self) -> None:
        """Only supporting evidence returns 0.0."""
        assert BeliefModule.calculate_contradiction_index(5, 0) == 0.0

    def test_only_contradicting(self) -> None:
        """Only contradicting evidence returns 1.0."""
        assert BeliefModule.calculate_contradiction_index(0, 5) == 1.0

    def test_equal_evidence(self) -> None:
        """Equal supporting and contradicting returns 0.5."""
        assert BeliefModule.calculate_contradiction_index(3, 3) == 0.5

    def test_more_contradicting(self) -> None:
        """More contradicting than supporting returns > 0.5."""
        result = BeliefModule.calculate_contradiction_index(2, 8)
        assert result == 0.8

    def test_more_supporting(self) -> None:
        """More supporting than contradicting returns < 0.5."""
        result = BeliefModule.calculate_contradiction_index(8, 2)
        assert result == 0.2


# =============================================================================
# TestClassifyBelief
# =============================================================================

class TestClassifyBelief:
    """Test belief classification."""

    def test_limiting_keywords(self, belief_module: BeliefModule) -> None:
        """Limiting keywords classify as limiting."""
        assert belief_module._classify_belief("I can't do anything right") == "limiting"
        assert belief_module._classify_belief("It's impossible for me") == "limiting"
        assert belief_module._classify_belief("I'm not good enough") == "limiting"

    def test_empowering_keywords(self, belief_module: BeliefModule) -> None:
        """Empowering keywords classify as empowering."""
        assert belief_module._classify_belief("I am capable of anything") == "empowering"
        assert belief_module._classify_belief("I can learn and grow") == "empowering"

    def test_neutral_defaults_to_limiting(self, belief_module: BeliefModule) -> None:
        """Neutral text defaults to limiting."""
        assert belief_module._classify_belief("The sky is blue") == "limiting"


# =============================================================================
# TestParseEvidence
# =============================================================================

class TestParseEvidence:
    """Test evidence parsing."""

    def test_newline_separated(self, belief_module: BeliefModule) -> None:
        """Evidence items separated by newlines."""
        result = belief_module._parse_evidence("First thing\nSecond thing\nThird thing")
        assert len(result) == 3

    def test_numbered_list(self, belief_module: BeliefModule) -> None:
        """Numbered list items are parsed."""
        result = belief_module._parse_evidence("1. First\n2. Second\n3. Third")
        assert len(result) == 3

    def test_bullet_list(self, belief_module: BeliefModule) -> None:
        """Bullet list items are parsed."""
        result = belief_module._parse_evidence("- First\n- Second")
        assert len(result) == 2

    def test_single_item(self, belief_module: BeliefModule) -> None:
        """Single evidence item without line breaks."""
        result = belief_module._parse_evidence("I failed once")
        assert len(result) == 1
        assert result[0] == "I failed once"

    def test_empty_input(self, belief_module: BeliefModule) -> None:
        """Empty input returns empty list."""
        result = belief_module._parse_evidence("")
        assert len(result) == 0

    def test_short_items_filtered(self, belief_module: BeliefModule) -> None:
        """Very short items (2 chars or less) are filtered out."""
        result = belief_module._parse_evidence("OK\nno\nThis is valid evidence")
        assert len(result) == 1


# =============================================================================
# TestSegmentSpecificBehavior
# =============================================================================

class TestSegmentSpecificBehavior:
    """Test segment-specific behavior in state handlers."""

    @pytest.mark.asyncio
    async def test_au_evidence_against_structured(self, belief_module: BeliefModule) -> None:
        """AU segment gets structured evidence summary."""
        ctx = _make_ctx("AU", state=BeliefState.EVIDENCE_AGAINST)
        belief_module._sessions[ctx.user_id] = BeliefSession(
            belief_text="I can't learn new things",
            evidence_for=["Struggled with math"],
        )
        r = await belief_module.handle("Learned to cook last year", ctx)
        assert "Supporting" in r.text or "Contradicting" in r.text

    @pytest.mark.asyncio
    async def test_ad_evidence_against_engaging(self, belief_module: BeliefModule) -> None:
        """AD segment gets engaging evidence presentation."""
        ctx = _make_ctx("AD", state=BeliefState.EVIDENCE_AGAINST)
        belief_module._sessions[ctx.user_id] = BeliefSession(
            belief_text="I never finish things",
            evidence_for=["Left project X"],
        )
        r = await belief_module.handle("Finished my degree", ctx)
        assert "Interesting" in r.text or "interesting" in r.text.lower()


# =============================================================================
# TestGDPR
# =============================================================================

class TestGDPR:
    """Test GDPR compliance methods."""

    @pytest.mark.asyncio
    async def test_export_returns_dict(self, belief_module: BeliefModule) -> None:
        """export_user_data returns expected keys."""
        data = await belief_module.export_user_data(user_id=1)
        assert "beliefs" in data
        assert "belief_evidence" in data

    @pytest.mark.asyncio
    async def test_delete_runs(self, belief_module: BeliefModule) -> None:
        """delete_user_data runs without error."""
        await belief_module.delete_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_freeze_runs(self, belief_module: BeliefModule) -> None:
        """freeze_user_data runs without error."""
        await belief_module.freeze_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_unfreeze_runs(self, belief_module: BeliefModule) -> None:
        """unfreeze_user_data runs without error."""
        await belief_module.unfreeze_user_data(user_id=1)


# =============================================================================
# TestOnExit
# =============================================================================

class TestOnExit:
    """Test session cleanup on module exit."""

    @pytest.mark.asyncio
    async def test_on_exit_cleans_session(self, belief_module: BeliefModule) -> None:
        """on_exit removes the user's session."""
        ctx = _make_ctx("NT", user_id=99)
        await belief_module.on_enter(ctx)
        assert 99 in belief_module._sessions
        await belief_module.on_exit(ctx)
        assert 99 not in belief_module._sessions


# =============================================================================
# TestDailyWorkflowHooks
# =============================================================================

class TestDailyWorkflowHooks:
    """Test daily workflow hooks."""

    def test_hooks_defined(self, belief_module: BeliefModule) -> None:
        """Belief module defines planning_enrichment hook."""
        hooks = belief_module.get_daily_workflow_hooks()
        assert hooks.planning_enrichment is not None
        assert hooks.hook_name == "belief"
        assert hooks.priority == 30


# =============================================================================
# TestUnknownState
# =============================================================================

class TestUnknownState:
    """Test handling of unknown states."""

    @pytest.mark.asyncio
    async def test_unknown_state_restarts(self, belief_module: BeliefModule) -> None:
        """Unknown state triggers on_enter (restart)."""
        ctx = _make_ctx("NT", state="NONEXISTENT")
        response = await belief_module.handle("hello", ctx)
        assert response.next_state == BeliefState.SURFACE


# =============================================================================
# TestModuleIdentity
# =============================================================================

class TestModuleIdentity:
    """Test module identity attributes."""

    def test_name(self, belief_module: BeliefModule) -> None:
        """Module name is 'belief'."""
        assert belief_module.name == "belief"

    def test_pillar(self, belief_module: BeliefModule) -> None:
        """Module pillar is 'second_brain'."""
        assert belief_module.pillar == "second_brain"

    def test_intents(self, belief_module: BeliefModule) -> None:
        """Module has expected intents."""
        assert "belief.surface" in belief_module.intents
        assert "belief.challenge" in belief_module.intents


# =============================================================================
# TestBeliefModel
# =============================================================================

class TestBeliefModel:
    """Test Belief SQLAlchemy model."""

    def test_tablename(self) -> None:
        """Belief model has correct tablename."""
        assert Belief.__tablename__ == "beliefs"

    def test_evidence_tablename(self) -> None:
        """BeliefEvidence model has correct tablename."""
        assert BeliefEvidence.__tablename__ == "belief_evidence"
