"""
Planning Module Helper Methods.

Message builders, parsers, segment guidance, and i18n helpers for the planning flow.

Reference: planning.py (main module)
"""

from __future__ import annotations

import re
from typing import Any

from src.core.module_context import ModuleContext
from src.core.segment_context import SegmentContext
from src.modules.planning_state import PlanningSession, PriorityItem


# =============================================================================
# Message Builders
# =============================================================================

def build_welcome_message(
    ctx: ModuleContext,
    session: PlanningSession,
    max_priorities: int,
    sprint_minutes: int,
) -> str:
    """Build welcome message with segment-specific framing.

    Args:
        ctx: Module context
        session: Planning session
        max_priorities: Max priorities for this segment
        sprint_minutes: Sprint duration for this segment

    Returns:
        Welcome message text
    """
    segment = ctx.segment_context

    # Build vision section
    vision_section = ""
    if session.vision_content:
        vision_section = f"\n\nYour Vision:\n{session.vision_content[:200]}..."
    elif session.goals_90d:
        goals_text = "\n".join(
            f"- {goal.get('title', 'Untitled')}"
            for goal in session.goals_90d[:3]
        )
        vision_section = f"\n\nYour 90-Day Goals:\n{goals_text}"

    # Build segment-specific guidance
    guidance = get_segment_guidance(segment)

    return (
        f"Welcome to your daily planning, {ctx.language}!\n"
        f"{vision_section}\n\n"
        f"{guidance}\n\n"
        f"First, let me ask: **Does today's plan serve your vision?**\n"
        f"(Think about your 90-day goals as you answer)"
    )


def get_segment_guidance(segment: SegmentContext) -> str:
    """Get segment-specific guidance text.

    Uses SegmentContext fields, NOT segment code checks.

    Args:
        segment: User's segment context

    Returns:
        Guidance text
    """
    max_priorities = segment.core.max_priorities
    sprint_minutes = segment.core.sprint_minutes

    # Build guidance based on segment features
    features = segment.features

    if features.routine_anchoring:
        # Autism: routine anchoring
        return (
            f"For today, let's focus on {max_priorities} priority(ies). "
            f"We'll work in {sprint_minutes}-minute focused sessions with regular breaks. "
            f"This structure helps maintain consistency."
        )
    elif features.icnu_enabled and features.sensory_check_required:
        # AuDHD: both ICNU and sensory
        return (
            f"Let's plan together. We'll aim for {max_priorities} priorities "
            f"with {sprint_minutes}-minute work blocks. "
            f"I'll check in on your energy and sensory state to keep things sustainable."
        )
    elif features.icnu_enabled:
        # ADHD: ICNU-based
        return (
            f"Today we'll select up to {max_priorities} priorities. "
            f"We'll work in {sprint_minutes}-minute focused sprints. "
            f"I'll help you stay in your optimal activation zone."
        )
    else:
        # Neurotypical / default
        return (
            f"Let's plan your day. You can select up to {max_priorities} priorities, "
            f"working in {sprint_minutes}-minute focused blocks."
        )


def build_overview_message(
    ctx: ModuleContext,
    session: PlanningSession,
    pending_tasks: list[dict[str, Any]],
) -> str:
    """Build overview message with pending tasks.

    Args:
        ctx: Module context
        session: Planning session
        pending_tasks: List of pending tasks

    Returns:
        Overview message
    """
    task_list = "\n".join(
        f"- {task.get('title', 'Untitled')}"
        for task in pending_tasks[:5]
    )

    more_count = len(pending_tasks) - 5
    more_text = f"\n(+{more_count} more)" if more_count > 0 else ""

    return (
        f"Here are your pending tasks from previous sessions:\n\n"
        f"{task_list}{more_text}\n\n"
        f"What would you like to focus on today? You can:\n"
        f"- Continue with pending tasks\n"
        f"- Start something new\n"
        f"- Mix of both"
    )


def build_priorities_prompt(
    ctx: ModuleContext,
    max_priorities: int,
) -> str:
    """Build priorities selection prompt.

    Args:
        ctx: Module context
        max_priorities: Maximum number of priorities

    Returns:
        Prompt text
    """
    return (
        f"Please select up to {max_priorities} priority(ies) for today.\n\n"
        f"What matters most? Tell me in your own words what you want to accomplish."
    )


def build_commitment_message(
    ctx: ModuleContext,
    session: PlanningSession,
    sprint_minutes: int,
) -> str:
    """Build commitment confirmation message.

    Args:
        ctx: Module context
        session: Planning session
        sprint_minutes: Sprint duration

    Returns:
        Commitment message
    """
    task_list = "\n".join(
        f"- {task.get('title', 'Untitled')}"
        for task in session.tasks[:3]
    )

    more_count = len(session.tasks) - 3
    more_text = f"\n(+{more_count} more)" if more_count > 0 else ""

    return (
        f"Here's your plan for today:\n\n"
        f"{task_list}{more_text}\n\n"
        f"We'll work in {sprint_minutes}-minute focused sessions.\n\n"
        f"Do you commit to this plan? (Yes/No or modify)"
    )


# =============================================================================
# Parsers
# =============================================================================

def parse_priorities(
    message: str,
    max_priorities: int,
) -> list[PriorityItem]:
    """Parse priorities from user message.

    Args:
        message: User's message
        max_priorities: Maximum allowed

    Returns:
        List of PriorityItem
    """
    # Simple parsing - split by newlines or numbered list
    lines = message.strip().split("\n")
    priorities = []

    for i, line in enumerate(lines[:max_priorities]):
        line = line.strip()
        # Remove numbering if present
        if line and (line[0].isdigit() or line.startswith("-") or line.startswith("*")):
            line = line[1:].strip()

        if line:
            priorities.append(
                PriorityItem(
                    id=f"priority_{i + 1}",
                    title=line,
                )
            )

    return priorities


def parse_tasks(
    message: str,
    priorities: list[PriorityItem],
) -> list[dict[str, Any]]:
    """Parse tasks from user message.

    Args:
        message: User's message
        priorities: Parent priorities

    Returns:
        List of task dicts
    """
    # Simple parsing - each line is a task
    lines = message.strip().split("\n")
    tasks = []

    for i, line in enumerate(lines):
        line = line.strip()
        if line and len(line) > 2:
            # Remove numbering/bullets
            if line[0].isdigit() or line.startswith("-") or line.startswith("*"):
                line = line[1:].strip()

            if line:
                tasks.append({
                    "id": f"task_{i + 1}",
                    "title": line,
                    "priority": 1,  # Default priority
                })

    return tasks


# =============================================================================
# Segment Check Helpers
# =============================================================================

def is_sensory_overloaded(message: str) -> bool:
    """Check if user indicates sensory overload.

    Args:
        message: User's response

    Returns:
        True if overloaded
    """
    overloaded_indicators = [
        "overwhelmed", "too much", "sensory",
        "drained", "burned out", "can't handle",
        "overload", "shut down", "shutting down",
    ]
    message_lower = message.lower()
    return any(indicator in message_lower for indicator in overloaded_indicators)


def parse_icnu(message: str) -> int:
    """Parse ICNU charge from message.

    Args:
        message: User's response

    Returns:
        ICNU charge (1-5)
    """
    # Simple parsing - look for numbers
    numbers = re.findall(r'\d+', message)
    if numbers:
        charge = int(numbers[0])
        return max(1, min(5, charge))

    # Default to middle
    return 3


def parse_channel(message: str) -> str | None:
    """Parse channel dominance from message.

    Args:
        message: User's response

    Returns:
        Channel name or None
    """
    channels = ["focus", "creative", "social", "physical", "learning"]
    message_lower = message.lower()

    for channel in channels:
        if channel in message_lower:
            return channel

    return None


def check_integrity(
    message: str,
    session: PlanningSession,
) -> bool:
    """Check if plan aligns with integrity values.

    Args:
        message: User's response
        session: Planning session

    Returns:
        True if aligned
    """
    # Simple check - user says it's aligned
    yes_responses = ["yes", "y", "aligned", "fits", "matches"]
    return any(yes in message.lower() for yes in yes_responses)


# =============================================================================
# i18n Helper
# =============================================================================

def get_message(ctx: ModuleContext, key: str) -> str:
    """Get localized message for key.

    Args:
        ctx: Module context
        key: Message key

    Returns:
        Localized message
    """
    # TODO: Implement proper i18n
    # For now, return English messages

    messages = {
        "scope_acknowledged": "Got it. Let's make sure this serves your vision first.",
        "realign_with_vision": "Let's realign with your vision. What matters most right now?",
        "vision_check_clarify": "Please answer yes or no - does this plan serve your vision?",
        "no_pending_tasks": "No pending tasks from before. Let's focus on today's priorities.",
        "too_many_priorities": "I understand you want to do {count} things, but to stay focused, let's limit to {max}. Which are most important?",
        "sensory_check": "Before we break this down, how's your sensory state? Are you feeling calm or overwhelmed?",
        "icnu_check": "What's your energy level right now? (1=low, 5=high)",
        "channel_check": "Which channel feels most aligned right now? (focus, creative, social, physical, learning)",
        "channel_check_clarify": "Which channel fits best? focus, creative, social, physical, or learning?",
        "priorities_accepted": "Got {count} priority(ies). Let's break these into specific tasks.",
        "segment_check_passed": "Good. Now let's break this down into actionable tasks.",
        "sensory_overload_redirect": "It sounds like you're experiencing sensory overload. Let's take it easy today - maybe just one small task or rest.",
        "low_icnu_adjust": "Your energy is low. Let's adjust - perhaps fewer priorities or shorter sessions?",
        "integrity_mismatch": "This doesn't quite align with your values. Let's realign before committing.",
        "commitment_confirmed": "Your plan is set! You've got this. I'll check in later.",
        "commitment_modify": "No problem. What would you like to change?",
        "commitment_clarify": "Please confirm (yes) or let me know what to change.",
    }

    return messages.get(key, key)
