"""
Proactive Engine for Aurora Agent.

Manages proactive impulse delivery to users:
- ReadinessScore calculation based on user state
- Max 3 proactive impulses per week (admin-approved types only)
- Boom-bust detection for ADHD (via SegmentContext.neuro.burnout_model)
- Impulse type registry with admin-approved types

Core rule: The system proposes, never acts autonomously.
All impulse types must be admin-approved before delivery.

Reference: ARCHITECTURE.md Section 5 (Aurora Agent - Proactive Engine)
Reference: ARCHITECTURE.md Section 12 (Self-Learning - Proactive Impulses)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from src.core.segment_context import SegmentContext

# Maximum proactive impulses per week (hard limit)
MAX_IMPULSES_PER_WEEK = 3


class ImpulseType(StrEnum):
    """Types of proactive impulses.

    Only admin-approved types can be delivered to users.
    """

    ENERGY_REMINDER = "energy_reminder"         # Gentle energy check
    VISION_REFRESHER = "vision_refresher"       # Reconnect with vision
    PATTERN_ALERT = "pattern_alert"             # Destructive pattern emerging
    MILESTONE_CELEBRATION = "milestone_celebration"  # Celebrate achievement
    BURNOUT_WARNING = "burnout_warning"         # Early burnout signal
    HABIT_ENCOURAGEMENT = "habit_encouragement" # Habit streak support
    GROWTH_INSIGHT = "growth_insight"           # Growth trajectory insight


# Default admin-approved impulse types
DEFAULT_APPROVED_TYPES: frozenset[ImpulseType] = frozenset({
    ImpulseType.ENERGY_REMINDER,
    ImpulseType.VISION_REFRESHER,
    ImpulseType.MILESTONE_CELEBRATION,
    ImpulseType.HABIT_ENCOURAGEMENT,
    ImpulseType.GROWTH_INSIGHT,
})


@dataclass
class ReadinessScore:
    """Score indicating user readiness for a proactive impulse.

    Combines energy state, recent interaction patterns,
    and segment-specific factors to determine if now is
    a good time to send a proactive message.
    """

    score: float = 0.0  # 0.0-1.0 (1.0 = very ready)
    energy_factor: float = 0.0
    engagement_factor: float = 0.0
    timing_factor: float = 0.0
    boom_bust_risk: float = 0.0  # Risk of boom-bust cycle (ADHD)
    should_send: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "score": self.score,
            "energy_factor": self.energy_factor,
            "engagement_factor": self.engagement_factor,
            "timing_factor": self.timing_factor,
            "boom_bust_risk": self.boom_bust_risk,
            "should_send": self.should_send,
            "reason": self.reason,
        }


@dataclass
class ProactiveImpulse:
    """A proactive impulse to be delivered to a user.

    Impulses are proposals, not actions. They are queued
    and delivered at appropriate times based on ReadinessScore.
    """

    impulse_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: int = 0
    impulse_type: ImpulseType = ImpulseType.ENERGY_REMINDER
    content: str = ""
    priority: int = 1  # 1 (low) to 5 (high)
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    delivered_at: str | None = None
    expired: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "impulse_id": self.impulse_id,
            "user_id": self.user_id,
            "impulse_type": self.impulse_type.value,
            "content": self.content,
            "priority": self.priority,
            "created_at": self.created_at,
            "delivered_at": self.delivered_at,
            "expired": self.expired,
            "metadata": self.metadata,
        }


class ProactiveEngine:
    """Proactive Engine for Aurora Agent.

    Manages proactive impulse delivery with readiness scoring
    and admin-approved type enforcement.

    Usage:
        engine = ProactiveEngine()
        readiness = engine.calculate_readiness(user_id=1, segment_ctx=ctx, ...)
        if readiness.should_send:
            impulses = engine.get_pending_impulses(user_id=1)
    """

    def __init__(
        self,
        approved_types: frozenset[ImpulseType] | None = None,
    ) -> None:
        """Initialize the proactive engine.

        Args:
            approved_types: Admin-approved impulse types (uses defaults if None)
        """
        self._approved_types = (
            approved_types
            if approved_types is not None
            else DEFAULT_APPROVED_TYPES
        )
        # In-memory storage (production: PostgreSQL + Redis)
        self._impulse_queue: dict[int, list[ProactiveImpulse]] = {}
        self._delivery_log: dict[int, list[ProactiveImpulse]] = {}

    def calculate_readiness(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
        current_energy: float = 0.5,
        hours_since_last_interaction: float = 4.0,
        interactions_this_week: int = 5,
        current_hour: int | None = None,
    ) -> ReadinessScore:
        """Calculate readiness for a proactive impulse.

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context
            current_energy: Current energy level (0.0-1.0)
            hours_since_last_interaction: Hours since last user interaction
            interactions_this_week: Number of interactions this week
            current_hour: Current hour (0-23), defaults to now

        Returns:
            ReadinessScore indicating whether to send an impulse
        """
        if current_hour is None:
            current_hour = datetime.now(UTC).hour

        # Check weekly limit first
        deliveries_this_week = self._count_weekly_deliveries(user_id)
        if deliveries_this_week >= MAX_IMPULSES_PER_WEEK:
            return ReadinessScore(
                score=0.0,
                should_send=False,
                reason=f"Weekly limit reached ({MAX_IMPULSES_PER_WEEK}/{MAX_IMPULSES_PER_WEEK})",
            )

        # Energy factor: higher energy = more ready
        energy_factor = current_energy

        # Engagement factor: based on recent interaction frequency
        # Too many interactions = user is active, don't interrupt
        # Too few = user may be disengaged
        if interactions_this_week < 2:
            engagement_factor = 0.3  # Low engagement, might help
        elif interactions_this_week > 10:
            engagement_factor = 0.2  # Very active, don't interrupt
        else:
            engagement_factor = 0.7  # Moderate engagement, good target

        # Timing factor: based on hours since last interaction
        # Sweet spot: 4-24 hours since last interaction
        if hours_since_last_interaction < 1.0:
            timing_factor = 0.1  # Too recent, don't pile on
        elif hours_since_last_interaction < 4.0:
            timing_factor = 0.4
        elif hours_since_last_interaction < 24.0:
            timing_factor = 0.8  # Sweet spot
        elif hours_since_last_interaction < 48.0:
            timing_factor = 0.6
        else:
            timing_factor = 0.3  # Too long, user may be away

        # Time-of-day hard block: NEVER send impulses at night
        if current_hour < 7 or current_hour > 22:
            return ReadinessScore(
                score=0.0,
                energy_factor=energy_factor,
                engagement_factor=engagement_factor,
                timing_factor=0.0,
                boom_bust_risk=0.0,
                should_send=False,
                reason="Outside active hours (7:00-22:00)",
            )

        # Boom-bust detection for ADHD/AuDHD
        boom_bust_risk = self._calculate_boom_bust_risk(
            segment_ctx, current_energy, interactions_this_week
        )

        # Reduce readiness if boom-bust risk is high
        boom_bust_penalty = boom_bust_risk * 0.5

        # Calculate overall score
        score = (
            energy_factor * 0.30
            + engagement_factor * 0.30
            + timing_factor * 0.40
        ) - boom_bust_penalty

        score = min(1.0, max(0.0, score))

        # Threshold for sending
        should_send = score >= 0.45

        # Generate reason
        if should_send:
            reason = "Readiness threshold met"
            if boom_bust_risk > 0.5:
                reason += " (but boom-bust risk is elevated)"
        else:
            reasons: list[str] = []
            if energy_factor < 0.3:
                reasons.append("low energy")
            if timing_factor < 0.3:
                reasons.append("poor timing")
            if engagement_factor < 0.3:
                reasons.append("engagement concerns")
            if boom_bust_risk > 0.7:
                reasons.append("high boom-bust risk")
            reason = (
                "Below threshold: " + ", ".join(reasons)
                if reasons
                else "Below threshold"
            )

        return ReadinessScore(
            score=round(score, 4),
            energy_factor=round(energy_factor, 4),
            engagement_factor=round(engagement_factor, 4),
            timing_factor=round(timing_factor, 4),
            boom_bust_risk=round(boom_bust_risk, 4),
            should_send=should_send,
            reason=reason,
        )

    def should_send_impulse(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
        current_energy: float = 0.5,
        hours_since_last_interaction: float = 4.0,
        interactions_this_week: int = 5,
        current_hour: int | None = None,
    ) -> bool:
        """Quick check: should we send a proactive impulse now?

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context
            current_energy: Current energy level (0.0-1.0)
            hours_since_last_interaction: Hours since last interaction
            interactions_this_week: Number of interactions this week
            current_hour: Current hour (0-23)

        Returns:
            True if an impulse should be sent
        """
        readiness = self.calculate_readiness(
            user_id=user_id,
            segment_ctx=segment_ctx,
            current_energy=current_energy,
            hours_since_last_interaction=hours_since_last_interaction,
            interactions_this_week=interactions_this_week,
            current_hour=current_hour,
        )
        return readiness.should_send

    def queue_impulse(
        self,
        user_id: int,
        impulse_type: ImpulseType,
        content: str,
        priority: int = 1,
    ) -> ProactiveImpulse | None:
        """Queue a proactive impulse for delivery.

        Only admin-approved types can be queued.

        Args:
            user_id: The user's unique identifier
            impulse_type: Type of impulse
            content: The impulse message content
            priority: Priority (1-5)

        Returns:
            The queued ProactiveImpulse, or None if type not approved
        """
        if impulse_type not in self._approved_types:
            return None

        impulse = ProactiveImpulse(
            user_id=user_id,
            impulse_type=impulse_type,
            content=content,
            priority=min(5, max(1, priority)),
        )

        if user_id not in self._impulse_queue:
            self._impulse_queue[user_id] = []
        self._impulse_queue[user_id].append(impulse)

        return impulse

    def get_pending_impulses(
        self, user_id: int
    ) -> list[ProactiveImpulse]:
        """Get pending (undelivered) impulses for a user.

        Returns impulses sorted by priority (highest first).

        Args:
            user_id: The user's unique identifier

        Returns:
            List of pending ProactiveImpulse objects
        """
        impulses = self._impulse_queue.get(user_id, [])
        pending = [i for i in impulses if not i.delivered_at and not i.expired]
        return sorted(pending, key=lambda i: i.priority, reverse=True)

    def deliver_impulse(
        self, user_id: int, impulse_id: str
    ) -> ProactiveImpulse | None:
        """Mark an impulse as delivered.

        Args:
            user_id: The user's unique identifier
            impulse_id: The impulse to mark as delivered

        Returns:
            The delivered impulse, or None if not found
        """
        impulses = self._impulse_queue.get(user_id, [])
        for impulse in impulses:
            if impulse.impulse_id == impulse_id and not impulse.delivered_at:
                impulse.delivered_at = datetime.now(UTC).isoformat()
                # Record in delivery log
                if user_id not in self._delivery_log:
                    self._delivery_log[user_id] = []
                self._delivery_log[user_id].append(impulse)
                return impulse
        return None

    def get_approved_types(self) -> frozenset[ImpulseType]:
        """Get the set of admin-approved impulse types.

        Returns:
            Frozenset of approved ImpulseType values
        """
        return self._approved_types

    def export_user_data(self, user_id: int) -> dict[str, Any]:
        """GDPR export for proactive data.

        Args:
            user_id: The user's unique identifier

        Returns:
            All proactive data for the user
        """
        queue = self._impulse_queue.get(user_id, [])
        log = self._delivery_log.get(user_id, [])
        return {
            "impulse_queue": [i.to_dict() for i in queue],
            "delivery_log": [i.to_dict() for i in log],
        }

    def delete_user_data(self, user_id: int) -> None:
        """GDPR delete for proactive data.

        Args:
            user_id: The user's unique identifier
        """
        self._impulse_queue.pop(user_id, None)
        self._delivery_log.pop(user_id, None)

    def _count_weekly_deliveries(self, user_id: int) -> int:
        """Count impulses delivered this week.

        Args:
            user_id: The user's unique identifier

        Returns:
            Number of deliveries this week
        """
        log = self._delivery_log.get(user_id, [])
        if not log:
            return 0

        week_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        count = 0
        for impulse in log:
            if impulse.delivered_at and impulse.delivered_at >= week_ago:
                count += 1
        return count

    def _calculate_boom_bust_risk(
        self,
        segment_ctx: SegmentContext,
        current_energy: float,
        interactions_this_week: int,
    ) -> float:
        """Calculate boom-bust cycle risk.

        ADHD users are vulnerable to boom-bust cycles:
        high energy + high activity = potential bust incoming.

        Uses SegmentContext.neuro.burnout_model to determine
        if boom-bust detection is relevant.

        Args:
            segment_ctx: The user's segment context
            current_energy: Current energy level (0.0-1.0)
            interactions_this_week: Number of interactions this week

        Returns:
            Risk score 0.0-1.0
        """
        burnout_model = segment_ctx.neuro.burnout_model

        # Only boom-bust model has this specific risk
        if burnout_model == "boom_bust":
            # High energy + high activity = risk
            if current_energy > 0.8 and interactions_this_week > 12:
                return 0.8
            elif current_energy > 0.7 and interactions_this_week > 8:
                return 0.5
            elif current_energy > 0.6 and interactions_this_week > 6:
                return 0.3
            return 0.1

        # Three-type model (AuDHD) has partial risk
        if burnout_model == "three_type":
            if current_energy > 0.8 and interactions_this_week > 12:
                return 0.6
            elif current_energy > 0.7 and interactions_this_week > 8:
                return 0.4
            return 0.1

        # Other models have minimal boom-bust risk
        return 0.0
