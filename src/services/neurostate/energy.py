"""
Energy Prediction Service for Aurora Sun V1.

Predicts energy levels from behavioral proxies:
- Response latency
- Message length
- Vocabulary complexity
- Time-of-day patterns
- Session context

References:
- ARCHITECTURE.md Section 3 (Neurotype Segmentation)
- ARCHITECTURE.md Section 3.7 (Energy Prediction)
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.core.segment_context import SegmentContext
from src.models.neurostate import EnergyLevel, EnergyLevelRecord

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class BehavioralSignals:
    """Behavioral signals extracted from user interaction."""

    response_latency_ms: int | None = None
    message_length: int = 0
    vocabulary_complexity: float = 0.0
    time_of_day_hour: int = 0
    day_of_week: int = 0
    recent_message_count: int = 0
    avg_message_length: float = 0.0
    punctuation_usage: float = 0.0           # Higher = more deliberate
    question_count: int = 0
    exclamation_count: int = 0


@dataclass
class EnergyPrediction:
    """Energy level prediction result."""

    energy_level: EnergyLevel
    energy_score: float                       # Numeric score (0-100)
    confidence: float                         # Prediction confidence (0-1)
    signals_used: dict[str, float]            # Which signals were used
    contributing_factors: list[str]          # What's affecting energy
    recommendations: list[str]


# =============================================================================
# Service
# =============================================================================

class EnergyPredictor:
    """
    Predicts energy levels from behavioral proxies.

    Key Principles:
    - Energy ≠ Mood or Motivation
    - Behavioral proxies are more reliable than self-report (especially for AU/AH)
    - Combines multiple signals for robust prediction
    - Adapts to individual baseline

    Behavioral Proxies:
    - Response latency: Slower = lower energy (or deeper processing for AU)
    - Message length: Very short = low/overwhelmed, moderate = baseline, long = engaged
    - Vocabulary complexity: Reflects cognitive load processing
    - Time-of-day: Individual circadian patterns
    - Punctuation: More deliberate = more energy

    Usage:
        predictor = EnergyPredictor(db)
        prediction = await predictor.predict(user_id=123, behavioral_signals={...})
    """

    # Energy level thresholds
    ENERGY_CRITICAL = 15.0
    ENERGY_LOW = 35.0
    ENERGY_BASELINE = 50.0
    ENERGY_ELEVATED = 70.0
    ENERGY_HYPERFOCUS = 85.0

    # Signal weights
    LATENCY_WEIGHT = 0.25
    MESSAGE_LENGTH_WEIGHT = 0.20
    VOCAB_WEIGHT = 0.15
    TIME_WEIGHT = 0.15
    ENGAGEMENT_WEIGHT = 0.25

    # Message length thresholds
    LENGTH_CRITICAL = 10      # Very short
    LENGTH_LOW = 30          # Short
    LENGTH_BASELINE = 100    # Normal
    LENGTH_LONG = 300        # Long/engaged

    def __init__(self, db: Session, segment_context: SegmentContext | None = None):
        """
        Initialize the energy predictor.

        Args:
            db: SQLAlchemy database session
            segment_context: Optional segment context (for segment-aware assessment)
        """
        self.db = db
        self.segment_context = segment_context

    async def predict(
        self,
        user_id: int,
        behavioral_signals: BehavioralSignals | None = None,
        self_report_score: float | None = None,
    ) -> EnergyPrediction:
        """
        Predict energy level from behavioral signals (and optionally self-report).

        Segment-aware assessment:
        - AU: behavioral_proxy only (interoception unreliable)
        - AH: composite (behavioral + self-report, behavioral weighted heavily)
        - AD/NT: self_report primary, behavioral supplementary

        Args:
            user_id: The user's ID
            behavioral_signals: Optional pre-extracted signals
            self_report_score: Optional self-reported energy (0-100)

        Returns:
            EnergyPrediction with level and recommendations
        """
        # Get signals
        if behavioral_signals is None:
            signals = await self._get_signals_from_history(user_id)
        else:
            signals = behavioral_signals

        # Get user's baseline (personalized)
        baseline = await self._get_user_baseline(user_id)

        # Calculate each signal's contribution
        latency_score = self._score_latency(signals.response_latency_ms)
        length_score = self._score_message_length(signals.message_length)
        vocab_score = self._score_vocabulary(signals.vocabulary_complexity)
        time_score = self._score_time_of_day(signals.time_of_day_hour, signals.day_of_week)
        engagement_score = self._score_engagement(signals)

        # Weighted combination (behavioral)
        behavioral_score = (
            latency_score * self.LATENCY_WEIGHT +
            length_score * self.MESSAGE_LENGTH_WEIGHT +
            vocab_score * self.VOCAB_WEIGHT +
            time_score * self.TIME_WEIGHT +
            engagement_score * self.ENGAGEMENT_WEIGHT
        )

        # Apply segment-specific assessment method
        if self.segment_context:
            assessment_method = self.segment_context.neuro.energy_assessment
            interoception = self.segment_context.neuro.interoception_reliability

            if assessment_method == "behavioral_proxy":
                # AU: ONLY behavioral (interoception unreliable)
                raw_score = behavioral_score
                confidence_note = f"Behavioral proxy only (interoception: {interoception})"
            elif assessment_method == "composite" and self_report_score is not None:
                # AH: Composite with behavioral weighted heavily (85% behavioral, 15% self-report)
                # because interoception is very_low
                raw_score = behavioral_score * 0.85 + self_report_score * 0.15
                confidence_note = f"Composite: 85% behavioral + 15% self-report (interoception: {interoception})"
            elif assessment_method == "self_report" and self_report_score is not None:
                # AD/NT: Self-report primary (60% self-report, 40% behavioral)
                raw_score = self_report_score * 0.60 + behavioral_score * 0.40
                confidence_note = f"Self-report primary (interoception: {interoception})"
            else:
                # Fallback: behavioral only if no self-report provided
                raw_score = behavioral_score
                confidence_note = "Behavioral proxy (no self-report provided)"
        else:
            # No segment context: use behavioral only (safe default)
            raw_score = behavioral_score
            confidence_note = "Behavioral proxy (no segment context)"

        # Adjust for user baseline
        adjusted_score = self._adjust_for_baseline(raw_score, baseline)

        # Determine energy level
        energy_level = self._score_to_level(adjusted_score)
        energy_score = min(100.0, max(0.0, adjusted_score))

        # Calculate confidence
        confidence = self._calculate_confidence(signals, baseline)

        # Get contributing factors
        factors = self._get_contributing_factors(
            signals, latency_score, length_score, vocab_score, time_score, engagement_score
        )
        factors.append(confidence_note)  # Add assessment method note

        # Get recommendations
        recommendations = self._get_recommendations(energy_level, energy_score)

        # Log the prediction
        await self._log_prediction(
            user_id=user_id,
            energy_level=energy_level,
            energy_score=energy_score,
            behavioral_signals=signals,
        )

        return EnergyPrediction(
            energy_level=energy_level,
            energy_score=energy_score,
            confidence=confidence,
            signals_used={
                "latency": latency_score,
                "length": length_score,
                "vocab": vocab_score,
                "time": time_score,
                "engagement": engagement_score,
            },
            contributing_factors=factors,
            recommendations=recommendations,
        )

    def _score_latency(self, latency_ms: int | None) -> float:
        """Score response latency."""
        if latency_ms is None:
            return self.ENERGY_BASELINE

        # Very fast (s) = high energy<1 or impulse
        # Normal (1-5s) = baseline
        # Slow (>10s) = low energy OR deep processing (for AU)

        if latency_ms < 1000:
            return 75.0  # Quick response
        elif latency_ms < 3000:
            return 60.0  # Normal
        elif latency_ms < 10000:
            return 45.0  # Slower
        else:
            return 30.0  # Very slow

    def _score_message_length(self, length: int) -> float:
        """Score message length."""
        if length < self.LENGTH_CRITICAL:
            return 20.0  # Very short - low energy or overwhelmed
        elif length < self.LENGTH_LOW:
            return 40.0  # Short
        elif length < self.LENGTH_BASELINE:
            return 55.0  # Normal
        elif length < self.LENGTH_LONG:
            return 70.0  # Longer - engaged
        else:
            return 85.0  # Very long - high engagement

    def _score_vocabulary(self, complexity: float) -> float:
        """Score vocabulary complexity."""
        # Complexity 0-1
        # Low complexity = low energy OR simple communication style
        # High complexity = high energy OR detail-focused (AU)

        if complexity < 0.2:
            return 35.0
        elif complexity < 0.4:
            return 50.0
        elif complexity < 0.6:
            return 60.0
        else:
            return 75.0

    def _score_time_of_day(self, hour: int, day_of_week: int) -> float:
        """Score time-of-day based on typical circadian patterns."""
        # This would ideally be personalized per user
        # For now, use general patterns

        # Morning (6-10): Typically higher
        # Midday (10-14): Baseline
        # Afternoon (14-18): Can have dip
        # Evening (18-22): Variable
        # Night (22-6): Typically lower

        if 6 <= hour < 10:
            return 65.0
        elif 10 <= hour < 14:
            return 60.0
        elif 14 <= hour < 18:
            return 50.0
        elif 18 <= hour < 22:
            return 55.0
        else:
            return 40.0

    def _score_engagement(self, signals: BehavioralSignals) -> float:
        """Score overall engagement level."""
        score = 50.0

        # Questions show engagement
        if signals.question_count > 2:
            score += 15.0
        elif signals.question_count > 0:
            score += 8.0

        # Exclamations show energy
        if signals.exclamation_count > 2:
            score += 15.0
        elif signals.exclamation_count > 0:
            score += 8.0

        # Punctuation shows deliberation
        if signals.punctuation_usage > 0.5:
            score += 10.0

        # Recent message count shows session engagement
        if signals.recent_message_count > 10:
            score += 10.0
        elif signals.recent_message_count > 5:
            score += 5.0

        return min(100.0, score)

    def _adjust_for_baseline(self, score: float, baseline: float) -> float:
        """Adjust score based on user's typical baseline."""
        # Blend raw score with baseline (30% baseline, 70% raw)
        return score * 0.7 + baseline * 0.3

    def _score_to_level(self, score: float) -> EnergyLevel:
        """Convert numeric score to energy level."""
        if score < self.ENERGY_CRITICAL:
            return EnergyLevel.CRITICAL
        elif score < self.ENERGY_LOW:
            return EnergyLevel.LOW
        elif score < self.ENERGY_BASELINE:
            return EnergyLevel.BASELINE
        elif score < self.ENERGY_ELEVATED:
            return EnergyLevel.ELEVATED
        else:
            return EnergyLevel.HYPERFOCUS

    def _calculate_confidence(
        self,
        signals: BehavioralSignals,
        baseline: float,
    ) -> float:
        """Calculate prediction confidence."""
        # More signals = higher confidence
        signal_count = sum([
            signals.response_latency_ms is not None,
            signals.message_length > 0,
            signals.vocabulary_complexity > 0,
            signals.recent_message_count > 0,
        ])

        base_confidence = signal_count / 4.0

        # Adjust for baseline reliability
        if baseline > 0:
            base_confidence += 0.2

        return min(1.0, base_confidence)

    def _get_contributing_factors(
        self,
        signals: BehavioralSignals,
        latency: float,
        length: float,
        vocab: float,
        time: float,
        engagement: float,
    ) -> list[str]:
        """Identify factors contributing to the prediction."""
        factors = []

        if signals.response_latency_ms:
            if signals.response_latency_ms < 1000:
                factors.append("Quick responses")
            elif signals.response_latency_ms > 10000:
                factors.append("Slow responses")

        if signals.message_length < self.LENGTH_LOW:
            factors.append("Brief messages")
        elif signals.message_length > self.LENGTH_LONG:
            factors.append("Detailed messages")

        if signals.question_count > 2:
            factors.append("Many questions")
        if signals.exclamation_count > 2:
            factors.append("Enthusiastic tone")

        # Time-based
        if 6 <= signals.time_of_day_hour < 10:
            factors.append("Morning time")
        elif 22 <= signals.time_of_day_hour or signals.time_of_day_hour < 6:
            factors.append("Evening/night time")

        return factors

    def _get_recommendations(
        self,
        energy_level: EnergyLevel,
        energy_score: float,
    ) -> list[str]:
        """Get recommendations based on energy level."""
        if energy_level == EnergyLevel.CRITICAL:
            return [
                "Energy critically low - prioritize rest",
                "Minimize demands, no new tasks",
                "Consider shutdown protocol for AU/AH",
            ]
        elif energy_level == EnergyLevel.LOW:
            return [
                "Energy low - focus on essential tasks only",
                "Consider delegating or postponing non-essentials",
                "Short rest may help",
            ]
        elif energy_level == EnergyLevel.BASELINE:
            return [
                "Energy is normal - sustainable pace",
                "Good for routine tasks",
                "Avoid overcommitment",
            ]
        elif energy_level == EnergyLevel.ELEVATED:
            return [
                "Energy elevated - good for demanding tasks",
                "Good time for challenging work",
                "Watch for overcommitment",
            ]
        else:  # HYPERFOCUS
            return [
                "Energy very high - may indicate hyperfocus",
                "Channel into important tasks",
                "Remember to take breaks and eat",
            ]

    async def _get_signals_from_history(
        self,
        user_id: int,
    ) -> BehavioralSignals:
        """Extract signals from recent message history."""
        # This would typically query session messages
        # For now, return defaults
        now = datetime.now(UTC)
        return BehavioralSignals(
            time_of_day_hour=now.hour,
            day_of_week=now.weekday(),
        )

    async def _get_user_baseline(self, user_id: int) -> float:
        """Get user's typical energy baseline."""
        # Query recent energy records
        recent = (
            self.db.query(func.avg(EnergyLevelRecord.energy_score))
            .filter(
                EnergyLevelRecord.user_id == user_id,
                EnergyLevelRecord.predicted_at >= datetime.now(UTC) - timedelta(days=7),
            )
            .scalar()
        )

        return float(recent) if recent else self.ENERGY_BASELINE

    async def _log_prediction(
        self,
        user_id: int,
        energy_level: EnergyLevel,
        energy_score: float,
        behavioral_signals: BehavioralSignals,
    ) -> EnergyLevelRecord:
        """Log the prediction to database."""
        record = EnergyLevelRecord(
            user_id=user_id,
            energy_level=energy_level.value,
            energy_score=energy_score,
            behavioral_proxies={
                "message_length": behavioral_signals.message_length,
                "time_of_day": behavioral_signals.time_of_day_hour,
            },
        )
        self.db.add(record)
        self.db.commit()
        return record


__all__ = ["EnergyPredictor", "BehavioralSignals", "EnergyPrediction"]
