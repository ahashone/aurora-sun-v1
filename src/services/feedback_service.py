"""
Feedback Service for Aurora Sun V1.

Tracks explicit and implicit user feedback for all interventions, modules, and features.
Aggregates per-segment to feed into RIA learning cycle (SW-20).

Key Features:
- Explicit feedback capture: "That was helpful" / "This doesn't work" / thumbs up/down
- Context storage: which intervention, which module, which segment, timestamp
- Implicit feedback integration: EffectivenessService outcome signals, PatternDetection recurrence
- Per-segment aggregation (NEVER across segments)
- Feed aggregated data into RIA learning cycle

Reference: ROADMAP.md 3.8 (FeedbackService)
"""

from __future__ import annotations

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
    ForeignKey,
    Integer,
    String,
    Text,
    and_,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.segment_context import WorkingStyleCode
from src.models.base import Base

# =============================================================================
# Enums
# =============================================================================


class FeedbackType(StrEnum):
    """Types of feedback."""

    # Explicit feedback
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    RATING = "rating"  # 1-5 stars
    COMMENT = "comment"

    # Implicit feedback (from EffectivenessService)
    TASK_COMPLETED = "task_completed"
    TASK_NOT_COMPLETED = "task_not_completed"
    PATTERN_BROKEN = "pattern_broken"
    PATTERN_RECURRED = "pattern_recurred"
    ENERGY_IMPROVED = "energy_improved"
    ENERGY_DECLINED = "energy_declined"
    ENGAGEMENT_INCREASED = "engagement_increased"
    ENGAGEMENT_DECREASED = "engagement_decreased"


class FeedbackContext(StrEnum):
    """Context where feedback was given."""

    INTERVENTION = "intervention"
    MODULE = "module"
    DAILY_WORKFLOW = "daily_workflow"
    COACHING = "coaching"
    PLANNING = "planning"
    REVIEW = "review"
    HABIT_CHECKIN = "habit_checkin"


# =============================================================================
# SQLAlchemy Models
# =============================================================================


class FeedbackRecord(Base):
    """
    Individual feedback record.

    Data Classification: INTERNAL
    - Feedback metadata, not personal content.
    """
    __tablename__ = "feedback_records"

    # Primary key
    feedback_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # User and segment
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    segment = Column(String(2), nullable=False, index=True)  # AD/AU/AH/NT/CU

    # Feedback type and value
    feedback_type = Column(String(50), nullable=False, index=True)  # FeedbackType value
    feedback_value = Column(Float, nullable=True)  # For ratings (1-5)
    feedback_comment = Column(Text, nullable=True)  # Optional text comment

    # Context
    context_type = Column(String(50), nullable=False, index=True)  # FeedbackContext value
    context_id = Column(String(100), nullable=True)  # Intervention ID, module name, etc.
    module = Column(String(50), nullable=True)  # Which module
    intervention_type = Column(String(50), nullable=True)  # Which intervention type

    # Timestamp
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    # Source
    is_explicit = Column(Boolean, nullable=False, default=True)  # Explicit vs implicit


class FeedbackAggregation(Base):
    """
    Aggregated feedback metrics per segment and context.

    Data Classification: INTERNAL
    """
    __tablename__ = "feedback_aggregations"

    # Composite primary key
    segment = Column(String(2), primary_key=True)  # AD/AU/AH/NT/CU
    context_type = Column(String(50), primary_key=True)  # FeedbackContext value
    context_id = Column(String(100), primary_key=True)  # Intervention type, module name, etc.

    # Aggregated counts
    total_feedback = Column(Integer, nullable=False, default=0)
    positive_count = Column(Integer, nullable=False, default=0)
    negative_count = Column(Integer, nullable=False, default=0)
    neutral_count = Column(Integer, nullable=False, default=0)

    # Ratings (if applicable)
    total_ratings = Column(Integer, nullable=False, default=0)
    avg_rating = Column(Float, nullable=False, default=0.0)
    sum_ratings = Column(Float, nullable=False, default=0.0)

    # Computed metrics
    satisfaction_rate = Column(Float, nullable=False, default=0.0)  # positive / total
    dissatisfaction_rate = Column(Float, nullable=False, default=0.0)  # negative / total

    # Last updated
    last_updated = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


# =============================================================================
# Pydantic Models for API Responses
# =============================================================================


@dataclass
class FeedbackSummary:
    """Summary of feedback for a context."""

    segment: str
    context_type: str
    context_id: str
    total_feedback: int
    satisfaction_rate: float
    avg_rating: float | None
    positive_count: int
    negative_count: int
    neutral_count: int


@dataclass
class FeedbackTrend:
    """Feedback trend over time."""

    segment: str
    context_type: str
    context_id: str
    time_window: str  # "last_7_days", "last_30_days", etc.
    feedback_count: int
    satisfaction_rate: float
    trend_direction: str  # "improving", "stable", "declining"


@dataclass
class FeedbackReport:
    """Weekly feedback report for admin."""

    generated_at: datetime
    total_feedback: int
    segment_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    top_performing: list[dict[str, Any]] = field(default_factory=list)
    underperforming: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# =============================================================================
# Service Implementation
# =============================================================================


class FeedbackService:
    """
    Track and aggregate user feedback per segment.

    Per ROADMAP.md 3.8:
    - Explicit feedback capture: thumbs up/down, ratings, comments
    - Context storage: intervention, module, segment, timestamp
    - Implicit feedback integration from EffectivenessService
    - Per-segment aggregation (NEVER across segments)
    - Feed aggregated data into RIA learning cycle
    """

    # Feedback categorization
    POSITIVE_TYPES = {
        FeedbackType.THUMBS_UP,
        FeedbackType.HELPFUL,
        FeedbackType.TASK_COMPLETED,
        FeedbackType.PATTERN_BROKEN,
        FeedbackType.ENERGY_IMPROVED,
        FeedbackType.ENGAGEMENT_INCREASED,
    }

    NEGATIVE_TYPES = {
        FeedbackType.THUMBS_DOWN,
        FeedbackType.NOT_HELPFUL,
        FeedbackType.TASK_NOT_COMPLETED,
        FeedbackType.PATTERN_RECURRED,
        FeedbackType.ENERGY_DECLINED,
        FeedbackType.ENGAGEMENT_DECREASED,
    }

    def __init__(self, session: AsyncSession):
        """Initialize with database session."""
        self.session = session

    async def record_feedback(
        self,
        user_id: int,
        segment: str,
        feedback_type: FeedbackType,
        context_type: FeedbackContext,
        context_id: str | None = None,
        module: str | None = None,
        intervention_type: str | None = None,
        feedback_value: float | None = None,
        feedback_comment: str | None = None,
        is_explicit: bool = True,
    ) -> str:
        """
        Record a feedback entry.

        Args:
            user_id: The user ID
            segment: User's segment (AD/AU/AH/NT/CU)
            feedback_type: Type of feedback (thumbs up/down, rating, etc.)
            context_type: Context where feedback was given (intervention, module, etc.)
            context_id: Optional context ID (intervention ID, module name, etc.)
            module: Optional module name
            intervention_type: Optional intervention type
            feedback_value: Optional numerical value (for ratings)
            feedback_comment: Optional text comment
            is_explicit: True if user explicitly gave feedback, False if implicit

        Returns:
            feedback_id: UUID for the feedback record
        """
        record = FeedbackRecord(
            feedback_id=str(uuid.uuid4()),
            user_id=user_id,
            segment=segment,
            feedback_type=feedback_type.value,
            feedback_value=feedback_value,
            feedback_comment=feedback_comment,
            context_type=context_type.value,
            context_id=context_id,
            module=module,
            intervention_type=intervention_type,
            created_at=datetime.now(UTC),
            is_explicit=is_explicit,
        )

        self.session.add(record)

        # Update aggregation
        await self._update_aggregation(record, feedback_type)

        await self.session.commit()

        return str(record.feedback_id)

    async def _update_aggregation(
        self,
        record: FeedbackRecord,
        feedback_type: FeedbackType,
    ) -> None:
        """Update aggregated feedback metrics."""
        # Find or create aggregation record
        stmt = select(FeedbackAggregation).where(
            and_(
                FeedbackAggregation.segment == record.segment,
                FeedbackAggregation.context_type == record.context_type,
                FeedbackAggregation.context_id == (record.context_id or ""),
            )
        )
        result = await self.session.execute(stmt)
        agg = result.scalar_one_or_none()

        if not agg:
            agg = FeedbackAggregation(
                segment=record.segment,
                context_type=record.context_type,
                context_id=record.context_id or "",
            )
            self.session.add(agg)

        # Update counts
        agg.total_feedback += 1  # type: ignore[assignment]

        if feedback_type in self.POSITIVE_TYPES:
            agg.positive_count += 1  # type: ignore[assignment]
        elif feedback_type in self.NEGATIVE_TYPES:
            agg.negative_count += 1  # type: ignore[assignment]
        else:
            agg.neutral_count += 1  # type: ignore[assignment]

        # Update ratings if applicable
        if feedback_type == FeedbackType.RATING and record.feedback_value is not None:
            agg.total_ratings += 1  # type: ignore[assignment]
            agg.sum_ratings += record.feedback_value  # type: ignore[assignment]
            agg.avg_rating = agg.sum_ratings / agg.total_ratings  # type: ignore[assignment]

        # Recalculate rates
        if agg.total_feedback > 0:
            agg.satisfaction_rate = agg.positive_count / agg.total_feedback  # type: ignore[assignment]
            agg.dissatisfaction_rate = agg.negative_count / agg.total_feedback  # type: ignore[assignment]

        agg.last_updated = datetime.now(UTC)  # type: ignore[assignment]

    async def get_summary(
        self,
        segment: str | None = None,
        context_type: FeedbackContext | None = None,
        context_id: str | None = None,
    ) -> list[FeedbackSummary]:
        """
        Get feedback summary, optionally filtered.

        Args:
            segment: Filter by segment (optional)
            context_type: Filter by context type (optional)
            context_id: Filter by context ID (optional)

        Returns:
            List of FeedbackSummary objects
        """
        stmt = select(FeedbackAggregation)

        if segment:
            stmt = stmt.where(FeedbackAggregation.segment == segment)
        if context_type:
            stmt = stmt.where(FeedbackAggregation.context_type == context_type.value)
        if context_id:
            stmt = stmt.where(FeedbackAggregation.context_id == context_id)

        result = await self.session.execute(stmt)
        aggregations = result.scalars().all()

        summaries = []
        for agg in aggregations:
            summaries.append(
                FeedbackSummary(
                    segment=str(agg.segment),
                    context_type=str(agg.context_type),
                    context_id=str(agg.context_id),
                    total_feedback=int(agg.total_feedback),
                    satisfaction_rate=float(agg.satisfaction_rate),
                    avg_rating=float(agg.avg_rating) if agg.total_ratings > 0 else None,
                    positive_count=int(agg.positive_count),
                    negative_count=int(agg.negative_count),
                    neutral_count=int(agg.neutral_count),
                )
            )

        return summaries

    async def get_trend(
        self,
        segment: str,
        context_type: FeedbackContext,
        context_id: str,
        time_window_days: int = 7,
    ) -> FeedbackTrend:
        """
        Get feedback trend over a time window.

        Args:
            segment: User segment
            context_type: Context type
            context_id: Context ID
            time_window_days: Number of days to analyze

        Returns:
            FeedbackTrend object
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=time_window_days)

        # Count feedback in time window
        stmt = (
            select(func.count(FeedbackRecord.feedback_id))
            .where(
                and_(
                    FeedbackRecord.segment == segment,
                    FeedbackRecord.context_type == context_type.value,
                    FeedbackRecord.context_id == context_id,
                    FeedbackRecord.created_at >= cutoff,
                )
            )
        )
        result = await self.session.execute(stmt)
        feedback_count = result.scalar() or 0

        # Count positive feedback
        stmt_positive = (
            select(func.count(FeedbackRecord.feedback_id))
            .where(
                and_(
                    FeedbackRecord.segment == segment,
                    FeedbackRecord.context_type == context_type.value,
                    FeedbackRecord.context_id == context_id,
                    FeedbackRecord.created_at >= cutoff,
                    FeedbackRecord.feedback_type.in_([t.value for t in self.POSITIVE_TYPES]),
                )
            )
        )
        result_positive = await self.session.execute(stmt_positive)
        positive_count = result_positive.scalar() or 0

        satisfaction_rate = positive_count / feedback_count if feedback_count > 0 else 0.0

        # Determine trend direction (compare to previous window)
        prev_cutoff = now - timedelta(days=time_window_days * 2)
        prev_end = cutoff

        stmt_prev = (
            select(func.count(FeedbackRecord.feedback_id))
            .where(
                and_(
                    FeedbackRecord.segment == segment,
                    FeedbackRecord.context_type == context_type.value,
                    FeedbackRecord.context_id == context_id,
                    FeedbackRecord.created_at >= prev_cutoff,
                    FeedbackRecord.created_at < prev_end,
                )
            )
        )
        result_prev = await self.session.execute(stmt_prev)
        prev_feedback_count = result_prev.scalar() or 0

        stmt_prev_positive = (
            select(func.count(FeedbackRecord.feedback_id))
            .where(
                and_(
                    FeedbackRecord.segment == segment,
                    FeedbackRecord.context_type == context_type.value,
                    FeedbackRecord.context_id == context_id,
                    FeedbackRecord.created_at >= prev_cutoff,
                    FeedbackRecord.created_at < prev_end,
                    FeedbackRecord.feedback_type.in_([t.value for t in self.POSITIVE_TYPES]),
                )
            )
        )
        result_prev_positive = await self.session.execute(stmt_prev_positive)
        prev_positive_count = result_prev_positive.scalar() or 0

        prev_satisfaction_rate = (
            prev_positive_count / prev_feedback_count if prev_feedback_count > 0 else 0.0
        )

        # Determine trend
        if satisfaction_rate > prev_satisfaction_rate + 0.1:
            trend_direction = "improving"
        elif satisfaction_rate < prev_satisfaction_rate - 0.1:
            trend_direction = "declining"
        else:
            trend_direction = "stable"

        return FeedbackTrend(
            segment=segment,
            context_type=context_type.value,
            context_id=context_id,
            time_window=f"last_{time_window_days}_days",
            feedback_count=feedback_count,
            satisfaction_rate=satisfaction_rate,
            trend_direction=trend_direction,
        )

    async def generate_weekly_report(self) -> FeedbackReport:
        """
        Generate weekly feedback report for admin.

        Returns:
            FeedbackReport with per-segment stats and recommendations
        """
        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)

        # Count all feedback from past week
        stmt = select(func.count(FeedbackRecord.feedback_id)).where(
            FeedbackRecord.created_at >= week_ago
        )
        result = await self.session.execute(stmt)
        total_feedback = result.scalar() or 0

        # Per-segment stats
        segment_stats: dict[str, dict[str, Any]] = {}
        all_segments: list[WorkingStyleCode] = ["AD", "AU", "AH", "NT", "CU"]

        for segment in all_segments:
            stmt_seg = (
                select(func.count(FeedbackRecord.feedback_id))
                .where(
                    and_(
                        FeedbackRecord.segment == segment,
                        FeedbackRecord.created_at >= week_ago,
                    )
                )
            )
            result_seg = await self.session.execute(stmt_seg)
            seg_count = result_seg.scalar() or 0

            stmt_pos = (
                select(func.count(FeedbackRecord.feedback_id))
                .where(
                    and_(
                        FeedbackRecord.segment == segment,
                        FeedbackRecord.created_at >= week_ago,
                        FeedbackRecord.feedback_type.in_([t.value for t in self.POSITIVE_TYPES]),
                    )
                )
            )
            result_pos = await self.session.execute(stmt_pos)
            pos_count = result_pos.scalar() or 0

            if seg_count > 0:
                segment_stats[segment] = {
                    "total_feedback": seg_count,
                    "positive_count": pos_count,
                    "satisfaction_rate": pos_count / seg_count,
                }

        # Top performing contexts (sorted by satisfaction rate, min 5 feedback items)
        stmt_top = select(FeedbackAggregation).where(
            FeedbackAggregation.total_feedback >= 5
        )
        result_top = await self.session.execute(stmt_top)
        all_aggs = result_top.scalars().all()

        top_performing: list[dict[str, Any]] = [
            {
                "segment": agg.segment,
                "context_type": agg.context_type,
                "context_id": agg.context_id,
                "satisfaction_rate": float(agg.satisfaction_rate),
                "total_feedback": int(agg.total_feedback),
            }
            for agg in all_aggs
        ]
        top_performing.sort(key=lambda x: float(x["satisfaction_rate"]), reverse=True)
        top_performing = top_performing[:5]

        # Underperforming contexts
        underperforming: list[dict[str, Any]] = [
            {
                "segment": agg.segment,
                "context_type": agg.context_type,
                "context_id": agg.context_id,
                "satisfaction_rate": float(agg.satisfaction_rate),
                "total_feedback": int(agg.total_feedback),
            }
            for agg in all_aggs
        ]
        underperforming.sort(key=lambda x: float(x["satisfaction_rate"]))
        underperforming = underperforming[:5]

        # Generate recommendations
        recommendations = []

        # Low satisfaction segments
        for segment_key, stats in segment_stats.items():
            if stats["satisfaction_rate"] < 0.5 and stats["total_feedback"] >= 5:
                recommendations.append(
                    f"Segment {segment_key.upper()} has low satisfaction ({stats['satisfaction_rate']:.1%}). "
                    f"RIA should analyze feedback and propose improvements."
                )

        # Underperforming contexts
        for context in underperforming[:3]:
            if float(context["satisfaction_rate"]) < 0.4:
                recommendations.append(
                    f"{context['context_type']} '{context['context_id']}' has low satisfaction "
                    f"({float(context['satisfaction_rate']):.1%}). Review and adjust."
                )

        # Positive recommendations
        for context in top_performing[:3]:
            if float(context["satisfaction_rate"]) > 0.8:
                recommendations.append(
                    f"{context['context_type']} '{context['context_id']}' performing well "
                    f"({float(context['satisfaction_rate']):.1%}). Consider expanding usage."
                )

        return FeedbackReport(
            generated_at=now,
            total_feedback=total_feedback,
            segment_stats=segment_stats,
            top_performing=top_performing,
            underperforming=underperforming,
            recommendations=recommendations,
        )

    async def export_user_feedback(self, user_id: int) -> dict[str, Any]:
        """GDPR Art. 15: Export all feedback for a user."""
        stmt = select(FeedbackRecord).where(FeedbackRecord.user_id == user_id)
        result = await self.session.execute(stmt)
        records = result.scalars().all()

        return {
            "feedback_records": [
                {
                    "feedback_id": r.feedback_id,
                    "feedback_type": r.feedback_type,
                    "context_type": r.context_type,
                    "context_id": r.context_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ]
        }

    async def delete_user_feedback(self, user_id: int) -> None:
        """GDPR Art. 17: Delete all feedback for a user."""
        stmt = select(FeedbackRecord).where(FeedbackRecord.user_id == user_id)
        result = await self.session.execute(stmt)
        records = result.scalars().all()

        for record in records:
            await self.session.delete(record)

        await self.session.commit()


# =============================================================================
# Service Factory
# =============================================================================


async def get_feedback_service(session: AsyncSession) -> FeedbackService:
    """Get or create FeedbackService instance."""
    return FeedbackService(session)
