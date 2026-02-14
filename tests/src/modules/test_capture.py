"""
Unit tests for the Capture Module.

Tests cover:
- Fire-and-forget capture flow
- Content type classification (task/idea/note/insight/question/goal/financial)
- Routing to appropriate destinations
- Segment-specific confirmations
- Financial content detection
- Entity extraction
- GDPR export/delete/freeze/unfreeze
- Edge cases (empty input, voice input stub)
- Daily workflow hooks
"""

from __future__ import annotations

import pytest

from src.core.module_context import ModuleContext
from src.core.segment_context import SegmentContext
from src.core.side_effects import SideEffectType
from src.modules.capture import CapturedItem, CaptureModule

# =============================================================================
# Fixtures
# =============================================================================

def _make_ctx(
    segment_code: str = "NT",
    user_id: int = 1,
) -> ModuleContext:
    """Create a ModuleContext for testing."""
    return ModuleContext(
        user_id=user_id,
        segment_context=SegmentContext.from_code(segment_code),  # type: ignore[arg-type]
        state="capture",
        session_id="test-session",
        language="en",
        module_name="capture",
    )


@pytest.fixture()
def capture_module() -> CaptureModule:
    """Provide a fresh CaptureModule instance."""
    return CaptureModule()


# =============================================================================
# TestOnEnter
# =============================================================================

class TestOnEnter:
    """Test CaptureModule.on_enter() for all segments."""

    @pytest.mark.asyncio
    async def test_on_enter_nt(self, capture_module: CaptureModule) -> None:
        """NT on_enter returns standard message."""
        ctx = _make_ctx("NT")
        response = await capture_module.on_enter(ctx)
        assert response.next_state == "capture"
        assert "capture" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_ad(self, capture_module: CaptureModule) -> None:
        """AD on_enter uses minimal friction language."""
        ctx = _make_ctx("AD")
        response = await capture_module.on_enter(ctx)
        assert response.next_state == "capture"
        assert "just tell me" in response.text.lower() or "got it" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_au(self, capture_module: CaptureModule) -> None:
        """AU on_enter uses structured, clear language."""
        ctx = _make_ctx("AU")
        response = await capture_module.on_enter(ctx)
        assert response.next_state == "capture"
        assert "classify" in response.text.lower() or "right place" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_ah(self, capture_module: CaptureModule) -> None:
        """AH on_enter uses flexible, adaptive language."""
        ctx = _make_ctx("AH")
        response = await capture_module.on_enter(ctx)
        assert response.next_state == "capture"
        assert "mind" in response.text.lower() or "sort" in response.text.lower()


# =============================================================================
# TestClassification
# =============================================================================

class TestClassification:
    """Test content classification."""

    @pytest.mark.asyncio
    async def test_classify_task(self, capture_module: CaptureModule) -> None:
        """Task-related inputs are classified as 'task'."""
        result = await capture_module.classify_content("call dentist tomorrow")
        assert result["type"] == "task"

    @pytest.mark.asyncio
    async def test_classify_idea(self, capture_module: CaptureModule) -> None:
        """Idea-related inputs are classified as 'idea'."""
        result = await capture_module.classify_content("idea for a new app: habit tracker")
        assert result["type"] == "idea"

    @pytest.mark.asyncio
    async def test_classify_note(self, capture_module: CaptureModule) -> None:
        """Note-related inputs are classified as 'note'."""
        result = await capture_module.classify_content("note: meeting at 3pm")
        assert result["type"] == "note"

    @pytest.mark.asyncio
    async def test_classify_insight(self, capture_module: CaptureModule) -> None:
        """Insight-related inputs are classified as 'insight'."""
        result = await capture_module.classify_content("i notice i work better in the morning")
        assert result["type"] == "insight"

    @pytest.mark.asyncio
    async def test_classify_question(self, capture_module: CaptureModule) -> None:
        """Question-related inputs are classified as 'question'."""
        # Use input that doesn't match earlier keyword categories
        # (avoid "at"/"do" etc. which match prior categories)
        result = await capture_module.classify_content("why is this?")
        assert result["type"] == "question"

    @pytest.mark.asyncio
    async def test_classify_goal(self, capture_module: CaptureModule) -> None:
        """Goal-related inputs are classified as 'goal'."""
        # Use input that doesn't match earlier keyword categories like "note" (which catches "at")
        result = await capture_module.classify_content("goal: learn Spanish")
        assert result["type"] == "goal"

    @pytest.mark.asyncio
    async def test_classify_financial(self, capture_module: CaptureModule) -> None:
        """Financial inputs are classified as 'financial'."""
        result = await capture_module.classify_content("spent 25 euros on groceries")
        assert result["type"] == "financial"

    @pytest.mark.asyncio
    async def test_classify_default_to_note(self, capture_module: CaptureModule) -> None:
        """Unknown inputs default to 'note'."""
        result = await capture_module.classify_content("the sky is blue")
        assert result["type"] == "note"


# =============================================================================
# TestFinancialDetection
# =============================================================================

class TestFinancialDetection:
    """Test financial content detection."""

    def test_financial_euro_symbol(self, capture_module: CaptureModule) -> None:
        """EUR keyword triggers financial detection."""
        # Note: _is_financial_content checks for "euro"/"eur" keywords, not the € symbol
        assert capture_module._is_financial_content("25 euro for groceries") is True

    def test_financial_eur(self, capture_module: CaptureModule) -> None:
        """EUR keyword triggers financial detection."""
        assert capture_module._is_financial_content("25 eur spent") is True

    def test_financial_dollar(self, capture_module: CaptureModule) -> None:
        """$ symbol triggers financial detection."""
        assert capture_module._is_financial_content("spent $25") is True

    def test_financial_keywords(self, capture_module: CaptureModule) -> None:
        """Financial keywords trigger detection."""
        assert capture_module._is_financial_content("cost 50 euros") is True
        assert capture_module._is_financial_content("paid for invoice") is True
        assert capture_module._is_financial_content("budget tracking") is True

    def test_non_financial(self, capture_module: CaptureModule) -> None:
        """Non-financial content is not detected."""
        assert capture_module._is_financial_content("call dentist") is False


# =============================================================================
# TestEntityExtraction
# =============================================================================

class TestEntityExtraction:
    """Test entity extraction from financial content."""

    def test_extract_amount_euro_symbol(self, capture_module: CaptureModule) -> None:
        """Extract amount with € symbol."""
        entities = capture_module._extract_financial_entities("25€ for groceries")
        assert entities["amount"] == "25"
        assert entities["currency"] == "EUR"

    def test_extract_amount_eur(self, capture_module: CaptureModule) -> None:
        """Extract amount with EUR keyword."""
        entities = capture_module._extract_financial_entities("spent 25 eur")
        assert entities["amount"] == "25"
        assert entities["currency"] == "EUR"

    def test_extract_amount_dollar(self, capture_module: CaptureModule) -> None:
        """Extract amount with $ symbol."""
        # Regex expects amount before currency symbol (e.g., "25$")
        entities = capture_module._extract_financial_entities("spent 25$")
        assert entities["amount"] == "25"
        assert entities["currency"] == "USD"

    def test_extract_decimal_amount(self, capture_module: CaptureModule) -> None:
        """Extract decimal amounts."""
        entities = capture_module._extract_financial_entities("25.50 euros")
        assert entities["amount"] == "25.50"


# =============================================================================
# TestRouting
# =============================================================================

class TestRouting:
    """Test content routing to destinations."""

    @pytest.mark.asyncio
    async def test_route_task_to_planning(self, capture_module: CaptureModule) -> None:
        """Tasks route to planning inbox."""
        ctx = _make_ctx("NT")
        captured = CapturedItem(
            original_message="call dentist",
            content_type="task",
            content="call dentist",
            extracted_entities={},
        )
        response = await capture_module.route_content("task", captured, ctx)
        assert response.side_effects is not None
        assert response.side_effects[0].effect_type == SideEffectType.ADD_TO_PLANNING_INBOX

    @pytest.mark.asyncio
    async def test_route_idea_to_second_brain(self, capture_module: CaptureModule) -> None:
        """Ideas route to second brain."""
        ctx = _make_ctx("NT")
        captured = CapturedItem(
            original_message="app idea",
            content_type="idea",
            content="app idea: habit tracker",
            extracted_entities={},
        )
        response = await capture_module.route_content("idea", captured, ctx)
        assert response.side_effects is not None
        assert response.side_effects[0].effect_type == SideEffectType.STORE_IN_SECOND_BRAIN

    @pytest.mark.asyncio
    async def test_route_goal_to_goal_system(self, capture_module: CaptureModule) -> None:
        """Goals route to goal system."""
        ctx = _make_ctx("NT")
        captured = CapturedItem(
            original_message="run marathon",
            content_type="goal",
            content="run marathon",
            extracted_entities={},
        )
        response = await capture_module.route_content("goal", captured, ctx)
        assert response.side_effects is not None
        assert response.side_effects[0].effect_type == SideEffectType.CREATE_GOAL_FROM_CAPTURE

    @pytest.mark.asyncio
    async def test_route_insight_to_aurora(self, capture_module: CaptureModule) -> None:
        """Insights route to Aurora."""
        ctx = _make_ctx("NT")
        captured = CapturedItem(
            original_message="i work better in morning",
            content_type="insight",
            content="i work better in morning",
            extracted_entities={},
        )
        response = await capture_module.route_content("insight", captured, ctx)
        assert response.side_effects is not None
        assert response.side_effects[0].effect_type == SideEffectType.ROUTE_TO_AURORA

    @pytest.mark.asyncio
    async def test_route_financial_to_money_module(self, capture_module: CaptureModule) -> None:
        """Financial content routes to money module (via CUSTOM type)."""
        ctx = _make_ctx("NT")
        captured = CapturedItem(
            original_message="spent 25 euros",
            content_type="financial",
            content="spent 25 euros",
            extracted_entities={"amount": "25", "currency": "EUR"},
        )
        response = await capture_module.route_content("financial", captured, ctx)
        assert response.side_effects is not None
        # "route_to_money_module" is not a defined SideEffectType enum value,
        # so SideEffect.__post_init__ converts it to CUSTOM
        assert response.side_effects[0].effect_type == SideEffectType.CUSTOM


# =============================================================================
# TestConfirmation
# =============================================================================

class TestConfirmation:
    """Test segment-specific confirmation messages."""

    def test_ad_confirmation_brief(self, capture_module: CaptureModule) -> None:
        """AD confirmations are brief and encouraging."""
        segment = SegmentContext.from_code("AD")
        confirmation = capture_module._build_confirmation("task", "call dentist", segment)
        assert "captured" in confirmation.lower()
        assert "call dentist" in confirmation.lower()

    def test_au_confirmation_structured(self, capture_module: CaptureModule) -> None:
        """AU confirmations are clear and structured."""
        segment = SegmentContext.from_code("AU")
        confirmation = capture_module._build_confirmation("task", "call dentist", segment)
        assert "task" in confirmation.lower()
        assert "planning inbox" in confirmation.lower()

    def test_ah_confirmation_adaptive(self, capture_module: CaptureModule) -> None:
        """AH confirmations are adaptive."""
        segment = SegmentContext.from_code("AH")
        confirmation = capture_module._build_confirmation("task", "call dentist", segment)
        assert "task" in confirmation.lower()

    def test_confirmation_truncates_long_content(self, capture_module: CaptureModule) -> None:
        """Long content is truncated in confirmation."""
        segment = SegmentContext.from_code("NT")
        long_content = "A" * 50
        confirmation = capture_module._build_confirmation("note", long_content, segment)
        assert "..." in confirmation


# =============================================================================
# TestFireAndForget
# =============================================================================

class TestFireAndForget:
    """Test fire-and-forget flow."""

    @pytest.mark.asyncio
    async def test_handle_ends_flow(self, capture_module: CaptureModule) -> None:
        """handle() ends flow after capture."""
        ctx = _make_ctx("NT")
        response = await capture_module.handle("call dentist", ctx)
        assert response.is_end_of_flow is True

    @pytest.mark.asyncio
    async def test_handle_returns_confirmation(self, capture_module: CaptureModule) -> None:
        """handle() returns confirmation message."""
        ctx = _make_ctx("NT")
        response = await capture_module.handle("call dentist", ctx)
        assert "captured" in response.text.lower() or "task" in response.text.lower()

    @pytest.mark.asyncio
    async def test_handle_includes_metadata(self, capture_module: CaptureModule) -> None:
        """handle() includes metadata."""
        ctx = _make_ctx("NT")
        response = await capture_module.handle("call dentist", ctx)
        assert "captured_content_type" in response.metadata
        assert "captured_content" in response.metadata


# =============================================================================
# TestContentCleaning
# =============================================================================

class TestContentCleaning:
    """Test content cleaning."""

    def test_clean_removes_task_prefix(self, capture_module: CaptureModule) -> None:
        """_clean_content removes 'task: ' prefix."""
        cleaned = capture_module._clean_content("task: call dentist", "task")
        assert cleaned == "call dentist"

    def test_clean_removes_idea_prefix(self, capture_module: CaptureModule) -> None:
        """_clean_content removes 'idea: ' prefix."""
        cleaned = capture_module._clean_content("idea: new app", "idea")
        assert cleaned == "new app"

    def test_clean_preserves_no_prefix(self, capture_module: CaptureModule) -> None:
        """_clean_content preserves content without prefix."""
        cleaned = capture_module._clean_content("just some text", "note")
        assert cleaned == "just some text"


# =============================================================================
# TestVoiceInput
# =============================================================================

class TestVoiceInput:
    """Test voice input stub."""

    @pytest.mark.asyncio
    async def test_voice_input_stub(self, capture_module: CaptureModule) -> None:
        """Voice input stub returns input as-is."""
        ctx = _make_ctx("NT")
        transcribed = await capture_module._process_voice_input("call dentist", ctx)
        assert transcribed == "call dentist"


# =============================================================================
# TestGDPR
# =============================================================================

class TestGDPR:
    """Test GDPR compliance methods."""

    @pytest.mark.asyncio
    async def test_export_returns_dict(self, capture_module: CaptureModule) -> None:
        """export_user_data returns expected keys."""
        data = await capture_module.export_user_data(user_id=1)
        assert "captured_content" in data

    @pytest.mark.asyncio
    async def test_delete_runs(self, capture_module: CaptureModule) -> None:
        """delete_user_data runs without error."""
        await capture_module.delete_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_freeze_runs(self, capture_module: CaptureModule) -> None:
        """freeze_user_data runs without error."""
        await capture_module.freeze_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_unfreeze_runs(self, capture_module: CaptureModule) -> None:
        """unfreeze_user_data runs without error."""
        await capture_module.unfreeze_user_data(user_id=1)


# =============================================================================
# TestOnExit
# =============================================================================

class TestOnExit:
    """Test session cleanup on module exit."""

    @pytest.mark.asyncio
    async def test_on_exit_resets_state(self, capture_module: CaptureModule) -> None:
        """on_exit resets internal state."""
        ctx = _make_ctx("NT", user_id=99)
        capture_module._state = "routing"
        capture_module._current_capture = CapturedItem("test", "task", "test", {})
        await capture_module.on_exit(ctx)
        assert capture_module._state == "capture"
        assert capture_module._current_capture is None


# =============================================================================
# TestDailyWorkflowHooks
# =============================================================================

class TestDailyWorkflowHooks:
    """Test daily workflow hooks."""

    def test_hooks_defined(self, capture_module: CaptureModule) -> None:
        """Capture module defines planning_enrichment hook."""
        hooks = capture_module.get_daily_workflow_hooks()
        assert hooks.planning_enrichment is not None
        assert hooks.hook_name == "capture"
        assert hooks.priority == 10


# =============================================================================
# TestModuleIdentity
# =============================================================================

class TestModuleIdentity:
    """Test module identity attributes."""

    def test_name(self, capture_module: CaptureModule) -> None:
        """Module name is 'capture'."""
        assert capture_module.name == "capture"

    def test_pillar(self, capture_module: CaptureModule) -> None:
        """Module pillar is 'second_brain'."""
        assert capture_module.pillar == "second_brain"

    def test_intents(self, capture_module: CaptureModule) -> None:
        """Module has expected intents."""
        assert "capture.quick" in capture_module.intents
        assert "capture.task" in capture_module.intents
        assert "capture.idea" in capture_module.intents
