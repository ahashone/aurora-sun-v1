"""
Effectiveness Service for Aurora Sun V1.

Tracks and measures intervention effectiveness per SW-6:
- Track every intervention delivered (type, id, segment, timestamp)
- Measure behavioral outcome within 48h window
- Compare variants (A/B testing)
- Weekly effectiveness report

Reference: ARCHITECTURE.md Section 2.6 (SW-6: Effectiveness Measurement Loop)

Author: Aurora Sun V1 Team
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    and_,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.segment_context import WorkingStyleCode
from src.models.base import Base

# ============================================================================
# Enums
# ============================================================================

class InterventionType(StrEnum):
    """Types of interventions delivered to users."""

    # Coaching interventions
    INLINE_COACHING = "inline_coaching"
    BODY_DOUBLE = "body_double"
    ACCOUNTABILITY_CHECK = "accountability_check"

    # Proactive interventions
    PROACTIVE_IMPULSE = "proactive_impulse"
    ENERGY_REMINDER = "energy_reminder"
    VISION_REFRESHER = "vision_refresher"

    # Module interventions
    PLANNING_PROMPT = "planning_prompt"
    REVIEW_PROMPT = "review_prompt"
    MONEY_PROMPT = "money_prompt"

    # Crisis/Safety interventions
    CRISIS_CHECK = "crisis_check"
    BURNOUT_REDIRECT = "burnout_redirect"
    INERTIA_SUPPORT = "inertia_support"

    # Custom/Generic
    GENERIC_PROMPT = "generic_prompt"


class InterventionOutcome(StrEnum):
    """Outcomes measured after 48h window."""

    # Positive outcomes
    TASK_COMPLETED = "task_completed"
    ENERGY_IMPROVED = "energy_improved"
    PATTERN_BROKEN = "pattern_broken"
    ENGAGEMENT_INCREASED = "engagement_increased"

    # Negative outcomes
    TASK_NOT_COMPLETED = "task_not_completed"
    PATTERN_RECURRED = "pattern_recurred"
    ENERGY_DECLINED = "energy_declined"
    ENGAGEMENT_DECREASED = "engagement_decreased"

    # Neutral/Other outcomes
    NO_RESPONSE = "no_response"
    SESSION_ENDED_EARLY = "session_ended_early"
    NO_DATA = "no_data"


class SegmentCode(StrEnum):
    """
    DEPRECATED: Use WorkingStyleCode from src.core.segment_context instead.

    Kept for backwards compatibility only. Maps to canonical segment codes.
    """

    AD = "AD"  # ADHD (Momentum)
    AU = "AU"  # Autism (Structure)
    AH = "AH"  # AuDHD (Hybrid)
    NT = "NT"  # Neurotypical (Adaptive)
    CU = "CU"  # Custom




# ============================================================================
# SQLAlchemy Models
# ============================================================================

class InterventionInstance(Base):
    """Records a single intervention delivery."""

    __tablename__ = "effectiveness_intervention_instances"

    # Unique identifier for this intervention instance
    instance_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # User and segment
    user_id = Column(Integer, nullable=False, index=True)
    segment = Column(String(2), nullable=False, index=True)  # AD/AU/AH/NT/CU

    # Intervention details
    intervention_type = Column(String(50), nullable=False, index=True)  # inline_coaching, proactive_impulse, etc.
    intervention_id = Column(String(100), nullable=False, index=True)    # Reference to specific intervention (prompt ID, etc.)
    module = Column(String(50), nullable=False, default="unknown")      # Which module delivered it

    # Variant tracking (for A/B testing)
    variant = Column(String(10), nullable=True)  # "A" or "B" for comparison

    # Timestamps
    delivered_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC)
    )
    outcome_logged_at = Column(DateTime(timezone=True), nullable=True)

    # Outcome
    outcome = Column(String(50), nullable=True)  # InterventionOutcome value
    outcome_latency_hours = Column(Float, nullable=True)  # Hours between delivery and outcome

    # Behavioral signals (collected during 48h window)
    task_completion_before = Column(Float, nullable=True)  # Rate before intervention (0.0-1.0)
    task_completion_after = Column(Float, nullable=True)   # Rate after intervention (0.0-1.0)
    response_latency_change = Column(Float, nullable=True)  # Seconds faster/slower
    session_length_change = Column(Float, nullable=True)   # Minutes change
    energy_trajectory = Column(String(20), nullable=True)  # "improved", "stable", "declined"
    pattern_recurrence = Column(Boolean, nullable=True)  # True if pattern came back


class EffectivenessMetrics(Base):
    """Aggregated effectiveness metrics per intervention type/segment."""

    __tablename__ = "effectiveness_metrics"

    # Primary key (composite)
    intervention_type = Column(String(50), primary_key=True)
    segment = Column(String(2), primary_key=True)

    # Aggregated counts
    delivery_count = Column(Integer, nullable=False, default=0)
    outcome_count = Column(Integer, nullable=False, default=0)

    # Success metrics
    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    no_response_count = Column(Integer, nullable=False, default=0)

    # Timing
    total_latency_hours = Column(Float, nullable=False, default=0.0)
    avg_latency_hours = Column(Float, nullable=False, default=0.0)

    # Computed rates
    success_rate = Column(Float, nullable=False, default=0.0)
    failure_rate = Column(Float, nullable=False, default=0.0)
    no_response_rate = Column(Float, nullable=False, default=0.0)

    # Last updated
    last_updated = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC)
    )


class VariantExperiment(Base):
    """Tracks A/B test experiments."""

    __tablename__ = "effectiveness_variant_experiments"

    experiment_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    intervention_type = Column(String(50), nullable=False, index=True)
    segment = Column(String(2), nullable=False, index=True)

    # Variants
    variant_a = Column(String(50), nullable=False, default="control")
    variant_b = Column(String(50), nullable=False, default="treatment")

    # Sample requirements
    min_samples = Column(Integer, nullable=False, default=20)

    # Status
    status = Column(String(20), nullable=False, default="active")  # "active", "completed", "paused"

    # Results
    variant_a_success_rate = Column(Float, nullable=True)
    variant_b_success_rate = Column(Float, nullable=True)
    winner = Column(String(10), nullable=True)  # "A" or "B"
    confidence = Column(Float, nullable=True)  # Statistical confidence

    # Timestamps
    started_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC)
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)


# ============================================================================
# Pydantic Models for API Responses
# ============================================================================

@dataclass
class EffectivenessMetricsResponse:
    """Response model for effectiveness metrics."""

    intervention_type: str
    segment: str
    delivery_count: int
    success_rate: float
    avg_latency_hours: float
    outcome_count: int
    failure_rate: float
    no_response_rate: float


@dataclass
class VariantComparisonResult:
    """Response model for A/B test comparison."""

    experiment_id: str
    intervention_type: str
    segment: str
    variant_a: str
    variant_b: str
    variant_a_success_rate: float
    variant_b_success_rate: float
    variant_a_count: int
    variant_b_count: int
    winner: str | None
    confidence: float | None
    is_significant: bool


@dataclass
class InterventionOutcomeData:
    """Data for logging an intervention outcome."""

    outcome: InterventionOutcome
    task_completion_before: float | None = None
    task_completion_after: float | None = None
    response_latency_change: float | None = None
    session_length_change: float | None = None
    energy_trajectory: str | None = None
    pattern_recurrence: bool | None = None


@dataclass
class EffectivenessReport:
    """Weekly effectiveness report for admin."""

    generated_at: datetime

    # Summary stats
    total_interventions: int
    total_with_outcomes: int

    # Per-segment breakdown
    segment_stats: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Per-intervention-type breakdown
    type_stats: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Top performing interventions (per segment)
    top_performers: list[dict[str, Any]] = field(default_factory=list)

    # Underperforming interventions
    underperformers: list[dict[str, Any]] = field(default_factory=list)

    # Active experiments
    active_experiments: list[dict[str, Any]] = field(default_factory=list)

    # Recommendations
    recommendations: list[str] = field(default_factory=list)


# ============================================================================
# Service Implementation
# ============================================================================

class EffectivenessService:
    """
    Track and measure intervention effectiveness.

    Per SW-6:
    - Track every intervention delivered (type, id, segment, timestamp)
    - Measure behavioral outcome within 48h window
    - Compare variants (A/B testing)
    - Weekly effectiveness report
    """

    # Outcome categories for success/failure calculation
    SUCCESS_OUTCOMES = {
        InterventionOutcome.TASK_COMPLETED,
        InterventionOutcome.ENERGY_IMPROVED,
        InterventionOutcome.PATTERN_BROKEN,
        InterventionOutcome.ENGAGEMENT_INCREASED,
    }

    FAILURE_OUTCOMES = {
        InterventionOutcome.TASK_NOT_COMPLETED,
        InterventionOutcome.PATTERN_RECURRED,
        InterventionOutcome.ENERGY_DECLINED,
        InterventionOutcome.ENGAGEMENT_DECREASED,
    }

    def __init__(self, session: AsyncSession):
        """Initialize with database session."""
        self.session = session

    # Maximum confidence for user-reported outcomes (system-verified can reach 1.0).
    # Only system-verified outcomes can reach 1.0.
    MAX_USER_REPORTED_CONFIDENCE = 0.9

    async def log_intervention(
        self,
        user_id: int,
        intervention_type: str,
        intervention_id: str,
        segment: str,
        module: str,
        variant: str | None = None,
    ) -> str:
        """
        Log an intervention delivery. Returns intervention_instance_id.

        Args:
            user_id: The user ID
            intervention_type: Type of intervention (e.g., "inline_coaching")
            intervention_id: Unique identifier for the specific intervention
            segment: User's segment (AD/AU/AH/NT/CU)
            module: Which module delivered the intervention
            variant: Optional variant for A/B testing ("A" or "B")

        Returns:
            intervention_instance_id: UUID for tracking
        """
        instance = InterventionInstance(
            instance_id=str(uuid.uuid4()),
            user_id=user_id,
            segment=segment,
            intervention_type=intervention_type,
            intervention_id=intervention_id,
            module=module,
            variant=variant,
            delivered_at=datetime.now(UTC),
        )

        self.session.add(instance)

        # Increment delivery_count in metrics
        await self._increment_delivery_count(intervention_type, segment)

        await self.session.commit()

        return str(instance.instance_id)

    async def _increment_delivery_count(
        self,
        intervention_type: str,
        segment: str,
    ) -> None:
        """Increment delivery_count when an intervention is logged."""

        # Find or create metrics record
        stmt = select(EffectivenessMetrics).where(
            and_(
                EffectivenessMetrics.intervention_type == intervention_type,
                EffectivenessMetrics.segment == segment,
            )
        )
        result = await self.session.execute(stmt)
        metrics = result.scalar_one_or_none()

        if not metrics:
            metrics = EffectivenessMetrics(
                intervention_type=intervention_type,
                segment=segment,
            )
            self.session.add(metrics)

        metrics.delivery_count += 1  # type: ignore[assignment]
        metrics.last_updated = datetime.now(UTC)  # type: ignore[assignment]

    async def log_outcome(
        self,
        intervention_instance_id: str,
        outcome: InterventionOutcome,
        behavioral_signals: InterventionOutcomeData | None = None,
        user_id: int | None = None,
        system_verified: bool = False,
    ) -> None:
        """
        Log outcome after 48h window.

        Validates that the intervention belongs to the claiming user
        and applies a confidence ceiling for user-reported outcomes.

        Args:
            intervention_instance_id: The instance ID returned from log_intervention
            outcome: The measured outcome
            behavioral_signals: Optional behavioral signals collected during window
            user_id: The user reporting the outcome (required for ownership validation)
            system_verified: If True, outcome is system-verified (no confidence ceiling)
        """
        # Fetch the intervention instance
        stmt = select(InterventionInstance).where(
            InterventionInstance.instance_id == intervention_instance_id
        )
        result = await self.session.execute(stmt)
        instance = result.scalar_one_or_none()

        if not instance:
            raise ValueError(f"Intervention instance not found: {intervention_instance_id}")

        # Validate that TASK_COMPLETED outcomes require a corresponding
        # intervention that belongs to the reporting user.
        if user_id is not None and instance.user_id != user_id:
            raise ValueError(
                f"Intervention {intervention_instance_id} does not belong to user {user_id}"
            )

        # Apply confidence ceiling for user-reported outcomes.
        # Only system-verified outcomes can have confidence up to 1.0.
        if behavioral_signals and not system_verified:
            if behavioral_signals.task_completion_after is not None:
                behavioral_signals.task_completion_after = min(
                    behavioral_signals.task_completion_after,
                    self.MAX_USER_REPORTED_CONFIDENCE,
                )
            if behavioral_signals.task_completion_before is not None:
                behavioral_signals.task_completion_before = min(
                    behavioral_signals.task_completion_before,
                    self.MAX_USER_REPORTED_CONFIDENCE,
                )

        # Calculate latency
        now = datetime.now(UTC)
        latency = now - instance.delivered_at
        latency_hours = latency.total_seconds() / 3600

        # Update instance
        instance.outcome = outcome.value  # type: ignore[assignment]
        instance.outcome_logged_at = now  # type: ignore[assignment]
        instance.outcome_latency_hours = latency_hours

        # Add behavioral signals if provided
        if behavioral_signals:
            instance.task_completion_before = behavioral_signals.task_completion_before  # type: ignore[assignment]
            instance.task_completion_after = behavioral_signals.task_completion_after  # type: ignore[assignment]
            instance.response_latency_change = behavioral_signals.response_latency_change  # type: ignore[assignment]
            instance.session_length_change = behavioral_signals.session_length_change  # type: ignore[assignment]
            instance.energy_trajectory = behavioral_signals.energy_trajectory  # type: ignore[assignment]
            instance.pattern_recurrence = behavioral_signals.pattern_recurrence  # type: ignore[assignment]

        # Update aggregated metrics
        await self._update_metrics(instance, outcome)

        await self.session.commit()

    async def _update_metrics(
        self,
        instance: InterventionInstance,
        outcome: InterventionOutcome,
    ) -> None:
        """Update aggregated effectiveness metrics."""

        # Find or create metrics record
        stmt = select(EffectivenessMetrics).where(
            and_(
                EffectivenessMetrics.intervention_type == instance.intervention_type,
                EffectivenessMetrics.segment == instance.segment,
            )
        )
        result = await self.session.execute(stmt)
        metrics = result.scalar_one_or_none()

        if not metrics:
            metrics = EffectivenessMetrics(
                intervention_type=instance.intervention_type,
                segment=instance.segment,
            )
            self.session.add(metrics)

        # Update last_updated
        metrics.last_updated = datetime.now(UTC)  # type: ignore[assignment]

        # Categorize outcome
        if outcome in self.SUCCESS_OUTCOMES:
            metrics.success_count += 1  # type: ignore[assignment]
        elif outcome in self.FAILURE_OUTCOMES:
            metrics.failure_count += 1  # type: ignore[assignment]
        else:  # NO_RESPONSE, SESSION_ENDED_EARLY, NO_DATA
            metrics.no_response_count += 1  # type: ignore[assignment]

        if instance.outcome_latency_hours:
            metrics.total_latency_hours += instance.outcome_latency_hours  # type: ignore[assignment]
            metrics.outcome_count += 1  # type: ignore[assignment]

        # Recalculate rates
        if metrics.delivery_count > 0:
            metrics.success_rate = metrics.success_count / metrics.delivery_count  # type: ignore[assignment]
            metrics.failure_rate = metrics.failure_count / metrics.delivery_count  # type: ignore[assignment]
            metrics.no_response_rate = metrics.no_response_count / metrics.delivery_count  # type: ignore[assignment]

        if metrics.outcome_count > 0:
            metrics.avg_latency_hours = metrics.total_latency_hours / metrics.outcome_count  # type: ignore[assignment]

    async def get_effectiveness(
        self,
        intervention_type: str | None = None,
        segment: str | None = None,
    ) -> EffectivenessMetricsResponse:
        """
        Get effectiveness metrics for intervention/segment.

        Args:
            intervention_type: Filter by intervention type (optional)
            segment: Filter by segment (optional)

        Returns:
            EffectivenessMetricsResponse with aggregated data
        """
        stmt = select(EffectivenessMetrics)

        if intervention_type:
            stmt = stmt.where(EffectivenessMetrics.intervention_type == intervention_type)
        if segment:
            stmt = stmt.where(EffectivenessMetrics.segment == segment)

        result = await self.session.execute(stmt)
        metrics_list = result.scalars().all()

        if not metrics_list:
            # Return empty metrics
            return EffectivenessMetricsResponse(
                intervention_type=intervention_type or "all",
                segment=segment or "all",
                delivery_count=0,
                success_rate=0.0,
                avg_latency_hours=0.0,
                outcome_count=0,
                failure_rate=0.0,
                no_response_rate=0.0,
            )

        # Aggregate across multiple records if needed
        total_delivery = sum(m.delivery_count for m in metrics_list)
        total_success = sum(m.success_count for m in metrics_list)
        total_failure = sum(m.failure_count for m in metrics_list)
        total_no_response = sum(m.no_response_count for m in metrics_list)
        total_latency = sum(m.total_latency_hours for m in metrics_list)
        total_outcomes = sum(m.outcome_count for m in metrics_list)

        return EffectivenessMetricsResponse(
            intervention_type=intervention_type or "all",
            segment=segment or "all",
            delivery_count=int(total_delivery),
            success_rate=float(total_success / total_delivery if total_delivery > 0 else 0.0),
            avg_latency_hours=float(total_latency / total_outcomes if total_outcomes > 0 else 0.0),
            outcome_count=int(total_outcomes),
            failure_rate=float(total_failure / total_delivery if total_delivery > 0 else 0.0),
            no_response_rate=float(total_no_response / total_delivery if total_delivery > 0 else 0.0),
        )

    async def compare_variants(
        self,
        intervention_type: str,
        variant_a: str,
        variant_b: str,
        segment: str | None = None,
        min_samples: int = 20,
    ) -> VariantComparisonResult:
        """
        A/B test comparison.

        Args:
            intervention_type: Type of intervention being compared
            variant_a: First variant name (e.g., "control")
            variant_b: Second variant name (e.g., "treatment")
            segment: Filter by segment (optional, but recommended)
            min_samples: Minimum samples required for comparison

        Returns:
            VariantComparisonResult with comparison data
        """
        # Collect counts for both variants
        success_a, total_a = await self._query_variant_counts(
            intervention_type, variant_a, segment,
        )
        success_b, total_b = await self._query_variant_counts(
            intervention_type, variant_b, segment,
        )

        # Calculate success rates
        rate_a = success_a / total_a if total_a > 0 else 0.0
        rate_b = success_b / total_b if total_b > 0 else 0.0

        # Statistical significance test
        winner, confidence, is_significant = self._two_proportion_z_test(
            success_a, total_a, rate_a,
            success_b, total_b, rate_b,
            variant_a, variant_b,
            min_samples,
        )

        # Update experiment record
        experiment_id = await self._update_experiment_record(
            intervention_type, segment,
            rate_a, rate_b, winner, confidence,
            total_a, total_b, min_samples,
        )

        return VariantComparisonResult(
            experiment_id=experiment_id,
            intervention_type=intervention_type,
            segment=segment or "all",
            variant_a=variant_a,
            variant_b=variant_b,
            variant_a_success_rate=rate_a,
            variant_b_success_rate=rate_b,
            variant_a_count=total_a,
            variant_b_count=total_b,
            winner=winner,
            confidence=confidence,
            is_significant=is_significant,
        )

    async def _query_variant_counts(
        self,
        intervention_type: str,
        variant: str,
        segment: str | None,
    ) -> tuple[int, int]:
        """Query success count and total count for a single variant.

        Args:
            intervention_type: The intervention type to filter by.
            variant: The variant name (e.g. "control").
            segment: Optional segment filter.

        Returns:
            Tuple of (success_count, total_count).
        """
        # Success count
        stmt_success = select(func.count(InterventionInstance.instance_id)).where(
            and_(
                InterventionInstance.intervention_type == intervention_type,
                InterventionInstance.variant == variant,
                InterventionInstance.outcome.in_([o.value for o in self.SUCCESS_OUTCOMES]),
            )
        )
        if segment:
            stmt_success = stmt_success.where(InterventionInstance.segment == segment)
        result_success = await self.session.execute(stmt_success)
        success = result_success.scalar() or 0

        # Total count
        stmt_total = select(func.count(InterventionInstance.instance_id)).where(
            and_(
                InterventionInstance.intervention_type == intervention_type,
                InterventionInstance.variant == variant,
            )
        )
        if segment:
            stmt_total = stmt_total.where(InterventionInstance.segment == segment)
        result_total = await self.session.execute(stmt_total)
        total = result_total.scalar() or 0

        return success, total

    @staticmethod
    def _two_proportion_z_test(
        success_a: int,
        total_a: int,
        rate_a: float,
        success_b: int,
        total_b: int,
        rate_b: float,
        variant_a: str,
        variant_b: str,
        min_samples: int,
    ) -> tuple[str | None, float | None, bool]:
        """Run a two-proportion z-test to determine statistical significance.

        H0: p_a = p_b (no difference in success rates)
        H1: p_a != p_b (significant difference)

        Args:
            success_a: Successes in variant A.
            total_a: Total in variant A.
            rate_a: Success rate for variant A.
            success_b: Successes in variant B.
            total_b: Total in variant B.
            rate_b: Success rate for variant B.
            variant_a: Name of variant A.
            variant_b: Name of variant B.
            min_samples: Minimum samples per variant.

        Returns:
            Tuple of (winner, confidence, is_significant).
        """
        winner: str | None = None
        confidence: float | None = None
        is_significant = False

        if total_a < min_samples or total_b < min_samples:
            return winner, confidence, is_significant

        # Calculate pooled proportion
        p_pooled = (success_a + success_b) / (total_a + total_b)

        # Calculate standard error
        se = math.sqrt(p_pooled * (1 - p_pooled) * (1 / total_a + 1 / total_b))

        if se <= 0:
            # If SE is 0, rates are identical or sample size issue
            return winner, 0.0, False

        z_score = abs(rate_a - rate_b) / se

        # Check significance at 95% confidence level (z > 1.96)
        is_significant = z_score > 1.96

        # Calculate approximate confidence using standard normal CDF
        confidence = min(
            0.99, 1 - 2 * math.exp(-0.717 * z_score - 0.416 * z_score**2)
        )

        if is_significant:
            if rate_b > rate_a:
                winner = variant_b
            elif rate_a > rate_b:
                winner = variant_a

        return winner, confidence, is_significant

    async def _update_experiment_record(
        self,
        intervention_type: str,
        segment: str | None,
        rate_a: float,
        rate_b: float,
        winner: str | None,
        confidence: float | None,
        total_a: int,
        total_b: int,
        min_samples: int,
    ) -> str:
        """Find and update the active experiment record, or generate a new ID.

        Args:
            intervention_type: The intervention type.
            segment: Segment filter (may be None).
            rate_a: Success rate for variant A.
            rate_b: Success rate for variant B.
            winner: Winner variant name, or None.
            confidence: Statistical confidence, or None.
            total_a: Total count for variant A.
            total_b: Total count for variant B.
            min_samples: Minimum sample threshold.

        Returns:
            The experiment ID (existing or newly generated).
        """
        experiment_id = str(uuid.uuid4())

        if not segment:
            return experiment_id

        stmt_exp = select(VariantExperiment).where(
            and_(
                VariantExperiment.intervention_type == intervention_type,
                VariantExperiment.segment == segment,
                VariantExperiment.status == "active",
            )
        )
        result_exp = await self.session.execute(stmt_exp)
        experiment = result_exp.scalar_one_or_none()

        if not experiment:
            return experiment_id

        experiment_id = experiment.experiment_id  # type: ignore[assignment]
        experiment.variant_a_success_rate = rate_a  # type: ignore[assignment]
        experiment.variant_b_success_rate = rate_b  # type: ignore[assignment]
        experiment.winner = winner  # type: ignore[assignment]
        experiment.confidence = confidence  # type: ignore[assignment]

        if total_a >= min_samples and total_b >= min_samples:
            experiment.status = "completed"  # type: ignore[assignment]
            experiment.completed_at = datetime.now(UTC)  # type: ignore[assignment]

        await self.session.commit()

        return experiment_id

    async def generate_weekly_report(self) -> EffectivenessReport:
        """
        Generate weekly effectiveness report for admin.

        Returns:
            EffectivenessReport with comprehensive metrics
        """
        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)

        # Phase 1: Data collection
        interventions = await self._collect_weekly_interventions(week_ago)

        # Phase 2: Calculate breakdowns
        segment_stats = self._calculate_segment_stats(interventions)
        type_stats = self._calculate_type_stats(interventions)

        # Phase 3: Rank performers
        top_performers = self._rank_performers(type_stats, ascending=False)
        underperformers = self._rank_performers(type_stats, ascending=True)

        # Phase 4: Collect active experiments
        active_experiments = await self._collect_active_experiments()

        # Phase 5: Generate recommendations
        recommendations = self._generate_recommendations(
            segment_stats, type_stats, top_performers,
        )

        return EffectivenessReport(
            generated_at=now,
            total_interventions=len(interventions),
            total_with_outcomes=sum(1 for i in interventions if i.outcome is not None),
            segment_stats=segment_stats,
            type_stats=type_stats,
            top_performers=top_performers,
            underperformers=underperformers,
            active_experiments=active_experiments,
            recommendations=recommendations,
        )

    async def _collect_weekly_interventions(
        self,
        since: datetime,
    ) -> list[InterventionInstance]:
        """Fetch all intervention instances delivered since the given timestamp.

        Args:
            since: Start of the reporting window.

        Returns:
            List of InterventionInstance rows.
        """
        stmt = select(InterventionInstance).where(
            InterventionInstance.delivered_at >= since
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def _calculate_segment_stats(
        self,
        interventions: list[InterventionInstance],
    ) -> dict[str, dict[str, Any]]:
        """Calculate per-segment delivery/outcome/success stats.

        Args:
            interventions: All interventions for the reporting period.

        Returns:
            Dict keyed by segment code with count and rate dicts.
        """
        success_values = [o.value for o in self.SUCCESS_OUTCOMES]
        segment_stats: dict[str, dict[str, Any]] = {}
        all_segments: list[WorkingStyleCode] = ["AD", "AU", "AH", "NT", "CU"]

        for segment in all_segments:
            seg_interventions = [i for i in interventions if i.segment == segment]
            if not seg_interventions:
                continue
            seg_with_outcomes = [i for i in seg_interventions if i.outcome is not None]
            seg_success = [
                i for i in seg_with_outcomes if i.outcome in success_values
            ]
            segment_stats[segment] = {
                "delivery_count": len(seg_interventions),
                "outcome_count": len(seg_with_outcomes),
                "success_count": len(seg_success),
                "success_rate": (
                    len(seg_success) / len(seg_interventions)
                    if seg_interventions
                    else 0.0
                ),
            }
        return segment_stats

    def _calculate_type_stats(
        self,
        interventions: list[InterventionInstance],
    ) -> dict[str, dict[str, Any]]:
        """Calculate per-intervention-type delivery/outcome/success stats.

        Args:
            interventions: All interventions for the reporting period.

        Returns:
            Dict keyed by intervention type string with count and rate dicts.
        """
        success_values = [o.value for o in self.SUCCESS_OUTCOMES]
        type_stats: dict[str, dict[str, Any]] = {}

        for i_type in [t.value for t in InterventionType]:
            type_interventions = [
                i for i in interventions if i.intervention_type == i_type
            ]
            if not type_interventions:
                continue
            type_with_outcomes = [
                i for i in type_interventions if i.outcome is not None
            ]
            type_success = [
                i for i in type_with_outcomes if i.outcome in success_values
            ]
            type_stats[i_type] = {
                "delivery_count": len(type_interventions),
                "outcome_count": len(type_with_outcomes),
                "success_count": len(type_success),
                "success_rate": (
                    len(type_success) / len(type_interventions)
                    if type_interventions
                    else 0.0
                ),
            }
        return type_stats

    @staticmethod
    def _rank_performers(
        type_stats: dict[str, dict[str, Any]],
        *,
        ascending: bool,
        min_deliveries: int = 5,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Rank intervention types by success rate.

        Args:
            type_stats: Per-type stats dict.
            ascending: If True, return worst performers first; else best first.
            min_deliveries: Minimum deliveries required to be included.
            limit: Maximum number of results to return.

        Returns:
            Sorted list of performer dicts.
        """
        candidates = [
            {
                "intervention_type": i_type,
                "success_rate": stats["success_rate"],
                "delivery_count": stats["delivery_count"],
            }
            for i_type, stats in type_stats.items()
            if stats["delivery_count"] >= min_deliveries
        ]
        candidates.sort(key=lambda x: x["success_rate"], reverse=not ascending)
        return candidates[:limit]

    async def _collect_active_experiments(self) -> list[dict[str, Any]]:
        """Fetch all active variant experiments.

        Returns:
            List of experiment summary dicts.
        """
        stmt_exp = select(VariantExperiment).where(
            VariantExperiment.status == "active"
        )
        result_exp = await self.session.execute(stmt_exp)
        experiments = result_exp.scalars().all()

        return [
            {
                "experiment_id": e.experiment_id,
                "intervention_type": e.intervention_type,
                "segment": e.segment,
                "variant_a": e.variant_a,
                "variant_b": e.variant_b,
                "started_at": e.started_at.isoformat(),
            }
            for e in experiments
        ]

    @staticmethod
    def _generate_recommendations(
        segment_stats: dict[str, dict[str, Any]],
        type_stats: dict[str, dict[str, Any]],
        top_performers: list[dict[str, Any]],
    ) -> list[str]:
        """Generate actionable recommendations from the report data.

        Args:
            segment_stats: Per-segment stats.
            type_stats: Per-intervention-type stats.
            top_performers: Top-performing interventions.

        Returns:
            List of human-readable recommendation strings.
        """
        recommendations: list[str] = []

        # Check for low-performing segments
        for segment_key, stats in segment_stats.items():
            if stats["success_rate"] < 0.4 and stats["delivery_count"] >= 10:
                recommendations.append(
                    f"Segment {segment_key.upper()} has low success rate "
                    f"({stats['success_rate']:.1%}). "
                    f"Consider reviewing intervention approach."
                )

        # Check for underperforming intervention types
        for i_type, stats in type_stats.items():
            if stats["success_rate"] < 0.3 and stats["delivery_count"] >= 10:
                recommendations.append(
                    f"Intervention type '{i_type}' has low success rate "
                    f"({stats['success_rate']:.1%}). "
                    f"RIA should analyze and propose improvements."
                )

        # Add positive recommendations
        for performer in top_performers[:3]:
            recommendations.append(
                f"Intervention '{performer['intervention_type']}' performing well "
                f"({performer['success_rate']:.1%} success rate). "
                f"Consider expanding usage."
            )

        return recommendations

    async def get_pending_outcomes(
        self,
        max_age_hours: int = 48,
    ) -> list[InterventionInstance]:
        """
        Get interventions that are due for outcome measurement.

        Args:
            max_age_hours: Maximum age in hours (default 48)

        Returns:
            List of intervention instances awaiting outcome
        """
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)

        stmt = select(InterventionInstance).where(
            and_(
                InterventionInstance.delivered_at <= cutoff,
                InterventionInstance.outcome.is_(None),
            )
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())


# ============================================================================
# Service Factory
# ============================================================================

_effectiveness_service: EffectivenessService | None = None


async def get_effectiveness_service(session: AsyncSession) -> EffectivenessService:
    """Get or create EffectivenessService instance."""
    return EffectivenessService(session)
