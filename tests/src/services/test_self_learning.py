"""
Unit tests for Self-Learning Service.

Tests verify:
- Proposal creation, approval, rejection
- Deployment and rollout flow
- Variant comparison
- Weekly report generation
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.base import Base
from src.services.self_learning import (
    Proposal,
    ProposalCreate,
    ProposalStatus,
    ProposalType,
    RolloutStage,
    SelfLearningService,
    WeeklyReport,
    WeeklyReportData,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture()
def sync_db_session():
    """Provide a synchronous SQLAlchemy session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture()
async def self_learning_service():
    """Provide a SelfLearningService with async session (mocked)."""
    # Create async-compatible session mock
    from unittest.mock import AsyncMock, MagicMock

    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.execute = AsyncMock()

    return SelfLearningService(session=mock_session)


# ============================================================================
# TestProposalCreate
# ============================================================================


class TestProposalCreate:
    """Test proposal creation."""

    @pytest.mark.asyncio
    async def test_create_proposal_returns_id(self):
        """create_proposal returns a UUID."""
        from unittest.mock import AsyncMock, MagicMock

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        service = SelfLearningService(session=mock_session)

        proposal_data = ProposalCreate(
            proposal_type=ProposalType.PROMPT_CHANGE,
            title="Improve inline coaching for ADHD",
            description="Shorten prompts to reduce cognitive load",
            rationale="ADHD users have lower working memory capacity",
            evidence="Finding-042: ADHD users drop off after 3+ sentence prompts",
            target_segment="AD",
        )

        proposal_id = await service.create_proposal(proposal_data)

        assert isinstance(proposal_id, str)
        assert len(proposal_id) == 36  # UUID length with dashes

    @pytest.mark.asyncio
    async def test_create_proposal_calls_session_add(self):
        """create_proposal adds a Proposal to session."""
        from unittest.mock import AsyncMock, MagicMock

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        service = SelfLearningService(session=mock_session)

        proposal_data = ProposalCreate(
            proposal_type=ProposalType.NEW_INTERVENTION,
            title="Add body doubling for Autism",
            description="Implement virtual body doubling for inertia",
            rationale="Autistic inertia is different from ADHD activation deficit",
        )

        await service.create_proposal(proposal_data)

        mock_session.add.assert_called_once()
        call_args = mock_session.add.call_args[0]
        assert isinstance(call_args[0], Proposal)

    @pytest.mark.asyncio
    async def test_create_proposal_sets_pending_status(self):
        """Newly created proposals start with PENDING status."""
        from unittest.mock import AsyncMock, MagicMock

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        service = SelfLearningService(session=mock_session)

        proposal_data = ProposalCreate(
            proposal_type=ProposalType.PARAMETER_TUNING,
            title="Adjust sprint duration for AuDHD",
            description="Increase sprint from 25 to 30 minutes",
            rationale="AuDHD users need longer focus blocks",
        )

        await service.create_proposal(proposal_data)

        call_args = mock_session.add.call_args[0]
        proposal = call_args[0]
        assert proposal.status == ProposalStatus.PENDING.value


# ============================================================================
# TestProposalApproval
# ============================================================================


class TestProposalApproval:
    """Test proposal approval workflow."""

    @pytest.mark.asyncio
    async def test_approve_proposal_changes_status(self):
        """approve_proposal changes status to APPROVED."""
        from unittest.mock import AsyncMock, MagicMock

        # Create a mock proposal
        mock_proposal = MagicMock()
        mock_proposal.status = ProposalStatus.PENDING.value

        # Create mock result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_proposal

        # Create mock session
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        service = SelfLearningService(session=mock_session)

        await service.approve_proposal(
            proposal_id="test-id",
            admin_notes="Looks good, deploy ASAP"
        )

        assert mock_proposal.status == ProposalStatus.APPROVED.value
        assert mock_proposal.admin_notes == "Looks good, deploy ASAP"

    @pytest.mark.asyncio
    async def test_reject_proposal_changes_status(self):
        """reject_proposal changes status to REJECTED."""
        from unittest.mock import AsyncMock, MagicMock

        # Create a mock proposal
        mock_proposal = MagicMock()
        mock_proposal.status = ProposalStatus.PENDING.value

        # Create mock result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_proposal

        # Create mock session
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        service = SelfLearningService(session=mock_session)

        await service.reject_proposal(
            proposal_id="test-id",
            admin_notes="Not enough evidence"
        )

        assert mock_proposal.status == ProposalStatus.REJECTED.value
        assert mock_proposal.admin_notes == "Not enough evidence"

    @pytest.mark.asyncio
    async def test_approve_proposal_raises_if_not_found(self):
        """approve_proposal raises ValueError if proposal not found."""
        from unittest.mock import AsyncMock, MagicMock

        # Create mock result (no proposal found)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        # Create mock session
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = SelfLearningService(session=mock_session)

        with pytest.raises(ValueError, match="Proposal not found"):
            await service.approve_proposal(proposal_id="nonexistent")


# ============================================================================
# TestRollout
# ============================================================================


class TestRollout:
    """Test staged rollout flow."""

    @pytest.mark.asyncio
    async def test_start_rollout_sets_rollout_status(self):
        """start_rollout changes status to ROLLOUT."""
        from unittest.mock import AsyncMock, MagicMock

        mock_proposal = MagicMock()
        mock_proposal.status = ProposalStatus.DEPLOYED.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_proposal

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        service = SelfLearningService(session=mock_session)

        await service.start_rollout(
            proposal_id="test-id",
            initial_stage=RolloutStage.STAGE_10
        )

        assert mock_proposal.status == ProposalStatus.ROLLOUT.value
        assert mock_proposal.rollout_stage == RolloutStage.STAGE_10.value
        assert mock_proposal.rollout_percentage == 10

    @pytest.mark.asyncio
    async def test_advance_rollout_to_50_percent(self):
        """advance_rollout moves from 10% to 50%."""
        from unittest.mock import AsyncMock, MagicMock

        mock_proposal = MagicMock()
        mock_proposal.status = ProposalStatus.ROLLOUT.value
        mock_proposal.rollout_stage = RolloutStage.STAGE_10.value
        mock_proposal.rollout_percentage = 10

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_proposal

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        service = SelfLearningService(session=mock_session)

        await service.advance_rollout(
            proposal_id="test-id",
            next_stage=RolloutStage.STAGE_50
        )

        assert mock_proposal.rollout_stage == RolloutStage.STAGE_50.value
        assert mock_proposal.rollout_percentage == 50

    @pytest.mark.asyncio
    async def test_advance_rollout_to_100_marks_completed(self):
        """advance_rollout to 100% marks proposal as COMPLETED."""
        from unittest.mock import AsyncMock, MagicMock

        mock_proposal = MagicMock()
        mock_proposal.status = ProposalStatus.ROLLOUT.value
        mock_proposal.rollout_stage = RolloutStage.STAGE_50.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_proposal

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        service = SelfLearningService(session=mock_session)

        await service.advance_rollout(
            proposal_id="test-id",
            next_stage=RolloutStage.STAGE_100
        )

        assert mock_proposal.status == ProposalStatus.COMPLETED.value
        assert mock_proposal.rollout_percentage == 100

    @pytest.mark.asyncio
    async def test_revert_proposal_sets_reverted_status(self):
        """revert_proposal changes status to REVERTED."""
        from unittest.mock import AsyncMock, MagicMock

        mock_proposal = MagicMock()
        mock_proposal.status = ProposalStatus.ROLLOUT.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_proposal

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        service = SelfLearningService(session=mock_session)

        await service.revert_proposal(
            proposal_id="test-id",
            admin_notes="Success rate dropped by 15%"
        )

        assert mock_proposal.status == ProposalStatus.REVERTED.value
        assert mock_proposal.admin_notes == "Success rate dropped by 15%"


# ============================================================================
# TestEffectiveness
# ============================================================================


class TestEffectiveness:
    """Test effectiveness tracking."""

    @pytest.mark.asyncio
    async def test_update_effectiveness_calculates_delta(self):
        """update_effectiveness calculates improvement_delta."""
        from unittest.mock import AsyncMock, MagicMock

        mock_proposal = MagicMock()
        mock_proposal.baseline_success_rate = 0.6
        mock_proposal.current_success_rate = None
        mock_proposal.improvement_delta = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_proposal

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        service = SelfLearningService(session=mock_session)

        await service.update_effectiveness(
            proposal_id="test-id",
            current_success_rate=0.75
        )

        assert mock_proposal.current_success_rate == 0.75
        assert abs(mock_proposal.improvement_delta - 0.15) < 0.0001  # 0.75 - 0.6 (floating point)

    @pytest.mark.asyncio
    async def test_create_variant_comparison_returns_id(self):
        """create_variant_comparison returns comparison_id."""
        from unittest.mock import AsyncMock, MagicMock

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        service = SelfLearningService(session=mock_session)

        comparison_id = await service.create_variant_comparison(
            proposal_id="test-proposal",
            variant_a_count=100,
            variant_a_success_rate=0.6,
            variant_b_count=100,
            variant_b_success_rate=0.75,
            is_significant=True,
            confidence=0.95,
            winner="B",
        )

        assert isinstance(comparison_id, str)
        assert len(comparison_id) == 36


# ============================================================================
# TestWeeklyReport
# ============================================================================


class TestWeeklyReport:
    """Test weekly self-doubt check report."""

    @pytest.mark.asyncio
    async def test_generate_weekly_report_returns_id(self):
        """generate_weekly_report returns report_id."""
        from unittest.mock import AsyncMock, MagicMock

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        service = SelfLearningService(session=mock_session)

        report_data = WeeklyReportData(
            q1_users_improving=True,
            q2_intervention_effectiveness=0.72,
            q3_segment_performance="AU",
            q4_new_patterns=5,
            q5_proposal_count=3,
            overall_health="good",
            key_findings=[
                "ADHD segment performing well (80% success rate)",
                "Autism segment needs attention (55% success rate)",
            ],
            action_items=[
                "Review Autism-specific interventions",
                "Consider new body doubling approach",
            ],
        )

        report_id = await service.generate_weekly_report(report_data)

        assert isinstance(report_id, str)
        assert len(report_id) == 36

    @pytest.mark.asyncio
    async def test_generate_weekly_report_stores_data(self):
        """generate_weekly_report stores all 5 questions."""
        from unittest.mock import AsyncMock, MagicMock

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        service = SelfLearningService(session=mock_session)

        report_data = WeeklyReportData(
            q1_users_improving=True,
            q2_intervention_effectiveness=0.68,
            q3_segment_performance="AH",
            q4_new_patterns=7,
            q5_proposal_count=2,
            overall_health="neutral",
        )

        await service.generate_weekly_report(report_data)

        # Verify session.add was called with WeeklyReport
        mock_session.add.assert_called_once()
        call_args = mock_session.add.call_args[0]
        report = call_args[0]

        assert isinstance(report, WeeklyReport)
        assert report.q1_users_improving is True
        assert report.q2_intervention_effectiveness == 0.68
        assert report.q3_segment_performance == "AH"
        assert report.q4_new_patterns == 7
        assert report.q5_proposal_count == 2


# ============================================================================
# TestGetters
# ============================================================================


class TestGetters:
    """Test getter methods."""

    @pytest.mark.asyncio
    async def test_get_pending_proposals_returns_list(self):
        """get_pending_proposals returns list of ProposalResponse."""
        from unittest.mock import AsyncMock, MagicMock

        # Create mock proposals
        mock_proposal1 = MagicMock()
        mock_proposal1.proposal_id = "id1"
        mock_proposal1.proposal_type = ProposalType.PROMPT_CHANGE.value
        mock_proposal1.title = "Test 1"
        mock_proposal1.description = "Desc 1"
        mock_proposal1.rationale = "Rat 1"
        mock_proposal1.status = ProposalStatus.PENDING.value
        mock_proposal1.proposed_at = datetime.now(UTC)
        mock_proposal1.target_segment = "AD"
        mock_proposal1.rollout_stage = RolloutStage.STAGE_0.value
        mock_proposal1.rollout_percentage = 0
        mock_proposal1.baseline_success_rate = None
        mock_proposal1.current_success_rate = None
        mock_proposal1.improvement_delta = None

        # Create mock result
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_proposal1]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        # Create mock session
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = SelfLearningService(session=mock_session)

        proposals = await service.get_pending_proposals()

        assert len(proposals) == 1
        assert proposals[0].proposal_id == "id1"
        assert proposals[0].status == ProposalStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_get_active_rollouts_returns_list(self):
        """get_active_rollouts returns list of active rollouts."""
        from unittest.mock import AsyncMock, MagicMock

        # Create mock scalars with no rollouts
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = SelfLearningService(session=mock_session)

        rollouts = await service.get_active_rollouts()

        assert isinstance(rollouts, list)
        assert len(rollouts) == 0
