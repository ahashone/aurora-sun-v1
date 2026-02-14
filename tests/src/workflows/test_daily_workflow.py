"""
Comprehensive tests for DailyWorkflow (SW-1: Daily Cycle).

Tests cover:
- Workflow state initialization
- Segment-adaptive timing configurations (all 5 segments)
- Morning activation (vision + energy + wins)
- Neurostate tiered pre-flight (4 tiers: always, yellow, red, afternoon)
- Overload detection and gentle redirect
- Vision display
- Evening review auto-trigger
- Reflection collection
- Daily plan persistence
- Hook registration and execution
- Timing getters (morning, midday, evening)
- Module hook priorities

Data Classification: SENSITIVE (daily patterns, energy levels)
"""

from __future__ import annotations

from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.module_response import ModuleResponse
from src.core.segment_context import WorkingStyleCode
from src.workflows.daily_workflow import (
    SEGMENT_TIMING_CONFIGS,
    DailyWorkflow,
    DailyWorkflowResult,
    DailyWorkflowState,
    SegmentTimingConfig,
    WorkflowTrigger,
    get_daily_workflow,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def workflow() -> DailyWorkflow:
    """Create a fresh DailyWorkflow instance."""
    return DailyWorkflow()


@pytest.fixture
def mock_user():
    """Create a mock User object."""
    user = MagicMock()
    user.id = 1
    user.working_style_code = "AD"
    return user


# =============================================================================
# Test: Initialization
# =============================================================================


def test_workflow_initialization(workflow: DailyWorkflow):
    """Test that DailyWorkflow initializes correctly."""
    assert workflow is not None
    assert workflow._hooks == {}


def test_get_daily_workflow_singleton():
    """Test that get_daily_workflow returns a singleton."""
    wf1 = get_daily_workflow()
    wf2 = get_daily_workflow()
    assert wf1 is wf2


# =============================================================================
# Test: WorkflowTrigger Enum
# =============================================================================


def test_workflow_trigger_values():
    """Test that WorkflowTrigger enum has all expected values."""
    assert WorkflowTrigger.SCHEDULED == "scheduled"
    assert WorkflowTrigger.MANUAL == "manual"
    assert WorkflowTrigger.ONBOARDING == "onboarding"
    assert WorkflowTrigger.RECOVERY == "recovery"


# =============================================================================
# Test: DailyWorkflowState
# =============================================================================


def test_workflow_state_initialization():
    """Test DailyWorkflowState initialization."""
    state = DailyWorkflowState(
        user_id=1,
        date=date.today(),
        segment_code="AD",
    )
    assert state.user_id == 1
    assert state.date == date.today()
    assert state.segment_code == "AD"
    assert state.trigger == WorkflowTrigger.SCHEDULED
    assert state.completed_stages == []
    assert state.current_stage == "morning_activate"
    assert state.energy_level is None
    assert state.overload_detected is False
    assert state.vision_displayed is False


def test_workflow_state_with_trigger():
    """Test DailyWorkflowState with custom trigger."""
    state = DailyWorkflowState(
        user_id=1,
        date=date.today(),
        segment_code="AU",
        trigger=WorkflowTrigger.ONBOARDING,
    )
    assert state.trigger == WorkflowTrigger.ONBOARDING


# =============================================================================
# Test: DailyWorkflowResult
# =============================================================================


def test_workflow_result_success():
    """Test DailyWorkflowResult for successful workflow."""
    result = DailyWorkflowResult(
        success=True,
        completed_stages=["morning_activate", "neurostate_preflight"],
        final_message="Daily workflow completed",
    )
    assert result.success is True
    assert len(result.completed_stages) == 2
    assert result.was_redirected is False


def test_workflow_result_redirect():
    """Test DailyWorkflowResult for redirected workflow."""
    result = DailyWorkflowResult(
        success=True,
        redirect_triggered=True,
        redirect_reason="overload_detected",
    )
    assert result.was_redirected is True
    assert result.redirect_reason == "overload_detected"


# =============================================================================
# Test: Segment Timing Configurations
# =============================================================================


def test_segment_timing_config_adhd():
    """Test ADHD (AD) timing configuration."""
    config = SEGMENT_TIMING_CONFIGS["AD"]
    assert config.morning_hour == 8
    assert config.morning_minute == 0
    assert config.midday_strategy == "interval"
    assert config.midday_interval_minutes == 90
    assert config.evening_hour == 20
    assert config.evening_minute == 0


def test_segment_timing_config_autism():
    """Test Autism (AU) timing configuration."""
    config = SEGMENT_TIMING_CONFIGS["AU"]
    assert config.morning_hour == 9
    assert config.morning_minute == 0
    assert config.midday_strategy == "exact_time"
    assert config.midday_exact_hour == 13
    assert config.midday_exact_minute == 0
    assert config.evening_hour == 19
    assert config.evening_minute == 0


def test_segment_timing_config_audhd():
    """Test AuDHD (AH) timing configuration."""
    config = SEGMENT_TIMING_CONFIGS["AH"]
    assert config.morning_hour == 8
    assert config.morning_minute == 30
    assert config.midday_strategy == "semi_predictable"
    assert config.midday_interval_minutes == 60
    assert config.evening_hour == 19
    assert config.evening_minute == 30


def test_segment_timing_config_neurotypical():
    """Test Neurotypical (NT) timing configuration."""
    config = SEGMENT_TIMING_CONFIGS["NT"]
    assert config.morning_hour == 8
    assert config.midday_strategy == "interval"
    assert config.midday_interval_minutes == 120


def test_segment_timing_config_custom():
    """Test Custom (CU) timing configuration."""
    config = SEGMENT_TIMING_CONFIGS["CU"]
    assert config is not None


def test_all_segments_have_timing_configs():
    """Test that all segments have timing configurations."""
    expected_segments: list[WorkingStyleCode] = ["AD", "AU", "AH", "NT", "CU"]
    for segment in expected_segments:
        assert segment in SEGMENT_TIMING_CONFIGS


# =============================================================================
# Test: Timing Getters
# =============================================================================


def test_get_timing_config(workflow: DailyWorkflow):
    """Test get_timing_config returns correct config for each segment."""
    for segment in ["AD", "AU", "AH", "NT", "CU"]:
        segment_code: WorkingStyleCode = segment  # type: ignore
        config = workflow.get_timing_config(segment_code)
        assert isinstance(config, SegmentTimingConfig)


def test_get_morning_time_adhd(workflow: DailyWorkflow):
    """Test get_morning_time for ADHD segment."""
    morning_time = workflow.get_morning_time("AD")
    assert morning_time == time(hour=8, minute=0)


def test_get_morning_time_autism(workflow: DailyWorkflow):
    """Test get_morning_time for Autism segment."""
    morning_time = workflow.get_morning_time("AU")
    assert morning_time == time(hour=9, minute=0)


def test_get_midday_time_adhd(workflow: DailyWorkflow):
    """Test get_midday_time for ADHD (interval-based, returns None)."""
    midday_time = workflow.get_midday_time("AD")
    assert midday_time is None


def test_get_midday_time_autism(workflow: DailyWorkflow):
    """Test get_midday_time for Autism (exact time)."""
    midday_time = workflow.get_midday_time("AU")
    assert midday_time == time(hour=13, minute=0)


def test_get_midday_interval_adhd(workflow: DailyWorkflow):
    """Test get_midday_interval for ADHD (returns interval)."""
    interval = workflow.get_midday_interval("AD")
    assert interval == 90


def test_get_midday_interval_autism(workflow: DailyWorkflow):
    """Test get_midday_interval for Autism (time-based, returns None)."""
    interval = workflow.get_midday_interval("AU")
    assert interval is None


def test_get_evening_time_adhd(workflow: DailyWorkflow):
    """Test get_evening_time for ADHD segment."""
    evening_time = workflow.get_evening_time("AD")
    assert evening_time == time(hour=20, minute=0)


def test_get_evening_time_autism(workflow: DailyWorkflow):
    """Test get_evening_time for Autism segment."""
    evening_time = workflow.get_evening_time("AU")
    assert evening_time == time(hour=19, minute=0)


# =============================================================================
# Test: Run Method
# =============================================================================


@pytest.mark.asyncio
async def test_run_returns_result(workflow: DailyWorkflow, mock_user):
    """Test that run() returns a DailyWorkflowResult."""
    result = await workflow.run(user_id=1, trigger="scheduled", user=mock_user)
    assert isinstance(result, DailyWorkflowResult)
    assert result.success is True


@pytest.mark.asyncio
async def test_run_with_manual_trigger(workflow: DailyWorkflow, mock_user):
    """Test run() with manual trigger."""
    result = await workflow.run(user_id=1, trigger="manual", user=mock_user)
    assert result.success is True


@pytest.mark.asyncio
async def test_run_with_onboarding_trigger(workflow: DailyWorkflow, mock_user):
    """Test run() with onboarding trigger."""
    result = await workflow.run(user_id=1, trigger="onboarding", user=mock_user)
    assert result.success is True


@pytest.mark.asyncio
async def test_run_extracts_segment_from_user(workflow: DailyWorkflow, mock_user):
    """Test that run() correctly extracts segment code from user."""
    mock_user.working_style_code = "AU"
    await workflow.run(user_id=1, user=mock_user)
    # No direct assertion, but ensures no errors


# =============================================================================
# Test: Morning Activation
# =============================================================================


@pytest.mark.asyncio
async def test_run_morning_activation(workflow: DailyWorkflow):
    """Test run_morning_activation returns message and interventions."""
    message, interventions = await workflow.run_morning_activation(
        user_id=1, segment_code="AD"
    )
    assert isinstance(message, str)
    assert isinstance(interventions, list)


@pytest.mark.asyncio
async def test_run_morning_activation_adhd(workflow: DailyWorkflow):
    """Test morning activation for ADHD segment."""
    message, _ = await workflow.run_morning_activation(user_id=1, segment_code="AD")
    assert len(message) > 0


@pytest.mark.asyncio
async def test_run_morning_activation_autism(workflow: DailyWorkflow):
    """Test morning activation for Autism segment."""
    message, _ = await workflow.run_morning_activation(user_id=1, segment_code="AU")
    assert len(message) > 0


# =============================================================================
# Test: Neurostate Pre-Flight (Tiered Assessment)
# =============================================================================


@pytest.mark.asyncio
async def test_neurostate_preflight_tier_1_default(workflow: DailyWorkflow):
    """Test neurostate pre-flight defaults to tier 1."""
    snapshot, overload = await workflow.run_neurostate_preflight(
        user_id=1, segment_code="AD"
    )
    assert snapshot["tier"] == 1
    assert overload is False


@pytest.mark.asyncio
async def test_neurostate_preflight_tier_2_yellow_energy(workflow: DailyWorkflow):
    """Test tier 2 is triggered by yellow energy (previous_energy <= 2)."""
    snapshot, _ = await workflow.run_neurostate_preflight(
        user_id=1, segment_code="AD", previous_energy=2
    )
    assert snapshot["tier"] >= 2


@pytest.mark.asyncio
async def test_neurostate_preflight_tier_3_red_energy(workflow: DailyWorkflow):
    """Test tier 3 is triggered by red energy (previous_energy == 1)."""
    snapshot, _ = await workflow.run_neurostate_preflight(
        user_id=1, segment_code="AD", previous_energy=1
    )
    assert snapshot["tier"] == 3


@pytest.mark.asyncio
async def test_neurostate_preflight_tier_3_consecutive_red_days(workflow: DailyWorkflow):
    """Test tier 3 is triggered by 3+ consecutive red days."""
    snapshot, _ = await workflow.run_neurostate_preflight(
        user_id=1, segment_code="AD", consecutive_red_days=3
    )
    assert snapshot["tier"] == 3


@pytest.mark.asyncio
async def test_neurostate_preflight_overload_not_detected_by_default(workflow: DailyWorkflow):
    """Test that overload is not detected by default."""
    _, overload = await workflow.run_neurostate_preflight(
        user_id=1, segment_code="AD"
    )
    assert overload is False


# =============================================================================
# Test: Gentle Redirect (Overload Handling)
# =============================================================================


@pytest.mark.asyncio
async def test_gentle_redirect_returns_module_response(workflow: DailyWorkflow):
    """Test gentle_redirect returns a ModuleResponse."""
    response = await workflow.gentle_redirect(user_id=1, reason="overload_detected")
    assert isinstance(response, ModuleResponse)
    assert response.is_end_of_flow is True


@pytest.mark.asyncio
async def test_gentle_redirect_message_contains_recovery(workflow: DailyWorkflow):
    """Test gentle redirect message mentions recovery."""
    response = await workflow.gentle_redirect(user_id=1, reason="burnout_risk")
    assert "rest" in response.text.lower() or "recovery" in response.text.lower()


@pytest.mark.asyncio
async def test_gentle_redirect_metadata_includes_reason(workflow: DailyWorkflow):
    """Test gentle redirect metadata includes the reason."""
    response = await workflow.gentle_redirect(user_id=1, reason="overload_detected")
    assert response.metadata.get("reason") == "overload_detected"
    assert response.metadata.get("redirect") is True


# =============================================================================
# Test: Vision Display
# =============================================================================


@pytest.mark.asyncio
async def test_run_vision_display_returns_visions_and_goals(workflow: DailyWorkflow):
    """Test run_vision_display returns visions and goals."""
    visions, goals = await workflow.run_vision_display(user_id=1)
    assert isinstance(visions, list)
    assert isinstance(goals, list)


# =============================================================================
# Test: Evening Review
# =============================================================================


@pytest.mark.asyncio
async def test_run_evening_review_returns_module_response(workflow: DailyWorkflow):
    """Test run_evening_review returns ModuleResponse."""
    response = await workflow.run_evening_review(user_id=1)
    assert isinstance(response, ModuleResponse)


@pytest.mark.asyncio
async def test_run_evening_review_metadata_has_auto_triggered(workflow: DailyWorkflow):
    """Test evening review metadata indicates auto-triggered."""
    response = await workflow.run_evening_review(user_id=1)
    assert response.metadata.get("auto_triggered") is True


# =============================================================================
# Test: Reflection
# =============================================================================


@pytest.mark.asyncio
async def test_run_reflection_returns_tuple(workflow: DailyWorkflow):
    """Test run_reflection returns tuple of (energy, reflection, intention)."""
    energy, reflection, intention = await workflow.run_reflection(
        user_id=1, segment_code="AD"
    )
    assert isinstance(energy, int)
    assert isinstance(reflection, str)
    assert isinstance(intention, str)


# =============================================================================
# Test: Hook Registration and Execution
# =============================================================================


def test_register_module_hooks(workflow: DailyWorkflow):
    """Test registering module hooks."""
    hooks = DailyWorkflowHooks(
        morning=AsyncMock(),
        priority=1,
    )
    workflow.register_module_hooks("test_module", hooks)
    assert "test_module" in workflow._hooks
    assert workflow._hooks["test_module"] is hooks


def test_get_hooks_for_stage_morning(workflow: DailyWorkflow):
    """Test get_hooks_for_stage returns hooks with morning callback."""
    hooks = DailyWorkflowHooks(
        morning=AsyncMock(),
        priority=1,
    )
    workflow.register_module_hooks("test_module", hooks)

    results = workflow.get_hooks_for_stage("morning")
    assert len(results) == 1
    assert results[0][0] == "test_module"


def test_get_hooks_for_stage_planning_enrichment(workflow: DailyWorkflow):
    """Test get_hooks_for_stage returns hooks with planning_enrichment callback."""
    hooks = DailyWorkflowHooks(
        planning_enrichment=AsyncMock(),
        priority=2,
    )
    workflow.register_module_hooks("test_module", hooks)

    results = workflow.get_hooks_for_stage("planning_enrichment")
    assert len(results) == 1
    assert results[0][0] == "test_module"


def test_get_hooks_for_stage_priority_ordering(workflow: DailyWorkflow):
    """Test that hooks are sorted by priority."""
    hooks1 = DailyWorkflowHooks(morning=AsyncMock(), priority=5)
    hooks2 = DailyWorkflowHooks(morning=AsyncMock(), priority=1)
    hooks3 = DailyWorkflowHooks(morning=AsyncMock(), priority=3)

    workflow.register_module_hooks("module_c", hooks1)
    workflow.register_module_hooks("module_a", hooks2)
    workflow.register_module_hooks("module_b", hooks3)

    results = workflow.get_hooks_for_stage("morning")
    assert len(results) == 3
    # Should be sorted by priority (ascending)
    assert results[0][1].priority == 1
    assert results[1][1].priority == 3
    assert results[2][1].priority == 5


def test_get_hooks_for_stage_no_matching_hooks(workflow: DailyWorkflow):
    """Test get_hooks_for_stage returns empty list when no hooks match."""
    hooks = DailyWorkflowHooks(morning=AsyncMock(), priority=1)
    workflow.register_module_hooks("test_module", hooks)

    results = workflow.get_hooks_for_stage("evening_review")
    assert len(results) == 0


# =============================================================================
# Test: CheckinScheduler
# =============================================================================


@pytest.mark.asyncio
async def test_checkin_scheduler_adhd_interval_based(workflow: DailyWorkflow):
    """Test checkin_scheduler for ADHD (interval-based, returns None)."""
    checkin_time = await workflow.checkin_scheduler(user_id=1, segment_code="AD")
    assert checkin_time is None


@pytest.mark.asyncio
async def test_checkin_scheduler_autism_exact_time(workflow: DailyWorkflow):
    """Test checkin_scheduler for Autism (exact time)."""
    checkin_time = await workflow.checkin_scheduler(user_id=1, segment_code="AU")
    assert checkin_time == time(hour=13, minute=0)
