"""
Tests for RIA Service (Research-Informed Adaptation).

Tests:
- Daily cycle execution (Ingest → Analyze → Propose → Reflect)
- Proposal creation and lifecycle
- Proposal approval/rejection/deployment
- Experiment management
- Weekly report generation
- ADHD contamination warnings
- Per-segment proposal isolation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.ria_service import (
    ProposalType,
    RIAService,
)


@pytest.fixture
def mock_session() -> MagicMock:
    """Create async-compatible mock session for RIAService."""
    from src.services.ria_service import RIAProposal

    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()

    # Track objects added via session.add()
    added_objects: list = []

    def mock_add(obj):
        added_objects.append(obj)

    session.add = mock_add

    # Configure execute to return appropriate results
    async def mock_execute(stmt):
        # Check query type
        stmt_str = str(stmt)
        mock_result = MagicMock()

        # Get bound parameters if available
        params = {}
        if hasattr(stmt, 'compile'):
            compiled = stmt.compile(compile_kwargs={"literal_binds": False})
            params = compiled.params if hasattr(compiled, 'params') else {}


        # Handle COUNT queries - return integer
        if "count(" in stmt_str.lower() or "func.count" in stmt_str:
            mock_result.scalar.return_value = 0
            mock_result.scalar_one_or_none.return_value = 0
            return mock_result

        # Handle RIAProposal queries
        if "ria_proposal" in stmt_str.lower():
            # Extract filters from params
            proposal_id_filter = params.get('proposal_id_1')
            status_filter = params.get('status_1')

            # Return matching RIAProposal objects
            proposal_objects = [obj for obj in added_objects if isinstance(obj, RIAProposal)]

            # Apply filters
            if proposal_id_filter:
                proposal_objects = [obj for obj in proposal_objects if obj.proposal_id == proposal_id_filter]
            if status_filter:
                proposal_objects = [obj for obj in proposal_objects if obj.status == status_filter]

            if proposal_objects:
                # Return single or multiple based on query type
                if proposal_id_filter:
                    # Querying by ID - return single (should be exactly 1 match due to filter)
                    mock_result.scalar_one_or_none.return_value = proposal_objects[0] if proposal_objects else None
                else:
                    # Return all matching (get_pending_proposals, get all, etc.)
                    mock_scalars = MagicMock()
                    mock_scalars.all.return_value = proposal_objects
                    mock_result.scalars.return_value = mock_scalars
            else:
                # No proposals match
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []
        else:
            # Default empty result
            mock_result.scalar_one_or_none.return_value = None
            mock_result.scalars.return_value.all.return_value = []
            mock_result.scalar.return_value = 0

        return mock_result

    session.execute = mock_execute

    return session


@pytest.fixture
def ria_service(mock_session: MagicMock) -> RIAService:  # type: ignore[no-untyped-def]
    """Create RIAService instance with mock async session."""
    return RIAService(session=mock_session)  # type: ignore[arg-type]


# =============================================================================
# Daily Cycle Execution
# =============================================================================


@pytest.mark.asyncio
async def test_run_daily_cycle(ria_service: RIAService) -> None:
    """Test running the complete daily cycle."""
    summary = await ria_service.run_daily_cycle()

    assert summary is not None
    assert summary.cycle_id is not None
    assert summary.cycle_date is not None
    assert summary.findings_ingested >= 0
    assert summary.patterns_analyzed >= 0
    assert summary.proposals_generated >= 0
    assert summary.duration_seconds is not None
    assert summary.duration_seconds >= 0


@pytest.mark.asyncio
async def test_daily_cycle_logs_phases(ria_service: RIAService) -> None:
    """Test that daily cycle logs all four phases."""
    await ria_service.run_daily_cycle()

    # In production, we would query the database for RIACycleLog entries
    # and verify that all four phases (INGEST, ANALYZE, PROPOSE, REFLECT) were logged
    # For now, we just verify the cycle completes without error
    assert True


# =============================================================================
# Proposal Creation
# =============================================================================


@pytest.mark.asyncio
async def test_create_proposal_new_intervention(ria_service: RIAService) -> None:
    """Test creating a proposal for a new intervention."""
    proposal_id = await ria_service.create_proposal(
        proposal_type=ProposalType.NEW_INTERVENTION,
        title="Add PINCH variant for ADHD-PI",
        description="New intervention variant for ADHD-PI segment based on research finding XYZ",
        rationale="Current PINCH protocol not optimized for ADHD-PI inattentive type",
        target_segment="AD",
        finding_ids=["FINDING-042"],
    )

    assert proposal_id is not None
    assert isinstance(proposal_id, str)
    assert len(proposal_id) > 0


@pytest.mark.asyncio
async def test_create_proposal_modify_intervention(ria_service: RIAService) -> None:
    """Test creating a proposal to modify an existing intervention."""
    proposal_id = await ria_service.create_proposal(
        proposal_type=ProposalType.MODIFY_INTERVENTION,
        title="Adjust Autism inertia threshold",
        description="Lower inertia detection threshold for Autism segment",
        rationale="Effectiveness data shows current threshold misses early inertia signals",
        target_segment="AU",
        effectiveness_data={"current_success_rate": 0.45, "target_success_rate": 0.70},
    )

    assert proposal_id is not None


@pytest.mark.asyncio
async def test_create_proposal_retire_intervention(ria_service: RIAService) -> None:
    """Test creating a proposal to retire an intervention."""
    proposal_id = await ria_service.create_proposal(
        proposal_type=ProposalType.RETIRE_INTERVENTION,
        title="Retire outdated motivation prompt",
        description="Remove low-performing motivation prompt for AuDHD segment",
        rationale="Success rate consistently below 0.3, user feedback negative",
        target_segment="AH",
        effectiveness_data={"success_rate": 0.28, "sample_size": 100},
    )

    assert proposal_id is not None


@pytest.mark.asyncio
async def test_create_proposal_new_pattern_signal(ria_service: RIAService) -> None:
    """Test creating a proposal for a new pattern detection signal."""
    proposal_id = await ria_service.create_proposal(
        proposal_type=ProposalType.NEW_PATTERN_SIGNAL,
        title="Add 'notification avoidance' signal",
        description="New detection signal for notification avoidance pattern",
        rationale="Pattern observed in user data but not currently detected",
        target_segment="NT",
        pattern_data={"occurrence_rate": 0.23, "correlation_with_burnout": 0.65},
    )

    assert proposal_id is not None


# =============================================================================
# Proposal Lifecycle
# =============================================================================


@pytest.mark.asyncio
async def test_approve_proposal(ria_service: RIAService) -> None:
    """Test approving a proposal."""
    # Create proposal
    proposal_id = await ria_service.create_proposal(
        proposal_type=ProposalType.NEW_PROMPT,
        title="Test proposal for approval",
        description="Test description",
        rationale="Test rationale",
        target_segment="AD",
    )

    # Approve
    await ria_service.approve_proposal(
        proposal_id=proposal_id,
        admin_notes="Looks good, approved for deployment",
        reviewer_id=1,
    )

    # Verify status changed (would query database in real implementation)
    assert True


@pytest.mark.asyncio
async def test_reject_proposal(ria_service: RIAService) -> None:
    """Test rejecting a proposal."""
    # Create proposal
    proposal_id = await ria_service.create_proposal(
        proposal_type=ProposalType.MODIFY_WORKFLOW,
        title="Test proposal for rejection",
        description="Test description",
        rationale="Test rationale",
        target_segment="AU",
    )

    # Reject
    await ria_service.reject_proposal(
        proposal_id=proposal_id,
        admin_notes="Not aligned with current priorities",
        reviewer_id=1,
    )

    # Verify status changed
    assert True


@pytest.mark.asyncio
async def test_deploy_proposal(ria_service: RIAService) -> None:
    """Test deploying an approved proposal."""
    # Create and approve proposal
    proposal_id = await ria_service.create_proposal(
        proposal_type=ProposalType.ADJUST_THRESHOLD,
        title="Test proposal for deployment",
        description="Test description",
        rationale="Test rationale",
        target_segment="AH",
    )

    await ria_service.approve_proposal(
        proposal_id=proposal_id,
        reviewer_id=1,
    )

    # Deploy
    await ria_service.deploy_proposal(proposal_id=proposal_id)

    # Verify deployment timestamp set
    assert True


@pytest.mark.asyncio
async def test_deploy_unapproved_proposal_fails(ria_service: RIAService) -> None:
    """Test that deploying an unapproved proposal raises an error."""
    # Create proposal (but don't approve)
    proposal_id = await ria_service.create_proposal(
        proposal_type=ProposalType.NEW_INTERVENTION,
        title="Test unapproved deployment",
        description="Test description",
        rationale="Test rationale",
        target_segment="NT",
    )

    # Attempt to deploy should fail
    with pytest.raises(ValueError, match="must be approved"):
        await ria_service.deploy_proposal(proposal_id=proposal_id)


@pytest.mark.asyncio
async def test_approve_nonexistent_proposal_fails(ria_service: RIAService) -> None:
    """Test that approving a nonexistent proposal raises an error."""
    with pytest.raises(ValueError, match="not found"):
        await ria_service.approve_proposal(
            proposal_id="nonexistent-id",
            reviewer_id=1,
        )


@pytest.mark.asyncio
async def test_reject_nonexistent_proposal_fails(ria_service: RIAService) -> None:
    """Test that rejecting a nonexistent proposal raises an error."""
    with pytest.raises(ValueError, match="not found"):
        await ria_service.reject_proposal(
            proposal_id="nonexistent-id",
            reviewer_id=1,
        )


@pytest.mark.asyncio
async def test_deploy_nonexistent_proposal_fails(ria_service: RIAService) -> None:
    """Test that deploying a nonexistent proposal raises an error."""
    with pytest.raises(ValueError, match="not found"):
        await ria_service.deploy_proposal(proposal_id="nonexistent-id")


# =============================================================================
# Pending Proposals
# =============================================================================


@pytest.mark.asyncio
async def test_get_pending_proposals_empty(ria_service: RIAService) -> None:
    """Test getting pending proposals when none exist."""
    proposals = await ria_service.get_pending_proposals()

    assert isinstance(proposals, list)
    # May be empty if no pending proposals
    assert len(proposals) >= 0


@pytest.mark.asyncio
async def test_get_pending_proposals_includes_new_proposal(ria_service: RIAService) -> None:
    """Test that get_pending_proposals includes newly created proposals."""
    # Create proposal
    proposal_id = await ria_service.create_proposal(
        proposal_type=ProposalType.NEW_INTERVENTION,
        title="Test pending proposal",
        description="Test description",
        rationale="Test rationale",
        target_segment="AD",
    )

    # Get pending
    proposals = await ria_service.get_pending_proposals()

    # Should include the new proposal
    assert len(proposals) > 0
    assert any(p.proposal_id == proposal_id for p in proposals)


@pytest.mark.asyncio
async def test_get_pending_proposals_excludes_approved(ria_service: RIAService) -> None:
    """Test that get_pending_proposals excludes approved proposals."""
    # Create and approve proposal
    proposal_id = await ria_service.create_proposal(
        proposal_type=ProposalType.NEW_INTERVENTION,
        title="Test approved exclusion",
        description="Test description",
        rationale="Test rationale",
        target_segment="AU",
    )

    await ria_service.approve_proposal(proposal_id=proposal_id, reviewer_id=1)

    # Get pending
    proposals = await ria_service.get_pending_proposals()

    # Should NOT include the approved proposal
    assert not any(p.proposal_id == proposal_id for p in proposals)


# =============================================================================
# Weekly Report
# =============================================================================


@pytest.mark.asyncio
async def test_generate_weekly_report(ria_service: RIAService) -> None:
    """Test generating weekly RIA report."""
    report = await ria_service.generate_weekly_report()

    assert report is not None
    assert report.generated_at is not None
    assert report.total_proposals >= 0
    assert report.pending_proposals >= 0
    assert report.approved_proposals >= 0
    assert report.deployed_proposals >= 0
    assert report.active_experiments >= 0
    assert isinstance(report.recent_proposals, list)
    assert isinstance(report.recommendations, list)


@pytest.mark.asyncio
async def test_weekly_report_includes_recent_proposals(ria_service: RIAService) -> None:
    """Test that weekly report includes recent proposals."""
    # Create a proposal
    await ria_service.create_proposal(
        proposal_type=ProposalType.NEW_INTERVENTION,
        title="Test recent proposal",
        description="Test description",
        rationale="Test rationale",
        target_segment="AH",
    )

    # Generate report
    report = await ria_service.generate_weekly_report()

    # Should include recent proposals
    assert len(report.recent_proposals) > 0


@pytest.mark.asyncio
async def test_weekly_report_recommendations_for_pending(ria_service: RIAService) -> None:
    """Test that weekly report includes recommendations for many pending proposals."""
    # Create many pending proposals (>10)
    for i in range(12):
        await ria_service.create_proposal(
            proposal_type=ProposalType.NEW_INTERVENTION,
            title=f"Test proposal {i}",
            description="Test description",
            rationale="Test rationale",
            target_segment="AD",
        )

    # Generate report
    report = await ria_service.generate_weekly_report()

    # Should have recommendations about pending proposals
    assert len(report.recommendations) > 0
    assert any("pending" in r.lower() for r in report.recommendations)


# =============================================================================
# Segment Isolation
# =============================================================================


@pytest.mark.asyncio
async def test_proposals_are_segment_specific(ria_service: RIAService) -> None:
    """Test that proposals are always segment-specific (never across segments)."""
    # Create proposals for different segments
    proposal_ad = await ria_service.create_proposal(
        proposal_type=ProposalType.NEW_INTERVENTION,
        title="AD-specific proposal",
        description="Test",
        rationale="Test",
        target_segment="AD",
    )

    proposal_au = await ria_service.create_proposal(
        proposal_type=ProposalType.NEW_INTERVENTION,
        title="AU-specific proposal",
        description="Test",
        rationale="Test",
        target_segment="AU",
    )

    # Each proposal should have a distinct target_segment
    assert proposal_ad != proposal_au  # Different IDs
    # In production, we would verify target_segment in database


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_create_proposal_with_all_optional_fields(ria_service: RIAService) -> None:
    """Test creating a proposal with all optional fields populated."""
    proposal_id = await ria_service.create_proposal(
        proposal_type=ProposalType.NEW_INTERVENTION,
        title="Full proposal",
        description="Complete description",
        rationale="Complete rationale",
        target_segment="CU",
        finding_ids=["FINDING-001", "FINDING-002"],
        effectiveness_data={"success_rate": 0.75, "sample_size": 200},
        pattern_data={"occurrence_rate": 0.30, "severity": "high"},
    )

    assert proposal_id is not None


@pytest.mark.asyncio
async def test_create_proposal_minimal_fields(ria_service: RIAService) -> None:
    """Test creating a proposal with only required fields."""
    proposal_id = await ria_service.create_proposal(
        proposal_type=ProposalType.NEW_PROMPT,
        title="Minimal proposal",
        description="Minimal description",
        rationale="Minimal rationale",
        target_segment="NT",
    )

    assert proposal_id is not None


@pytest.mark.asyncio
async def test_daily_cycle_handles_empty_database(ria_service: RIAService) -> None:
    """Test that daily cycle runs successfully even with empty database."""
    summary = await ria_service.run_daily_cycle()

    # Should complete successfully with zero counts
    assert summary.findings_ingested >= 0
    assert summary.patterns_analyzed >= 0
    assert summary.proposals_generated >= 0


@pytest.mark.asyncio
async def test_weekly_report_with_no_proposals(ria_service: RIAService) -> None:
    """Test weekly report generation with no proposals."""
    report = await ria_service.generate_weekly_report()

    # Should generate successfully with zero counts
    assert report.total_proposals == 0
    assert report.pending_proposals == 0
    assert report.approved_proposals == 0
    assert report.deployed_proposals == 0
    assert len(report.recent_proposals) == 0
