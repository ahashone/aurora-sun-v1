"""
Planning Module State Handlers.

Contains all state handler methods for the planning flow state machine.
Each handler processes user input for a specific state and returns the next response.

Reference: planning.py (main module)
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse
from src.core.side_effects import SideEffect
from src.modules.planning_helpers import (
    build_commitment_message,
    build_overview_message,
    build_priorities_prompt,
    check_integrity,
    get_message,
    is_sensory_overloaded,
    parse_channel,
    parse_icnu,
    parse_priorities,
    parse_tasks,
)
from src.modules.planning_state import PlanningSession, PlanningState


# =============================================================================
# State Handlers
# =============================================================================

async def handle_scope(
    message: str,
    ctx: ModuleContext,
    session: PlanningSession,
) -> ModuleResponse:
    """Handle SCOPE state - ask what user wants to accomplish.

    Args:
        message: User's message
        ctx: Module context
        session: Planning session data

    Returns:
        ModuleResponse
    """
    session.scope = message

    # Move to VISION state
    return ModuleResponse(
        text=get_message(ctx, "scope_acknowledged"),
        next_state=PlanningState.VISION,
    )


async def handle_vision(
    message: str,
    ctx: ModuleContext,
    session: PlanningSession,
    load_pending_tasks_fn: Any,
) -> ModuleResponse:
    """Handle VISION state - vision alignment check.

    Key question: "Does today's plan serve your vision?"

    Args:
        message: User's response
        ctx: Module context
        session: Planning session data
        load_pending_tasks_fn: Async callable to load pending tasks

    Returns:
        ModuleResponse
    """
    # F-013: Use word boundary matching instead of substring
    message_lower = message.lower().strip()

    # Strict yes/no patterns (word boundary matching)
    yes_pattern = re.compile(r'\b(yes|y|ja|si|da|yeah|yep|sure|ok|okay)\b')
    no_pattern = re.compile(r'\b(no|n|nein|nao|nope|not really)\b')

    if yes_pattern.search(message_lower):
        session.vision_aligned = True

        # Show pending tasks from previous sessions
        pending_tasks = await load_pending_tasks_fn(ctx)

        if pending_tasks:
            # Show overview with pending tasks
            return ModuleResponse(
                text=build_overview_message(ctx, session, pending_tasks),
                next_state=PlanningState.OVERVIEW,
                metadata={"pending_tasks_count": len(pending_tasks)},
            )
        else:
            # Skip to priorities if no pending tasks
            return ModuleResponse(
                text=get_message(ctx, "no_pending_tasks"),
                next_state=PlanningState.PRIORITIES,
            )

    elif no_pattern.search(message_lower):
        # User says no - help them realign
        return ModuleResponse(
            text=get_message(ctx, "realign_with_vision"),
            next_state=PlanningState.VISION,  # Stay in VISION
        )

    else:
        # Ambiguous response - ask again
        return ModuleResponse(
            text=get_message(ctx, "vision_check_clarify"),
            next_state=PlanningState.VISION,
        )


async def handle_overview(
    message: str,
    ctx: ModuleContext,
    session: PlanningSession,
) -> ModuleResponse:
    """Handle OVERVIEW state - show pending tasks and get scope.

    Args:
        message: User's response
        ctx: Module context
        session: Planning session data

    Returns:
        ModuleResponse
    """
    # Store user's scope if provided
    if message.strip():
        session.scope = message

    # Move to PRIORITIES
    max_priorities = ctx.segment_context.core.max_priorities

    return ModuleResponse(
        text=build_priorities_prompt(ctx, max_priorities),
        next_state=PlanningState.PRIORITIES,
    )


async def handle_priorities(
    message: str,
    ctx: ModuleContext,
    session: PlanningSession,
) -> ModuleResponse:
    """Handle PRIORITIES state - select priorities.

    Enforces max_priorities from SegmentContext:
    - ADHD: max 2
    - Autism: max 3
    - AuDHD: max 3
    - Neurotypical: max 3

    Args:
        message: User's priorities
        ctx: Module context
        session: Planning session data

    Returns:
        ModuleResponse
    """
    segment = ctx.segment_context
    max_priorities = segment.core.max_priorities

    # Parse priorities from message
    priorities = parse_priorities(message, max_priorities)

    if len(priorities) > max_priorities:
        # Too many priorities - ask to reduce
        return ModuleResponse(
            text=get_message(ctx, "too_many_priorities").format(
                max=max_priorities,
                count=len(priorities),
            ),
            next_state=PlanningState.PRIORITIES,
        )

    session.priorities = priorities

    # Check if segment check is needed
    if segment.features.sensory_check_required:
        # AU/AH: need sensory check before breakdown
        return ModuleResponse(
            text=get_message(ctx, "sensory_check"),
            next_state=PlanningState.SEGMENT_CHECK,
            metadata={"sensory_check_required": True},
        )
    elif segment.features.icnu_enabled:
        # AD/AH: ICNU check
        return ModuleResponse(
            text=get_message(ctx, "icnu_check"),
            next_state=PlanningState.SEGMENT_CHECK,
            metadata={"icnu_check_required": True},
        )
    elif segment.features.channel_dominance_enabled:
        # AH: channel dominance check
        return ModuleResponse(
            text=get_message(ctx, "channel_check"),
            next_state=PlanningState.SEGMENT_CHECK,
            metadata={"channel_check_required": True},
        )
    else:
        # NT: skip to breakdown
        return ModuleResponse(
            text=get_message(ctx, "priorities_accepted").format(
                count=len(priorities),
            ),
            next_state=PlanningState.BREAKDOWN,
        )


async def handle_breakdown(
    message: str,
    ctx: ModuleContext,
    session: PlanningSession,
) -> ModuleResponse:
    """Handle BREAKDOWN state - break down priorities into tasks.

    Args:
        message: User's task breakdown
        ctx: Module context
        session: Planning session data

    Returns:
        ModuleResponse
    """
    # Parse tasks from message
    tasks = parse_tasks(message, session.priorities)
    session.tasks = tasks

    # Move to commitment
    sprint_minutes = ctx.segment_context.core.sprint_minutes

    return ModuleResponse(
        text=build_commitment_message(ctx, session, sprint_minutes),
        next_state=PlanningState.COMMITMENT,
    )


async def handle_segment_check(
    message: str,
    ctx: ModuleContext,
    session: PlanningSession,
) -> ModuleResponse:
    """Handle SEGMENT_CHECK state - validate segment-specific constraints.

    Handles:
    - Sensory check (AU/AH)
    - ICNU check (AD/AH)
    - Channel dominance check (AH)
    - Integrity trigger (AH)

    Args:
        message: User's response to segment check
        ctx: Module context
        session: Planning session data

    Returns:
        ModuleResponse
    """
    metadata = ctx.metadata or {}

    # Process based on check type
    if metadata.get("sensory_check_required"):
        # Check sensory state
        if is_sensory_overloaded(message):
            return ModuleResponse(
                text=get_message(ctx, "sensory_overload_redirect"),
                is_end_of_flow=True,
            )

    if metadata.get("icnu_check_required"):
        # Check ICNU charge
        icnu_charge = parse_icnu(message)
        if icnu_charge < 3:
            return ModuleResponse(
                text=get_message(ctx, "low_icnu_adjust"),
                next_state=PlanningState.PRIORITIES,
            )

    if metadata.get("channel_check_required"):
        # Check channel dominance
        channel = parse_channel(message)
        if not channel:
            return ModuleResponse(
                text=get_message(ctx, "channel_check_clarify"),
                next_state=PlanningState.SEGMENT_CHECK,
            )

    if metadata.get("integrity_trigger_enabled"):
        # Check integrity alignment
        if not check_integrity(message, session):
            return ModuleResponse(
                text=get_message(ctx, "integrity_mismatch"),
                next_state=PlanningState.PRIORITIES,
            )

    # All checks passed
    return ModuleResponse(
        text=get_message(ctx, "segment_check_passed"),
        next_state=PlanningState.BREAKDOWN,
    )


async def handle_commitment(
    message: str,
    ctx: ModuleContext,
    session: PlanningSession,
    persist_tasks_fn: Any,
) -> ModuleResponse:
    """Handle COMMITMENT state - confirm and persist today's commitment.

    Args:
        message: User's confirmation
        ctx: Module context
        session: Planning session data
        persist_tasks_fn: Async callable to persist tasks

    Returns:
        ModuleResponse
    """
    # F-013: Use word boundary matching instead of substring
    message_lower = message.lower().strip()

    # Strict confirmation patterns (word boundary matching)
    yes_pattern = re.compile(r'\b(yes|y|ja|si|da|yep|sure|ok|okay|confirm|commit)\b')
    no_pattern = re.compile(r'\b(no|n|nein|nao|nope|change|modify|edit)\b')

    if yes_pattern.search(message_lower):
        # Persist tasks
        await persist_tasks_fn(ctx, session)

        # Build success message with segment-specific gamification
        segment = ctx.segment_context
        gamification = segment.ux.gamification

        return ModuleResponse(
            text=get_message(ctx, "commitment_confirmed"),
            is_end_of_flow=True,
            side_effects=[
                SideEffect(
                    effect_type="create_tasks",  # type: ignore[arg-type]
                    payload={
                        "tasks": session.tasks,
                        "committed_date": date.today().isoformat(),
                    },
                )
            ],
            metadata={
                "gamification": gamification,
                "tasks_created": len(session.tasks),
            },
        )

    elif no_pattern.search(message_lower):
        # User wants to modify - go back to breakdown
        return ModuleResponse(
            text=get_message(ctx, "commitment_modify"),
            next_state=PlanningState.BREAKDOWN,
        )

    else:
        # Clarify
        return ModuleResponse(
            text=get_message(ctx, "commitment_clarify"),
            next_state=PlanningState.COMMITMENT,
        )
