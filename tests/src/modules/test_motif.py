"""
Unit tests for the Landscape of Motifs Module.

Tests cover:
- State machine transitions (EXPLORE -> DETECT -> MAP -> REFLECT -> DONE)
- Segment-specific behavior (ADHD, Autism, AuDHD, NT)
- GDPR export/delete/freeze/unfreeze
- Model creation (Motif, MotifSignal)
- Helper methods (detect_motifs_from_text, confidence calculation, landscape building)
- Passion archaeology
- Edge cases (unknown state, empty input, no motifs detected)
- Daily workflow hooks
"""

from __future__ import annotations

import pytest

from src.core.module_context import ModuleContext
from src.core.segment_context import SegmentContext
from src.modules.motif import (
    MOTIF_TYPES,
    SIGNAL_SOURCES,
    Motif,
    MotifExplorationSession,
    MotifModule,
    MotifSignal,
    MotifState,
)

# =============================================================================
# Fixtures
# =============================================================================

def _make_ctx(
    segment_code: str = "NT",
    state: str = MotifState.EXPLORE,
    user_id: int = 1,
) -> ModuleContext:
    """Create a ModuleContext for testing."""
    return ModuleContext(
        user_id=user_id,
        segment_context=SegmentContext.from_code(segment_code),  # type: ignore[arg-type]
        state=state,
        session_id="test-session",
        language="en",
        module_name="motif",
    )


@pytest.fixture()
def motif_module() -> MotifModule:
    """Provide a fresh MotifModule instance."""
    return MotifModule()


# =============================================================================
# TestMotifState
# =============================================================================

class TestMotifState:
    """Test MotifState constants."""

    def test_all_states_defined(self) -> None:
        """All 5 states are defined."""
        assert len(MotifState.ALL) == 5

    def test_state_values(self) -> None:
        """State values match expected strings."""
        assert MotifState.EXPLORE == "EXPLORE"
        assert MotifState.DETECT == "DETECT"
        assert MotifState.MAP == "MAP"
        assert MotifState.REFLECT == "REFLECT"
        assert MotifState.DONE == "DONE"


# =============================================================================
# TestMotifTypes
# =============================================================================

class TestMotifTypes:
    """Test motif type and signal source constants."""

    def test_six_motif_types(self) -> None:
        """There are 6 motif types."""
        assert len(MOTIF_TYPES) == 6
        assert "drive" in MOTIF_TYPES
        assert "talent" in MOTIF_TYPES
        assert "passion" in MOTIF_TYPES
        assert "fear" in MOTIF_TYPES
        assert "avoidance" in MOTIF_TYPES
        assert "attraction" in MOTIF_TYPES

    def test_five_signal_sources(self) -> None:
        """There are 5 signal sources."""
        assert len(SIGNAL_SOURCES) == 5
        assert "aurora" in SIGNAL_SOURCES
        assert "user_input" in SIGNAL_SOURCES


# =============================================================================
# TestOnEnter
# =============================================================================

class TestOnEnter:
    """Test MotifModule.on_enter() for all segments."""

    @pytest.mark.asyncio
    async def test_on_enter_nt(self, motif_module: MotifModule) -> None:
        """NT on_enter returns standard message and EXPLORE state."""
        ctx = _make_ctx("NT")
        response = await motif_module.on_enter(ctx)
        assert response.next_state == MotifState.EXPLORE
        assert "motif" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_ad(self, motif_module: MotifModule) -> None:
        """AD on_enter uses discovery-focused language."""
        ctx = _make_ctx("AD")
        response = await motif_module.on_enter(ctx)
        assert response.next_state == MotifState.EXPLORE
        assert "discover" in response.text.lower() or "archaeology" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_au(self, motif_module: MotifModule) -> None:
        """AU on_enter uses structured language with numbered steps."""
        ctx = _make_ctx("AU")
        response = await motif_module.on_enter(ctx)
        assert response.next_state == MotifState.EXPLORE
        assert "1." in response.text  # Numbered steps

    @pytest.mark.asyncio
    async def test_on_enter_ah(self, motif_module: MotifModule) -> None:
        """AH on_enter references channels."""
        ctx = _make_ctx("AH")
        response = await motif_module.on_enter(ctx)
        assert response.next_state == MotifState.EXPLORE
        assert "channel" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_creates_session(self, motif_module: MotifModule) -> None:
        """on_enter creates a session for the user."""
        ctx = _make_ctx("NT", user_id=42)
        await motif_module.on_enter(ctx)
        assert 42 in motif_module._sessions


# =============================================================================
# TestExploreState
# =============================================================================

class TestExploreState:
    """Test EXPLORE state handler."""

    @pytest.mark.asyncio
    async def test_explore_with_passion_keyword(self, motif_module: MotifModule) -> None:
        """Passion archaeology triggered by keyword."""
        ctx = _make_ctx("NT", state=MotifState.EXPLORE)
        motif_module._sessions[ctx.user_id] = MotifExplorationSession()
        r = await motif_module.handle("Let's do passion archaeology", ctx)
        assert r.next_state == MotifState.DETECT
        assert "past" in r.text.lower() or "childhood" in r.text.lower()

    @pytest.mark.asyncio
    async def test_explore_with_motif_keywords(self, motif_module: MotifModule) -> None:
        """Motifs detected from keywords in user input."""
        ctx = _make_ctx("NT", state=MotifState.EXPLORE)
        motif_module._sessions[ctx.user_id] = MotifExplorationSession()
        r = await motif_module.handle("I love painting and I'm afraid of failure", ctx)
        assert r.next_state == MotifState.DETECT
        assert "motif" in r.text.lower() or "detect" in r.text.lower()

    @pytest.mark.asyncio
    async def test_explore_no_motifs(self, motif_module: MotifModule) -> None:
        """No motifs detected prompts for more information."""
        ctx = _make_ctx("NT", state=MotifState.EXPLORE)
        motif_module._sessions[ctx.user_id] = MotifExplorationSession()
        r = await motif_module.handle("I had breakfast today", ctx)
        assert r.next_state == MotifState.DETECT
        assert "time" in r.text.lower() or "topics" in r.text.lower()


# =============================================================================
# TestDetectState
# =============================================================================

class TestDetectState:
    """Test DETECT state handler."""

    @pytest.mark.asyncio
    async def test_detect_with_motifs(self, motif_module: MotifModule) -> None:
        """DETECT with new motifs moves to MAP."""
        ctx = _make_ctx("NT", state=MotifState.DETECT)
        motif_module._sessions[ctx.user_id] = MotifExplorationSession(
            detected_motifs=[{"name": "Creating", "type": "passion"}],
        )
        r = await motif_module.handle("I'm also drawn to music", ctx)
        assert r.next_state == MotifState.MAP

    @pytest.mark.asyncio
    async def test_detect_no_motifs_triggers_archaeology(self, motif_module: MotifModule) -> None:
        """DETECT with no motifs at all triggers passion archaeology."""
        ctx = _make_ctx("NT", state=MotifState.DETECT)
        motif_module._sessions[ctx.user_id] = MotifExplorationSession()
        r = await motif_module.handle("Just normal stuff", ctx)
        assert r.next_state == MotifState.DETECT
        assert "past" in r.text.lower() or "childhood" in r.text.lower()


# =============================================================================
# TestMapState
# =============================================================================

class TestMapState:
    """Test MAP state handler."""

    @pytest.mark.asyncio
    async def test_map_creates_landscape(self, motif_module: MotifModule) -> None:
        """MAP state creates a landscape visualization."""
        ctx = _make_ctx("NT", state=MotifState.MAP)
        motif_module._sessions[ctx.user_id] = MotifExplorationSession(
            detected_motifs=[
                {"name": "Creating art", "type": "passion"},
                {"name": "Public speaking", "type": "fear"},
            ],
        )
        r = await motif_module.handle("5 for creating, 3 for fear", ctx)
        assert r.next_state == MotifState.REFLECT
        assert "Landscape" in r.text or "landscape" in r.text.lower()


# =============================================================================
# TestReflectState
# =============================================================================

class TestReflectState:
    """Test REFLECT state handler."""

    @pytest.mark.asyncio
    async def test_reflect_saves_and_ends(self, motif_module: MotifModule) -> None:
        """REFLECT state saves motifs and ends flow."""
        ctx = _make_ctx("NT", state=MotifState.REFLECT)
        motif_module._sessions[ctx.user_id] = MotifExplorationSession(
            mapped_motifs=[{"name": "Creating", "type": "passion", "confidence": "0.8"}],
        )
        r = await motif_module.handle("I notice creating is central to who I am", ctx)
        assert r.is_end_of_flow is True
        assert r.next_state == MotifState.DONE
        assert r.side_effects is not None
        assert len(r.side_effects) == 1


# =============================================================================
# TestMotifDetection
# =============================================================================

class TestMotifDetection:
    """Test motif detection from text."""

    def test_detect_passion(self, motif_module: MotifModule) -> None:
        """Passion keywords detected."""
        result = motif_module._detect_motifs_from_text("I love painting")
        types = [m["type"] for m in result]
        assert "passion" in types

    def test_detect_fear(self, motif_module: MotifModule) -> None:
        """Fear keywords detected."""
        result = motif_module._detect_motifs_from_text("I'm afraid of rejection")
        types = [m["type"] for m in result]
        assert "fear" in types

    def test_detect_drive(self, motif_module: MotifModule) -> None:
        """Drive keywords detected."""
        result = motif_module._detect_motifs_from_text("I feel compelled to create")
        types = [m["type"] for m in result]
        assert "drive" in types

    def test_detect_talent(self, motif_module: MotifModule) -> None:
        """Talent keywords detected."""
        result = motif_module._detect_motifs_from_text("I'm good at explaining things")
        types = [m["type"] for m in result]
        assert "talent" in types

    def test_detect_avoidance(self, motif_module: MotifModule) -> None:
        """Avoidance keywords detected."""
        result = motif_module._detect_motifs_from_text("I always avoid conflict")
        types = [m["type"] for m in result]
        assert "avoidance" in types

    def test_detect_attraction(self, motif_module: MotifModule) -> None:
        """Attraction keywords detected."""
        result = motif_module._detect_motifs_from_text("I'm drawn to music")
        types = [m["type"] for m in result]
        assert "attraction" in types

    def test_detect_multiple(self, motif_module: MotifModule) -> None:
        """Multiple motif types detected from same text."""
        result = motif_module._detect_motifs_from_text(
            "I love coding and I'm afraid of public speaking"
        )
        types = [m["type"] for m in result]
        assert "passion" in types
        assert "fear" in types

    def test_no_motifs_detected(self, motif_module: MotifModule) -> None:
        """No motifs detected from neutral text."""
        result = motif_module._detect_motifs_from_text("The weather is nice today")
        assert len(result) == 0


# =============================================================================
# TestConfidenceCalculation
# =============================================================================

class TestConfidenceCalculation:
    """Test confidence score calculation."""

    def test_zero_signals(self) -> None:
        """Zero signals returns 0.0."""
        assert MotifModule.calculate_confidence(0) == 0.0

    def test_negative_signals(self) -> None:
        """Negative signals returns 0.0."""
        assert MotifModule.calculate_confidence(-1) == 0.0

    def test_one_signal(self) -> None:
        """One signal returns low confidence."""
        result = MotifModule.calculate_confidence(1)
        assert 0.0 < result < 0.5

    def test_five_signals(self) -> None:
        """Five signals returns medium confidence."""
        result = MotifModule.calculate_confidence(5)
        assert 0.5 < result < 0.9

    def test_twenty_signals(self) -> None:
        """Twenty signals returns high confidence."""
        result = MotifModule.calculate_confidence(20)
        assert result > 0.7

    def test_monotonic_increase(self) -> None:
        """Confidence monotonically increases with signal count."""
        prev = 0.0
        for n in range(1, 20):
            current = MotifModule.calculate_confidence(n)
            assert current > prev
            prev = current

    def test_max_clamp(self) -> None:
        """Confidence never exceeds 1.0."""
        result = MotifModule.calculate_confidence(1000)
        assert result <= 1.0


# =============================================================================
# TestConfidenceBar
# =============================================================================

class TestConfidenceBar:
    """Test confidence bar visualization."""

    def test_zero_confidence(self) -> None:
        """Zero confidence shows empty bar."""
        assert MotifModule._confidence_bar(0.0) == "[     ]"

    def test_full_confidence(self) -> None:
        """Full confidence shows full bar."""
        assert MotifModule._confidence_bar(1.0) == "[=====]"

    def test_half_confidence(self) -> None:
        """Half confidence shows partial bar."""
        result = MotifModule._confidence_bar(0.5)
        assert "==" in result
        assert " " in result


# =============================================================================
# TestLandscapeBuilding
# =============================================================================

class TestLandscapeBuilding:
    """Test landscape text visualization."""

    def test_empty_motifs(self, motif_module: MotifModule) -> None:
        """Empty motifs list returns placeholder."""
        result = motif_module._build_landscape_text([])
        assert "No motifs" in result

    def test_grouped_by_type(self, motif_module: MotifModule) -> None:
        """Motifs are grouped by type in landscape."""
        motifs = [
            {"name": "Creating", "type": "passion", "confidence": "0.8"},
            {"name": "Teaching", "type": "talent", "confidence": "0.6"},
        ]
        result = motif_module._build_landscape_text(motifs)
        assert "Passion" in result
        assert "Talent" in result


# =============================================================================
# TestGDPR
# =============================================================================

class TestGDPR:
    """Test GDPR compliance methods."""

    @pytest.mark.asyncio
    async def test_export_returns_dict(self, motif_module: MotifModule) -> None:
        """export_user_data returns expected keys."""
        data = await motif_module.export_user_data(user_id=1)
        assert "motifs" in data
        assert "motif_signals" in data

    @pytest.mark.asyncio
    async def test_delete_runs(self, motif_module: MotifModule) -> None:
        """delete_user_data runs without error."""
        await motif_module.delete_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_freeze_runs(self, motif_module: MotifModule) -> None:
        """freeze_user_data runs without error."""
        await motif_module.freeze_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_unfreeze_runs(self, motif_module: MotifModule) -> None:
        """unfreeze_user_data runs without error."""
        await motif_module.unfreeze_user_data(user_id=1)


# =============================================================================
# TestOnExit
# =============================================================================

class TestOnExit:
    """Test session cleanup on module exit."""

    @pytest.mark.asyncio
    async def test_on_exit_cleans_session(self, motif_module: MotifModule) -> None:
        """on_exit removes the user's session."""
        ctx = _make_ctx("NT", user_id=99)
        await motif_module.on_enter(ctx)
        assert 99 in motif_module._sessions
        await motif_module.on_exit(ctx)
        assert 99 not in motif_module._sessions


# =============================================================================
# TestDailyWorkflowHooks
# =============================================================================

class TestDailyWorkflowHooks:
    """Test daily workflow hooks."""

    def test_hooks_defined(self, motif_module: MotifModule) -> None:
        """Motif module defines planning_enrichment hook."""
        hooks = motif_module.get_daily_workflow_hooks()
        assert hooks.planning_enrichment is not None
        assert hooks.hook_name == "motif"
        assert hooks.priority == 40


# =============================================================================
# TestUnknownState
# =============================================================================

class TestUnknownState:
    """Test handling of unknown states."""

    @pytest.mark.asyncio
    async def test_unknown_state_restarts(self, motif_module: MotifModule) -> None:
        """Unknown state triggers on_enter (restart)."""
        ctx = _make_ctx("NT", state="NONEXISTENT")
        response = await motif_module.handle("hello", ctx)
        assert response.next_state == MotifState.EXPLORE


# =============================================================================
# TestModuleIdentity
# =============================================================================

class TestModuleIdentity:
    """Test module identity attributes."""

    def test_name(self, motif_module: MotifModule) -> None:
        """Module name is 'motif'."""
        assert motif_module.name == "motif"

    def test_pillar(self, motif_module: MotifModule) -> None:
        """Module pillar is 'second_brain'."""
        assert motif_module.pillar == "second_brain"

    def test_intents(self, motif_module: MotifModule) -> None:
        """Module has expected intents."""
        assert "motif.explore" in motif_module.intents
        assert "motif.archaeology" in motif_module.intents


# =============================================================================
# TestMotifModel
# =============================================================================

class TestMotifModel:
    """Test Motif SQLAlchemy model."""

    def test_tablename(self) -> None:
        """Motif model has correct tablename."""
        assert Motif.__tablename__ == "motifs"

    def test_signal_tablename(self) -> None:
        """MotifSignal model has correct tablename."""
        assert MotifSignal.__tablename__ == "motif_signals"
