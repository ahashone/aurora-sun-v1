"""
Unit tests for the Habit Module.

Tests cover:
- State machine transitions (CREATE -> IDENTITY -> CUE -> CRAVING -> RESPONSE -> REWARD -> TRACKING -> DONE)
- Segment-specific behavior (ADHD, Autism, AuDHD, NT)
- GDPR export/delete/freeze/unfreeze
- Model creation (Habit, HabitLog)
- Helper methods (2-minute rule, CoherenceRatio, tracking info)
- Edge cases (unknown state, empty input, session cleanup)
- Daily workflow hooks
- Encryption (CRIT-5: All Art.9 behavioral data encrypted)
"""

from __future__ import annotations

import json

import pytest

from src.core.module_context import ModuleContext
from src.core.segment_context import SegmentContext
from src.lib.encrypted_field import EncryptedFieldDescriptor
from src.modules.habit import (
    Habit,
    HabitCreationSession,
    HabitLog,
    HabitModule,
    HabitState,
)

# =============================================================================
# Fixtures
# =============================================================================

def _make_ctx(
    segment_code: str = "NT",
    state: str = HabitState.CREATE,
    user_id: int = 1,
) -> ModuleContext:
    """Create a ModuleContext for testing."""
    return ModuleContext(
        user_id=user_id,
        segment_context=SegmentContext.from_code(segment_code),  # type: ignore[arg-type]
        state=state,
        session_id="test-session",
        language="en",
        module_name="habit",
    )


@pytest.fixture()
def habit_module() -> HabitModule:
    """Provide a fresh HabitModule instance."""
    return HabitModule()


# =============================================================================
# TestHabitState
# =============================================================================

class TestHabitState:
    """Test HabitState constants."""

    def test_all_states_defined(self) -> None:
        """All 8 states are defined."""
        assert len(HabitState.ALL) == 8

    def test_state_values(self) -> None:
        """State values match expected strings."""
        assert HabitState.CREATE == "CREATE"
        assert HabitState.IDENTITY == "IDENTITY"
        assert HabitState.CUE == "CUE"
        assert HabitState.CRAVING == "CRAVING"
        assert HabitState.RESPONSE == "RESPONSE"
        assert HabitState.REWARD == "REWARD"
        assert HabitState.TRACKING == "TRACKING"
        assert HabitState.DONE == "DONE"


# =============================================================================
# TestOnEnter
# =============================================================================

class TestOnEnter:
    """Test HabitModule.on_enter() for all segments."""

    @pytest.mark.asyncio
    async def test_on_enter_nt(self, habit_module: HabitModule) -> None:
        """NT on_enter returns standard message and CREATE state."""
        ctx = _make_ctx("NT")
        response = await habit_module.on_enter(ctx)
        assert response.next_state == HabitState.CREATE
        assert "Atomic Habits" in response.text

    @pytest.mark.asyncio
    async def test_on_enter_ad(self, habit_module: HabitModule) -> None:
        """AD on_enter uses exciting, novelty-positive language."""
        ctx = _make_ctx("AD")
        response = await habit_module.on_enter(ctx)
        assert response.next_state == HabitState.CREATE
        assert "2-minute" in response.text

    @pytest.mark.asyncio
    async def test_on_enter_au(self, habit_module: HabitModule) -> None:
        """AU on_enter uses structured, predictable language."""
        ctx = _make_ctx("AU")
        response = await habit_module.on_enter(ctx)
        assert response.next_state == HabitState.CREATE
        assert "step" in response.text.lower() or "routine" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_ah(self, habit_module: HabitModule) -> None:
        """AH on_enter uses channel-aware language."""
        ctx = _make_ctx("AH")
        response = await habit_module.on_enter(ctx)
        assert response.next_state == HabitState.CREATE
        assert "channel" in response.text.lower()

    @pytest.mark.asyncio
    async def test_on_enter_creates_session(self, habit_module: HabitModule) -> None:
        """on_enter creates a session for the user."""
        ctx = _make_ctx("NT", user_id=42)
        await habit_module.on_enter(ctx)
        assert 42 in habit_module._sessions


# =============================================================================
# TestHandleCreate
# =============================================================================

class TestHandleCreate:
    """Test CREATE state handler."""

    @pytest.mark.asyncio
    async def test_create_captures_name(self, habit_module: HabitModule) -> None:
        """CREATE state captures habit name and moves to IDENTITY."""
        ctx = _make_ctx("NT", state=HabitState.CREATE)
        await habit_module.on_enter(ctx)
        response = await habit_module.handle("Meditate daily", ctx)
        assert response.next_state == HabitState.IDENTITY
        assert "Meditate daily" in response.text

    @pytest.mark.asyncio
    async def test_create_applies_two_minute_rule(self, habit_module: HabitModule) -> None:
        """CREATE state suggests 2-minute version."""
        ctx = _make_ctx("NT", state=HabitState.CREATE)
        await habit_module.on_enter(ctx)
        response = await habit_module.handle("Meditate daily", ctx)
        assert "2 minute" in response.text.lower() or "sit quietly" in response.text.lower()

    @pytest.mark.asyncio
    async def test_create_ad_exciting_language(self, habit_module: HabitModule) -> None:
        """AD CREATE uses exciting language."""
        ctx = _make_ctx("AD", state=HabitState.CREATE)
        await habit_module.on_enter(ctx)
        response = await habit_module.handle("Exercise", ctx)
        assert "Love it" in response.text or "fun" in response.text.lower()


# =============================================================================
# TestStateTransitions
# =============================================================================

class TestStateTransitions:
    """Test full state machine transitions."""

    @pytest.mark.asyncio
    async def test_full_flow_nt(self, habit_module: HabitModule) -> None:
        """Full flow from CREATE to TRACKING for NT segment."""
        ctx = _make_ctx("NT")
        await habit_module.on_enter(ctx)

        # CREATE -> IDENTITY
        ctx.state = HabitState.CREATE
        r = await habit_module.handle("Read books", ctx)
        assert r.next_state == HabitState.IDENTITY

        # IDENTITY -> CUE
        ctx.state = HabitState.IDENTITY
        r = await habit_module.handle("I am someone who reads every day", ctx)
        assert r.next_state == HabitState.CUE

        # CUE -> CRAVING
        ctx.state = HabitState.CUE
        r = await habit_module.handle("After I pour my coffee", ctx)
        assert r.next_state == HabitState.CRAVING

        # CRAVING -> RESPONSE
        ctx.state = HabitState.CRAVING
        r = await habit_module.handle("I crave the calm focus reading gives me", ctx)
        assert r.next_state == HabitState.RESPONSE

        # RESPONSE -> REWARD
        ctx.state = HabitState.RESPONSE
        r = await habit_module.handle("Read one page", ctx)
        assert r.next_state == HabitState.REWARD

        # REWARD -> TRACKING
        ctx.state = HabitState.REWARD
        r = await habit_module.handle("Mark it off on my tracker", ctx)
        assert r.next_state == HabitState.TRACKING
        assert "Shall I save" in r.text or "save" in r.text.lower()

    @pytest.mark.asyncio
    async def test_tracking_confirm_saves(self, habit_module: HabitModule) -> None:
        """Confirming in TRACKING saves the habit and ends flow."""
        ctx = _make_ctx("NT", state=HabitState.TRACKING)
        habit_module._sessions[ctx.user_id] = HabitCreationSession(
            habit_name="Test",
            identity_statement="I am a tester",
            cue="After work",
            craving="I want to test",
            response="Run one test",
            reward="Check it off",
        )
        r = await habit_module.handle("yes", ctx)
        assert r.is_end_of_flow is True
        assert r.next_state == HabitState.DONE
        assert r.side_effects is not None
        assert len(r.side_effects) == 1

    @pytest.mark.asyncio
    async def test_tracking_cancel(self, habit_module: HabitModule) -> None:
        """Cancelling in TRACKING ends flow without side effects."""
        ctx = _make_ctx("NT", state=HabitState.TRACKING)
        habit_module._sessions[ctx.user_id] = HabitCreationSession(habit_name="Test")
        r = await habit_module.handle("no", ctx)
        assert r.is_end_of_flow is True
        assert r.side_effects is None

    @pytest.mark.asyncio
    async def test_tracking_ambiguous_reprompts(self, habit_module: HabitModule) -> None:
        """Ambiguous input in TRACKING re-prompts."""
        ctx = _make_ctx("NT", state=HabitState.TRACKING)
        habit_module._sessions[ctx.user_id] = HabitCreationSession(habit_name="Test")
        r = await habit_module.handle("maybe later", ctx)
        assert r.next_state == HabitState.TRACKING
        assert "confirm" in r.text.lower() or "save" in r.text.lower()


# =============================================================================
# TestSegmentSpecificBehavior
# =============================================================================

class TestSegmentSpecificBehavior:
    """Test segment-specific behavior using SegmentContext fields."""

    @pytest.mark.asyncio
    async def test_ad_cumulative_tracking(self, habit_module: HabitModule) -> None:
        """AD segment gets cumulative tracking (no streaks)."""
        ctx = _make_ctx("AD", state=HabitState.REWARD)
        habit_module._sessions[ctx.user_id] = HabitCreationSession(
            habit_name="Exercise",
            identity_statement="I am active",
            cue="Morning alarm",
            craving="Energy",
            response="5 pushups",
        )
        r = await habit_module.handle("Feel good", ctx)
        assert "Cumulative" in r.text or "cumulative" in r.text.lower()

    @pytest.mark.asyncio
    async def test_au_consistent_tracking(self, habit_module: HabitModule) -> None:
        """AU segment gets consistent practice tracking (14 day threshold)."""
        ctx = _make_ctx("AU", state=HabitState.REWARD)
        habit_module._sessions[ctx.user_id] = HabitCreationSession(
            habit_name="Journal",
            identity_statement="I reflect",
            cue="Before bed",
            craving="Clarity",
            response="Write one line",
        )
        r = await habit_module.handle("Peace of mind", ctx)
        assert "14" in r.text  # 14 day threshold for AU

    @pytest.mark.asyncio
    async def test_ah_adaptive_tracking(self, habit_module: HabitModule) -> None:
        """AH segment gets adaptive tracking."""
        ctx = _make_ctx("AH", state=HabitState.REWARD)
        habit_module._sessions[ctx.user_id] = HabitCreationSession(
            habit_name="Stretch",
            identity_statement="I move",
            cue="After lunch",
            craving="Flexibility",
            response="One stretch",
        )
        r = await habit_module.handle("Feeling loose", ctx)
        assert "Adaptive" in r.text or "adaptive" in r.text.lower()

    @pytest.mark.asyncio
    async def test_ad_save_confirmation_cumulative(self, habit_module: HabitModule) -> None:
        """AD save confirmation mentions cumulative count."""
        ctx = _make_ctx("AD", state=HabitState.TRACKING)
        habit_module._sessions[ctx.user_id] = HabitCreationSession(
            habit_name="Walk",
            identity_statement="I walk daily",
            cue="After lunch",
            craving="Fresh air",
            response="Walk around the block",
            reward="Enjoy the sun",
        )
        r = await habit_module.handle("yes", ctx)
        assert "cumulative" in r.text.lower()

    @pytest.mark.asyncio
    async def test_au_response_handler_predictable(self, habit_module: HabitModule) -> None:
        """AU RESPONSE handler uses predictable language."""
        ctx = _make_ctx("AU", state=HabitState.RESPONSE)
        habit_module._sessions[ctx.user_id] = HabitCreationSession(
            habit_name="Read",
            identity_statement="I read",
            cue="After dinner",
            craving="Knowledge",
        )
        r = await habit_module.handle("Read one page", ctx)
        assert "consistent" in r.text.lower() or "predictable" in r.text.lower()


# =============================================================================
# TestHabitStacking
# =============================================================================

class TestHabitStacking:
    """Test habit stacking detection."""

    @pytest.mark.asyncio
    async def test_habit_stack_detected(self, habit_module: HabitModule) -> None:
        """Habit stacking is detected from cue input."""
        ctx = _make_ctx("NT", state=HabitState.CUE)
        habit_module._sessions[ctx.user_id] = HabitCreationSession(
            habit_name="Stretch",
            identity_statement="I am flexible",
        )
        await habit_module.handle("After I pour my coffee", ctx)
        session = habit_module._sessions[ctx.user_id]
        assert session.habit_stack_after == "After I pour my coffee"

    @pytest.mark.asyncio
    async def test_no_habit_stack_without_keyword(self, habit_module: HabitModule) -> None:
        """No habit stacking detected without 'after/when/before' keywords."""
        ctx = _make_ctx("NT", state=HabitState.CUE)
        habit_module._sessions[ctx.user_id] = HabitCreationSession(
            habit_name="Read",
            identity_statement="I read",
        )
        await habit_module.handle("9am every morning", ctx)
        session = habit_module._sessions[ctx.user_id]
        assert session.habit_stack_after == ""


# =============================================================================
# TestTwoMinuteRule
# =============================================================================

class TestTwoMinuteRule:
    """Test the 2-minute rule suggestions."""

    def test_meditation_suggestion(self, habit_module: HabitModule) -> None:
        """Meditation gets 'sit quietly for 2 minutes'."""
        result = habit_module._apply_two_minute_rule("Meditate daily")
        assert "sit quietly" in result

    def test_exercise_suggestion(self, habit_module: HabitModule) -> None:
        """Exercise gets 'put on your workout clothes'."""
        result = habit_module._apply_two_minute_rule("Exercise regularly")
        assert "workout clothes" in result

    def test_reading_suggestion(self, habit_module: HabitModule) -> None:
        """Reading gets 'read one page'."""
        result = habit_module._apply_two_minute_rule("Read more books")
        assert "one page" in result

    def test_unknown_habit_default(self, habit_module: HabitModule) -> None:
        """Unknown habit gets generic 2-minute suggestion."""
        result = habit_module._apply_two_minute_rule("Do the thing")
        assert "2 minutes" in result


# =============================================================================
# TestCoherenceRatio
# =============================================================================

class TestCoherenceRatio:
    """Test CoherenceRatio calculation."""

    def test_zero_completions(self, habit_module: HabitModule) -> None:
        """Zero completions returns 0.0."""
        assert habit_module.get_coherence_ratio(0, 0.5) == 0.0

    def test_zero_progress(self, habit_module: HabitModule) -> None:
        """Zero goal progress returns 0.0."""
        assert habit_module.get_coherence_ratio(10, 0.0) == 0.0

    def test_positive_ratio(self, habit_module: HabitModule) -> None:
        """Positive completions and progress returns value 0-1."""
        ratio = habit_module.get_coherence_ratio(10, 0.5)
        assert 0.0 < ratio <= 1.0

    def test_max_clamp(self, habit_module: HabitModule) -> None:
        """Ratio is clamped to 1.0 max."""
        ratio = habit_module.get_coherence_ratio(1, 1.0)
        assert ratio <= 1.0


# =============================================================================
# TestTrackingInfo
# =============================================================================

class TestTrackingInfo:
    """Test tracking info generation."""

    def test_cumulative_tracking(self, habit_module: HabitModule) -> None:
        """Cumulative gamification shows no streaks."""
        result = habit_module._get_tracking_info("cumulative", 21)
        assert "no streaks" in result.lower() or "Cumulative" in result
        assert "21" in result

    def test_adaptive_tracking(self, habit_module: HabitModule) -> None:
        """Adaptive gamification mentions energy/channel."""
        result = habit_module._get_tracking_info("adaptive", 21)
        assert "energy" in result.lower() or "adaptive" in result.lower()

    def test_none_tracking(self, habit_module: HabitModule) -> None:
        """No gamification shows simple tracking."""
        result = habit_module._get_tracking_info("none", 14)
        assert "14" in result


# =============================================================================
# TestGDPR
# =============================================================================

class TestGDPR:
    """Test GDPR compliance methods."""

    @pytest.mark.asyncio
    async def test_export_returns_dict(self, habit_module: HabitModule) -> None:
        """export_user_data returns a dict with expected keys."""
        data = await habit_module.export_user_data(user_id=1)
        assert "habits" in data
        assert "habit_logs" in data

    @pytest.mark.asyncio
    async def test_delete_runs(self, habit_module: HabitModule) -> None:
        """delete_user_data runs without error."""
        await habit_module.delete_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_freeze_runs(self, habit_module: HabitModule) -> None:
        """freeze_user_data runs without error."""
        await habit_module.freeze_user_data(user_id=1)

    @pytest.mark.asyncio
    async def test_unfreeze_runs(self, habit_module: HabitModule) -> None:
        """unfreeze_user_data runs without error."""
        await habit_module.unfreeze_user_data(user_id=1)


# =============================================================================
# TestOnExit
# =============================================================================

class TestOnExit:
    """Test session cleanup on module exit."""

    @pytest.mark.asyncio
    async def test_on_exit_cleans_session(self, habit_module: HabitModule) -> None:
        """on_exit removes the user's session."""
        ctx = _make_ctx("NT", user_id=99)
        await habit_module.on_enter(ctx)
        assert 99 in habit_module._sessions
        await habit_module.on_exit(ctx)
        assert 99 not in habit_module._sessions

    @pytest.mark.asyncio
    async def test_on_exit_no_error_without_session(self, habit_module: HabitModule) -> None:
        """on_exit does not error if no session exists."""
        ctx = _make_ctx("NT", user_id=999)
        await habit_module.on_exit(ctx)  # Should not raise


# =============================================================================
# TestDailyWorkflowHooks
# =============================================================================

class TestDailyWorkflowHooks:
    """Test daily workflow hooks."""

    def test_hooks_defined(self, habit_module: HabitModule) -> None:
        """Habit module defines morning and evening hooks."""
        hooks = habit_module.get_daily_workflow_hooks()
        assert hooks.morning is not None
        assert hooks.evening_review is not None
        assert hooks.hook_name == "habit"
        assert hooks.priority == 20

    @pytest.mark.asyncio
    async def test_morning_hook_no_habits(self, habit_module: HabitModule) -> None:
        """Morning hook returns None when no habits exist."""
        ctx = _make_ctx("NT")
        result = await habit_module._morning_habit_reminder(ctx)
        assert result is None


# =============================================================================
# TestUnknownState
# =============================================================================

class TestUnknownState:
    """Test handling of unknown states."""

    @pytest.mark.asyncio
    async def test_unknown_state_restarts(self, habit_module: HabitModule) -> None:
        """Unknown state triggers on_enter (restart)."""
        ctx = _make_ctx("NT", state="NONEXISTENT")
        response = await habit_module.handle("hello", ctx)
        assert response.next_state == HabitState.CREATE


# =============================================================================
# TestModuleIdentity
# =============================================================================

class TestModuleIdentity:
    """Test module identity attributes."""

    def test_name(self, habit_module: HabitModule) -> None:
        """Module name is 'habit'."""
        assert habit_module.name == "habit"

    def test_pillar(self, habit_module: HabitModule) -> None:
        """Module pillar is 'vision_to_task'."""
        assert habit_module.pillar == "vision_to_task"

    def test_intents(self, habit_module: HabitModule) -> None:
        """Module has expected intents."""
        assert "habit.create" in habit_module.intents
        assert "habit.check_in" in habit_module.intents


# =============================================================================
# TestHabitModel
# =============================================================================

class TestHabitModel:
    """Test Habit SQLAlchemy model."""

    def test_tablename(self) -> None:
        """Habit model has correct tablename."""
        assert Habit.__tablename__ == "habits"

    def test_habitlog_tablename(self) -> None:
        """HabitLog model has correct tablename."""
        assert HabitLog.__tablename__ == "habit_logs"


# =============================================================================
# TestEncryption (CRIT-5)
# =============================================================================

class TestEncryption:
    """Test that all Art.9 behavioral data fields use EncryptedFieldDescriptor."""

    def test_name_uses_encrypted_field_descriptor(self) -> None:
        """name field uses EncryptedFieldDescriptor."""
        assert isinstance(Habit.name, EncryptedFieldDescriptor)

    def test_identity_statement_uses_encrypted_field_descriptor(self) -> None:
        """identity_statement field uses EncryptedFieldDescriptor."""
        assert isinstance(Habit.identity_statement, EncryptedFieldDescriptor)

    def test_cue_uses_encrypted_field_descriptor(self) -> None:
        """cue field uses EncryptedFieldDescriptor."""
        assert isinstance(Habit.cue, EncryptedFieldDescriptor)

    def test_craving_uses_encrypted_field_descriptor(self) -> None:
        """craving field uses EncryptedFieldDescriptor."""
        assert isinstance(Habit.craving, EncryptedFieldDescriptor)

    def test_response_uses_encrypted_field_descriptor(self) -> None:
        """response field uses EncryptedFieldDescriptor."""
        assert isinstance(Habit.response, EncryptedFieldDescriptor)

    def test_reward_uses_encrypted_field_descriptor(self) -> None:
        """reward field uses EncryptedFieldDescriptor."""
        assert isinstance(Habit.reward, EncryptedFieldDescriptor)

    def test_all_descriptors_use_fail_hard(self) -> None:
        """All encrypted fields use fail_hard=True (no plaintext fallback)."""
        for field_name in ["name", "identity_statement", "cue", "craving", "response", "reward"]:
            descriptor = getattr(Habit, field_name)
            assert descriptor.fail_hard is True, f"{field_name} must have fail_hard=True"

    def test_encrypted_field_round_trip(self, db_session) -> None:  # type: ignore[no-untyped-def]
        """Encrypted fields can be set and retrieved (round-trip test)."""
        habit = Habit(user_id=1, is_active=1, cumulative_count=0)
        habit.name = "Test Habit"
        habit.identity_statement = "I am someone who tests"
        habit.cue = "After breakfast"
        habit.craving = "I want to verify encryption"
        habit.response = "Write a test"
        habit.reward = "Check it off"

        db_session.add(habit)
        db_session.commit()

        # Retrieve from DB
        retrieved = db_session.query(Habit).filter_by(user_id=1).first()
        assert retrieved is not None
        assert retrieved.name == "Test Habit"
        assert retrieved.identity_statement == "I am someone who tests"
        assert retrieved.cue == "After breakfast"
        assert retrieved.craving == "I want to verify encryption"
        assert retrieved.response == "Write a test"
        assert retrieved.reward == "Check it off"

    def test_encrypted_fields_stored_as_json(self, db_session) -> None:  # type: ignore[no-untyped-def]
        """Encrypted fields are stored as JSON with ciphertext in database."""
        habit = Habit(user_id=2, is_active=1, cumulative_count=0)
        habit.name = "Secret Habit"
        habit.identity_statement = "I am secure"

        db_session.add(habit)
        db_session.commit()

        # Check raw storage
        raw_name = habit._name_plaintext
        raw_identity = habit._identity_statement_plaintext

        # Should be JSON strings containing ciphertext
        name_data = json.loads(str(raw_name))
        identity_data = json.loads(str(raw_identity))

        assert "ciphertext" in name_data, "name should store ciphertext"
        assert "ciphertext" in identity_data, "identity_statement should store ciphertext"
        assert "classification" in name_data
        assert name_data["classification"] == "sensitive"
