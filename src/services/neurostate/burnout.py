"""
Burnout Type Classifier Service for Aurora Sun V1.

Three distinct burnout types as defined in ARCHITECTURE.md Section 3:
- ADHD Boom-Bust: Hyperfocus -> Crash cycle
- Autism Overload->Shutdown: Sensory/Cognitive overload
- AuDHD Triple: All three combined

References:
- ARCHITECTURE.md Section 3 (Neurotype Segmentation)
- ARCHITECTURE.md Section 3.4 (Burnout Types)
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.models.neurostate import BurnoutAssessment, BurnoutType

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class BurnoutState:
    """Current burnout state for a user."""

    user_id: int
    burnout_type: BurnoutType
    severity: float                       # 0-100
    is_active: bool
    days_in_state: int
    trajectory: list[float]                # Last N days of energy
    indicators: dict
    last_assessed: datetime


@dataclass
class BurnoutClassification:
    """Result of burnout classification."""

    burnout_type: BurnoutType
    confidence: float                      # 0-1
    severity: float                        # 0-100
    trajectory_pattern: str               # "declining", "stable", "volatile", "recovering"
    recommended_protocol: str


# =============================================================================
# Service
# =============================================================================

class BurnoutClassifier:
    """
    Classifies and tracks burnout type for neurodivergent users.

    Key Principles:
    - Three distinct burnout types (not one-size-fits-all)
    - Classification requires understanding the TRAJECTORY, not just current state
    - Intervention differs by type

    Burnout Types:
    - AD (Boom-Bust): Pattern of high activity -> complete exhaustion
    - AU (Overload): Gradual accumulation -> sudden shutdown
    - AH (Triple): Both patterns + classic exhaustion

    Usage:
        classifier = BurnoutClassifier(db)
        result = await classifier.classify(user_id=123, energy_trajectory=[...])
    """

    # Thresholds
    SEVERITY_MILD = 25.0
    SEVERITY_MODERATE = 50.0
    SEVERITY_SEVERE = 75.0

    # Trajectory analysis
    TRAJECTORY_DAYS = 14                   # Analyze last 14 days
    VOLATILITY_THRESHOLD = 30.0           # High variance = volatile
    DECLINE_RATE_THRESHOLD = 10.0         # >10 points/day = declining

    def __init__(self, db: Session):
        """
        Initialize the burnout classifier.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    async def classify(
        self,
        user_id: int,
        energy_trajectory: list[float],
    ) -> BurnoutClassification:
        """
        Classify burnout type based on energy trajectory.

        Args:
            user_id: The user's ID
            energy_trajectory: List of daily energy levels (0-100), oldest first

        Returns:
            BurnoutClassification with type, confidence, and recommendations
        """
        if len(energy_trajectory) < 3:
            return BurnoutClassification(
                burnout_type=BurnoutType.AD_BOOM_BUST,
                confidence=0.0,
                severity=0.0,
                trajectory_pattern="insufficient_data",
                recommended_protocol="Monitor energy levels",
            )

        # Get user segment
        segment_code = self._get_user_segment(user_id)

        # Analyze trajectory
        trajectory_pattern = self._analyze_trajectory(energy_trajectory)
        severity = self._calculate_severity(energy_trajectory, trajectory_pattern)

        # Classify based on segment and pattern
        if segment_code == "AU":
            burnout_type, confidence = self._classify_autism(energy_trajectory, trajectory_pattern)
        elif segment_code == "AD":
            burnout_type, confidence = self._classify_adhd(energy_trajectory, trajectory_pattern)
        else:  # AH or default
            burnout_type, confidence = self._classify_audhd(energy_trajectory, trajectory_pattern)

        # Get recommended protocol
        protocol = self._get_burnout_protocol(burnout_type, severity, trajectory_pattern)

        return BurnoutClassification(
            burnout_type=burnout_type,
            confidence=confidence,
            severity=severity,
            trajectory_pattern=trajectory_pattern,
            recommended_protocol=protocol,
        )

    async def assess_current_state(
        self,
        user_id: int,
    ) -> BurnoutState | None:
        """
        Get the current burnout state for a user.

        Args:
            user_id: The user's ID

        Returns:
            BurnoutState or None if no active assessment
        """
        assessment = (
            self.db.query(BurnoutAssessment)
            .filter(
                BurnoutAssessment.user_id == user_id,
                BurnoutAssessment.resolved_at.is_(None),
            )
            .order_by(BurnoutAssessment.assessed_at.desc())
            .first()
        )

        if not assessment:
            return None

        trajectory = assessment.energy_trajectory or []
        days_in_state = (datetime.now(UTC) - assessment.assessed_at).days

        return BurnoutState(
            user_id=user_id,
            burnout_type=BurnoutType(assessment.burnout_type),
            severity=assessment.severity_score,
            is_active=assessment.resolved_at is None,
            days_in_state=days_in_state,
            trajectory=trajectory,
            indicators=assessment.indicators or {},
            last_assessed=assessment.assessed_at,
        )

    async def create_assessment(
        self,
        user_id: int,
        burnout_type: BurnoutType,
        severity: float,
        energy_trajectory: list[float],
        indicators: dict | None = None,
        notes: str | None = None,
    ) -> BurnoutAssessment:
        """
        Create a new burnout assessment.

        Args:
            user_id: The user's ID
            burnout_type: Classified burnout type
            severity: Severity score (0-100)
            energy_trajectory: Energy levels over time
            indicators: Supporting indicators
            notes: Assessment notes

        Returns:
            Created BurnoutAssessment
        """
        # Close any existing active assessment
        active = (
            self.db.query(BurnoutAssessment)
            .filter(
                BurnoutAssessment.user_id == user_id,
                BurnoutAssessment.resolved_at.is_(None),
            )
            .all()
        )
        for a in active:
            a.resolved_at = datetime.now(UTC)

        # Create new assessment
        assessment = BurnoutAssessment(
            user_id=user_id,
            burnout_type=burnout_type.value,
            severity_score=severity,
            energy_trajectory=energy_trajectory,
            indicators=indicators or {},
            notes=notes,
        )
        self.db.add(assessment)
        self.db.commit()
        self.db.refresh(assessment)
        return assessment

    async def resolve_assessment(
        self,
        assessment_id: int,
        notes: str | None = None,
    ) -> BurnoutAssessment:
        """
        Mark a burnout assessment as resolved.

        Args:
            assessment_id: The assessment ID
            notes: Resolution notes

        Returns:
            Updated BurnoutAssessment
        """
        assessment = (
            self.db.query(BurnoutAssessment)
            .filter(BurnoutAssessment.id == assessment_id)
            .first()
        )
        if not assessment:
            raise ValueError(f"BurnoutAssessment {assessment_id} not found")

        assessment.resolved_at = datetime.now(UTC)
        if notes:
            assessment.notes = (assessment.notes or "") + f"\nResolution: {notes}"

        self.db.commit()
        self.db.refresh(assessment)
        return assessment

    def _analyze_trajectory(self, trajectory: list[float]) -> str:
        """Analyze the energy trajectory pattern."""
        if len(trajectory) < 3:
            return "insufficient_data"

        # Calculate volatility (variance)
        import statistics
        if len(trajectory) > 1:
            variance = statistics.variance(trajectory)
            if variance > self.VOLATILITY_THRESHOLD ** 2:
                return "volatile"

        # Calculate trend
        recent = trajectory[-7:] if len(trajectory) >= 7 else trajectory
        if len(recent) >= 3:
            early_avg = sum(recent[:len(recent)//2]) / (len(recent)//2)
            late_avg = sum(recent[len(recent)//2:]) / (len(recent) - len(recent)//2)

            if late_avg < early_avg - self.DECLINE_RATE_THRESHOLD * 3:
                return "declining"
            elif late_avg > early_avg + self.DECLINE_RATE_THRESHOLD * 3:
                return "recovering"

        return "stable"

    def _calculate_severity(
        self,
        trajectory: list[float],
        pattern: str,
    ) -> float:
        """Calculate severity score from trajectory and pattern."""
        if not trajectory:
            return 0.0

        # Base severity on current level
        current = trajectory[-1]
        base_severity = 100 - current

        # Adjust based on pattern
        if pattern == "declining":
            base_severity *= 1.2
        elif pattern == "volatile":
            base_severity *= 1.1
        elif pattern == "recovering":
            base_severity *= 0.8

        return min(100.0, max(0.0, base_severity))

    def _classify_autism(
        self,
        trajectory: list[float],
        pattern: str,
    ) -> tuple[BurnoutType, float]:
        """Classify burnout for Autism segment."""
        # AU: Gradual overload pattern
        # Look for: sustained high-low pattern, slow decline, then crash
        if len(trajectory) >= 7:
            recent = trajectory[-7:]
            if all(e < 40 for e in recent):
                return BurnoutType.AU_OVERLOAD, 0.85
            elif pattern == "declining" and any(e < 30 for e in trajectory[-3:]):
                return BurnoutType.AU_OVERLOAD, 0.75

        return BurnoutType.AU_OVERLOAD, 0.6

    def _classify_adhd(
        self,
        trajectory: list[float],
        pattern: str,
    ) -> tuple[BurnoutType, float]:
        """Classify burnout for ADHD segment."""
        # AD: Boom-bust pattern
        # Look for: high variance, peaks followed by crashes
        if len(trajectory) >= 5:
            import statistics
            variance = statistics.variance(trajectory) if len(trajectory) > 1 else 0

            # High volatility with recent crash
            if variance > self.VOLATILITY_THRESHOLD ** 2 and trajectory[-1] < 30:
                return BurnoutType.AD_BOOM_BUST, 0.85

            # Very high then very low
            if max(trajectory[-5:]) > 80 and min(trajectory[-5:]) < 30:
                return BurnoutType.AD_BOOM_BUST, 0.8

        return BurnoutType.AD_BOOM_BUST, 0.6

    def _classify_audhd(
        self,
        trajectory: list[float],
        pattern: str,
    ) -> tuple[BurnoutType, float]:
        """Classify burnout for AuDHD segment."""
        # AH: Triple type - both patterns + exhaustion
        # This is the default for AH as they can experience all three

        # First check if it's clearly one type
        autism_type, autism_conf = self._classify_autism(trajectory, pattern)
        adhd_type, adhd_conf = self._classify_adhd(trajectory, pattern)

        # If both have high confidence, it's likely triple type
        if autism_conf > 0.7 and adhd_conf > 0.7:
            return BurnoutType.AH_TRIPLE, 0.9

        # If volatility is high + low current = triple
        import statistics
        variance = statistics.variance(trajectory) if len(trajectory) > 1 else 0
        if variance > self.VOLATILITY_THRESHOLD ** 2 and trajectory[-1] < 40:
            return BurnoutType.AH_TRIPLE, 0.8

        # Default to highest confidence single type
        if autism_conf > adhd_conf:
            return autism_type, autism_conf * 0.7
        else:
            return adhd_type, adhd_conf * 0.7

    def _get_burnout_protocol(
        self,
        burnout_type: BurnoutType,
        severity: float,
        pattern: str,
    ) -> str:
        """Get recommended protocol based on burnout type and severity."""
        if severity >= self.SEVERITY_SEVERE:
            if burnout_type == BurnoutType.AD_BOOM_BUST:
                return "CRASH PROTOCOL: Complete rest, no demands, rehydration, sleep hygiene"
            elif burnout_type == BurnoutType.AU_OVERLOAD:
                return "SHUTDOWN PROTOCOL: Sensory reduction, dark quiet space, no social demands, wait"
            else:
                return "TRIPLE CRISIS PROTOCOL: All of above + check physical needs + professional support"

        if severity >= self.SEVERITY_MODERATE:
            if burnout_type == BurnoutType.AD_BOOM_BUST:
                return "Recovery: Reduce demands, restore sleep, avoid stimulation cycling"
            elif burnout_type == BurnoutType.AU_OVERLOAD:
                return "Recovery: Sensory accommodation, predictability, reduce cognitive load"
            else:
                return "Recovery: Combined approach - sensory first, then structure"

        if severity >= self.SEVERITY_MILD:
            return "Early intervention: Monitor, reduce non-essential demands"

        return "Prevention: Maintain current patterns, watch for escalation"

    def _get_user_segment(self, user_id: int) -> str:
        """Get user's segment code."""
        from src.models.user import User
        user = self.db.query(User).filter(User.id == user_id).first()
        return user.working_style_code if user else "NT"


__all__ = ["BurnoutClassifier", "BurnoutState", "BurnoutClassification"]
