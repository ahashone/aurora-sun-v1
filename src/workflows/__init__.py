"""
Daily Workflow Engine for Aurora Sun V1.

The Daily Workflow is a first-class LangGraph that orchestrates the daily
planning cycle for users.

Reference:
- ARCHITECTURE.md Section 3 (Daily Workflow Engine)
- ARCHITECTURE.md SW-1 (Daily Cycle)
"""

from src.workflows.daily_workflow import (
    DailyWorkflow,
    DailyWorkflowState,
    DailyWorkflowResult,
    WorkflowTrigger,
    SegmentTimingConfig,
    get_daily_workflow,
)

from src.workflows.daily_graph import (
    DailyGraphState,
    GraphNode,
    EdgeRoute,
    build_daily_graph,
    run_daily_graph,
    get_segment_adaptive_schedule,
)

__all__ = [
    # Daily Workflow Engine
    "DailyWorkflow",
    "DailyWorkflowState",
    "DailyWorkflowResult",
    "WorkflowTrigger",
    "SegmentTimingConfig",
    "get_daily_workflow",
    # Daily Graph
    "DailyGraphState",
    "GraphNode",
    "EdgeRoute",
    "build_daily_graph",
    "run_daily_graph",
    "get_segment_adaptive_schedule",
]
