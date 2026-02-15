"""
RIA Service (Research-Informed Adaptation) for Aurora Sun V1.

The RIA Service is the system's learning engine. It runs a daily cycle to:
- Ingest research findings into Neo4j + Qdrant
- Analyze pattern detection signals + neurostate signals
- Generate segment-specific proposals (finding → hypothesis → proposal)
- Manage A/B test lifecycle
- Optimize interventions using DSPy (BootstrapFewShot <200 traces, MIPROv2 >=200)

Key Principle: **Every proposal → DM to admin. No deployment without OK.**

Reference: ROADMAP.md 3.9 (RIA Service)
"""

from __future__ import annotations

import hashlib
import hmac
import os
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
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.segment_context import WorkingStyleCode
from src.models.base import Base

# =============================================================================
# Enums
# =============================================================================


class ProposalStatus(StrEnum):
    """Status of an RIA proposal."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPLOYED = "deployed"


class ProposalType(StrEnum):
    """Types of RIA proposals."""

    NEW_INTERVENTION = "new_intervention"
    MODIFY_INTERVENTION = "modify_intervention"
    RETIRE_INTERVENTION = "retire_intervention"
    NEW_PATTERN_SIGNAL = "new_pattern_signal"
    ADJUST_THRESHOLD = "adjust_threshold"
    NEW_PROMPT = "new_prompt"
    MODIFY_WORKFLOW = "modify_workflow"


class RIACyclePhase(StrEnum):
    """Phases of the RIA daily cycle."""

    INGEST = "ingest"
    ANALYZE = "analyze"
    PROPOSE = "propose"
    REFLECT = "reflect"


# =============================================================================
# SQLAlchemy Models
# =============================================================================


class RIAProposal(Base):
    """
    RIA proposal record.

    Data Classification: INTERNAL
    """
    __tablename__ = "ria_proposals"

    # Primary key
    proposal_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Proposal details
    proposal_type = Column(String(50), nullable=False, index=True)  # ProposalType value
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)  # Why this change is needed

    # Segment targeting
    target_segment = Column(String(2), nullable=False, index=True)  # AD/AU/AH/NT/CU

    # Supporting evidence
    finding_ids = Column(Text, nullable=True)  # JSON list of research finding IDs
    effectiveness_data = Column(Text, nullable=True)  # JSON of effectiveness metrics
    pattern_data = Column(Text, nullable=True)  # JSON of pattern detection data

    # Status
    status = Column(String(20), nullable=False, default=ProposalStatus.PENDING.value, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    deployed_at = Column(DateTime(timezone=True), nullable=True)

    # Admin feedback
    admin_notes = Column(Text, nullable=True)
    reviewer_id = Column(Integer, nullable=True)  # Admin user ID


class RIACycleLog(Base):
    """
    Log of RIA daily cycles.

    Data Classification: INTERNAL

    Each log entry includes an HMAC integrity hash computed
    over the immutable fields (cycle_id, cycle_date, phase, metrics,
    started_at). This allows tamper detection on audit review.
    """
    __tablename__ = "ria_cycle_logs"

    # Primary key
    cycle_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Cycle details
    cycle_date = Column(DateTime(timezone=True), nullable=False, index=True)
    phase = Column(String(20), nullable=False)  # RIACyclePhase value

    # Metrics
    findings_ingested = Column(Integer, nullable=False, default=0)
    patterns_analyzed = Column(Integer, nullable=False, default=0)
    proposals_generated = Column(Integer, nullable=False, default=0)
    errors = Column(Text, nullable=True)  # JSON list of errors

    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # HMAC integrity hash for tamper detection on audit review
    integrity_hash = Column(String(64), nullable=True)


class RIAFinding(Base):
    """
    Research finding ingested into RIA.

    Data Classification: PUBLIC
    """
    __tablename__ = "ria_findings"

    # Primary key
    finding_id = Column(String(100), primary_key=True)  # e.g., "FINDING-001"

    # Finding details
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    source = Column(String(200), nullable=True)  # Research source
    finding_type = Column(String(50), nullable=True)  # Pattern, intervention, threshold, etc.

    # Segment applicability
    applicable_segments = Column(Text, nullable=False)  # JSON list of segments

    # ADHD contamination warning for Autism findings
    adhd_contamination_risk = Column(Boolean, nullable=False, default=False)
    contamination_notes = Column(Text, nullable=True)

    # Metadata
    confidence_score = Column(Float, nullable=True)  # 0.0-1.0
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    neo4j_node_id = Column(String(100), nullable=True)  # Link to knowledge graph
    qdrant_point_id = Column(String(100), nullable=True)  # Link to vector store


class RIAExperiment(Base):
    """
    A/B test experiment managed by RIA.

    Data Classification: INTERNAL
    """
    __tablename__ = "ria_experiments"

    # Primary key
    experiment_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Experiment details
    name = Column(String(200), nullable=False)
    hypothesis = Column(Text, nullable=False)
    segment = Column(String(2), nullable=False, index=True)  # AD/AU/AH/NT/CU

    # Variants
    variant_a_id = Column(String(100), nullable=False)
    variant_b_id = Column(String(100), nullable=False)
    variant_a_description = Column(Text, nullable=False)
    variant_b_description = Column(Text, nullable=False)

    # Sample requirements
    min_samples_per_variant = Column(Integer, nullable=False, default=20)
    target_power = Column(Float, nullable=False, default=0.8)  # Statistical power

    # Status
    status = Column(String(20), nullable=False, default="active", index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Results
    winner = Column(String(10), nullable=True)  # "A" or "B"
    confidence = Column(Float, nullable=True)  # Statistical confidence
    result_summary = Column(Text, nullable=True)

    # Related proposal
    proposal_id = Column(String(36), ForeignKey("ria_proposals.proposal_id"), nullable=True)


# =============================================================================
# Pydantic Models for API Responses
# =============================================================================


@dataclass
class RIAProposalSummary:
    """Summary of an RIA proposal."""

    proposal_id: str
    title: str
    proposal_type: str
    target_segment: str
    status: str
    created_at: datetime
    rationale: str


@dataclass
class RIACycleSummary:
    """Summary of an RIA cycle."""

    cycle_id: str
    cycle_date: datetime
    findings_ingested: int
    patterns_analyzed: int
    proposals_generated: int
    duration_seconds: float | None


@dataclass
class RIAReport:
    """Weekly RIA report for admin."""

    generated_at: datetime
    total_proposals: int
    pending_proposals: int
    approved_proposals: int
    deployed_proposals: int
    active_experiments: int
    recent_proposals: list[RIAProposalSummary] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# =============================================================================
# Service Implementation
# =============================================================================


def _compute_cycle_log_hmac(log: RIACycleLog) -> str:
    """
    Compute HMAC-SHA256 integrity hash for a RIA cycle log entry.

    The HMAC is computed over the immutable fields of the log entry:
    cycle_id, cycle_date, phase, findings_ingested, patterns_analyzed,
    proposals_generated, started_at.

    The HMAC key is derived from AURORA_MASTER_KEY env var. If not set,
    falls back to a static key (development only -- logs a warning).

    Args:
        log: The RIACycleLog entry to compute the hash for.

    Returns:
        Hex-encoded HMAC-SHA256 digest (64 characters).
    """
    import logging as _logging

    key_material = os.environ.get("AURORA_MASTER_KEY", "")
    if not key_material:
        _logging.getLogger(__name__).warning(
            "AURORA_MASTER_KEY not set; using insecure fallback for cycle log HMAC"
        )
        key_material = "dev-only-insecure-key"

    # Build the message from immutable fields
    message_parts = [
        str(log.cycle_id),
        str(log.cycle_date.isoformat()) if log.cycle_date else "",
        str(log.phase),
        str(log.findings_ingested),
        str(log.patterns_analyzed),
        str(log.proposals_generated),
        str(log.started_at.isoformat()) if log.started_at else "",
    ]
    message = "|".join(message_parts).encode("utf-8")

    return hmac.new(
        key_material.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


def verify_cycle_log_integrity(log: RIACycleLog) -> bool:
    """
    Verify the HMAC integrity of a RIA cycle log entry.

    Args:
        log: The RIACycleLog entry to verify.

    Returns:
        True if the integrity hash matches, False if tampered or missing.
    """
    if not log.integrity_hash:
        return False
    expected = _compute_cycle_log_hmac(log)
    return hmac.compare_digest(str(log.integrity_hash), expected)


class RIAService:
    """
    Research-Informed Adaptation (RIA) Service.

    The RIA Service is the system's learning engine. It runs a daily cycle:
    1. INGEST: Research findings → Neo4j + Qdrant
    2. ANALYZE: Pattern signals + neurostate signals + effectiveness data
    3. PROPOSE: Generate segment-specific proposals (finding → hypothesis → proposal)
    4. REFLECT: Update confidence scores, identify gaps

    Key Principles:
    - Every proposal → DM to admin. No deployment without OK.
    - ADHD contamination warning for Autism findings
    - Per-segment proposals (NEVER across segments)
    - A/B test lifecycle management
    - DSPy optimization: BootstrapFewShot (<200 traces), MIPROv2 (>=200)
    """

    def __init__(self, session: AsyncSession):
        """Initialize with database session."""
        self.session = session

    async def run_daily_cycle(self) -> RIACycleSummary:
        """
        Run the daily RIA cycle.

        Phases:
        1. INGEST: Research findings → knowledge graph
        2. ANALYZE: Detection signals + effectiveness data
        3. PROPOSE: Generate proposals
        4. REFLECT: Update confidence scores

        Returns:
            RIACycleSummary with cycle metrics
        """
        cycle_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        # Phase 1: INGEST
        ingest_log = await self._run_ingest_phase(cycle_id, now)

        # Phase 2: ANALYZE
        analyze_log = await self._run_analyze_phase(cycle_id, now)

        # Phase 3: PROPOSE
        propose_log = await self._run_propose_phase(cycle_id, now)

        # Phase 4: REFLECT
        await self._run_reflect_phase(cycle_id, now)

        # Aggregate metrics
        total_findings = ingest_log.findings_ingested
        total_patterns = analyze_log.patterns_analyzed
        total_proposals = propose_log.proposals_generated

        duration = (datetime.now(UTC) - now).total_seconds()

        return RIACycleSummary(
            cycle_id=cycle_id,
            cycle_date=now,
            findings_ingested=int(total_findings),
            patterns_analyzed=int(total_patterns),
            proposals_generated=int(total_proposals),
            duration_seconds=duration,
        )

    async def _run_ingest_phase(
        self,
        cycle_id: str,
        cycle_date: datetime,
    ) -> RIACycleLog:
        """
        INGEST phase: Load research findings into knowledge graph.

        For now, this is a stub. In production, this would:
        - Load findings from knowledge/research/*.json
        - Parse applicable_segments, ADHD contamination warnings
        - Store in Neo4j + Qdrant for semantic search
        """
        log = RIACycleLog(
            cycle_id=f"{cycle_id}-ingest",
            cycle_date=cycle_date,
            phase=RIACyclePhase.INGEST.value,
            findings_ingested=0,
            patterns_analyzed=0,
            proposals_generated=0,
            started_at=datetime.now(UTC),
        )

        # TODO: Implement finding ingestion
        # - Parse knowledge/research/meta-synthesis-*.json
        # - Check ADHD contamination for Autism findings
        # - Store in RIAFinding table
        # - Create Neo4j nodes + Qdrant embeddings

        log.completed_at = datetime.now(UTC)  # type: ignore[assignment]
        log.duration_seconds = (log.completed_at - log.started_at).total_seconds()

        # Compute HMAC integrity hash before persisting (tamper detection)
        log.integrity_hash = _compute_cycle_log_hmac(log)  # type: ignore[assignment]

        self.session.add(log)
        await self.session.commit()

        return log

    async def _run_analyze_phase(
        self,
        cycle_id: str,
        cycle_date: datetime,
    ) -> RIACycleLog:
        """
        ANALYZE phase: Pattern detection signals + effectiveness data.

        For now, this is a stub. In production, this would:
        - Query EffectivenessService for intervention outcomes
        - Query PatternDetection for recurrence signals
        - Query NeurostateService for trajectory changes
        - Identify underperforming interventions (success rate < 0.4)
        """
        log = RIACycleLog(
            cycle_id=f"{cycle_id}-analyze",
            cycle_date=cycle_date,
            phase=RIACyclePhase.ANALYZE.value,
            findings_ingested=0,
            patterns_analyzed=0,
            proposals_generated=0,
            started_at=datetime.now(UTC),
        )

        # TODO: Implement analysis
        # - Load EffectivenessService data
        # - Load PatternDetection signals
        # - Load FeedbackService aggregations
        # - Identify gaps and opportunities

        log.completed_at = datetime.now(UTC)  # type: ignore[assignment]
        log.duration_seconds = (log.completed_at - log.started_at).total_seconds()

        # Compute HMAC integrity hash before persisting (tamper detection)
        log.integrity_hash = _compute_cycle_log_hmac(log)  # type: ignore[assignment]

        self.session.add(log)
        await self.session.commit()

        return log

    async def _run_propose_phase(
        self,
        cycle_id: str,
        cycle_date: datetime,
    ) -> RIACycleLog:
        """
        PROPOSE phase: Generate segment-specific proposals.

        For now, this is a stub. In production, this would:
        - finding → hypothesis → proposal
        - Segment-specific: NEVER propose across segments
        - ADHD contamination check for Autism proposals
        - Create RIAProposal records
        - Send DM to admin via Telegram
        """
        log = RIACycleLog(
            cycle_id=f"{cycle_id}-propose",
            cycle_date=cycle_date,
            phase=RIACyclePhase.PROPOSE.value,
            findings_ingested=0,
            patterns_analyzed=0,
            proposals_generated=0,
            started_at=datetime.now(UTC),
        )

        # TODO: Implement proposal generation
        # - Match findings to observed patterns
        # - Generate segment-specific hypotheses
        # - Create proposals (NEW_INTERVENTION, MODIFY_INTERVENTION, etc.)
        # - DM admin for approval

        log.completed_at = datetime.now(UTC)  # type: ignore[assignment]
        log.duration_seconds = (log.completed_at - log.started_at).total_seconds()

        # Compute HMAC integrity hash before persisting (tamper detection)
        log.integrity_hash = _compute_cycle_log_hmac(log)  # type: ignore[assignment]

        self.session.add(log)
        await self.session.commit()

        return log

    async def _run_reflect_phase(
        self,
        cycle_id: str,
        cycle_date: datetime,
    ) -> RIACycleLog:
        """
        REFLECT phase: Update confidence scores, identify gaps.

        For now, this is a stub. In production, this would:
        - Update finding confidence based on effectiveness data
        - Identify research gaps (patterns without findings)
        - Log insights for next cycle
        """
        log = RIACycleLog(
            cycle_id=f"{cycle_id}-reflect",
            cycle_date=cycle_date,
            phase=RIACyclePhase.REFLECT.value,
            findings_ingested=0,
            patterns_analyzed=0,
            proposals_generated=0,
            started_at=datetime.now(UTC),
        )

        # TODO: Implement reflection
        # - Update confidence scores
        # - Identify gaps in research coverage
        # - Log insights

        log.completed_at = datetime.now(UTC)  # type: ignore[assignment]
        log.duration_seconds = (log.completed_at - log.started_at).total_seconds()

        # Compute HMAC integrity hash before persisting (tamper detection)
        log.integrity_hash = _compute_cycle_log_hmac(log)  # type: ignore[assignment]

        self.session.add(log)
        await self.session.commit()

        return log

    async def create_proposal(
        self,
        proposal_type: ProposalType,
        title: str,
        description: str,
        rationale: str,
        target_segment: WorkingStyleCode,
        finding_ids: list[str] | None = None,
        effectiveness_data: dict[str, Any] | None = None,
        pattern_data: dict[str, Any] | None = None,
    ) -> str:
        """
        Create a new RIA proposal.

        Args:
            proposal_type: Type of proposal (NEW_INTERVENTION, etc.)
            title: Short title
            description: Full description
            rationale: Why this change is needed
            target_segment: Which segment this applies to
            finding_ids: Optional list of research finding IDs
            effectiveness_data: Optional effectiveness metrics
            pattern_data: Optional pattern detection data

        Returns:
            proposal_id: UUID of the created proposal
        """
        import json

        proposal = RIAProposal(
            proposal_id=str(uuid.uuid4()),
            proposal_type=proposal_type.value,
            title=title,
            description=description,
            rationale=rationale,
            target_segment=target_segment,
            finding_ids=json.dumps(finding_ids) if finding_ids else None,
            effectiveness_data=json.dumps(effectiveness_data) if effectiveness_data else None,
            pattern_data=json.dumps(pattern_data) if pattern_data else None,
            status=ProposalStatus.PENDING.value,
            created_at=datetime.now(UTC),
        )

        self.session.add(proposal)
        await self.session.commit()

        # TODO: Send DM to admin via Telegram
        # from src.bot.telegram_service import send_admin_dm
        # await send_admin_dm(
        #     f"New RIA Proposal: {title}\n\n"
        #     f"Type: {proposal_type}\n"
        #     f"Segment: {target_segment}\n"
        #     f"Rationale: {rationale}\n\n"
        #     f"Review at /ria/proposals/{proposal.proposal_id}"
        # )

        return str(proposal.proposal_id)

    async def approve_proposal(
        self,
        proposal_id: str,
        admin_notes: str | None = None,
        reviewer_id: int | None = None,
    ) -> None:
        """
        Approve an RIA proposal.

        Args:
            proposal_id: The proposal ID
            admin_notes: Optional notes from admin
            reviewer_id: Optional admin user ID
        """
        stmt = select(RIAProposal).where(RIAProposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalar_one_or_none()

        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")

        proposal.status = ProposalStatus.APPROVED.value  # type: ignore[assignment]
        proposal.reviewed_at = datetime.now(UTC)  # type: ignore[assignment]
        proposal.admin_notes = admin_notes  # type: ignore[assignment]
        proposal.reviewer_id = reviewer_id  # type: ignore[assignment]

        await self.session.commit()

    async def reject_proposal(
        self,
        proposal_id: str,
        admin_notes: str | None = None,
        reviewer_id: int | None = None,
    ) -> None:
        """
        Reject an RIA proposal.

        Args:
            proposal_id: The proposal ID
            admin_notes: Optional notes from admin
            reviewer_id: Optional admin user ID
        """
        stmt = select(RIAProposal).where(RIAProposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalar_one_or_none()

        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")

        proposal.status = ProposalStatus.REJECTED.value  # type: ignore[assignment]
        proposal.reviewed_at = datetime.now(UTC)  # type: ignore[assignment]
        proposal.admin_notes = admin_notes  # type: ignore[assignment]
        proposal.reviewer_id = reviewer_id  # type: ignore[assignment]

        await self.session.commit()

    async def deploy_proposal(self, proposal_id: str) -> None:
        """
        Mark a proposal as deployed.

        This is called after the admin has manually deployed the changes.

        Args:
            proposal_id: The proposal ID
        """
        stmt = select(RIAProposal).where(RIAProposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalar_one_or_none()

        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")

        if proposal.status != ProposalStatus.APPROVED.value:
            raise ValueError(f"Proposal must be approved before deployment: {proposal_id}")

        proposal.status = ProposalStatus.DEPLOYED.value  # type: ignore[assignment]
        proposal.deployed_at = datetime.now(UTC)  # type: ignore[assignment]

        await self.session.commit()

    async def get_pending_proposals(self) -> list[RIAProposalSummary]:
        """Get all pending proposals for admin review."""
        stmt = (
            select(RIAProposal)
            .where(RIAProposal.status == ProposalStatus.PENDING.value)
            .order_by(RIAProposal.created_at.desc())
        )
        result = await self.session.execute(stmt)
        proposals = result.scalars().all()

        return [
            RIAProposalSummary(
                proposal_id=str(p.proposal_id),
                title=str(p.title),
                proposal_type=str(p.proposal_type),
                target_segment=str(p.target_segment),
                status=str(p.status),
                created_at=p.created_at,  # type: ignore[arg-type]
                rationale=str(p.rationale),
            )
            for p in proposals
        ]

    async def generate_weekly_report(self) -> RIAReport:
        """
        Generate weekly RIA report for admin.

        Returns:
            RIAReport with proposal stats and recommendations
        """
        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)

        # Count proposals
        stmt_total = select(RIAProposal)
        result_total = await self.session.execute(stmt_total)
        all_proposals = result_total.scalars().all()

        total_proposals = len(all_proposals)
        pending_proposals = len([p for p in all_proposals if p.status == ProposalStatus.PENDING.value])
        approved_proposals = len([p for p in all_proposals if p.status == ProposalStatus.APPROVED.value])
        deployed_proposals = len([p for p in all_proposals if p.status == ProposalStatus.DEPLOYED.value])

        # Count active experiments
        stmt_exp = select(RIAExperiment).where(RIAExperiment.status == "active")
        result_exp = await self.session.execute(stmt_exp)
        active_experiments = len(list(result_exp.scalars().all()))

        # Recent proposals (last 7 days)
        recent = [
            RIAProposalSummary(
                proposal_id=str(p.proposal_id),
                title=str(p.title),
                proposal_type=str(p.proposal_type),
                target_segment=str(p.target_segment),
                status=str(p.status),
                created_at=p.created_at,  # type: ignore[arg-type]
                rationale=str(p.rationale),
            )
            for p in all_proposals
            if p.created_at >= week_ago
        ]
        recent.sort(key=lambda x: x.created_at, reverse=True)

        # Generate recommendations
        recommendations = []

        if pending_proposals > 10:
            recommendations.append(
                f"{pending_proposals} proposals pending review. Consider prioritizing approval workflow."
            )

        if active_experiments > 5:
            recommendations.append(
                f"{active_experiments} active experiments. Monitor completion and analyze results."
            )

        if deployed_proposals / max(total_proposals, 1) < 0.3:
            recommendations.append(
                "Low deployment rate. Review proposal quality or approval criteria."
            )

        return RIAReport(
            generated_at=now,
            total_proposals=total_proposals,
            pending_proposals=pending_proposals,
            approved_proposals=approved_proposals,
            deployed_proposals=deployed_proposals,
            active_experiments=active_experiments,
            recent_proposals=recent[:10],
            recommendations=recommendations,
        )


# =============================================================================
# Service Factory
# =============================================================================


async def get_ria_service(session: AsyncSession) -> RIAService:
    """Get or create RIAService instance."""
    return RIAService(session)
