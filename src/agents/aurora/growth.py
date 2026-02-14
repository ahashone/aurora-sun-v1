"""
Growth Tracker for Aurora Agent.

Tracks user growth across 5 dimensions with 3-window comparison:
- Dimensions: consistency, resilience, self_awareness, goal_progress, wellbeing
- Windows: now (current week), 4 weeks ago, 12 weeks ago
- Produces trajectory scores showing direction of change

The growth tracker provides objective evidence of progress,
which is especially important for neurodivergent users who
often underestimate their own growth due to negativity bias.

Reference: ARCHITECTURE.md Section 5 (Aurora Agent - Growth Tracker)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.segment_context import SegmentContext


@dataclass
class TrajectoryScore:
    """Score across 5 growth dimensions.

    Each dimension is scored 0.0 to 1.0.
    A trajectory score represents a snapshot at a point in time.

    Dimensions:
    - consistency: How regularly the user engages with their systems
    - resilience: How quickly the user bounces back from setbacks
    - self_awareness: How accurately the user perceives their own state
    - goal_progress: How much progress toward declared goals
    - wellbeing: Overall energy and mood trajectory
    """

    consistency: float = 0.0
    resilience: float = 0.0
    self_awareness: float = 0.0
    goal_progress: float = 0.0
    wellbeing: float = 0.0
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    @property
    def overall(self) -> float:
        """Calculate overall trajectory score (weighted average).

        Returns:
            Weighted average of all dimensions (0.0-1.0)
        """
        weights = {
            "consistency": 0.20,
            "resilience": 0.25,
            "self_awareness": 0.20,
            "goal_progress": 0.15,
            "wellbeing": 0.20,
        }
        total = (
            self.consistency * weights["consistency"]
            + self.resilience * weights["resilience"]
            + self.self_awareness * weights["self_awareness"]
            + self.goal_progress * weights["goal_progress"]
            + self.wellbeing * weights["wellbeing"]
        )
        return round(total, 4)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "consistency": self.consistency,
            "resilience": self.resilience,
            "self_awareness": self.self_awareness,
            "goal_progress": self.goal_progress,
            "wellbeing": self.wellbeing,
            "overall": self.overall,
            "timestamp": self.timestamp,
        }


@dataclass
class WindowComparison:
    """Comparison between two trajectory windows.

    Shows the delta (change) in each dimension between
    the current window and a historical window.
    """

    window_label: str  # "4_weeks" or "12_weeks"
    current: TrajectoryScore = field(default_factory=TrajectoryScore)
    historical: TrajectoryScore = field(default_factory=TrajectoryScore)

    @property
    def delta_consistency(self) -> float:
        """Change in consistency."""
        return round(self.current.consistency - self.historical.consistency, 4)

    @property
    def delta_resilience(self) -> float:
        """Change in resilience."""
        return round(self.current.resilience - self.historical.resilience, 4)

    @property
    def delta_self_awareness(self) -> float:
        """Change in self-awareness."""
        return round(
            self.current.self_awareness - self.historical.self_awareness, 4
        )

    @property
    def delta_goal_progress(self) -> float:
        """Change in goal progress."""
        return round(
            self.current.goal_progress - self.historical.goal_progress, 4
        )

    @property
    def delta_wellbeing(self) -> float:
        """Change in wellbeing."""
        return round(self.current.wellbeing - self.historical.wellbeing, 4)

    @property
    def delta_overall(self) -> float:
        """Change in overall score."""
        return round(self.current.overall - self.historical.overall, 4)

    @property
    def improving_dimensions(self) -> list[str]:
        """List of dimensions that are improving (delta > 0.05)."""
        dims: list[str] = []
        if self.delta_consistency > 0.05:
            dims.append("consistency")
        if self.delta_resilience > 0.05:
            dims.append("resilience")
        if self.delta_self_awareness > 0.05:
            dims.append("self_awareness")
        if self.delta_goal_progress > 0.05:
            dims.append("goal_progress")
        if self.delta_wellbeing > 0.05:
            dims.append("wellbeing")
        return dims

    @property
    def declining_dimensions(self) -> list[str]:
        """List of dimensions that are declining (delta < -0.05)."""
        dims: list[str] = []
        if self.delta_consistency < -0.05:
            dims.append("consistency")
        if self.delta_resilience < -0.05:
            dims.append("resilience")
        if self.delta_self_awareness < -0.05:
            dims.append("self_awareness")
        if self.delta_goal_progress < -0.05:
            dims.append("goal_progress")
        if self.delta_wellbeing < -0.05:
            dims.append("wellbeing")
        return dims

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "window_label": self.window_label,
            "current": self.current.to_dict(),
            "historical": self.historical.to_dict(),
            "deltas": {
                "consistency": self.delta_consistency,
                "resilience": self.delta_resilience,
                "self_awareness": self.delta_self_awareness,
                "goal_progress": self.delta_goal_progress,
                "wellbeing": self.delta_wellbeing,
                "overall": self.delta_overall,
            },
            "improving": self.improving_dimensions,
            "declining": self.declining_dimensions,
        }


@dataclass
class GrowthSummary:
    """Complete growth summary with all windows.

    Contains the current trajectory plus comparisons to
    4 weeks and 12 weeks ago.
    """

    user_id: int = 0
    current: TrajectoryScore = field(default_factory=TrajectoryScore)
    vs_4_weeks: WindowComparison = field(
        default_factory=lambda: WindowComparison(window_label="4_weeks")
    )
    vs_12_weeks: WindowComparison = field(
        default_factory=lambda: WindowComparison(window_label="12_weeks")
    )
    overall_trend: str = "stable"  # "growing", "stable", "declining"
    narrative: str = ""  # Human-readable growth narrative
    generated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "user_id": self.user_id,
            "current": self.current.to_dict(),
            "vs_4_weeks": self.vs_4_weeks.to_dict(),
            "vs_12_weeks": self.vs_12_weeks.to_dict(),
            "overall_trend": self.overall_trend,
            "narrative": self.narrative,
            "generated_at": self.generated_at,
        }


class GrowthTracker:
    """Growth Tracker for Aurora Agent.

    Tracks user growth across 5 dimensions with 3-window comparison.
    Provides objective evidence of progress for users.

    Usage:
        tracker = GrowthTracker()
        score = tracker.calculate_trajectory(user_id=1, segment_ctx=ctx)
        summary = tracker.get_growth_summary(user_id=1, segment_ctx=ctx)
    """

    def __init__(self) -> None:
        """Initialize the growth tracker."""
        # In-memory storage (production: PostgreSQL)
        self._scores: dict[int, list[TrajectoryScore]] = {}

    def record_score(
        self,
        user_id: int,
        score: TrajectoryScore,
    ) -> None:
        """Record a trajectory score for a user.

        Args:
            user_id: The user's unique identifier
            score: The trajectory score to record
        """
        if user_id not in self._scores:
            self._scores[user_id] = []
        self._scores[user_id].append(score)

    def calculate_trajectory(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
        engagement_days: int = 5,
        total_days: int = 7,
        setback_recovery_hours: float = 48.0,
        energy_predictions_correct: int = 3,
        energy_predictions_total: int = 5,
        goals_completed: int = 2,
        goals_total: int = 5,
        avg_energy: float = 0.6,
        avg_mood: float = 0.6,
    ) -> TrajectoryScore:
        """Calculate current trajectory score for a user.

        In production, these inputs would come from real user data.
        For now, they are passed as parameters for testability.

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context
            engagement_days: Days with engagement in the current window
            total_days: Total days in the window
            setback_recovery_hours: Average hours to recover from setbacks
            energy_predictions_correct: Number of correct energy self-assessments
            energy_predictions_total: Total energy self-assessments
            goals_completed: Number of goals completed
            goals_total: Total goals set
            avg_energy: Average energy level (0-1)
            avg_mood: Average mood level (0-1)

        Returns:
            Calculated TrajectoryScore
        """
        # Consistency: engagement ratio
        consistency = (
            engagement_days / total_days if total_days > 0 else 0.0
        )
        consistency = min(1.0, max(0.0, consistency))

        # Resilience: inverse of recovery time, normalized to 0-1
        # 0h = perfect (1.0), 168h (1 week) = worst (0.0)
        max_recovery = 168.0  # 1 week in hours
        resilience = max(
            0.0, 1.0 - (setback_recovery_hours / max_recovery)
        )

        # Self-awareness: accuracy of energy self-report
        # For segments with low interoception, adjust threshold
        if energy_predictions_total > 0:
            raw_awareness = (
                energy_predictions_correct / energy_predictions_total
            )
        else:
            raw_awareness = 0.5  # Default if no data

        # Adjust for interoception reliability
        interoception = segment_ctx.neuro.interoception_reliability
        if interoception == "very_low":
            # AuDHD: even moderate accuracy is impressive
            self_awareness = min(1.0, raw_awareness * 1.5)
        elif interoception == "low":
            # Autism: moderate accuracy is good
            self_awareness = min(1.0, raw_awareness * 1.3)
        else:
            self_awareness = raw_awareness

        # Goal progress: completion ratio
        goal_progress = (
            goals_completed / goals_total if goals_total > 0 else 0.0
        )
        goal_progress = min(1.0, max(0.0, goal_progress))

        # Wellbeing: average of energy and mood
        wellbeing = (avg_energy + avg_mood) / 2.0
        wellbeing = min(1.0, max(0.0, wellbeing))

        score = TrajectoryScore(
            consistency=round(consistency, 4),
            resilience=round(resilience, 4),
            self_awareness=round(self_awareness, 4),
            goal_progress=round(goal_progress, 4),
            wellbeing=round(wellbeing, 4),
        )

        # Record score
        self.record_score(user_id, score)

        return score

    def compare_windows(
        self,
        user_id: int,
        current: TrajectoryScore,
        weeks_ago: int,
    ) -> WindowComparison:
        """Compare current trajectory to a historical window.

        Args:
            user_id: The user's unique identifier
            current: The current trajectory score
            weeks_ago: How many weeks back to compare

        Returns:
            WindowComparison with deltas
        """
        label = f"{weeks_ago}_weeks"
        historical = self._get_historical_score(user_id, weeks_ago)

        return WindowComparison(
            window_label=label,
            current=current,
            historical=historical,
        )

    def get_growth_summary(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
        current: TrajectoryScore | None = None,
    ) -> GrowthSummary:
        """Get complete growth summary with all windows.

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context
            current: Optional current score (calculates if None)

        Returns:
            Complete GrowthSummary
        """
        if current is None:
            current = self.calculate_trajectory(
                user_id=user_id, segment_ctx=segment_ctx
            )

        vs_4 = self.compare_windows(user_id, current, weeks_ago=4)
        vs_12 = self.compare_windows(user_id, current, weeks_ago=12)

        # Determine overall trend
        overall_trend = self._determine_trend(vs_4, vs_12)

        # Generate narrative
        narrative = self._generate_narrative(
            current, vs_4, vs_12, overall_trend
        )

        return GrowthSummary(
            user_id=user_id,
            current=current,
            vs_4_weeks=vs_4,
            vs_12_weeks=vs_12,
            overall_trend=overall_trend,
            narrative=narrative,
        )

    def export_user_data(self, user_id: int) -> dict[str, Any]:
        """GDPR export for growth data.

        Args:
            user_id: The user's unique identifier

        Returns:
            All growth data for the user
        """
        scores = self._scores.get(user_id, [])
        return {
            "trajectory_scores": [s.to_dict() for s in scores],
        }

    def delete_user_data(self, user_id: int) -> None:
        """GDPR delete for growth data.

        Args:
            user_id: The user's unique identifier
        """
        self._scores.pop(user_id, None)

    def _get_historical_score(
        self, user_id: int, weeks_ago: int
    ) -> TrajectoryScore:
        """Get the trajectory score from N weeks ago.

        Args:
            user_id: The user's unique identifier
            weeks_ago: How many weeks back to look

        Returns:
            Historical TrajectoryScore (or zero-score if no data)
        """
        scores = self._scores.get(user_id, [])
        if not scores:
            return TrajectoryScore()

        # Find score closest to N weeks ago
        target_date = datetime.now(UTC) - timedelta(weeks=weeks_ago)

        best_score = scores[0]
        best_distance = abs(
            _parse_timestamp(best_score.timestamp) - target_date
        ).total_seconds()

        for score in scores[1:]:
            distance = abs(
                _parse_timestamp(score.timestamp) - target_date
            ).total_seconds()
            if distance < best_distance:
                best_distance = distance
                best_score = score

        return best_score

    def _determine_trend(
        self,
        vs_4: WindowComparison,
        vs_12: WindowComparison,
    ) -> str:
        """Determine overall growth trend.

        Args:
            vs_4: Comparison to 4 weeks ago
            vs_12: Comparison to 12 weeks ago

        Returns:
            "growing", "stable", or "declining"
        """
        improving_4 = len(vs_4.improving_dimensions)
        declining_4 = len(vs_4.declining_dimensions)
        improving_12 = len(vs_12.improving_dimensions)
        declining_12 = len(vs_12.declining_dimensions)

        total_improving = improving_4 + improving_12
        total_declining = declining_4 + declining_12

        if total_improving > total_declining + 1:
            return "growing"
        elif total_declining > total_improving + 1:
            return "declining"
        return "stable"

    def _generate_narrative(
        self,
        current: TrajectoryScore,
        vs_4: WindowComparison,
        vs_12: WindowComparison,
        trend: str,
    ) -> str:
        """Generate a human-readable growth narrative.

        In production, this would use an LLM.
        For now, uses template-based generation.

        Args:
            current: Current trajectory score
            vs_4: Comparison to 4 weeks ago
            vs_12: Comparison to 12 weeks ago
            trend: Overall trend

        Returns:
            Human-readable narrative string
        """
        parts: list[str] = []

        if trend == "growing":
            parts.append(
                "You are on an upward trajectory. "
                "Growth is visible across multiple dimensions."
            )
        elif trend == "declining":
            parts.append(
                "Some areas have dipped recently. "
                "This is normal and does not erase your progress."
            )
        else:
            parts.append(
                "You are maintaining a steady course. "
                "Stability is a form of strength."
            )

        # Highlight strongest dimension
        dimensions = {
            "consistency": current.consistency,
            "resilience": current.resilience,
            "self_awareness": current.self_awareness,
            "goal_progress": current.goal_progress,
            "wellbeing": current.wellbeing,
        }
        strongest = max(dimensions, key=dimensions.get)  # type: ignore[arg-type]
        parts.append(
            f"Your strongest area right now is {strongest.replace('_', ' ')}."
        )

        # Highlight 4-week improvements
        improving = vs_4.improving_dimensions
        if improving:
            dim_text = ", ".join(d.replace("_", " ") for d in improving)
            parts.append(
                f"Compared to 4 weeks ago, you have improved in: {dim_text}."
            )

        return " ".join(parts)


def _parse_timestamp(timestamp: str) -> datetime:
    """Parse an ISO timestamp string to datetime.

    Args:
        timestamp: ISO format timestamp string

    Returns:
        Parsed datetime object (UTC)
    """
    # Handle various ISO formats
    try:
        dt = datetime.fromisoformat(timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return datetime.now(UTC)
