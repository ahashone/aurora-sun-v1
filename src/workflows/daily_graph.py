"""
LangGraph StateGraph for Daily Workflow.

The Daily Workflow is implemented as a first-class LangGraph -- not something
assembled from calling separate modules. It IS the central user experience.

Nodes:
    - morning_activate: Morning activation message
    - neurostate_preflight: Tiered neurostate assessment
    - vision_display: Show vision + 90d goals
    - planning: Invoke Planning Module
    - during_day: CheckinScheduler + inline coaching
    - evening_review: Auto-trigger Review Module
    - reflect: Energy + 1-line reflection + tomorrow intention
    - end: Save daily summary, feed Aurora

Edges:
    - Conditional routing based on neurostate (overload → gentle_redirect)
    - Segment-adaptive timing for during_day
    - Automatic progression from morning → evening → end

Reference:
- ARCHITECTURE.md Section 3 (Daily Workflow Engine)
- ARCHITECTURE.md SW-1 (Daily Cycle)
- ARCHITECTURE.md SW-12 (Burnout Redirect)
- ARCHITECTURE.md SW-18 (Neurostate Assessment)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional, TypedDict

from src.core.segment_context import WorkingStyleCode

logger = logging.getLogger(__name__)


# =============================================================================
# Graph State Definition
# =============================================================================

class DailyGraphState(TypedDict):
    """State definition for the Daily Workflow LangGraph.

    This TypedDict defines all fields that flow through the graph.
    Each node reads and updates specific fields.
    """

    # Identity
    user_id: int
    date: str
    segment_code: WorkingStyleCode
    trigger: str

    # Neurostate
    energy_level: Optional[int]
    sensory_load: Optional[float]
    burnout_risk: Optional[float]
    overload_detected: bool
    consecutive_red_days: int

    # Workflow progress
    current_stage: str
    completed_stages: list[str]
    vision_displayed: bool
    goals_reviewed: bool
    planning_completed: bool
    midday_completed: bool
    evening_completed: bool

    # Content
    morning_message: Optional[str]
    vision_texts: list[str]
    goals: list[dict[str, Any]]
    reflection_text: Optional[str]
    tomorrow_intention: Optional[str]
    interventions_delivered: list[str]

    # Redirect
    redirect_triggered: bool
    redirect_reason: Optional[str]


# =============================================================================
# Node Names
# =============================================================================

class GraphNode(str, Enum):
    """Names of nodes in the Daily Workflow graph."""

    MORNING_ACTIVATE = "morning_activate"
    NEUROSTATE_PREFILIGHT = "neurostate_preflight"
    GENTLE_REDIRECT = "gentle_redirect"
    VISION_DISPLAY = "vision_display"
    PLANNING = "planning"
    DURING_DAY = "during_day"
    EVENING_REVIEW = "evening_review"
    REFLECT = "reflect"
    END = "end"


# =============================================================================
# Edge Routes
# =============================================================================

class EdgeRoute(str, Enum):
    """Route names for conditional edges."""

    CONTINUE = "continue"
    REDIRECT = "redirect"
    SKIP_PLANNING = "skip_planning"
    DONE = "done"


# =============================================================================
# LangGraph Builder Functions
# =============================================================================

def build_daily_graph():
    """
    Build the Daily Workflow LangGraph.

    The graph structure:

                        +------------------+
                        | MORNING          |
                        | morning_activate |
                        +--------+---------+
                                 |
                        +--------v---------+
                        | NEUROSTATE       |
                        | tiered pre-flight|
                        +--------+---------+
                                 |
                      [overload?]--> GENTLE_REDIRECT
                                 |   (recovery protocol,
                                 |    no planning today)
                                 |
                        +--------v---------+
                        | VISION           |
                        | display vision   |
                        | show 90d goals   |
                        +--------+---------+
                                 |
                        +--------v---------+
                        | PLAN             |
                        | -> Planning      |
                        |    Module        |
                        +--------+---------+
                                 |
              +--------------+--------------+
              |                             |
    +---------v----------+       +----------v---------+
    | DURING DAY         |       | INLINE COACHING    |
    | auto_reminders     |<----->| triggered by:      |
    | (CheckinScheduler) |       | "I'm stuck"        |
    | segment-adaptive   |       | drift detected     |
    | timing             |       | pattern re-entry   |
    +--------+-----------+       +--------------------+
              |
    +---------v----------+
    | EVENING            |
    | auto_review        |
    +--------+-----------+
              |
    +---------v----------+
    | REFLECT            |
    | energy check       |
    | 1-line reflection  |
    | tomorrow intention |
    +--------+-----------+
              |
    +---------v----------+
    | END                |
    | save daily summary |
    | feed Aurora         |
    +--------------------+

    Returns:
        Compiled LangGraph StateGraph
    """
    try:
        from langgraph.graph import StateGraph, END as LangGraphEnd
    except ImportError:
        logger.warning("LangGraph not installed, returning None")
        return None

    # Define the graph with our state type
    workflow = StateGraph(DailyGraphState)

    # Add nodes
    workflow.add_node(GraphNode.MORNING_ACTIVATE, morning_activate_node)
    workflow.add_node(GraphNode.NEUROSTATE_PREFILIGHT, neurostate_preflight_node)
    workflow.add_node(GraphNode.GENTLE_REDIRECT, gentle_redirect_node)
    workflow.add_node(GraphNode.VISION_DISPLAY, vision_display_node)
    workflow.add_node(GraphNode.PLANNING, planning_node)
    workflow.add_node(GraphNode.DURING_DAY, during_day_node)
    workflow.add_node(GraphNode.EVENING_REVIEW, evening_review_node)
    workflow.add_node(GraphNode.REFLECT, reflect_node)
    workflow.add_node(GraphNode.END, end_node)

    # Set entry point
    workflow.set_entry_point(GraphNode.MORNING_ACTIVATE)

    # Add edges
    # morning_activate → neurostate_preflight
    workflow.add_edge(GraphNode.MORNING_ACTIVATE, GraphNode.NEUROSTATE_PREFILIGHT)

    # neurostate_preflight → conditional (overload check)
    workflow.add_conditional_edges(
        GraphNode.NEUROSTATE_PREFILIGHT,
        check_overload,
        {
            EdgeRoute.REDIRECT: GraphNode.GENTLE_REDIRECT,
            EdgeRoute.CONTINUE: GraphNode.VISION_DISPLAY,
        }
    )

    # gentle_redirect → end (no planning, go straight to evening)
    workflow.add_edge(GraphNode.GENTLE_REDIRECT, GraphNode.EVENING_REVIEW)

    # vision_display → planning
    workflow.add_edge(GraphNode.VISION_DISPLAY, GraphNode.PLANNING)

    # planning → during_day
    workflow.add_edge(GraphNode.PLANNING, GraphNode.DURING_DAY)

    # during_day → evening_review
    workflow.add_edge(GraphNode.DURING_DAY, GraphNode.EVENING_REVIEW)

    # evening_review → reflect
    workflow.add_edge(GraphNode.EVENING_REVIEW, GraphNode.REFLECT)

    # reflect → end
    workflow.add_edge(GraphNode.REFLECT, GraphNode.END)

    # Compile the graph
    compiled = workflow.compile()

    logger.info("Daily Workflow LangGraph built successfully")
    return compiled


# =============================================================================
# Node Functions
# =============================================================================

async def morning_activate_node(state: DailyGraphState) -> dict[str, Any]:
    """
    Node: Morning activation.

    Sends morning activation message including:
    - Vision reminder
    - Energy check (tiered based on segment)
    - Yesterday's wins (if available)

    Args:
        state: Current graph state

    Returns:
        Updated state dict
    """
    user_id = state["user_id"]
    segment_code = state["segment_code"]

    logger.info(f"Node: morning_activate for user {user_id}")

    # TODO: Build morning message
    # - Get vision
    # - Get yesterday's wins from previous DailyPlan
    # - Call morning hooks from registered modules

    message = f"Good morning! Today is {state['date']}."

    return {
        "current_stage": GraphNode.MORNING_ACTIVATE,
        "completed_stages": state["completed_stages"] + [GraphNode.MORNING_ACTIVATE],
        "morning_message": message,
    }


async def neurostate_preflight_node(state: DailyGraphState) -> dict[str, Any]:
    """
    Node: Tiered neurostate pre-flight.

    Reference: SW-18 (Neurostate Assessment Tiered Pre-Flight)

    TIER 1 (ALWAYS):
      - 1-question energy check

    TIER 2 (YELLOW energy):
      - + Sensory State Assessment (AU/AH)
      - + Channel Dominance Detection (AH only)

    TIER 3 (RED energy OR 3+ consecutive red days):
      - + Full assessment: sensory + masking + burnout trajectory
      - + Inertia Detection

    Args:
        state: Current graph state

    Returns:
        Updated state dict with neurostate data
    """
    user_id = state["user_id"]
    segment_code = state["segment_code"]
    previous_energy = state.get("energy_level")
    consecutive_red_days = state.get("consecutive_red_days", 0)

    logger.info(f"Node: neurostate_preflight for user {user_id}")

    # Determine tier based on conditions
    tier = 1
    if previous_energy is not None and previous_energy <= 2:
        tier = max(tier, 2)
    if (previous_energy is not None and previous_energy == 1) or consecutive_red_days >= 3:
        tier = max(tier, 3)

    # TODO: Run actual neurostate assessment
    # - Call NeurostateService with tier
    # - Get assessment results
    # - Store in state

    # Placeholder results
    overload_detected = False

    return {
        "current_stage": GraphNode.NEUROSTATE_PREFILIGHT,
        "completed_stages": state["completed_stages"] + [GraphNode.NEUROSTATE_PREFILIGHT],
        "burnout_risk": 0.0,
        "overload_detected": overload_detected,
    }


def check_overload(state: DailyGraphState) -> str:
    """
    Conditional edge: Check if overload was detected.

    Args:
        state: Current graph state

    Returns:
        EdgeRoute.REDIRECT if overload detected, EdgeRoute.CONTINUE otherwise
    """
    if state.get("overload_detected", False):
        return EdgeRoute.REDIRECT
    return EdgeRoute.CONTINUE


async def gentle_redirect_node(state: DailyGraphState) -> dict[str, Any]:
    """
    Node: Gentle redirect to recovery.

    When burnout or overload is detected, we don't proceed with planning.
    Instead, we redirect to a recovery protocol.

    Reference: SW-12 (Burnout Redirect)

    Args:
        state: Current graph state

    Returns:
        Updated state dict
    """
    user_id = state["user_id"]

    logger.info(f"Node: gentle_redirect for user {user_id}")

    # Recovery message (segment-adaptive)
    message = (
        "It sounds like you need rest today. That's completely okay.\n\n"
        "Let's focus on recovery instead of planning. Your energy is valuable, "
        "and sometimes the best thing we can do is simply rest.\n\n"
        "I'll check in with you later. Take care of yourself."
    )

    return {
        "current_stage": GraphNode.GENTLE_REDIRECT,
        "redirect_triggered": True,
        "redirect_reason": "overload_detected",
        "morning_message": message,
    }


async def vision_display_node(state: DailyGraphState) -> dict[str, Any]:
    """
    Node: Display vision and 90-day goals.

    Shows the user their life vision and 90-day goals before planning.

    Args:
        state: Current graph state

    Returns:
        Updated state dict
    """
    user_id = state["user_id"]

    logger.info(f"Node: vision_display for user {user_id}")

    # TODO: Load vision and goals from database
    # visions = await get_visions(user_id)
    # goals = await get_90d_goals(user_id)

    return {
        "current_stage": GraphNode.VISION_DISPLAY,
        "completed_stages": state["completed_stages"] + [GraphNode.VISION_DISPLAY],
        "vision_displayed": True,
        "goals_reviewed": True,
    }


async def planning_node(state: DailyGraphState) -> dict[str, Any]:
    """
    Node: Invoke Planning Module.

    Triggers the Planning Module for daily task planning.

    Args:
        state: Current graph state

    Returns:
        Updated state dict
    """
    user_id = state["user_id"]
    segment_code = state["segment_code"]

    logger.info(f"Node: planning for user {user_id}")

    # TODO: Invoke Planning Module
    # - Create module context
    # - Call planning.on_enter() or similar
    # - Handle state transitions

    return {
        "current_stage": GraphNode.PLANNING,
        "completed_stages": state["completed_stages"] + [GraphNode.PLANNING],
        "planning_completed": True,
    }


async def during_day_node(state: DailyGraphState) -> dict[str, Any]:
    """
    Node: During day - CheckinScheduler and inline coaching.

    Handles:
    - Segment-adaptive midday reminders
    - Inline coaching triggers ("I'm stuck", drift detection)

    Args:
        state: Current graph state

    Returns:
        Updated state dict
    """
    user_id = state["user_id"]
    segment_code = state["segment_code"]

    logger.info(f"Node: during_day for user {user_id}")

    # TODO: Set up CheckinScheduler
    # - Get segment-adaptive timing
    # - Schedule midday reminder
    # - Monitor for inline coaching triggers

    return {
        "current_stage": GraphNode.DURING_DAY,
        "completed_stages": state["completed_stages"] + [GraphNode.DURING_DAY],
        "midday_completed": True,
    }


async def evening_review_node(state: DailyGraphState) -> dict[str, Any]:
    """
    Node: Evening auto-review.

    Automatically triggered at segment-adaptive evening time.

    Reference: SW-1 step 10

    Args:
        state: Current graph state

    Returns:
        Updated state dict
    """
    user_id = state["user_id"]

    logger.info(f"Node: evening_review for user {user_id}")

    # TODO: Invoke Review Module
    # - Trigger at segment-adaptive time
    # - Collect day's accomplishments

    return {
        "current_stage": GraphNode.EVENING_REVIEW,
        "completed_stages": state["completed_stages"] + [GraphNode.EVENING_REVIEW],
        "evening_completed": True,
    }


async def reflect_node(state: DailyGraphState) -> dict[str, Any]:
    """
    Node: Reflection.

    Collects:
    - Evening energy check (1-5)
    - 1-line reflection on the day
    - Tomorrow's intention

    Args:
        state: Current graph state

    Returns:
        Updated state dict
    """
    user_id = state["user_id"]

    logger.info(f"Node: reflect for user {user_id}")

    # TODO: Prompt for reflection
    # This would be handled by the bot interface

    return {
        "current_stage": GraphNode.REFLECT,
        "completed_stages": state["completed_stages"] + [GraphNode.REFLECT],
    }


async def end_node(state: DailyGraphState) -> dict[str, Any]:
    """
    Node: End of daily workflow.

    Saves:
    - DailyPlan record to database
    - Daily summary to Aurora (narrative update)

    Args:
        state: Current graph state

    Returns:
        Final state dict
    """
    user_id = state["user_id"]
    date = state["date"]

    logger.info(f"Node: end for user {user_id}")

    # TODO: Save DailyPlan to database
    # await save_daily_plan(state)

    # TODO: Feed Aurora narrative
    # await feed_aurora_summary(state)

    return {
        "current_stage": GraphNode.END,
        "completed_stages": state["completed_stages"] + [GraphNode.END],
    }


# =============================================================================
# Graph Execution
# =============================================================================

async def run_daily_graph(
    user_id: int,
    date: str,
    segment_code: WorkingStyleCode,
    trigger: str = "scheduled",
    initial_energy: Optional[int] = None,
    consecutive_red_days: int = 0,
) -> dict[str, Any]:
    """
    Run the Daily Workflow LangGraph.

    Args:
        user_id: The user ID
        date: The date for this workflow (YYYY-MM-DD)
        segment_code: User's segment code
        trigger: What triggered this workflow
        initial_energy: Previous day's energy level (for tiered assessment)
        consecutive_red_days: Number of consecutive red energy days

    Returns:
        Final graph state
    """
    # Try to build the graph
    graph = build_daily_graph()

    if graph is None:
        logger.warning("LangGraph not available, returning empty state")
        return {}

    # Initialize input state
    initial_state: DailyGraphState = {
        "user_id": user_id,
        "date": date,
        "segment_code": segment_code,
        "trigger": trigger,
        "energy_level": initial_energy,
        "sensory_load": None,
        "burnout_risk": None,
        "overload_detected": False,
        "consecutive_red_days": consecutive_red_days,
        "current_stage": GraphNode.MORNING_ACTIVATE,
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

    # Run the graph
    result = await graph.ainvoke(initial_state)

    logger.info(f"Daily graph completed for user {user_id}")
    return result


# =============================================================================
# Convenience Functions
# =============================================================================

def get_segment_adaptive_schedule(segment_code: WorkingStyleCode) -> dict[str, Any]:
    """
    Get segment-adaptive schedule times.

    Args:
        segment_code: User's segment code

    Returns:
        Dict with morning, midday, evening times
    """
    from src.workflows.daily_workflow import SEGMENT_TIMING_CONFIGS

    config = SEGMENT_TIMING_CONFIGS.get(segment_code, SEGMENT_TIMING_CONFIGS["NT"])

    return {
        "morning": {"hour": config.morning_hour, "minute": config.morning_minute},
        "midday": {
            "strategy": config.midday_strategy,
            "exact_time": (
                {"hour": config.midday_exact_hour, "minute": config.midday_exact_minute}
                if config.midday_exact_hour
                else None
            ),
            "interval_minutes": config.midday_interval_minutes,
        },
        "evening": {"hour": config.evening_hour, "minute": config.evening_minute},
    }


__all__ = [
    "DailyGraphState",
    "GraphNode",
    "EdgeRoute",
    "build_daily_graph",
    "run_daily_graph",
    "get_segment_adaptive_schedule",
]
