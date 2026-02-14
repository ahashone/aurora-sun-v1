"""
Tests for DSPy Optimizer Service (src/services/dspy_optimizer.py).

Tests:
- Coaching trace collection
- Optimization run creation
- A/B test creation and tracking
- Per-segment optimization (never mix segments)
- Rate limiting and thresholds
"""

from datetime import UTC, datetime

import pytest

from src.services.dspy_optimizer import (
    CoachingTrace,
    DSPyOptimizerService,
    OptimizationAlgorithm,
    OptimizationTarget,
)


class TestDSPyOptimizerService:
    """Tests for DSPyOptimizerService."""

    def test_add_coaching_trace(self) -> None:
        """Test adding a coaching trace."""
        service = DSPyOptimizerService()
        trace = CoachingTrace(
            trace_id="trace_1",
            user_id=1,
            segment="AD",
            timestamp=datetime.now(UTC),
            input_context={"energy": 3, "tasks": 5},
            user_message="I'm feeling stuck",
            intervention_type="proactive_check_in",
            intervention_content="How can I help you get unstuck?",
            readiness_score_before=0.4,
            readiness_score_after=0.6,
            user_responded=True,
            user_sentiment="positive",
            task_completed_within_1h=True,
            effectiveness_score=0.8,
            model_version="v1.0",
        )

        service.add_coaching_trace(trace)
        assert service.get_trace_count("AD") == 1
        assert service.get_trace_count("AU") == 0

    def test_add_multiple_traces_per_segment(self) -> None:
        """Test adding multiple traces for different segments."""
        service = DSPyOptimizerService()

        # Add AD traces
        for i in range(5):
            trace = CoachingTrace(
                trace_id=f"ad_trace_{i}",
                user_id=i,
                segment="AD",
                timestamp=datetime.now(UTC),
                input_context={},
                user_message=None,
                intervention_type="test",
                intervention_content="test",
                readiness_score_before=0.5,
                readiness_score_after=0.6,
                user_responded=True,
                user_sentiment="neutral",
                task_completed_within_1h=False,
                effectiveness_score=0.5,
                model_version="v1.0",
            )
            service.add_coaching_trace(trace)

        # Add AU traces
        for i in range(3):
            trace = CoachingTrace(
                trace_id=f"au_trace_{i}",
                user_id=i,
                segment="AU",
                timestamp=datetime.now(UTC),
                input_context={},
                user_message=None,
                intervention_type="test",
                intervention_content="test",
                readiness_score_before=0.5,
                readiness_score_after=0.6,
                user_responded=True,
                user_sentiment="neutral",
                task_completed_within_1h=False,
                effectiveness_score=0.5,
                model_version="v1.0",
            )
            service.add_coaching_trace(trace)

        assert service.get_trace_count("AD") == 5
        assert service.get_trace_count("AU") == 3
        assert service.get_trace_count("AH") == 0

    def test_can_optimize_insufficient_traces(self) -> None:
        """Test that optimization requires minimum traces."""
        service = DSPyOptimizerService()

        # Add only 50 traces (need 200)
        for i in range(50):
            trace = CoachingTrace(
                trace_id=f"trace_{i}",
                user_id=i,
                segment="AD",
                timestamp=datetime.now(UTC),
                input_context={},
                user_message=None,
                intervention_type="test",
                intervention_content="test",
                readiness_score_before=0.5,
                readiness_score_after=0.6,
                user_responded=True,
                user_sentiment="neutral",
                task_completed_within_1h=False,
                effectiveness_score=0.5,
                model_version="v1.0",
            )
            service.add_coaching_trace(trace)

        assert service.can_optimize("AD", min_traces=200) is False
        assert service.can_optimize("AD", min_traces=50) is True
        assert service.can_optimize("AD", min_traces=25) is True

    def test_run_optimization_insufficient_traces(self) -> None:
        """Test that running optimization fails with insufficient traces."""
        service = DSPyOptimizerService()

        # Only 10 traces
        for i in range(10):
            trace = CoachingTrace(
                trace_id=f"trace_{i}",
                user_id=i,
                segment="AD",
                timestamp=datetime.now(UTC),
                input_context={},
                user_message=None,
                intervention_type="test",
                intervention_content="test",
                readiness_score_before=0.5,
                readiness_score_after=0.6,
                user_responded=True,
                user_sentiment="neutral",
                task_completed_within_1h=False,
                effectiveness_score=0.5,
                model_version="v1.0",
            )
            service.add_coaching_trace(trace)

        with pytest.raises(ValueError, match="Not enough traces"):
            service.run_optimization("AD", OptimizationTarget.READINESS_ACCURACY)

    def test_run_optimization_success(self) -> None:
        """Test successful optimization run."""
        service = DSPyOptimizerService()

        # Add 250 traces (more than minimum)
        for i in range(250):
            trace = CoachingTrace(
                trace_id=f"trace_{i}",
                user_id=i,
                segment="AD",
                timestamp=datetime.now(UTC),
                input_context={},
                user_message=None,
                intervention_type="test",
                intervention_content="test",
                readiness_score_before=0.5,
                readiness_score_after=0.6,
                user_responded=True,
                user_sentiment="neutral",
                task_completed_within_1h=False,
                effectiveness_score=0.5,
                model_version="v1.0",
            )
            service.add_coaching_trace(trace)

        run = service.run_optimization(
            "AD",
            OptimizationTarget.READINESS_ACCURACY,
            OptimizationAlgorithm.MIPRO_V2,
        )

        assert run.segment == "AD"
        assert run.target == OptimizationTarget.READINESS_ACCURACY
        assert run.algorithm == OptimizationAlgorithm.MIPRO_V2
        assert run.num_traces == 250
        assert run.baseline_metric is not None
        assert run.optimized_metric is not None
        assert run.improvement_pct is not None
        assert run.completed_at is not None
        assert run.deployed is False

    def test_deploy_optimization(self) -> None:
        """Test deploying an optimization."""
        service = DSPyOptimizerService()

        # Add traces and run optimization
        for i in range(250):
            trace = CoachingTrace(
                trace_id=f"trace_{i}",
                user_id=i,
                segment="AD",
                timestamp=datetime.now(UTC),
                input_context={},
                user_message=None,
                intervention_type="test",
                intervention_content="test",
                readiness_score_before=0.5,
                readiness_score_after=0.6,
                user_responded=True,
                user_sentiment="neutral",
                task_completed_within_1h=False,
                effectiveness_score=0.5,
                model_version="v1.0",
            )
            service.add_coaching_trace(trace)

        run = service.run_optimization("AD", OptimizationTarget.READINESS_ACCURACY)
        assert run.deployed is False

        # Deploy
        success = service.deploy_optimization(run.run_id)
        assert success is True
        assert run.deployed is True
        assert run.deployed_at is not None

    def test_deploy_nonexistent_optimization(self) -> None:
        """Test deploying a non-existent optimization."""
        service = DSPyOptimizerService()
        success = service.deploy_optimization("nonexistent_run_id")
        assert success is False

    def test_create_ab_test(self) -> None:
        """Test creating an A/B test."""
        service = DSPyOptimizerService()

        # Add traces and run optimization
        for i in range(250):
            trace = CoachingTrace(
                trace_id=f"trace_{i}",
                user_id=i,
                segment="AD",
                timestamp=datetime.now(UTC),
                input_context={},
                user_message=None,
                intervention_type="test",
                intervention_content="test",
                readiness_score_before=0.5,
                readiness_score_after=0.6,
                user_responded=True,
                user_sentiment="neutral",
                task_completed_within_1h=False,
                effectiveness_score=0.5,
                model_version="v1.0",
            )
            service.add_coaching_trace(trace)

        run = service.run_optimization("AD", OptimizationTarget.READINESS_ACCURACY)
        test_id = service.create_ab_test("AD", run.run_id)

        assert test_id is not None
        assert "ab_" in test_id
        assert "AD" in test_id

    def test_record_ab_impression(self) -> None:
        """Test recording A/B test impressions."""
        service = DSPyOptimizerService()

        # Setup optimization and A/B test
        for i in range(250):
            trace = CoachingTrace(
                trace_id=f"trace_{i}",
                user_id=i,
                segment="AD",
                timestamp=datetime.now(UTC),
                input_context={},
                user_message=None,
                intervention_type="test",
                intervention_content="test",
                readiness_score_before=0.5,
                readiness_score_after=0.6,
                user_responded=True,
                user_sentiment="neutral",
                task_completed_within_1h=False,
                effectiveness_score=0.5,
                model_version="v1.0",
            )
            service.add_coaching_trace(trace)

        run = service.run_optimization("AD", OptimizationTarget.READINESS_ACCURACY)
        test_id = service.create_ab_test("AD", run.run_id)

        # Get variant IDs
        results = service.get_ab_test_results(test_id)
        assert results is not None

        baseline_variant_id = f"{test_id}_baseline"
        optimized_variant_id = f"{test_id}_optimized"

        # Record impressions for baseline
        service.record_ab_impression(
            test_id, baseline_variant_id,
            user_responded=True, task_completed=True, effectiveness=0.7
        )
        service.record_ab_impression(
            test_id, baseline_variant_id,
            user_responded=False, task_completed=False, effectiveness=0.3
        )

        # Record impressions for optimized
        service.record_ab_impression(
            test_id, optimized_variant_id,
            user_responded=True, task_completed=True, effectiveness=0.9
        )

        results = service.get_ab_test_results(test_id)
        assert results is not None
        assert results["baseline"]["impressions"] == 2
        assert results["optimized"]["impressions"] == 1

    def test_get_ab_test_results(self) -> None:
        """Test getting A/B test results."""
        service = DSPyOptimizerService()

        # Setup
        for i in range(250):
            trace = CoachingTrace(
                trace_id=f"trace_{i}",
                user_id=i,
                segment="AD",
                timestamp=datetime.now(UTC),
                input_context={},
                user_message=None,
                intervention_type="test",
                intervention_content="test",
                readiness_score_before=0.5,
                readiness_score_after=0.6,
                user_responded=True,
                user_sentiment="neutral",
                task_completed_within_1h=False,
                effectiveness_score=0.5,
                model_version="v1.0",
            )
            service.add_coaching_trace(trace)

        run = service.run_optimization("AD", OptimizationTarget.READINESS_ACCURACY)
        test_id = service.create_ab_test("AD", run.run_id)

        results = service.get_ab_test_results(test_id)
        assert results is not None
        assert "baseline" in results
        assert "optimized" in results
        assert "improvement" in results
        assert results["segment"] == "AD"
