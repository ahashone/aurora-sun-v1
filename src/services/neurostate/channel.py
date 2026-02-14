"""
Channel Dominance Detector Service for Aurora Sun V1.

For AuDHD: detects ADHD-day vs Autism-day channel dominance.
As per ARCHITECTURE.md Section 3.6.

References:
- ARCHITECTURE.md Section 3 (Neurotype Segmentation)
- ARCHITECTURE.md Section 3.6 (Channel Dominance - AuDHD)
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from src.models.neurostate import ChannelState, ChannelType

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ChannelStateData:
    """Current channel state for a user."""

    user_id: int
    dominant_channel: ChannelType
    channel_scores: dict[ChannelType, float]    # Score per channel (0-100)
    confidence: float                           # Confidence in dominance (0-1)
    supporting_signals: list[str]
    period_start: datetime
    is_adhd_dominant: bool                      # True if ADHD-like day
    is_autism_dominant: bool                    # True if Autism-like day


@dataclass
class ChannelDetectionResult:
    """Result of channel dominance detection."""

    dominant_channel: ChannelType
    confidence: float
    channel_scores: dict[ChannelType, float]
    is_adhd_dominant: bool
    is_autism_dominant: bool
    recommended_approach: str


# =============================================================================
# Service
# =============================================================================

class ChannelDominanceDetector:
    """
    Detects channel dominance for AuDHD users.

    Key Principles:
    - AuDHD has VARIABLE channel dominance
    - "ADHD-day": More hyperactive/impulsive patterns
    - "Autism-day": More autistic/structured patterns
    - Channel can shift within day based on context
    - Detection via behavioral signals in conversation

    Channels:
    - Focus: Task-focused, detail-oriented
    - Creative: Divergent, idea generation
    - Social: Interaction-focused, connection-seeking
    - Physical: Body-aware, movement-oriented
    - Learning: Information-seeking, curiosity

    Usage:
        detector = ChannelDominanceDetector(db)
        result = await detector.detect(user_id=123)
    """

    CHANNELS = [
        ChannelType.FOCUS,
        ChannelType.CREATIVE,
        ChannelType.SOCIAL,
        ChannelType.PHYSICAL,
        ChannelType.LEARNING,
    ]

    # ADHD-day indicators (high in these = ADHD channel)
    ADHD_CHANNELS = [ChannelType.CREATIVE, ChannelType.PHYSICAL]
    AUTISM_CHANNELS = [ChannelType.FOCUS, ChannelType.LEARNING]
    SOCIAL_CHANNEL = ChannelType.SOCIAL

    # Detection thresholds
    DOMINANCE_THRESHOLD = 0.3                   # Score difference to claim dominance
    CONFIDENCE_HIGH = 0.7
    CONFIDENCE_MEDIUM = 0.5

    # Channel signal keywords
    CHANNEL_SIGNALS = {
        ChannelType.FOCUS: [
            "detail", "specific", "exact", "plan", "structure",
            "organize", "order", "system", "routine", "complete",
            "finish", "task", "deadline", "step", "sequence",
        ],
        ChannelType.CREATIVE: [
            "idea", "think", "maybe", "could", "imagine",
            "different", "new", "creative", "brainstorm", "possibility",
            "explore", "what if", "option", "alternative", "wonder",
        ],
        ChannelType.SOCIAL: [
            "talk", "discuss", "share", "tell", "ask",
            "friend", "family", "people", "connect", "together",
            "relationship", "conversation", "response", "help", "support",
        ],
        ChannelType.PHYSICAL: [
            "move", "do", "action", "start", "now",
            "physical", "body", "energy", "active", "exercise",
            "walk", "hands", "need to", "just", "go",
        ],
        ChannelType.LEARNING: [
            "learn", "understand", "research", "know", "information",
            "question", "why", "how", "explain", "read",
            "study", "discover", "find out", "curious", "interest",
        ],
    }

    def __init__(self, db: Session):
        """
        Initialize the channel dominance detector.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    async def detect(
        self,
        user_id: int,
        recent_messages: list[dict[str, str | bool]] | None = None,
    ) -> ChannelDetectionResult:
        """
        Detect current channel dominance.

        Args:
            user_id: The user's ID
            recent_messages: Optional message history for analysis

        Returns:
            ChannelDetectionResult with dominant channel and confidence
        """
        # Get or calculate channel scores
        if recent_messages:
            channel_scores = self._analyze_messages(recent_messages)
        else:
            # Use stored state
            state = await self.get_current_state(user_id)
            if state:
                channel_scores = state.channel_scores
            else:
                # Default equal scores
                channel_scores = {ch: 50.0 for ch in self.CHANNELS}

        # Determine dominant channel
        dominant = max(channel_scores.items(), key=lambda x: x[1])
        dominant_channel = dominant[0]
        max_score = dominant[1]

        # Calculate confidence based on spread
        min_score = min(channel_scores.values())
        score_spread = max_score - min_score
        confidence = min(1.0, score_spread / 50.0)

        # Determine ADHD vs Autism dominance
        adhd_score = sum(channel_scores.get(ch, 0) for ch in self.ADHD_CHANNELS) / len(self.ADHD_CHANNELS)
        autism_score = sum(channel_scores.get(ch, 0) for ch in self.AUTISM_CHANNELS) / len(self.AUTISM_CHANNELS)

        is_adhd_dominant = adhd_score > autism_score + 15
        is_autism_dominant = autism_score > adhd_score + 15

        # Recommended approach based on dominance
        approach = self._get_recommended_approach(
            dominant_channel, is_adhd_dominant, is_autism_dominant
        )

        return ChannelDetectionResult(
            dominant_channel=dominant_channel,
            confidence=confidence,
            channel_scores=channel_scores,
            is_adhd_dominant=is_adhd_dominant,
            is_autism_dominant=is_autism_dominant,
            recommended_approach=approach,
        )

    async def update_state(
        self,
        user_id: int,
        channel_scores: dict[ChannelType, float],
        confidence: float,
        supporting_signals: list[str] | None = None,
    ) -> ChannelState:
        """
        Update the channel state for a user.

        Args:
            user_id: The user's ID
            channel_scores: Current scores per channel
            confidence: Confidence in these scores
            supporting_signals: Signals that support this assessment

        Returns:
            Created/updated ChannelState
        """
        # Get current active state from DB directly
        from sqlalchemy import update
        current_db = (
            self.db.query(ChannelState)
            .filter(
                ChannelState.user_id == user_id,
                ChannelState.period_end.is_(None),
            )
            .order_by(ChannelState.period_start.desc())
            .first()
        )

        # Determine dominant channel
        dominant = max(channel_scores.items(), key=lambda x: x[1])
        dominant_channel = dominant[0]

        if current_db:
            # Update existing state
            self.db.execute(
                update(ChannelState).where(ChannelState.id == current_db.id).values(
                    channel_scores={k.value: v for k, v in channel_scores.items()},
                    dominant_channel=dominant_channel.value,
                    confidence=confidence,
                    supporting_signals=supporting_signals or []
                )
            )
            self.db.commit()
            self.db.refresh(current_db)
            return current_db
        else:
            # Create new state
            state = ChannelState(
                user_id=user_id,
                dominant_channel=dominant_channel.value,
                channel_scores={k.value: v for k, v in channel_scores.items()},
                confidence=confidence,
                supporting_signals=supporting_signals or [],
            )
            self.db.add(state)
            self.db.commit()
            self.db.refresh(state)
            return state

    async def get_current_state(
        self,
        user_id: int,
    ) -> ChannelStateData | None:
        """
        Get current channel state for a user.

        Args:
            user_id: The user's ID

        Returns:
            ChannelStateData or None
        """
        state = (
            self.db.query(ChannelState)
            .filter(
                ChannelState.user_id == user_id,
                ChannelState.period_end.is_(None),
            )
            .order_by(ChannelState.period_start.desc())
            .first()
        )

        if not state:
            return None

        # Convert to data class
        channel_scores = {
            ChannelType(k): v for k, v in state.channel_scores.items()
        } if state.channel_scores else {ch: 50.0 for ch in self.CHANNELS}

        adhd_score = sum(channel_scores.get(ch, 0) for ch in self.ADHD_CHANNELS) / len(self.ADHD_CHANNELS)
        autism_score = sum(channel_scores.get(ch, 0) for ch in self.AUTISM_CHANNELS) / len(self.AUTISM_CHANNELS)

        # Cast Column types to proper types
        return ChannelStateData(
            user_id=user_id,
            dominant_channel=ChannelType(str(state.dominant_channel)),
            channel_scores=channel_scores,
            confidence=float(state.confidence),
            supporting_signals=list(state.supporting_signals) if state.supporting_signals else [],
            period_start=state.period_start,  # type: ignore[arg-type]
            is_adhd_dominant=adhd_score > autism_score + 15,
            is_autism_dominant=autism_score > adhd_score + 15,
        )

    def _analyze_messages(
        self,
        messages: list[dict[str, str | bool]],
    ) -> dict[ChannelType, float]:
        """
        Analyze messages to determine channel scores.

        Args:
            messages: List of message dicts with 'text' and 'is_user' keys

        Returns:
            Channel scores (0-100 per channel)
        """
        user_messages = [str(m.get("text", "")).lower() for m in messages if m.get("is_user", False)]

        if not user_messages:
            return {ch: 50.0 for ch in self.CHANNELS}

        # Score each channel based on keyword matches
        scores = {ch: 0.0 for ch in self.CHANNELS}

        for msg in user_messages:
            for channel, keywords in self.CHANNEL_SIGNALS.items():
                matches = sum(1 for kw in keywords if kw in msg)
                scores[channel] += matches

        # Normalize scores to 0-100
        max_score = max(scores.values()) if max(scores.values()) > 0 else 1
        normalized = {
            ch: (score / max_score) * 100 for ch, score in scores.items()
        }

        # Blend with baseline (50) for stability
        blended = {
            ch: normalized[ch] * 0.7 + 50 * 0.3 for ch in self.CHANNELS
        }

        return blended

    def _get_recommended_approach(
        self,
        dominant_channel: ChannelType,
        is_adhd_dominant: bool,
        is_autism_dominant: bool,
    ) -> str:
        """Get recommended coaching approach based on channel dominance."""
        # Channel-specific approaches
        channel_approaches = {
            ChannelType.FOCUS: "Offer structured task breakdown, clear steps, completion tracking",
            ChannelType.CREATIVE: "Allow exploration time, diverge before converging, accept tangents",
            ChannelType.SOCIAL: "Prioritize connection, allow processing time, be present",
            ChannelType.PHYSICAL: "Incorporate movement, short active bursts, body-anchoring",
            ChannelType.LEARNING: "Provide context, explain reasoning, encourage curiosity",
        }

        base_approach = channel_approaches.get(dominant_channel, "Adapt to user preference")

        # Add day-type modifier
        if is_adhd_dominant:
            return f"{base_approach}\nNOTE: ADHD-day detected - may need more novelty/stimulation"
        elif is_autism_dominant:
            return f"{base_approach}\nNOTE: Autism-day detected - may need more predictability/stability"
        else:
            return base_approach


__all__ = ["ChannelDominanceDetector", "ChannelStateData", "ChannelDetectionResult"]
