"""
Money Module State Machine.

Defines the state machine for the money transaction flow.
States are segment-adaptive: 3-7 steps depending on neurotype.

Reference: money.py (main module)
"""

from __future__ import annotations

from enum import StrEnum


# =============================================================================
# State Machine
# =============================================================================

class MoneyState(StrEnum):
    """States for the money module state machine.

    The active states are determined by SegmentContext.ux.money_steps:
    - AD (3 steps): CAPTURE -> CLASSIFY -> DONE
    - NT (4 steps): CAPTURE -> CLASSIFY -> BUDGET_CHECK -> DONE
    - AH (6 steps): CAPTURE -> CLASSIFY -> CATEGORIZE -> BUDGET_CHECK -> PATTERN_CHECK -> DONE
    - AU (7 steps): CAPTURE -> CLASSIFY -> CATEGORIZE -> VERIFY -> BUDGET_CHECK -> PATTERN_CHECK -> DONE
    """

    CAPTURE = "capture"
    CLASSIFY = "classify"
    CATEGORIZE = "categorize"
    VERIFY = "verify"
    BUDGET_CHECK = "budget_check"
    PATTERN_CHECK = "pattern_check"
    DONE = "done"


# Ordered full pipeline (superset of all segments).
_FULL_PIPELINE: list[MoneyState] = [
    MoneyState.CAPTURE,
    MoneyState.CLASSIFY,
    MoneyState.CATEGORIZE,
    MoneyState.VERIFY,
    MoneyState.BUDGET_CHECK,
    MoneyState.PATTERN_CHECK,
    MoneyState.DONE,
]

# Mapping of money_steps -> which states to include (in order).
_STEPS_TO_STATES: dict[int, list[MoneyState]] = {
    3: [MoneyState.CAPTURE, MoneyState.CLASSIFY, MoneyState.DONE],
    4: [MoneyState.CAPTURE, MoneyState.CLASSIFY, MoneyState.BUDGET_CHECK, MoneyState.DONE],
    6: [
        MoneyState.CAPTURE,
        MoneyState.CLASSIFY,
        MoneyState.CATEGORIZE,
        MoneyState.BUDGET_CHECK,
        MoneyState.PATTERN_CHECK,
        MoneyState.DONE,
    ],
    7: _FULL_PIPELINE,
}


def get_pipeline_for_segment(money_steps: int) -> list[MoneyState]:
    """Return the state pipeline for the given money_steps value.

    Falls back to the closest known pipeline if the exact step count is not
    mapped (e.g. for Custom segments).

    Args:
        money_steps: The number of money steps from SegmentContext.ux.money_steps

    Returns:
        Ordered list of MoneyState values for this segment
    """
    if money_steps in _STEPS_TO_STATES:
        return _STEPS_TO_STATES[money_steps]
    # Fallback: pick the closest known step count
    closest = min(_STEPS_TO_STATES, key=lambda k: abs(k - money_steps))
    return _STEPS_TO_STATES[closest]


def next_state(current: MoneyState, money_steps: int) -> MoneyState:
    """Advance to the next state in the segment-specific pipeline.

    Args:
        current: The current state
        money_steps: From SegmentContext.ux.money_steps

    Returns:
        The next MoneyState in the pipeline
    """
    pipeline = get_pipeline_for_segment(money_steps)
    try:
        idx = pipeline.index(current)
    except ValueError:
        return MoneyState.DONE
    if idx + 1 < len(pipeline):
        return pipeline[idx + 1]
    return MoneyState.DONE
