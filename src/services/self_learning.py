"""
Self-Learning Service for Aurora Sun V1.

Implements autonomous learning loops per SW-7 and SW-8:
- Weekly Self-Doubt Check: "Are my users getting better?"
- Proposal flow: RIA → admin DM → approval → DSPy deploy → EffectivenessService verify
- Feature flag staged rollout capability (10% → 50% → 100%)
- Intervention variant comparison

Reference: ARCHITECTURE.md Section 11-12 (Autonomous Learning, Self-Learning Loops)

Author: Aurora Sun V1 Team
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.segment_context import WorkingStyleCode
from src.models.base import Base

# ============================================================================
# Enums
# ============================================================================


class ProposalType(StrEnum):
    """Types of proposals RIA can make."""

    PROMPT_CHANGE = "prompt_change"
    NEW_INTERVENTION = "new_intervention"
    PARAMETER_TUNING = "parameter_tuning"
    PATTERN_FLAG = "pattern_flag"
    SEGMENT_ADJUSTMENT = "segment_adjustment"
    WORKFLOW_CHANGE = "workflow_change"


class ProposalStatus(StrEnum):
    """Status of a proposal through its lifecycle."""

    PENDING = "pending"  # Awaiting admin review
    APPROVED = "approved"  # Admin approved
    REJECTED = "rejected"  # Admin rejected
    DEPLOYED = "deployed"  # Deployed to production
    ROLLOUT = "rollout"  # Staged rollout in progress
    COMPLETED = "completed"  # Rollout complete
    REVERTED = "reverted"  # Rolled back due to poor performance


class RolloutStage(StrEnum):
    """Stages of staged rollout."""

    STAGE_0 = "0%"  # Not started
    STAGE_10 = "10%"  # 10% of users
    STAGE_50 = "50%"  # 50% of users
    STAGE_100 = "100%"  # All users


# ============================================================================
# SQLAlchemy Models
# ============================================================================


class Proposal(Base):
    """A proposal from RIA for system improvement."""

    __tablename__ = "self_learning_proposals"

    # Identity
    proposal_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    proposal_type = Column(String(50), nullable=False, index=True)

    # Target
    target_segment = Column(String(2), nullable=True, index=True)  # AD/AU/AH/NT/CU or None for all
    target_intervention = Column(String(100), nullable=True)  # Specific intervention if applicable

    # Content
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)  # Why RIA thinks this will help
    evidence = Column(Text, nullable=True)  # Findings/patterns that support this

    # Status
    status = Column(String(20), nullable=False, default=ProposalStatus.PENDING.value, index=True)

    # Timestamps
    proposed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC)
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    deployed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Admin feedback
    admin_notes = Column(Text, nullable=True)

    # Rollout tracking
    rollout_stage = Column(String(10), nullable=False, default=RolloutStage.STAGE_0.value)
    rollout_percentage = Column(Integer, nullable=False, default=0)  # 0-100

    # Effectiveness tracking
    baseline_success_rate = Column(Float, nullable=True)  # Before deployment
    current_success_rate = Column(Float, nullable=True)  # After deployment
    improvement_delta = Column(Float, nullable=True)  # Difference


class WeeklyReport(Base):
    """Weekly self-doubt check report."""

    __tablename__ = "self_learning_weekly_reports"

    report_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Period
    week_start = Column(DateTime(timezone=True), nullable=False, index=True)
    week_end = Column(DateTime(timezone=True), nullable=False)
    generated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC)
    )

    # 5 Questions
    q1_users_improving = Column(Boolean, nullable=True)  # Are users getting better?
    q2_intervention_effectiveness = Column(Float, nullable=True)  # Overall success rate
    q3_segment_performance = Column(String(2), nullable=True)  # Weakest segment
    q4_new_patterns = Column(Integer, nullable=True)  # New patterns detected this week
    q5_proposal_count = Column(Integer, nullable=True)  # Proposals generated

    # Summary
    overall_health = Column(String(20), nullable=True)  # "good", "neutral", "concerning"
    key_findings = Column(Text, nullable=True)  # JSON list of findings
    action_items = Column(Text, nullable=True)  # JSON list of actions


class VariantComparison(Base):
    """Comparison between proposal and baseline (or variant A vs B)."""

    __tablename__ = "self_learning_variant_comparisons"

    comparison_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    proposal_id = Column(String(36), nullable=False, index=True)

    # Variants
    variant_a_name = Column(String(100), nullable=False, default="baseline")
    variant_b_name = Column(String(100), nullable=False, default="proposal")

    # Sample sizes
    variant_a_count = Column(Integer, nullable=False, default=0)
    variant_b_count = Column(Integer, nullable=False, default=0)

    # Success rates
    variant_a_success_rate = Column(Float, nullable=False, default=0.0)
    variant_b_success_rate = Column(Float, nullable=False, default=0.0)

    # Statistical significance
    is_significant = Column(Boolean, nullable=False, default=False)
    confidence = Column(Float, nullable=True)

    # Decision
    winner = Column(String(10), nullable=True)  # "A" or "B"
    decision = Column(String(20), nullable=True)  # "deploy", "revert", "continue"

    # Timestamps
    compared_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC)
    )


# ============================================================================
# Pydantic/Dataclass Models
# ============================================================================


@dataclass
class ProposalCreate:
    """Data for creating a new proposal."""

    proposal_type: ProposalType
    title: str
    description: str
    rationale: str
    evidence: str | None = None
    target_segment: WorkingStyleCode | None = None
    target_intervention: str | None = None


@dataclass
class ProposalResponse:
    """Response model for a proposal."""

    proposal_id: str
    proposal_type: str
    title: str
    description: str
    rationale: str
    status: str
    proposed_at: datetime
    target_segment: str | None
    rollout_stage: str
    rollout_percentage: int
    baseline_success_rate: float | None
    current_success_rate: float | None
    improvement_delta: float | None


@dataclass
class WeeklyReportData:
    """Data for weekly self-doubt check."""

    q1_users_improving: bool
    q2_intervention_effectiveness: float
    q3_segment_performance: str
    q4_new_patterns: int
    q5_proposal_count: int
    overall_health: str
    key_findings: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)


# ============================================================================
# Service Implementation
# ============================================================================


class SelfLearningService:
    """
    Autonomous learning loops for Aurora Sun V1.

    Per SW-7 & SW-8:
    - Weekly Self-Doubt Check
    - Proposal flow (RIA → admin → deploy → verify)
    - Staged rollout (10% → 50% → 100%)
    - Variant comparison
    """

    def __init__(self, session: AsyncSession):
        """Initialize with database session."""
        self.session = session

    async def create_proposal(
        self,
        proposal_data: ProposalCreate,
    ) -> str:
        """
        Create a new proposal from RIA.

        Args:
            proposal_data: Proposal details

        Returns:
            proposal_id: UUID for tracking
        """
        proposal = Proposal(
            proposal_id=str(uuid.uuid4()),
            proposal_type=proposal_data.proposal_type.value,
            title=proposal_data.title,
            description=proposal_data.description,
            rationale=proposal_data.rationale,
            evidence=proposal_data.evidence,
            target_segment=proposal_data.target_segment,
            target_intervention=proposal_data.target_intervention,
            status=ProposalStatus.PENDING.value,
            proposed_at=datetime.now(UTC),
        )

        self.session.add(proposal)
        await self.session.commit()

        return proposal.proposal_id  # type: ignore[return-value]

    async def approve_proposal(
        self,
        proposal_id: str,
        admin_notes: str | None = None,
    ) -> None:
        """
        Approve a proposal for deployment.

        Args:
            proposal_id: The proposal to approve
            admin_notes: Optional notes from admin
        """
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalar_one_or_none()

        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")

        proposal.status = ProposalStatus.APPROVED.value  # type: ignore[assignment]
        proposal.reviewed_at = datetime.now(UTC)  # type: ignore[assignment]
        if admin_notes:
            proposal.admin_notes = admin_notes  # type: ignore[assignment]

        await self.session.commit()

    async def reject_proposal(
        self,
        proposal_id: str,
        admin_notes: str | None = None,
    ) -> None:
        """
        Reject a proposal.

        Args:
            proposal_id: The proposal to reject
            admin_notes: Optional notes from admin
        """
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalar_one_or_none()

        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")

        proposal.status = ProposalStatus.REJECTED.value  # type: ignore[assignment]
        proposal.reviewed_at = datetime.now(UTC)  # type: ignore[assignment]
        if admin_notes:
            proposal.admin_notes = admin_notes  # type: ignore[assignment]

        await self.session.commit()

    async def deploy_proposal(
        self,
        proposal_id: str,
        baseline_success_rate: float | None = None,
    ) -> None:
        """
        Deploy an approved proposal.

        Args:
            proposal_id: The proposal to deploy
            baseline_success_rate: Success rate before deployment (for comparison)
        """
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalar_one_or_none()

        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")

        if proposal.status != ProposalStatus.APPROVED.value:
            raise ValueError(f"Proposal must be approved before deployment: {proposal.status}")

        proposal.status = ProposalStatus.DEPLOYED.value  # type: ignore[assignment]
        proposal.deployed_at = datetime.now(UTC)  # type: ignore[assignment]
        if baseline_success_rate is not None:
            proposal.baseline_success_rate = baseline_success_rate  # type: ignore[assignment]

        await self.session.commit()

    async def start_rollout(
        self,
        proposal_id: str,
        initial_stage: RolloutStage = RolloutStage.STAGE_10,
    ) -> None:
        """
        Start staged rollout for a proposal.

        Args:
            proposal_id: The proposal to roll out
            initial_stage: Starting rollout stage (default 10%)
        """
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalar_one_or_none()

        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")

        if proposal.status != ProposalStatus.DEPLOYED.value:
            raise ValueError(f"Proposal must be deployed before rollout: {proposal.status}")

        proposal.status = ProposalStatus.ROLLOUT.value  # type: ignore[assignment]
        proposal.rollout_stage = initial_stage.value  # type: ignore[assignment]
        proposal.rollout_percentage = int(initial_stage.value.strip("%"))  # type: ignore[assignment]

        await self.session.commit()

    async def advance_rollout(
        self,
        proposal_id: str,
        next_stage: RolloutStage,
    ) -> None:
        """
        Advance rollout to next stage.

        Args:
            proposal_id: The proposal being rolled out
            next_stage: Next rollout stage
        """
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalar_one_or_none()

        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")

        proposal.rollout_stage = next_stage.value  # type: ignore[assignment]
        proposal.rollout_percentage = int(next_stage.value.strip("%"))  # type: ignore[assignment]

        if next_stage == RolloutStage.STAGE_100:
            proposal.status = ProposalStatus.COMPLETED.value  # type: ignore[assignment]
            proposal.completed_at = datetime.now(UTC)  # type: ignore[assignment]

        await self.session.commit()

    async def revert_proposal(
        self,
        proposal_id: str,
        admin_notes: str | None = None,
    ) -> None:
        """
        Revert a proposal due to poor performance.

        Args:
            proposal_id: The proposal to revert
            admin_notes: Reason for revert
        """
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalar_one_or_none()

        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")

        proposal.status = ProposalStatus.REVERTED.value  # type: ignore[assignment]
        if admin_notes:
            proposal.admin_notes = admin_notes  # type: ignore[assignment]

        await self.session.commit()

    async def update_effectiveness(
        self,
        proposal_id: str,
        current_success_rate: float,
    ) -> None:
        """
        Update proposal effectiveness metrics.

        Args:
            proposal_id: The proposal to update
            current_success_rate: Current success rate
        """
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalar_one_or_none()

        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")

        proposal.current_success_rate = current_success_rate  # type: ignore[assignment]

        if proposal.baseline_success_rate is not None:
            proposal.improvement_delta = current_success_rate - proposal.baseline_success_rate  # type: ignore[assignment]

        await self.session.commit()

    async def create_variant_comparison(
        self,
        proposal_id: str,
        variant_a_count: int,
        variant_a_success_rate: float,
        variant_b_count: int,
        variant_b_success_rate: float,
        is_significant: bool,
        confidence: float | None = None,
        winner: str | None = None,
    ) -> str:
        """
        Create a variant comparison record.

        Args:
            proposal_id: The proposal being compared
            variant_a_count: Sample size for baseline
            variant_a_success_rate: Success rate for baseline
            variant_b_count: Sample size for proposal
            variant_b_success_rate: Success rate for proposal
            is_significant: Statistical significance
            confidence: Confidence level
            winner: "A" or "B" if significant

        Returns:
            comparison_id: UUID for tracking
        """
        comparison = VariantComparison(
            comparison_id=str(uuid.uuid4()),
            proposal_id=proposal_id,
            variant_a_count=variant_a_count,
            variant_a_success_rate=variant_a_success_rate,
            variant_b_count=variant_b_count,
            variant_b_success_rate=variant_b_success_rate,
            is_significant=is_significant,
            confidence=confidence,
            winner=winner,
        )

        self.session.add(comparison)
        await self.session.commit()

        return comparison.comparison_id  # type: ignore[return-value]

    async def generate_weekly_report(
        self,
        report_data: WeeklyReportData,
    ) -> str:
        """
        Generate weekly self-doubt check report.

        Args:
            report_data: Report data

        Returns:
            report_id: UUID for tracking
        """
        import json

        now = datetime.now(UTC)
        week_start = now - timedelta(days=7)

        report = WeeklyReport(
            report_id=str(uuid.uuid4()),
            week_start=week_start,
            week_end=now,
            generated_at=now,
            q1_users_improving=report_data.q1_users_improving,
            q2_intervention_effectiveness=report_data.q2_intervention_effectiveness,
            q3_segment_performance=report_data.q3_segment_performance,
            q4_new_patterns=report_data.q4_new_patterns,
            q5_proposal_count=report_data.q5_proposal_count,
            overall_health=report_data.overall_health,
            key_findings=json.dumps(report_data.key_findings),
            action_items=json.dumps(report_data.action_items),
        )

        self.session.add(report)
        await self.session.commit()

        return report.report_id  # type: ignore[return-value]

    async def get_pending_proposals(self) -> list[ProposalResponse]:
        """
        Get all pending proposals awaiting admin review.

        Returns:
            List of pending proposals
        """
        stmt = select(Proposal).where(
            Proposal.status == ProposalStatus.PENDING.value
        ).order_by(Proposal.proposed_at.desc())

        result = await self.session.execute(stmt)
        proposals = result.scalars().all()

        return [
            ProposalResponse(
                proposal_id=p.proposal_id,  # type: ignore[arg-type]
                proposal_type=p.proposal_type,  # type: ignore[arg-type]
                title=p.title,  # type: ignore[arg-type]
                description=p.description,  # type: ignore[arg-type]
                rationale=p.rationale,  # type: ignore[arg-type]
                status=p.status,  # type: ignore[arg-type]
                proposed_at=p.proposed_at,  # type: ignore[arg-type]
                target_segment=p.target_segment,  # type: ignore[arg-type]
                rollout_stage=p.rollout_stage,  # type: ignore[arg-type]
                rollout_percentage=p.rollout_percentage,  # type: ignore[arg-type]
                baseline_success_rate=p.baseline_success_rate,  # type: ignore[arg-type]
                current_success_rate=p.current_success_rate,  # type: ignore[arg-type]
                improvement_delta=p.improvement_delta,  # type: ignore[arg-type]
            )
            for p in proposals
        ]

    async def get_active_rollouts(self) -> list[ProposalResponse]:
        """
        Get all proposals currently in rollout.

        Returns:
            List of active rollouts
        """
        stmt = select(Proposal).where(
            Proposal.status == ProposalStatus.ROLLOUT.value
        ).order_by(Proposal.deployed_at.desc())

        result = await self.session.execute(stmt)
        proposals = result.scalars().all()

        return [
            ProposalResponse(
                proposal_id=p.proposal_id,  # type: ignore[arg-type]
                proposal_type=p.proposal_type,  # type: ignore[arg-type]
                title=p.title,  # type: ignore[arg-type]
                description=p.description,  # type: ignore[arg-type]
                rationale=p.rationale,  # type: ignore[arg-type]
                status=p.status,  # type: ignore[arg-type]
                proposed_at=p.proposed_at,  # type: ignore[arg-type]
                target_segment=p.target_segment,  # type: ignore[arg-type]
                rollout_stage=p.rollout_stage,  # type: ignore[arg-type]
                rollout_percentage=p.rollout_percentage,  # type: ignore[arg-type]
                baseline_success_rate=p.baseline_success_rate,  # type: ignore[arg-type]
                current_success_rate=p.current_success_rate,  # type: ignore[arg-type]
                improvement_delta=p.improvement_delta,  # type: ignore[arg-type]
            )
            for p in proposals
        ]

    async def get_recent_weekly_reports(self, limit: int = 10) -> list[WeeklyReport]:
        """
        Get recent weekly self-doubt check reports.

        Args:
            limit: Maximum number of reports to return

        Returns:
            List of recent reports
        """
        stmt = select(WeeklyReport).order_by(
            WeeklyReport.generated_at.desc()
        ).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())


# ============================================================================
# Service Factory
# ============================================================================


async def get_self_learning_service(session: AsyncSession) -> SelfLearningService:
    """Get or create SelfLearningService instance."""
    return SelfLearningService(session)
