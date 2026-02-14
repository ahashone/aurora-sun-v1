"""
Inertia Detection Service for Aurora Sun V1.

Three types of inertia as defined in ARCHITECTURE.md Section 3:
- Autistic Inertia: Cannot initiate/switch (monotropism)
- Activation Deficit: Cannot motivate (ADHD)
- Double Block: Both combined (AuDHD)

References:
- ARCHITECTURE.md Section 3 (Neurotype Segmentation)
- ARCHITECTURE.md Section 3.3 (Inertia - AD/AU/AH)
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.models.neurostate import InertiaEvent, InertiaType

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class InertiaEventData:
    """Represents an inertia event."""

    id: int | None = None
    user_id: int = 0
    inertia_type: InertiaType = InertiaType.ACTIVATION_DEFICIT
    severity: float = 0.0
    trigger: str | None = None
    attempted_interventions: list[str] = field(default_factory=list)
    outcome: str | None = None
    duration_minutes: int | None = None
    notes: str | None = None
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None


@dataclass
class InertiaDetectionResult:
    """Result of inertia detection analysis."""

    is_inertia: bool
    inertia_type: InertiaType | None = None
    confidence: float = 0.0
    trigger: str | None = None
    recommended_intervention: str | None = None
    severity: float = 0.0


# =============================================================================
# Service
# =============================================================================

class InertiaDetector:
    """
    Detects and tracks inertia events for neurodivergent users.

    Key Principles:
    - Three distinct types based on segment
    - Autistic Inertia != Activation Deficit (different mechanism)
    - AuDHD can have "double block" where both occur
    - Detection via behavioral patterns in conversation

    Detection Signals:
    - Autistic Inertia: "I want to but can't", repeated topic changes, "stuck"
    - Activation Deficit: "I should but won't", procrastination patterns, "later"
    - Double Block: Both patterns present

    Usage:
        detector = InertiaDetector(db)
        result = await detector.detect(user_id=123, recent_messages=[...])
    """

    # Detection thresholds
    MIN_MESSAGE_COUNT = 3
    INERTIA_KEYWORD_WEIGHT = 0.3
    PATTERN_WEIGHT = 0.5
    CONTEXT_WEIGHT = 0.2

    # Keywords for each inertia type
    AUTISTIC_INERTIA_KEYWORDS = [
        "stuck", "can't start", "want to but", "frozen", "overwhelmed",
        "don't know how", "too much", "decision paralysis", "paralyzed",
        "cannot switch", "tunnel", "loop", "ruminate", "rumination",
    ]

    ACTIVATION_DEFICIT_KEYWORDS = [
        "should", "need to", "want to", "later", "tomorrow", "eventually",
        "procrastinate", "lazy", "motivation", "can't be bothered",
        "hard to start", "put off", "keep forgetting", "distracted",
    ]

    DOUBLE_BLOCK_KEYWORDS = [
        "want to but shouldn't", "should but can't", "stuck and tired",
        "overwhelmed and bored", "too much and not enough",
    ]

    def __init__(self, db: Session):
        """
        Initialize the inertia detector.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    async def detect(
        self,
        user_id: int,
        recent_messages: list[dict],
    ) -> InertiaDetectionResult:
        """
        Detect inertia based on recent conversation messages.

        Args:
            user_id: The user's ID
            recent_messages: List of message dicts with 'text' and 'is_user' keys

        Returns:
            InertiaDetectionResult with detected type and confidence
        """
        if len(recent_messages) < self.MIN_MESSAGE_COUNT:
            return InertiaDetectionResult(is_inertia=False)

        # Get user segment for context
        segment_code = self._get_user_segment(user_id)

        # Analyze messages
        user_messages = [m["text"].lower() for m in recent_messages if m.get("is_user", False)]

        if not user_messages:
            return InertiaDetectionResult(is_inertia=False)

        # Score each inertia type
        autistic_score = self._score_autistic_inertia(user_messages)
        activation_score = self._score_activation_deficit(user_messages)
        double_block_score = self._score_double_block(user_messages)

        # Determine primary type based on segment
        if segment_code == "AU":
            primary_score = autistic_score
            primary_type = InertiaType.AUTISTIC_INERTIA
        elif segment_code == "AD":
            primary_score = activation_score
            primary_type = InertiaType.ACTIVATION_DEFICIT
        else:  # AH or default
            # Check for double block first
            if double_block_score > 0.5:
                primary_score = double_block_score
                primary_type = InertiaType.DOUBLE_BLOCK
            elif autistic_score > activation_score:
                primary_score = autistic_score
                primary_type = InertiaType.AUTISTIC_INERTIA
            else:
                primary_score = activation_score
                primary_type = InertiaType.ACTIVATION_DEFICIT

        # Determine if inertia is present
        is_inertia = primary_score > 0.4

        if not is_inertia:
            return InertiaDetectionResult(is_inertia=False)

        # Get recommended intervention
        intervention = self._get_recommended_intervention(primary_type, primary_score)

        # Extract trigger
        trigger = self._extract_trigger(user_messages)

        # Calculate severity (0-100)
        severity = min(100.0, primary_score * 100)

        return InertiaDetectionResult(
            is_inertia=True,
            inertia_type=primary_type,
            confidence=primary_score,
            trigger=trigger,
            recommended_intervention=intervention,
            severity=severity,
        )

    async def log_event(
        self,
        user_id: int,
        inertia_type: InertiaType,
        severity: float,
        trigger: str | None = None,
        notes: str | None = None,
    ) -> InertiaEvent:
        """
        Log an inertia event to the database.

        Args:
            user_id: The user's ID
            inertia_type: The type of inertia detected
            severity: Severity score (0-100)
            trigger: What triggered the inertia
            notes: Additional notes

        Returns:
            Created InertiaEvent
        """
        event = InertiaEvent(
            user_id=user_id,
            inertia_type=inertia_type.value,
            severity=severity,
            trigger=trigger,
            notes=notes,
            attempted_interventions=[],
            outcome="ongoing",
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    async def resolve_event(
        self,
        event_id: int,
        outcome: str,
        interventions_used: list[str],
        duration_minutes: int | None = None,
    ) -> InertiaEvent:
        """
        Mark an inertia event as resolved.

        Args:
            event_id: The event ID
            outcome: Outcome of the inertia ("resolved", "ongoing", "escalated")
            interventions_used: List of interventions attempted
            duration_minutes: How long the inertia lasted

        Returns:
            Updated InertiaEvent
        """
        event = self.db.query(InertiaEvent).filter(InertiaEvent.id == event_id).first()
        if not event:
            raise ValueError(f"InertiaEvent {event_id} not found")

        event.outcome = outcome
        event.attempted_interventions = interventions_used
        event.duration_minutes = duration_minutes
        event.resolved_at = datetime.now(UTC)

        self.db.commit()
        self.db.refresh(event)
        return event

    async def get_active_inertia(
        self,
        user_id: int,
    ) -> InertiaEvent | None:
        """
        Get the current active inertia event for a user.

        Args:
            user_id: The user's ID

        Returns:
            Active InertiaEvent or None
        """
        return (
            self.db.query(InertiaEvent)
            .filter(
                InertiaEvent.user_id == user_id,
                InertiaEvent.outcome == "ongoing",
            )
            .order_by(InertiaEvent.detected_at.desc())
            .first()
        )

    def _score_autistic_inertia(self, messages: list[str]) -> float:
        """Score messages for autistic inertia patterns."""
        score = 0.0
        for msg in messages:
            for keyword in self.AUTISTIC_INERTIA_KEYWORDS:
                if keyword in msg:
                    score += self.INERTIA_KEYWORD_WEIGHT

        # Pattern analysis
        # Repeated expressions of wanting to do something but can't
        want_cant_count = sum(1 for msg in messages if "want" in msg and "can" in msg)
        if want_cant_count >= 2:
            score += self.PATTERN_WEIGHT

        return min(1.0, score / len(messages) if messages else 0)

    def _score_activation_deficit(self, messages: list[str]) -> float:
        """Score messages for ADHD activation deficit patterns."""
        score = 0.0
        for msg in messages:
            for keyword in self.ACTIVATION_DEFICIT_KEYWORDS:
                if keyword in msg:
                    score += self.INERTIA_KEYWORD_WEIGHT

        # Pattern analysis
        # "should" but no action
        should_count = sum(1 for msg in messages if "should" in msg)
        later_count = sum(1 for msg in messages if "later" in msg or "tomorrow" in msg)
        if should_count >= 2 and later_count >= 1:
            score += self.PATTERN_WEIGHT

        return min(1.0, score / len(messages) if messages else 0)

    def _score_double_block(self, messages: list[str]) -> float:
        """Score messages for double block patterns (AuDHD)."""
        score = 0.0
        for msg in messages:
            for keyword in self.DOUBLE_BLOCK_KEYWORDS:
                if keyword in msg:
                    score += 0.5

        # Both types present
        autistic_indicators = sum(1 for msg in messages if any(k in msg for k in self.AUTISTIC_INERTIA_KEYWORDS))
        activation_indicators = sum(1 for msg in messages if any(k in msg for k in self.ACTIVATION_DEFICIT_KEYWORDS))

        if autistic_indicators > 0 and activation_indicators > 0:
            score += self.PATTERN_WEIGHT

        return min(1.0, score)

    def _get_recommended_intervention(
        self,
        inertia_type: InertiaType,
        severity: float,
    ) -> str:
        """Get recommended intervention based on inertia type and severity."""
        if severity > 0.8:
            if inertia_type == InertiaType.AUTISTIC_INERTIA:
                return "AUTISTIC INERTIA PROTOCOL: Reduce demand, sensory rest, wait for natural emergence"
            elif inertia_type == InertiaType.ACTIVATION_DEFICIT:
                return "ACTIVATION PROTOCOL: Body doubling, 2-minute rule, remove friction"
            else:
                return "DOUBLE BLOCK PROTOCOL: Address sensory first, then activation"

        if severity > 0.5:
            if inertia_type == InertiaType.AUTISTIC_INERTIA:
                return "Offer single-option choices, reduce decision burden"
            elif inertia_type == InertiaType.ACTIVATION_DEFICIT:
                return "Break into smallest possible step, remove barriers"
            else:
                return "Check sensory state, then try smallest step"

        return "Gentle prompt with specific offer"

    def _extract_trigger(self, messages: list[str]) -> str | None:
        """Extract potential trigger from messages."""
        # Look for common triggers
        trigger_phrases = [
            "because", "when", "since", "after", "before",
        ]

        for msg in messages:
            for phrase in trigger_phrases:
                if phrase in msg:
                    return f"Context: {msg[:100]}"

        return None

    def _get_user_segment(self, user_id: int) -> str:
        """Get user's segment code."""
        from src.models.user import User
        user = self.db.query(User).filter(User.id == user_id).first()
        return user.working_style_code if user else "NT"


__all__ = ["InertiaDetector", "InertiaEventData", "InertiaDetectionResult"]
