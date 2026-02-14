"""
Unit tests for the EnergyPredictor service.

Tests cover:
- Behavioral signal scoring (latency, message length, vocabulary, time-of-day, engagement)
- Weighted combination of signals
- Segment-specific assessment methods (behavioral_proxy for AU, composite for AH,
  self_report for AD/NT)
- Energy level classification from score
- Confidence calculation
- Contributing factor identification
- Recommendations per energy level
- Baseline adjustment
- Edge cases (zero energy, max energy, None signals)
- Database logging of predictions

All DB dependencies are mocked to avoid real database access.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.segment_context import SegmentContext
from src.models.neurostate import EnergyLevel
from src.services.neurostate.energy import (
    BehavioralSignals,
    EnergyPrediction,
    EnergyPredictor,
)

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Provide a mock database session."""
    db = MagicMock()
    # Mock the query chain for _get_user_baseline
    db.query.return_value.filter.return_value.scalar.return_value = None
    return db


@pytest.fixture
def predictor(mock_db):
    """Create an EnergyPredictor with a mock DB session and no segment context."""
    return EnergyPredictor(db=mock_db)


@pytest.fixture
def ad_predictor(mock_db):
    """Create an EnergyPredictor for ADHD segment."""
    ctx = SegmentContext.from_code("AD")
    return EnergyPredictor(db=mock_db, segment_context=ctx)


@pytest.fixture
def au_predictor(mock_db):
    """Create an EnergyPredictor for Autism segment."""
    ctx = SegmentContext.from_code("AU")
    return EnergyPredictor(db=mock_db, segment_context=ctx)


@pytest.fixture
def ah_predictor(mock_db):
    """Create an EnergyPredictor for AuDHD segment."""
    ctx = SegmentContext.from_code("AH")
    return EnergyPredictor(db=mock_db, segment_context=ctx)


@pytest.fixture
def nt_predictor(mock_db):
    """Create an EnergyPredictor for Neurotypical segment."""
    ctx = SegmentContext.from_code("NT")
    return EnergyPredictor(db=mock_db, segment_context=ctx)


@pytest.fixture
def high_energy_signals():
    """Behavioral signals indicating high energy."""
    return BehavioralSignals(
        response_latency_ms=500,
        message_length=400,
        vocabulary_complexity=0.7,
        time_of_day_hour=8,
        day_of_week=1,
        recent_message_count=12,
        avg_message_length=200.0,
        punctuation_usage=0.6,
        question_count=3,
        exclamation_count=3,
    )


@pytest.fixture
def low_energy_signals():
    """Behavioral signals indicating low energy."""
    return BehavioralSignals(
        response_latency_ms=15000,
        message_length=5,
        vocabulary_complexity=0.1,
        time_of_day_hour=2,
        day_of_week=0,
        recent_message_count=1,
        avg_message_length=10.0,
        punctuation_usage=0.1,
        question_count=0,
        exclamation_count=0,
    )


@pytest.fixture
def baseline_signals():
    """Behavioral signals indicating baseline energy."""
    return BehavioralSignals(
        response_latency_ms=2000,
        message_length=80,
        vocabulary_complexity=0.4,
        time_of_day_hour=12,
        day_of_week=2,
        recent_message_count=6,
        avg_message_length=80.0,
        punctuation_usage=0.3,
        question_count=1,
        exclamation_count=1,
    )


# =============================================================================
# TestScoreLatency
# =============================================================================

class TestScoreLatency:
    """Test the _score_latency() method."""

    def test_none_latency_returns_baseline(self, predictor):
        """None latency returns baseline score (50.0)."""
        assert predictor._score_latency(None) == 50.0

    def test_very_fast_response(self, predictor):
        """Response under 1000ms returns high score."""
        assert predictor._score_latency(500) == 75.0

    def test_normal_response(self, predictor):
        """Response 1000-3000ms returns moderate score."""
        assert predictor._score_latency(2000) == 60.0

    def test_slow_response(self, predictor):
        """Response 3000-10000ms returns lower score."""
        assert predictor._score_latency(5000) == 45.0

    def test_very_slow_response(self, predictor):
        """Response over 10000ms returns low score."""
        assert predictor._score_latency(15000) == 30.0

    def test_boundary_1000ms(self, predictor):
        """Exactly 1000ms falls into the normal bracket."""
        assert predictor._score_latency(1000) == 60.0

    def test_boundary_3000ms(self, predictor):
        """Exactly 3000ms falls into the slower bracket."""
        assert predictor._score_latency(3000) == 45.0

    def test_boundary_10000ms(self, predictor):
        """Exactly 10000ms falls into the very slow bracket."""
        assert predictor._score_latency(10000) == 30.0

    def test_zero_latency(self, predictor):
        """Zero latency returns the fast response score."""
        assert predictor._score_latency(0) == 75.0


# =============================================================================
# TestScoreMessageLength
# =============================================================================

class TestScoreMessageLength:
    """Test the _score_message_length() method."""

    def test_very_short_message(self, predictor):
        """Message under LENGTH_CRITICAL (10) returns very low score."""
        assert predictor._score_message_length(5) == 20.0

    def test_short_message(self, predictor):
        """Message 10-30 returns low score."""
        assert predictor._score_message_length(20) == 40.0

    def test_normal_message(self, predictor):
        """Message 30-100 returns baseline score."""
        assert predictor._score_message_length(80) == 55.0

    def test_long_message(self, predictor):
        """Message 100-300 returns elevated score."""
        assert predictor._score_message_length(200) == 70.0

    def test_very_long_message(self, predictor):
        """Message over 300 returns high engagement score."""
        assert predictor._score_message_length(500) == 85.0

    def test_zero_length(self, predictor):
        """Zero-length message returns the very short score."""
        assert predictor._score_message_length(0) == 20.0


# =============================================================================
# TestScoreVocabulary
# =============================================================================

class TestScoreVocabulary:
    """Test the _score_vocabulary() method."""

    def test_low_complexity(self, predictor):
        """Complexity under 0.2 returns low energy score."""
        assert predictor._score_vocabulary(0.1) == 35.0

    def test_moderate_low_complexity(self, predictor):
        """Complexity 0.2-0.4 returns moderate score."""
        assert predictor._score_vocabulary(0.3) == 50.0

    def test_moderate_high_complexity(self, predictor):
        """Complexity 0.4-0.6 returns elevated score."""
        assert predictor._score_vocabulary(0.5) == 60.0

    def test_high_complexity(self, predictor):
        """Complexity above 0.6 returns high score."""
        assert predictor._score_vocabulary(0.8) == 75.0

    def test_zero_complexity(self, predictor):
        """Zero complexity returns low score."""
        assert predictor._score_vocabulary(0.0) == 35.0


# =============================================================================
# TestScoreTimeOfDay
# =============================================================================

class TestScoreTimeOfDay:
    """Test the _score_time_of_day() method."""

    def test_morning_high_energy(self, predictor):
        """Morning (6-10) returns higher score."""
        assert predictor._score_time_of_day(8, 1) == 65.0

    def test_midday_baseline(self, predictor):
        """Midday (10-14) returns baseline score."""
        assert predictor._score_time_of_day(12, 1) == 60.0

    def test_afternoon_dip(self, predictor):
        """Afternoon (14-18) returns lower score."""
        assert predictor._score_time_of_day(15, 1) == 50.0

    def test_evening_moderate(self, predictor):
        """Evening (18-22) returns moderate score."""
        assert predictor._score_time_of_day(20, 1) == 55.0

    def test_night_low_energy(self, predictor):
        """Night (22-6) returns low score."""
        assert predictor._score_time_of_day(3, 1) == 40.0

    def test_boundary_6am(self, predictor):
        """Exactly 6:00 falls into morning bracket."""
        assert predictor._score_time_of_day(6, 1) == 65.0

    def test_boundary_22pm(self, predictor):
        """Exactly 22:00 falls into night bracket."""
        assert predictor._score_time_of_day(22, 1) == 40.0

    def test_midnight(self, predictor):
        """Midnight (0) falls into night bracket."""
        assert predictor._score_time_of_day(0, 1) == 40.0


# =============================================================================
# TestScoreEngagement
# =============================================================================

class TestScoreEngagement:
    """Test the _score_engagement() method."""

    def test_baseline_engagement(self, predictor):
        """Default signals return baseline score."""
        signals = BehavioralSignals()
        assert predictor._score_engagement(signals) == 50.0

    def test_many_questions_boost(self, predictor):
        """More than 2 questions adds 15 points."""
        signals = BehavioralSignals(question_count=3)
        assert predictor._score_engagement(signals) == 65.0

    def test_some_questions_boost(self, predictor):
        """1-2 questions adds 8 points."""
        signals = BehavioralSignals(question_count=1)
        assert predictor._score_engagement(signals) == 58.0

    def test_many_exclamations_boost(self, predictor):
        """More than 2 exclamations adds 15 points."""
        signals = BehavioralSignals(exclamation_count=4)
        assert predictor._score_engagement(signals) == 65.0

    def test_some_exclamations_boost(self, predictor):
        """1-2 exclamations adds 8 points."""
        signals = BehavioralSignals(exclamation_count=2)
        assert predictor._score_engagement(signals) == 58.0

    def test_high_punctuation_boost(self, predictor):
        """Punctuation usage above 0.5 adds 10 points."""
        signals = BehavioralSignals(punctuation_usage=0.6)
        assert predictor._score_engagement(signals) == 60.0

    def test_high_message_count_boost(self, predictor):
        """More than 10 recent messages adds 10 points."""
        signals = BehavioralSignals(recent_message_count=12)
        assert predictor._score_engagement(signals) == 60.0

    def test_moderate_message_count_boost(self, predictor):
        """6-10 recent messages adds 5 points."""
        signals = BehavioralSignals(recent_message_count=7)
        assert predictor._score_engagement(signals) == 55.0

    def test_combined_engagement_capped_at_100(self, predictor):
        """Engagement score is capped at 100."""
        signals = BehavioralSignals(
            question_count=5,
            exclamation_count=5,
            punctuation_usage=0.9,
            recent_message_count=15,
        )
        score = predictor._score_engagement(signals)
        assert score == 100.0


# =============================================================================
# TestScoreToLevel
# =============================================================================

class TestScoreToLevel:
    """Test the _score_to_level() method."""

    def test_critical_level(self, predictor):
        """Score below 15 returns CRITICAL."""
        assert predictor._score_to_level(10.0) == EnergyLevel.CRITICAL

    def test_low_level(self, predictor):
        """Score 15-35 returns LOW."""
        assert predictor._score_to_level(25.0) == EnergyLevel.LOW

    def test_baseline_level(self, predictor):
        """Score 35-50 returns BASELINE."""
        assert predictor._score_to_level(45.0) == EnergyLevel.BASELINE

    def test_elevated_level(self, predictor):
        """Score 50-70 returns ELEVATED."""
        assert predictor._score_to_level(60.0) == EnergyLevel.ELEVATED

    def test_hyperfocus_level(self, predictor):
        """Score above 70 returns HYPERFOCUS."""
        assert predictor._score_to_level(80.0) == EnergyLevel.HYPERFOCUS

    def test_boundary_critical_low(self, predictor):
        """Exactly 15.0 falls into LOW."""
        assert predictor._score_to_level(15.0) == EnergyLevel.LOW

    def test_boundary_low_baseline(self, predictor):
        """Exactly 35.0 falls into BASELINE."""
        assert predictor._score_to_level(35.0) == EnergyLevel.BASELINE

    def test_boundary_baseline_elevated(self, predictor):
        """Exactly 50.0 falls into ELEVATED."""
        assert predictor._score_to_level(50.0) == EnergyLevel.ELEVATED

    def test_boundary_elevated_hyperfocus(self, predictor):
        """Exactly 70.0 falls into HYPERFOCUS."""
        assert predictor._score_to_level(70.0) == EnergyLevel.HYPERFOCUS

    def test_zero_score(self, predictor):
        """Score of 0 returns CRITICAL."""
        assert predictor._score_to_level(0.0) == EnergyLevel.CRITICAL

    def test_max_score(self, predictor):
        """Score of 100 returns HYPERFOCUS."""
        assert predictor._score_to_level(100.0) == EnergyLevel.HYPERFOCUS


# =============================================================================
# TestAdjustForBaseline
# =============================================================================

class TestAdjustForBaseline:
    """Test the _adjust_for_baseline() method."""

    def test_blending_formula(self, predictor):
        """Score blends 70% raw + 30% baseline."""
        result = predictor._adjust_for_baseline(80.0, 50.0)
        expected = 80.0 * 0.7 + 50.0 * 0.3
        assert result == pytest.approx(expected)

    def test_baseline_equal_to_score(self, predictor):
        """When baseline equals score, result equals score."""
        result = predictor._adjust_for_baseline(60.0, 60.0)
        assert result == pytest.approx(60.0)

    def test_high_baseline_pulls_up(self, predictor):
        """High baseline pulls low score upward."""
        result = predictor._adjust_for_baseline(30.0, 70.0)
        assert result > 30.0

    def test_low_baseline_pulls_down(self, predictor):
        """Low baseline pulls high score downward."""
        result = predictor._adjust_for_baseline(90.0, 30.0)
        assert result < 90.0


# =============================================================================
# TestCalculateConfidence
# =============================================================================

class TestCalculateConfidence:
    """Test the _calculate_confidence() method."""

    def test_all_signals_present(self, predictor):
        """All 4 signals present gives high confidence."""
        signals = BehavioralSignals(
            response_latency_ms=1000,
            message_length=50,
            vocabulary_complexity=0.5,
            recent_message_count=5,
        )
        confidence = predictor._calculate_confidence(signals, 50.0)
        assert confidence == 1.0  # 4/4 + 0.2 = 1.2, capped at 1.0

    def test_no_signals_present(self, predictor):
        """No signals present gives low confidence."""
        signals = BehavioralSignals()
        confidence = predictor._calculate_confidence(signals, 0.0)
        assert confidence == 0.0

    def test_partial_signals(self, predictor):
        """Some signals present gives proportional confidence."""
        signals = BehavioralSignals(
            response_latency_ms=1000,
            message_length=50,
        )
        confidence = predictor._calculate_confidence(signals, 0.0)
        assert confidence == pytest.approx(0.5)  # 2/4

    def test_baseline_adds_confidence(self, predictor):
        """Non-zero baseline adds 0.2 to confidence."""
        signals = BehavioralSignals(
            response_latency_ms=1000,
            message_length=50,
        )
        confidence = predictor._calculate_confidence(signals, 50.0)
        assert confidence == pytest.approx(0.7)  # 2/4 + 0.2

    def test_confidence_capped_at_one(self, predictor):
        """Confidence never exceeds 1.0."""
        signals = BehavioralSignals(
            response_latency_ms=1000,
            message_length=50,
            vocabulary_complexity=0.5,
            recent_message_count=5,
        )
        confidence = predictor._calculate_confidence(signals, 50.0)
        assert confidence == 1.0


# =============================================================================
# TestGetRecommendations
# =============================================================================

class TestGetRecommendations:
    """Test the _get_recommendations() method."""

    def test_critical_recommendations(self, predictor):
        """Critical energy returns rest-focused recommendations."""
        recs = predictor._get_recommendations(EnergyLevel.CRITICAL, 5.0)
        assert any("rest" in r.lower() for r in recs)

    def test_low_recommendations(self, predictor):
        """Low energy returns essential-tasks recommendations."""
        recs = predictor._get_recommendations(EnergyLevel.LOW, 25.0)
        assert any("essential" in r.lower() for r in recs)

    def test_baseline_recommendations(self, predictor):
        """Baseline energy returns sustainable pace recommendations."""
        recs = predictor._get_recommendations(EnergyLevel.BASELINE, 45.0)
        assert any("normal" in r.lower() or "sustainable" in r.lower() for r in recs)

    def test_elevated_recommendations(self, predictor):
        """Elevated energy returns demanding task recommendations."""
        recs = predictor._get_recommendations(EnergyLevel.ELEVATED, 65.0)
        assert any("demanding" in r.lower() or "challenging" in r.lower() for r in recs)

    def test_hyperfocus_recommendations(self, predictor):
        """Hyperfocus energy returns channeling recommendations."""
        recs = predictor._get_recommendations(EnergyLevel.HYPERFOCUS, 90.0)
        assert any("hyperfocus" in r.lower() for r in recs)

    def test_all_levels_return_nonempty(self, predictor):
        """All energy levels return at least one recommendation."""
        for level in EnergyLevel:
            recs = predictor._get_recommendations(level, 50.0)
            assert len(recs) > 0


# =============================================================================
# TestGetContributingFactors
# =============================================================================

class TestGetContributingFactors:
    """Test the _get_contributing_factors() method."""

    def test_quick_responses_detected(self, predictor):
        """Fast response latency noted as contributing factor."""
        signals = BehavioralSignals(response_latency_ms=500)
        factors = predictor._get_contributing_factors(signals, 75, 50, 50, 50, 50)
        assert "Quick responses" in factors

    def test_slow_responses_detected(self, predictor):
        """Very slow response latency noted as contributing factor."""
        signals = BehavioralSignals(response_latency_ms=15000)
        factors = predictor._get_contributing_factors(signals, 30, 50, 50, 50, 50)
        assert "Slow responses" in factors

    def test_brief_messages_detected(self, predictor):
        """Short messages noted as contributing factor."""
        signals = BehavioralSignals(message_length=5)
        factors = predictor._get_contributing_factors(signals, 50, 20, 50, 50, 50)
        assert "Brief messages" in factors

    def test_detailed_messages_detected(self, predictor):
        """Very long messages noted as contributing factor."""
        signals = BehavioralSignals(message_length=400)
        factors = predictor._get_contributing_factors(signals, 50, 85, 50, 50, 50)
        assert "Detailed messages" in factors

    def test_morning_time_detected(self, predictor):
        """Morning time noted as contributing factor."""
        signals = BehavioralSignals(time_of_day_hour=7)
        factors = predictor._get_contributing_factors(signals, 50, 50, 50, 65, 50)
        assert "Morning time" in factors

    def test_night_time_detected(self, predictor):
        """Night time noted as contributing factor."""
        signals = BehavioralSignals(time_of_day_hour=23)
        factors = predictor._get_contributing_factors(signals, 50, 50, 50, 40, 50)
        assert "Evening/night time" in factors


# =============================================================================
# TestPredict -- async predict() method
# =============================================================================

class TestPredict:
    """Test the main predict() async method."""

    @pytest.mark.asyncio
    async def test_predict_returns_energy_prediction(self, predictor, baseline_signals):
        """predict() returns an EnergyPrediction dataclass."""
        result = await predictor.predict(user_id=1, behavioral_signals=baseline_signals)

        assert isinstance(result, EnergyPrediction)
        assert isinstance(result.energy_level, EnergyLevel)
        assert 0.0 <= result.energy_score <= 100.0
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.signals_used, dict)
        assert isinstance(result.contributing_factors, list)
        assert isinstance(result.recommendations, list)

    @pytest.mark.asyncio
    async def test_predict_high_energy_signals(self, predictor, high_energy_signals):
        """High energy signals produce elevated or hyperfocus level."""
        result = await predictor.predict(user_id=1, behavioral_signals=high_energy_signals)

        assert result.energy_level in (EnergyLevel.ELEVATED, EnergyLevel.HYPERFOCUS)
        assert result.energy_score > 50.0

    @pytest.mark.asyncio
    async def test_predict_low_energy_signals(self, predictor, low_energy_signals):
        """Low energy signals produce lower energy score (below elevated)."""
        result = await predictor.predict(user_id=1, behavioral_signals=low_energy_signals)

        # With baseline blending (30% of 50.0 baseline), raw low scores get pulled up
        # so the final score lands around 35-40 (BASELINE level)
        assert result.energy_level in (EnergyLevel.CRITICAL, EnergyLevel.LOW, EnergyLevel.BASELINE)
        assert result.energy_score < 50.0

    @pytest.mark.asyncio
    async def test_predict_logs_to_database(self, predictor, mock_db, baseline_signals):
        """predict() logs the prediction to the database."""
        await predictor.predict(user_id=1, behavioral_signals=baseline_signals)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_predict_score_clamped_0_100(self, predictor, low_energy_signals):
        """Energy score is clamped between 0 and 100."""
        result = await predictor.predict(user_id=1, behavioral_signals=low_energy_signals)
        assert 0.0 <= result.energy_score <= 100.0

    @pytest.mark.asyncio
    async def test_predict_signals_used_keys(self, predictor, baseline_signals):
        """signals_used contains all 5 signal keys."""
        result = await predictor.predict(user_id=1, behavioral_signals=baseline_signals)

        expected_keys = {"latency", "length", "vocab", "time", "engagement"}
        assert set(result.signals_used.keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_predict_without_signals_uses_history(self, predictor):
        """predict() without signals calls _get_signals_from_history."""
        with patch.object(
            predictor, "_get_signals_from_history",
            new_callable=AsyncMock,
            return_value=BehavioralSignals(time_of_day_hour=12, day_of_week=2),
        ) as mock_hist:
            await predictor.predict(user_id=1)
            mock_hist.assert_called_once_with(1)


# =============================================================================
# TestSegmentSpecificAssessment
# =============================================================================

class TestSegmentSpecificAssessment:
    """Test segment-specific energy assessment methods."""

    @pytest.mark.asyncio
    async def test_au_uses_behavioral_proxy_only(self, au_predictor, baseline_signals):
        """AU segment uses behavioral proxy only (interoception unreliable)."""
        result = await au_predictor.predict(
            user_id=1,
            behavioral_signals=baseline_signals,
            self_report_score=90.0,  # Should be IGNORED for AU
        )

        assert "behavioral_proxy" in result.contributing_factors[-1].lower() or \
               "behavioral proxy" in result.contributing_factors[-1].lower()

    @pytest.mark.asyncio
    async def test_au_ignores_self_report(self, au_predictor, baseline_signals):
        """AU segment ignores self-report even when provided."""
        result_with_report = await au_predictor.predict(
            user_id=1, behavioral_signals=baseline_signals, self_report_score=100.0,
        )
        result_without_report = await au_predictor.predict(
            user_id=2, behavioral_signals=baseline_signals,
        )

        # Both should produce the same energy score because AU ignores self-report
        assert result_with_report.energy_score == pytest.approx(
            result_without_report.energy_score, abs=0.1
        )

    @pytest.mark.asyncio
    async def test_ah_uses_composite(self, ah_predictor, baseline_signals):
        """AH segment uses composite: 85% behavioral + 15% self-report."""
        result = await ah_predictor.predict(
            user_id=1,
            behavioral_signals=baseline_signals,
            self_report_score=80.0,
        )

        assert "composite" in result.contributing_factors[-1].lower() or \
               "Composite" in result.contributing_factors[-1]

    @pytest.mark.asyncio
    async def test_ah_composite_weights(self, ah_predictor, baseline_signals):
        """AH composite weighs behavioral at 85% and self-report at 15%."""
        # With very different self-report, the score should shift slightly
        result_high_report = await ah_predictor.predict(
            user_id=1, behavioral_signals=baseline_signals, self_report_score=100.0,
        )
        result_low_report = await ah_predictor.predict(
            user_id=2, behavioral_signals=baseline_signals, self_report_score=0.0,
        )

        # The difference should be 15% of 100 = 15 points maximum
        score_diff = abs(result_high_report.energy_score - result_low_report.energy_score)
        # After baseline adjustment (0.7 factor), the effect is reduced
        assert score_diff > 0  # Some difference expected
        assert score_diff < 20  # But not huge since behavioral dominates

    @pytest.mark.asyncio
    async def test_ad_uses_self_report_primary(self, ad_predictor, baseline_signals):
        """AD segment uses self-report as primary (60% self-report, 40% behavioral)."""
        result = await ad_predictor.predict(
            user_id=1,
            behavioral_signals=baseline_signals,
            self_report_score=80.0,
        )

        assert "self-report" in result.contributing_factors[-1].lower() or \
               "Self-report" in result.contributing_factors[-1]

    @pytest.mark.asyncio
    async def test_nt_uses_self_report_primary(self, nt_predictor, baseline_signals):
        """NT segment uses self-report as primary."""
        result = await nt_predictor.predict(
            user_id=1,
            behavioral_signals=baseline_signals,
            self_report_score=80.0,
        )

        assert "self-report" in result.contributing_factors[-1].lower() or \
               "Self-report" in result.contributing_factors[-1]

    @pytest.mark.asyncio
    async def test_no_segment_falls_back_to_behavioral(self, predictor, baseline_signals):
        """Without segment context, falls back to behavioral proxy only."""
        result = await predictor.predict(
            user_id=1,
            behavioral_signals=baseline_signals,
            self_report_score=80.0,
        )

        assert "no segment context" in result.contributing_factors[-1].lower()

    @pytest.mark.asyncio
    async def test_ad_without_self_report_falls_back(self, ad_predictor, baseline_signals):
        """AD segment without self-report falls back to behavioral only."""
        result = await ad_predictor.predict(
            user_id=1,
            behavioral_signals=baseline_signals,
            # No self-report provided
        )

        assert "no self-report" in result.contributing_factors[-1].lower()


# =============================================================================
# TestEnergyLevelThresholds
# =============================================================================

class TestEnergyLevelThresholds:
    """Test that energy level thresholds are correctly configured."""

    def test_critical_threshold(self, predictor):
        """ENERGY_CRITICAL is 15.0."""
        assert predictor.ENERGY_CRITICAL == 15.0

    def test_low_threshold(self, predictor):
        """ENERGY_LOW is 35.0."""
        assert predictor.ENERGY_LOW == 35.0

    def test_baseline_threshold(self, predictor):
        """ENERGY_BASELINE is 50.0."""
        assert predictor.ENERGY_BASELINE == 50.0

    def test_elevated_threshold(self, predictor):
        """ENERGY_ELEVATED is 70.0."""
        assert predictor.ENERGY_ELEVATED == 70.0

    def test_hyperfocus_threshold(self, predictor):
        """ENERGY_HYPERFOCUS is 85.0."""
        assert predictor.ENERGY_HYPERFOCUS == 85.0


# =============================================================================
# TestSignalWeights
# =============================================================================

class TestSignalWeights:
    """Test that signal weights sum to 1.0."""

    def test_weights_sum_to_one(self, predictor):
        """All signal weights must sum to 1.0."""
        total = (
            predictor.LATENCY_WEIGHT +
            predictor.MESSAGE_LENGTH_WEIGHT +
            predictor.VOCAB_WEIGHT +
            predictor.TIME_WEIGHT +
            predictor.ENGAGEMENT_WEIGHT
        )
        assert total == pytest.approx(1.0)


# =============================================================================
# TestBehavioralSignalsDataclass
# =============================================================================

class TestBehavioralSignalsDataclass:
    """Test the BehavioralSignals dataclass."""

    def test_default_values(self):
        """BehavioralSignals defaults are sensible."""
        signals = BehavioralSignals()
        assert signals.response_latency_ms is None
        assert signals.message_length == 0
        assert signals.vocabulary_complexity == 0.0
        assert signals.time_of_day_hour == 0
        assert signals.day_of_week == 0
        assert signals.recent_message_count == 0
        assert signals.avg_message_length == 0.0
        assert signals.punctuation_usage == 0.0
        assert signals.question_count == 0
        assert signals.exclamation_count == 0

    def test_custom_values(self):
        """BehavioralSignals accepts custom values."""
        signals = BehavioralSignals(
            response_latency_ms=1500,
            message_length=100,
            vocabulary_complexity=0.5,
        )
        assert signals.response_latency_ms == 1500
        assert signals.message_length == 100
        assert signals.vocabulary_complexity == 0.5
