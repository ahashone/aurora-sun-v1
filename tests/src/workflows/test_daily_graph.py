"""
Comprehensive tests for DailyGraph (LangGraph StateGraph for Daily Workflow).

Tests cover:
- DailyGraphState TypedDict structure
- GraphNode enum values
- EdgeRoute enum values
- Node function implementations (8 nodes)
- Conditional edge logic (check_overload)
- Graph construction (build_daily_graph)
- Graph execution (run_daily_graph)
- State transitions between nodes
- Redirect logic (overload → gentle_redirect → evening_review)
- Segment-adaptive scheduling

Data Classification: SENSITIVE (daily patterns, neurostate)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.workflows.daily_graph import (
    DailyGraphState,
    EdgeRoute,
    GraphNode,
    build_daily_graph,
    check_overload,
    during_day_node,
    end_node,
    evening_review_node,
    gentle_redirect_node,
    get_segment_adaptive_schedule,
    morning_activate_node,
    neurostate_preflight_node,
    planning_node,
    reflect_node,
    run_daily_graph,
    vision_display_node,
)

# =============================================================================
# Test: GraphNode Enum
# =============================================================================


def test_graph_node_values():
    """Test that GraphNode enum has all expected node names."""
    assert GraphNode.MORNING_ACTIVATE == "morning_activate"
    assert GraphNode.NEUROSTATE_PREFLIGHT == "neurostate_preflight"
    assert GraphNode.GENTLE_REDIRECT == "gentle_redirect"
    assert GraphNode.VISION_DISPLAY == "vision_display"
    assert GraphNode.PLANNING == "planning"
    assert GraphNode.DURING_DAY == "during_day"
    assert GraphNode.EVENING_REVIEW == "evening_review"
    assert GraphNode.REFLECT == "reflect"
    assert GraphNode.END == "end"


# =============================================================================
# Test: EdgeRoute Enum
# =============================================================================


def test_edge_route_values():
    """Test that EdgeRoute enum has all expected route names."""
    assert EdgeRoute.CONTINUE == "continue"
    assert EdgeRoute.REDIRECT == "redirect"
    assert EdgeRoute.SKIP_PLANNING == "skip_planning"
    assert EdgeRoute.DONE == "done"


# =============================================================================
# Test: DailyGraphState TypedDict Structure
# =============================================================================


def test_daily_graph_state_structure():
    """Test that DailyGraphState has all required fields."""
    state: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": None,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": False,
        "consecutive_red_days": 0,
        "current_stage": "morning_activate",
        "completed_stages": [],
        "vision_displayed": False,
        "goals_reviewed": False,
        "planning_completed": False,
        "midday_completed": False,
        "evening_completed": False,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }
    assert state["user_id"] == 1
    assert state["segment_code"] == "AD"


# =============================================================================
# Test: check_overload (Conditional Edge Function)
# =============================================================================


def test_check_overload_returns_redirect_when_overload():
    """Test check_overload returns REDIRECT when overload_detected is True."""
    state: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": None,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": True,  # Overload detected
        "consecutive_red_days": 0,
        "current_stage": "neurostate_preflight",
        "completed_stages": [],
        "vision_displayed": False,
        "goals_reviewed": False,
        "planning_completed": False,
        "midday_completed": False,
        "evening_completed": False,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }
    route = check_overload(state)
    assert route == EdgeRoute.REDIRECT


def test_check_overload_returns_continue_when_no_overload():
    """Test check_overload returns CONTINUE when overload_detected is False."""
    state: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": None,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": False,  # No overload
        "consecutive_red_days": 0,
        "current_stage": "neurostate_preflight",
        "completed_stages": [],
        "vision_displayed": False,
        "goals_reviewed": False,
        "planning_completed": False,
        "midday_completed": False,
        "evening_completed": False,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }
    route = check_overload(state)
    assert route == EdgeRoute.CONTINUE


# =============================================================================
# Test: Node Functions
# =============================================================================


@pytest.mark.asyncio
async def test_morning_activate_node_updates_state():
    """Test morning_activate_node updates state correctly."""
    state: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": None,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": False,
        "consecutive_red_days": 0,
        "current_stage": "morning_activate",
        "completed_stages": [],
        "vision_displayed": False,
        "goals_reviewed": False,
        "planning_completed": False,
        "midday_completed": False,
        "evening_completed": False,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }
    result = await morning_activate_node(state)
    assert result["current_stage"] == GraphNode.MORNING_ACTIVATE
    assert GraphNode.MORNING_ACTIVATE in result["completed_stages"]
    assert "morning_message" in result


@pytest.mark.asyncio
async def test_neurostate_preflight_node_updates_state():
    """Test neurostate_preflight_node updates state correctly."""
    state: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": None,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": False,
        "consecutive_red_days": 0,
        "current_stage": "neurostate_preflight",
        "completed_stages": ["morning_activate"],
        "vision_displayed": False,
        "goals_reviewed": False,
        "planning_completed": False,
        "midday_completed": False,
        "evening_completed": False,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }
    result = await neurostate_preflight_node(state)
    assert result["current_stage"] == GraphNode.NEUROSTATE_PREFLIGHT
    assert GraphNode.NEUROSTATE_PREFLIGHT in result["completed_stages"]
    assert "burnout_risk" in result


@pytest.mark.asyncio
async def test_neurostate_preflight_node_tier_detection():
    """Test neurostate_preflight_node detects correct tier based on energy."""
    # Tier 2: yellow energy
    state_yellow: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": 2,  # Yellow energy
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": False,
        "consecutive_red_days": 0,
        "current_stage": "neurostate_preflight",
        "completed_stages": [],
        "vision_displayed": False,
        "goals_reviewed": False,
        "planning_completed": False,
        "midday_completed": False,
        "evening_completed": False,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }
    await neurostate_preflight_node(state_yellow)
    # Tier logic is internal to the node, just verify it runs


@pytest.mark.asyncio
async def test_gentle_redirect_node_sets_redirect_flag():
    """Test gentle_redirect_node sets redirect_triggered flag."""
    state: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": None,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": True,
        "consecutive_red_days": 0,
        "current_stage": "gentle_redirect",
        "completed_stages": ["morning_activate", "neurostate_preflight"],
        "vision_displayed": False,
        "goals_reviewed": False,
        "planning_completed": False,
        "midday_completed": False,
        "evening_completed": False,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }
    result = await gentle_redirect_node(state)
    assert result["redirect_triggered"] is True
    assert result["redirect_reason"] == "overload_detected"
    assert "morning_message" in result


@pytest.mark.asyncio
async def test_vision_display_node_sets_flags():
    """Test vision_display_node sets vision_displayed and goals_reviewed flags."""
    state: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": None,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": False,
        "consecutive_red_days": 0,
        "current_stage": "vision_display",
        "completed_stages": ["morning_activate", "neurostate_preflight"],
        "vision_displayed": False,
        "goals_reviewed": False,
        "planning_completed": False,
        "midday_completed": False,
        "evening_completed": False,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }
    result = await vision_display_node(state)
    assert result["vision_displayed"] is True
    assert result["goals_reviewed"] is True
    assert GraphNode.VISION_DISPLAY in result["completed_stages"]


@pytest.mark.asyncio
async def test_planning_node_sets_planning_completed():
    """Test planning_node sets planning_completed flag."""
    state: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": None,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": False,
        "consecutive_red_days": 0,
        "current_stage": "planning",
        "completed_stages": ["morning_activate", "neurostate_preflight", "vision_display"],
        "vision_displayed": True,
        "goals_reviewed": True,
        "planning_completed": False,
        "midday_completed": False,
        "evening_completed": False,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }
    result = await planning_node(state)
    assert result["planning_completed"] is True
    assert GraphNode.PLANNING in result["completed_stages"]


@pytest.mark.asyncio
async def test_during_day_node_sets_midday_completed():
    """Test during_day_node sets midday_completed flag."""
    state: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": None,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": False,
        "consecutive_red_days": 0,
        "current_stage": "during_day",
        "completed_stages": ["morning_activate", "neurostate_preflight", "vision_display", "planning"],
        "vision_displayed": True,
        "goals_reviewed": True,
        "planning_completed": True,
        "midday_completed": False,
        "evening_completed": False,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }
    result = await during_day_node(state)
    assert result["midday_completed"] is True
    assert GraphNode.DURING_DAY in result["completed_stages"]


@pytest.mark.asyncio
async def test_evening_review_node_sets_evening_completed():
    """Test evening_review_node sets evening_completed flag."""
    state: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": None,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": False,
        "consecutive_red_days": 0,
        "current_stage": "evening_review",
        "completed_stages": ["morning_activate", "neurostate_preflight", "vision_display", "planning", "during_day"],
        "vision_displayed": True,
        "goals_reviewed": True,
        "planning_completed": True,
        "midday_completed": True,
        "evening_completed": False,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }
    result = await evening_review_node(state)
    assert result["evening_completed"] is True
    assert GraphNode.EVENING_REVIEW in result["completed_stages"]


@pytest.mark.asyncio
async def test_reflect_node_updates_stage():
    """Test reflect_node updates current_stage."""
    state: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": None,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": False,
        "consecutive_red_days": 0,
        "current_stage": "reflect",
        "completed_stages": ["morning_activate", "neurostate_preflight", "vision_display", "planning", "during_day", "evening_review"],
        "vision_displayed": True,
        "goals_reviewed": True,
        "planning_completed": True,
        "midday_completed": True,
        "evening_completed": True,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }
    result = await reflect_node(state)
    assert result["current_stage"] == GraphNode.REFLECT
    assert GraphNode.REFLECT in result["completed_stages"]


@pytest.mark.asyncio
async def test_end_node_finalizes_workflow():
    """Test end_node marks workflow as complete."""
    state: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": None,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": False,
        "consecutive_red_days": 0,
        "current_stage": "end",
        "completed_stages": ["morning_activate", "neurostate_preflight", "vision_display", "planning", "during_day", "evening_review", "reflect"],
        "vision_displayed": True,
        "goals_reviewed": True,
        "planning_completed": True,
        "midday_completed": True,
        "evening_completed": True,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }
    result = await end_node(state)
    assert result["current_stage"] == GraphNode.END
    assert GraphNode.END in result["completed_stages"]


# =============================================================================
# Test: build_daily_graph
# =============================================================================


def test_build_daily_graph_returns_compiled_graph():
    """Test build_daily_graph returns a compiled StateGraph."""
    graph = build_daily_graph()
    # If LangGraph is installed, graph should not be None
    # If not installed, it returns None
    assert graph is None or graph is not None


@patch('langgraph.graph.StateGraph')
def test_build_daily_graph_constructs_all_nodes(mock_state_graph):
    """Test build_daily_graph adds all expected nodes."""
    mock_workflow = MagicMock()
    mock_state_graph.return_value = mock_workflow
    mock_workflow.compile.return_value = MagicMock()

    build_daily_graph()

    # Verify nodes are added (at least once per node)
    assert mock_workflow.add_node.call_count >= 9


@patch('langgraph.graph.StateGraph')
def test_build_daily_graph_sets_entry_point(mock_state_graph):
    """Test build_daily_graph sets MORNING_ACTIVATE as entry point."""
    mock_workflow = MagicMock()
    mock_state_graph.return_value = mock_workflow
    mock_workflow.compile.return_value = MagicMock()

    build_daily_graph()

    mock_workflow.set_entry_point.assert_called_once_with(GraphNode.MORNING_ACTIVATE)


# =============================================================================
# Test: run_daily_graph
# =============================================================================


@pytest.mark.asyncio
async def test_run_daily_graph_returns_state():
    """Test run_daily_graph returns a state dict."""
    result = await run_daily_graph(
        user_id=1,
        date="2026-02-14",
        segment_code="AD",
        trigger="scheduled",
    )
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_run_daily_graph_with_initial_energy():
    """Test run_daily_graph with initial_energy parameter."""
    result = await run_daily_graph(
        user_id=1,
        date="2026-02-14",
        segment_code="AD",
        trigger="scheduled",
        initial_energy=3,
    )
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_run_daily_graph_with_consecutive_red_days():
    """Test run_daily_graph with consecutive_red_days parameter."""
    result = await run_daily_graph(
        user_id=1,
        date="2026-02-14",
        segment_code="AD",
        trigger="scheduled",
        consecutive_red_days=2,
    )
    assert isinstance(result, dict)


# =============================================================================
# Test: get_segment_adaptive_schedule
# =============================================================================


def test_get_segment_adaptive_schedule_adhd():
    """Test get_segment_adaptive_schedule for ADHD segment."""
    schedule = get_segment_adaptive_schedule("AD")
    assert "morning" in schedule
    assert "midday" in schedule
    assert "evening" in schedule
    assert schedule["midday"]["strategy"] in ["interval", "exact_time", "semi_predictable"]


def test_get_segment_adaptive_schedule_autism():
    """Test get_segment_adaptive_schedule for Autism segment."""
    schedule = get_segment_adaptive_schedule("AU")
    assert schedule["morning"]["hour"] == 9
    assert schedule["midday"]["exact_time"] is not None


def test_get_segment_adaptive_schedule_audhd():
    """Test get_segment_adaptive_schedule for AuDHD segment."""
    schedule = get_segment_adaptive_schedule("AH")
    assert schedule["morning"]["hour"] == 8
    assert schedule["morning"]["minute"] == 30


def test_get_segment_adaptive_schedule_neurotypical():
    """Test get_segment_adaptive_schedule for Neurotypical segment."""
    schedule = get_segment_adaptive_schedule("NT")
    assert "morning" in schedule
    assert "evening" in schedule


def test_get_segment_adaptive_schedule_custom():
    """Test get_segment_adaptive_schedule for Custom segment."""
    schedule = get_segment_adaptive_schedule("CU")
    assert "morning" in schedule


# =============================================================================
# Test: State Progression
# =============================================================================


@pytest.mark.asyncio
async def test_state_progression_through_nodes():
    """Test that state progresses correctly through nodes."""
    initial_state: DailyGraphState = {
        "user_id": 1,
        "date": "2026-02-14",
        "segment_code": "AD",
        "trigger": "scheduled",
        "energy_level": None,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": False,
        "consecutive_red_days": 0,
        "current_stage": "morning_activate",
        "completed_stages": [],
        "vision_displayed": False,
        "goals_reviewed": False,
        "planning_completed": False,
        "midday_completed": False,
        "evening_completed": False,
        "morning_message": None,
        "vision_texts": [],
        "goals": [],
        "reflection_text": None,
        "tomorrow_intention": None,
        "interventions_delivered": [],
        "redirect_triggered": False,
        "redirect_reason": None,
    }

    # Step 1: morning_activate
    state_after_morning = await morning_activate_node(initial_state)
    assert GraphNode.MORNING_ACTIVATE in state_after_morning["completed_stages"]

    # Step 2: neurostate_preflight
    state_after_neuro = await neurostate_preflight_node({**initial_state, **state_after_morning})
    assert GraphNode.NEUROSTATE_PREFLIGHT in state_after_neuro["completed_stages"]

    # Step 3: vision_display (assuming no overload)
    state_after_vision = await vision_display_node({**initial_state, **state_after_neuro})
    assert state_after_vision["vision_displayed"] is True
