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

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Index, Text
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import Base


# ============================================================================
# Enums
# ============================================================================

class InterventionType(str, Enum):
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


class InterventionOutcome(str, Enum):
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


class SegmentCode(str, Enum):
    """Internal segment codes."""

    AD = "ad"  # ADHD (Momentum)
    AU = "au"  # Autism (Structure)
    AH = "ah"  # AuDHD (Hybrid)
    NT = "nt"  # Neurotypical (Adaptive)
    CU = "cu"  # Custom


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
        default=lambda: datetime.now(timezone.utc)
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
        default=lambda: datetime.now(timezone.utc)
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
        default=lambda: datetime.now(timezone.utc)
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
    winner: Optional[str]
    confidence: Optional[float]
    is_significant: bool


@dataclass
class InterventionOutcomeData:
    """Data for logging an intervention outcome."""

    outcome: InterventionOutcome
    task_completion_before: Optional[float] = None
    task_completion_after: Optional[float] = None
    response_latency_change: Optional[float] = None
    session_length_change: Optional[float] = None
    energy_trajectory: Optional[str] = None
    pattern_recurrence: Optional[bool] = None


@dataclass
class EffectivenessReport:
    """Weekly effectiveness report for admin."""

    generated_at: datetime

    # Summary stats
    total_interventions: int
    total_with_outcomes: int

    # Per-segment breakdown
    segment_stats: dict[str, dict] = field(default_factory=dict)

    # Per-intervention-type breakdown
    type_stats: dict[str, dict] = field(default_factory=dict)

    # Top performing interventions (per segment)
    top_performers: list[dict] = field(default_factory=list)

    # Underperforming interventions
    underperformers: list[dict] = field(default_factory=list)

    # Active experiments
    active_experiments: list[dict] = field(default_factory=list)

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

    async def log_intervention(
        self,
        user_id: int,
        intervention_type: str,
        intervention_id: str,
        segment: str,
        module: str,
        variant: Optional[str] = None,
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
            delivered_at=datetime.now(timezone.utc),
        )

        self.session.add(instance)
        await self.session.commit()

        return instance.instance_id

    async def log_outcome(
        self,
        intervention_instance_id: str,
        outcome: InterventionOutcome,
        behavioral_signals: Optional[InterventionOutcomeData] = None,
    ) -> None:
        """
        Log outcome after 48h window.

        Args:
            intervention_instance_id: The instance ID returned from log_intervention
            outcome: The measured outcome
            behavioral_signals: Optional behavioral signals collected during window
        """
        # Fetch the intervention instance
        stmt = select(InterventionInstance).where(
            InterventionInstance.instance_id == intervention_instance_id
        )
        result = await self.session.execute(stmt)
        instance = result.scalar_one_or_none()

        if not instance:
            raise ValueError(f"Intervention instance not found: {intervention_instance_id}")

        # Calculate latency
        now = datetime.now(timezone.utc)
        latency = now - instance.delivered_at
        latency_hours = latency.total_seconds() / 3600

        # Update instance
        instance.outcome = outcome.value
        instance.outcome_logged_at = now
        instance.outcome_latency_hours = latency_hours

        # Add behavioral signals if provided
        if behavioral_signals:
            instance.task_completion_before = behavioral_signals.task_completion_before
            instance.task_completion_after = behavioral_signals.task_completion_after
            instance.response_latency_change = behavioral_signals.response_latency_change
            instance.session_length_change = behavioral_signals.session_length_change
            instance.energy_trajectory = behavioral_signals.energy_trajectory
            instance.pattern_recurrence = behavioral_signals.pattern_recurrence

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

        # Update counts
        metrics.delivery_count += 1
        metrics.last_updated = datetime.now(timezone.utc)

        # Categorize outcome
        if outcome in self.SUCCESS_OUTCOMES:
            metrics.success_count += 1
        elif outcome in self.FAILURE_OUTCOMES:
            metrics.failure_count += 1
        else:  # NO_RESPONSE, SESSION_ENDED_EARLY, NO_DATA
            metrics.no_response_count += 1

        if instance.outcome_latency_hours:
            metrics.total_latency_hours += instance.outcome_latency_hours
            metrics.outcome_count += 1

        # Recalculate rates
        if metrics.delivery_count > 0:
            metrics.success_rate = metrics.success_count / metrics.delivery_count
            metrics.failure_rate = metrics.failure_count / metrics.delivery_count
            metrics.no_response_rate = metrics.no_response_count / metrics.delivery_count

        if metrics.outcome_count > 0:
            metrics.avg_latency_hours = metrics.total_latency_hours / metrics.outcome_count

    async def get_effectiveness(
        self,
        intervention_type: Optional[str] = None,
        segment: Optional[str] = None,
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
            delivery_count=total_delivery,
            success_rate=total_success / total_delivery if total_delivery > 0 else 0.0,
            avg_latency_hours=total_latency / total_outcomes if total_outcomes > 0 else 0.0,
            outcome_count=total_outcomes,
            failure_rate=total_failure / total_delivery if total_delivery > 0 else 0.0,
            no_response_rate=total_no_response / total_delivery if total_delivery > 0 else 0.0,
        )

    async def compare_variants(
        self,
        intervention_type: str,
        variant_a: str,
        variant_b: str,
        segment: Optional[str] = None,
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
        # Build query for variant A
        stmt_a = select(func.count(InterventionInstance.instance_id)).where(
            and_(
                InterventionInstance.intervention_type == intervention_type,
                InterventionInstance.variant == variant_a,
                InterventionInstance.outcome.in_([o.value for o in self.SUCCESS_OUTCOMES]),
            )
        )
        if segment:
            stmt_a = stmt_a.where(InterventionInstance.segment == segment)

        result_a = await self.session.execute(stmt_a)
        success_a = result_a.scalar() or 0

        # Total for variant A
        stmt_a_total = select(func.count(InterventionInstance.instance_id)).where(
            and_(
                InterventionInstance.intervention_type == intervention_type,
                InterventionInstance.variant == variant_a,
            )
        )
        if segment:
            stmt_a_total = stmt_a_total.where(InterventionInstance.segment == segment)

        result_a_total = await self.session.execute(stmt_a_total)
        total_a = result_a_total.scalar() or 0

        # Build query for variant B
        stmt_b = select(func.count(InterventionInstance.instance_id)).where(
            and_(
                InterventionInstance.intervention_type == intervention_type,
                InterventionInstance.variant == variant_b,
                InterventionInstance.outcome.in_([o.value for o in self.SUCCESS_OUTCOMES]),
            )
        )
        if segment:
            stmt_b = stmt_b.where(InterventionInstance.segment == segment)

        result_b = await self.session.execute(stmt_b)
        success_b = result_b.scalar() or 0

        # Total for variant B
        stmt_b_total = select(func.count(InterventionInstance.instance_id)).where(
            and_(
                InterventionInstance.intervention_type == intervention_type,
                InterventionInstance.variant == variant_b,
            )
        )
        if segment:
            stmt_b_total = stmt_b_total.where(InterventionInstance.segment == segment)

        result_b_total = await self.session.execute(stmt_b_total)
        total_b = result_b_total.scalar() or 0

        # Calculate success rates
        rate_a = success_a / total_a if total_a > 0 else 0.0
        rate_b = success_b / total_b if total_b > 0 else 0.0

        # Determine winner and confidence (simplified - would need proper stats in production)
        winner = None
        confidence = None
        is_significant = False

        if total_a >= min_samples and total_b >= min_samples:
            rate_diff = abs(rate_a - rate_b)
            # Simple heuristic: significant if difference > 10%
            is_significant = rate_diff > 0.10

            if rate_b > rate_a:
                winner = variant_b
            elif rate_a > rate_b:
                winner = variant_a

            # Rough confidence estimate (would use proper statistical test in production)
            confidence = min(0.95, rate_diff * 2) if rate_diff > 0 else 0.0

        # Get or create experiment record
        experiment_id = str(uuid.uuid4())
        if segment:
            stmt_exp = select(VariantExperiment).where(
                and_(
                    VariantExperiment.intervention_type == intervention_type,
                    VariantExperiment.segment == segment,
                    VariantExperiment.status == "active",
                )
            )
            result_exp = await self.session.execute(stmt_exp)
            experiment = result_exp.scalar_one_or_none()

            if experiment:
                experiment_id = experiment.experiment_id
                experiment.variant_a_success_rate = rate_a
                experiment.variant_b_success_rate = rate_b
                experiment.winner = winner
                experiment.confidence = confidence

                if total_a >= min_samples and total_b >= min_samples:
                    experiment.status = "completed"
                    experiment.completed_at = datetime.now(timezone.utc)

                await self.session.commit()

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

    async def generate_weekly_report(self) -> EffectivenessReport:
        """
        Generate weekly effectiveness report for admin.

        Returns:
            EffectivenessReport with comprehensive metrics
        """
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        # Get all interventions from the past week
        stmt = select(InterventionInstance).where(
            InterventionInstance.delivered_at >= week_ago
        )
        result = await self.session.execute(stmt)
        interventions = result.scalars().all()

        # Calculate summary stats
        total_interventions = len(interventions)
        total_with_outcomes = sum(1 for i in interventions if i.outcome is not None)

        # Per-segment breakdown
        segment_stats: dict[str, dict] = {}
        for segment in [s.value for s in SegmentCode]:
            seg_interventions = [i for i in interventions if i.segment == segment]
            seg_with_outcomes = [i for i in seg_interventions if i.outcome is not None]
            seg_success = [
                i for i in seg_with_outcomes
                if i.outcome in [o.value for o in self.SUCCESS_OUTCOMES]
            ]

            if seg_interventions:
                segment_stats[segment] = {
                    "delivery_count": len(seg_interventions),
                    "outcome_count": len(seg_with_outcomes),
                    "success_count": len(seg_success),
                    "success_rate": len(seg_success) / len(seg_interventions)
                    if len(seg_interventions) > 0
                    else 0.0,
                }

        # Per-intervention-type breakdown
        type_stats: dict[str, dict] = {}
        for i_type in [t.value for t in InterventionType]:
            type_interventions = [i for i in interventions if i.intervention_type == i_type]
            type_with_outcomes = [i for i in type_interventions if i.outcome is not None]
            type_success = [
                i for i in type_with_outcomes
                if i.outcome in [o.value for o in self.SUCCESS_OUTCOMES]
            ]

            if type_interventions:
                type_stats[i_type] = {
                    "delivery_count": len(type_interventions),
                    "outcome_count": len(type_with_outcomes),
                    "success_count": len(type_success),
                    "success_rate": len(type_success) / len(type_interventions)
                    if len(type_interventions) > 0
                    else 0.0,
                }

        # Top performers (sorted by success rate, min 5 deliveries)
        top_performers = []
        for i_type, stats in type_stats.items():
            if stats["delivery_count"] >= 5:
                top_performers.append(
                    {
                        "intervention_type": i_type,
                        "success_rate": stats["success_rate"],
                        "delivery_count": stats["delivery_count"],
                    }
                )

        top_performers.sort(key=lambda x: x["success_rate"], reverse=True)
        top_performers = top_performers[:5]

        # Underperformers (sorted by success rate, min 5 deliveries)
        underperformers = []
        for i_type, stats in type_stats.items():
            if stats["delivery_count"] >= 5:
                underperformers.append(
                    {
                        "intervention_type": i_type,
                        "success_rate": stats["success_rate"],
                        "delivery_count": stats["delivery_count"],
                    }
                )

        underperformers.sort(key=lambda x: x["success_rate"])
        underperformers = underperformers[:5]

        # Active experiments
        stmt_exp = select(VariantExperiment).where(
            VariantExperiment.status == "active"
        )
        result_exp = await self.session.execute(stmt_exp)
        experiments = result_exp.scalars().all()

        active_experiments = [
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

        # Generate recommendations
        recommendations = []

        # Check for low-performing segments
        for segment, stats in segment_stats.items():
            if stats["success_rate"] < 0.4 and stats["delivery_count"] >= 10:
                recommendations.append(
                    f"Segment {segment.upper()} has low success rate ({stats['success_rate']:.1%}). "
                    f"Consider reviewing intervention approach."
                )

        # Check for underperforming intervention types
        for i_type, stats in type_stats.items():
            if stats["success_rate"] < 0.3 and stats["delivery_count"] >= 10:
                recommendations.append(
                    f"Intervention type '{i_type}' has low success rate ({stats['success_rate']:.1%}). "
                    f"RIA should analyze and propose improvements."
                )

        # Add positive recommendations
        for performer in top_performers[:3]:
            recommendations.append(
                f"Intervention '{performer['intervention_type']}' performing well "
                f"({performer['success_rate']:.1%} success rate). Consider expanding usage."
            )

        return EffectivenessReport(
            generated_at=now,
            total_interventions=total_interventions,
            total_with_outcomes=total_with_outcomes,
            segment_stats=segment_stats,
            type_stats=type_stats,
            top_performers=top_performers,
            underperformers=underperformers,
            active_experiments=active_experiments,
            recommendations=recommendations,
        )

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
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        stmt = select(InterventionInstance).where(
            and_(
                InterventionInstance.delivered_at <= cutoff,
                InterventionInstance.outcome.is_(None),
            )
        )

        result = await self.session.execute(stmt)
        return result.scalars().all()


# ============================================================================
# Service Factory
# ============================================================================

_effectiveness_service: Optional[EffectivenessService] = None


async def get_effectiveness_service(session: AsyncSession) -> EffectivenessService:
    """Get or create EffectivenessService instance."""
    return EffectivenessService(session)
