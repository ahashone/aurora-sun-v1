"""
Unit tests for the InertiaDetector service.

Tests cover:
- detect() async method with insufficient messages, empty user messages, segment routing
- _score_autistic_inertia() keyword matching and "want" + "can" pattern
- _score_activation_deficit() keyword matching and "should" + "later/tomorrow" pattern
- _score_double_block() specific keywords and both-type indicators
- _get_recommended_intervention() type-specific and severity-based protocols

All DB dependencies are mocked to avoid real database access.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.models.neurostate import InertiaType
from src.services.neurostate.inertia import (
    InertiaDetectionResult,
    InertiaDetector,
)

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Provide a mock database session."""
    return MagicMock()


@pytest.fixture
def detector(mock_db):
    """Create an InertiaDetector with a mock DB session."""
    return InertiaDetector(db=mock_db)


# =============================================================================
# Helper
# =============================================================================

def _msg(text: str, is_user: bool = True) -> dict:
    """Create a message dict for test convenience."""
    return {"text": text, "is_user": is_user}


# =============================================================================
# TestDetect -- async detect() method
# =============================================================================

class TestDetect:
    """Test the main detect() async method."""

    @pytest.mark.asyncio
    async def test_insufficient_messages_empty(self, detector):
        """Empty message list returns is_inertia=False."""
        result = await detector.detect(user_id=1, recent_messages=[])
        assert result.is_inertia is False

    @pytest.mark.asyncio
    async def test_insufficient_messages_one(self, detector):
        """One message (below MIN_MESSAGE_COUNT=3) returns is_inertia=False."""
        result = await detector.detect(
            user_id=1,
            recent_messages=[_msg("I feel stuck")],
        )
        assert result.is_inertia is False

    @pytest.mark.asyncio
    async def test_insufficient_messages_two(self, detector):
        """Two messages returns is_inertia=False."""
        result = await detector.detect(
            user_id=1,
            recent_messages=[_msg("I feel stuck"), _msg("help me")],
        )
        assert result.is_inertia is False

    @pytest.mark.asyncio
    async def test_no_user_messages(self, detector):
        """Three messages but none from user returns is_inertia=False."""
        messages = [
            _msg("System response 1", is_user=False),
            _msg("System response 2", is_user=False),
            _msg("System response 3", is_user=False),
        ]
        result = await detector.detect(user_id=1, recent_messages=messages)
        assert result.is_inertia is False

    @pytest.mark.asyncio
    async def test_au_segment_autistic_inertia(self, detector):
        """AU segment with inertia keywords detects AUTISTIC_INERTIA."""
        messages = [
            _msg("I feel stuck and frozen, I want to move but can't"),
            _msg("I want to do it but I can't start, decision paralysis"),
            _msg("I'm overwhelmed and paralyzed by everything"),
        ]
        with patch.object(detector, "_get_user_segment", return_value="AU"):
            result = await detector.detect(user_id=1, recent_messages=messages)

        assert result.is_inertia is True
        assert result.inertia_type == InertiaType.AUTISTIC_INERTIA

    @pytest.mark.asyncio
    async def test_ad_segment_activation_deficit(self, detector):
        """AD segment with activation keywords detects ACTIVATION_DEFICIT."""
        messages = [
            _msg("I should do my homework"),
            _msg("I keep procrastinating, maybe later"),
            _msg("I should start but I'll do it tomorrow"),
        ]
        with patch.object(detector, "_get_user_segment", return_value="AD"):
            result = await detector.detect(user_id=1, recent_messages=messages)

        assert result.is_inertia is True
        assert result.inertia_type == InertiaType.ACTIVATION_DEFICIT

    @pytest.mark.asyncio
    async def test_ah_segment_double_block(self, detector):
        """AH segment with double block keywords detects DOUBLE_BLOCK."""
        messages = [
            _msg("I'm stuck and tired of everything"),
            _msg("I should but can't do this"),
            _msg("overwhelmed and bored at the same time"),
        ]
        with patch.object(detector, "_get_user_segment", return_value="AH"):
            result = await detector.detect(user_id=1, recent_messages=messages)

        assert result.is_inertia is True
        # AH checks double_block_score > 0.5 first
        assert result.inertia_type in (
            InertiaType.DOUBLE_BLOCK,
            InertiaType.AUTISTIC_INERTIA,
            InertiaType.ACTIVATION_DEFICIT,
        )

    @pytest.mark.asyncio
    async def test_ah_segment_falls_back_to_highest_score(self, detector):
        """AH segment with only autistic keywords picks highest scoring type."""
        messages = [
            _msg("I feel stuck in a loop"),
            _msg("frozen and can't switch tasks"),
            _msg("I'm paralyzed, too much going on"),
        ]
        with patch.object(detector, "_get_user_segment", return_value="AH"):
            result = await detector.detect(user_id=1, recent_messages=messages)

        # These are mostly autistic inertia keywords, no activation deficit ones
        assert result.is_inertia is True
        assert result.inertia_type == InertiaType.AUTISTIC_INERTIA

    @pytest.mark.asyncio
    async def test_score_below_threshold_no_inertia(self, detector):
        """Score <= 0.4 returns is_inertia=False."""
        messages = [
            _msg("Hello, how are you?"),
            _msg("I had a good day today"),
            _msg("Everything is going well"),
        ]
        with patch.object(detector, "_get_user_segment", return_value="AD"):
            result = await detector.detect(user_id=1, recent_messages=messages)

        assert result.is_inertia is False

    @pytest.mark.asyncio
    async def test_result_includes_severity(self, detector):
        """Detected inertia includes severity score."""
        messages = [
            _msg("I feel stuck and can't start"),
            _msg("I want to but I can't move"),
            _msg("I'm frozen, want to do it but can't"),
        ]
        with patch.object(detector, "_get_user_segment", return_value="AU"):
            result = await detector.detect(user_id=1, recent_messages=messages)

        assert result.is_inertia is True
        assert 0.0 <= result.severity <= 100.0

    @pytest.mark.asyncio
    async def test_result_includes_intervention(self, detector):
        """Detected inertia includes recommended_intervention."""
        messages = [
            _msg("I feel stuck and frozen"),
            _msg("I'm overwhelmed, can't start"),
            _msg("everything is too much, stuck in a loop"),
        ]
        with patch.object(detector, "_get_user_segment", return_value="AU"):
            result = await detector.detect(user_id=1, recent_messages=messages)

        assert result.is_inertia is True
        assert result.recommended_intervention is not None
        assert isinstance(result.recommended_intervention, str)

    @pytest.mark.asyncio
    async def test_result_type(self, detector):
        """detect() returns InertiaDetectionResult dataclass."""
        messages = [
            _msg("I feel stuck"),
            _msg("I want to start but can't"),
            _msg("I'm frozen and overwhelmed"),
        ]
        with patch.object(detector, "_get_user_segment", return_value="AU"):
            result = await detector.detect(user_id=1, recent_messages=messages)

        assert isinstance(result, InertiaDetectionResult)

    @pytest.mark.asyncio
    async def test_confidence_equals_primary_score(self, detector):
        """Confidence in result matches the primary_score value."""
        messages = [
            _msg("I should do it but I'll do it later"),
            _msg("I keep procrastinating, should really start"),
            _msg("I should stop putting it off until tomorrow"),
        ]
        with patch.object(detector, "_get_user_segment", return_value="AD"):
            result = await detector.detect(user_id=1, recent_messages=messages)

        if result.is_inertia:
            assert result.confidence > 0.4
            assert result.severity == pytest.approx(min(100.0, result.confidence * 100))


# =============================================================================
# TestScoreAutisticInertia
# =============================================================================

class TestScoreAutisticInertia:
    """Test the _score_autistic_inertia() method."""

    def test_no_keywords(self, detector):
        """Messages without keywords return 0 score."""
        messages = ["hello world", "nice weather today"]
        score = detector._score_autistic_inertia(messages)
        assert score == 0.0

    def test_single_keyword(self, detector):
        """Single keyword match adds INERTIA_KEYWORD_WEIGHT."""
        messages = ["i feel stuck"]
        score = detector._score_autistic_inertia(messages)
        assert score > 0.0

    def test_multiple_keywords(self, detector):
        """Multiple keywords increase score."""
        messages = ["i'm stuck and frozen", "overwhelmed by everything"]
        score = detector._score_autistic_inertia(messages)
        assert score > detector._score_autistic_inertia(["hello"])

    def test_want_can_pattern(self, detector):
        """'want' + 'can' in 2+ messages adds PATTERN_WEIGHT."""
        messages = [
            "i want to do it but i can't",
            "i want to start but can not",
            "it's too much",
        ]
        score = detector._score_autistic_inertia(messages)
        # Pattern should fire (2 messages with both "want" and "can")
        assert score > 0.0

    def test_want_can_pattern_not_enough(self, detector):
        """'want' + 'can' in only 1 message does not add pattern weight."""
        messages = [
            "i want to do it but i can't",
            "the weather is nice",
            "what should i do",
        ]
        score_one = detector._score_autistic_inertia(messages)

        messages_two = [
            "i want to do it but i can't",
            "i want to start but can not",
            "what should i do",
        ]
        score_two = detector._score_autistic_inertia(messages_two)

        # Score with 2 want+can messages should be higher due to pattern weight
        assert score_two > score_one

    def test_score_capped_at_one(self, detector):
        """Score is capped at 1.0."""
        # Many keywords should hit the cap
        messages = [
            "stuck frozen overwhelmed paralyzed rumination loop",
            "can't start too much decision paralysis tunnel",
            "stuck frozen overwhelmed cannot switch ruminate",
        ]
        score = detector._score_autistic_inertia(messages)
        assert score <= 1.0

    def test_empty_messages(self, detector):
        """Empty message list returns 0."""
        score = detector._score_autistic_inertia([])
        assert score == 0.0


# =============================================================================
# TestScoreActivationDeficit
# =============================================================================

class TestScoreActivationDeficit:
    """Test the _score_activation_deficit() method."""

    def test_no_keywords(self, detector):
        """Messages without keywords return 0 score."""
        messages = ["hello world", "nice weather today"]
        score = detector._score_activation_deficit(messages)
        assert score == 0.0

    def test_should_keyword(self, detector):
        """'should' keyword adds weight."""
        messages = ["i should do my homework"]
        score = detector._score_activation_deficit(messages)
        assert score > 0.0

    def test_procrastinate_keyword(self, detector):
        """'procrastinate' keyword adds weight."""
        messages = ["i always procrastinate"]
        score = detector._score_activation_deficit(messages)
        assert score > 0.0

    def test_should_later_pattern(self, detector):
        """'should' (2+) + 'later/tomorrow' (1+) adds PATTERN_WEIGHT."""
        messages = [
            "i should start working on this",
            "i should really do it later",
            "maybe tomorrow instead",
        ]
        score = detector._score_activation_deficit(messages)
        # 2 "should" messages + 1 "later" + 1 "tomorrow" -> pattern fires
        assert score > 0.0

    def test_should_without_later_no_pattern(self, detector):
        """'should' without 'later/tomorrow' does not trigger pattern."""
        messages_with = [
            "i should start",
            "i should really do it",
            "i'll do it later",
        ]
        messages_without = [
            "i should start",
            "i should really do it",
            "what time is it",
        ]
        score_with = detector._score_activation_deficit(messages_with)
        score_without = detector._score_activation_deficit(messages_without)
        assert score_with > score_without

    def test_motivation_keyword(self, detector):
        """'motivation' keyword is detected."""
        messages = ["i have no motivation at all"]
        score = detector._score_activation_deficit(messages)
        assert score > 0.0

    def test_score_capped_at_one(self, detector):
        """Score is capped at 1.0."""
        messages = [
            "should need to want to later tomorrow eventually procrastinate lazy motivation",
            "should put off keep forgetting distracted can't be bothered hard to start",
            "should need to later tomorrow eventually procrastinate lazy motivation",
        ]
        score = detector._score_activation_deficit(messages)
        assert score <= 1.0

    def test_empty_messages(self, detector):
        """Empty message list returns 0."""
        score = detector._score_activation_deficit([])
        assert score == 0.0


# =============================================================================
# TestScoreDoubleBlock
# =============================================================================

class TestScoreDoubleBlock:
    """Test the _score_double_block() method."""

    def test_no_keywords(self, detector):
        """Messages without keywords return 0 score."""
        messages = ["hello world", "nice weather"]
        score = detector._score_double_block(messages)
        assert score == 0.0

    def test_specific_double_block_keyword(self, detector):
        """Specific double block keywords add 0.5 weight each."""
        messages = ["i should but can't do anything"]
        score = detector._score_double_block(messages)
        assert score > 0.0

    def test_stuck_and_tired_keyword(self, detector):
        """'stuck and tired' is a recognized double block keyword."""
        messages = ["i'm stuck and tired of trying"]
        score = detector._score_double_block(messages)
        assert score > 0.0

    def test_both_type_indicators_present(self, detector):
        """Both autistic and activation indicators add PATTERN_WEIGHT."""
        messages = [
            "i feel stuck and frozen",       # autistic inertia keyword
            "i should do it later",          # activation deficit keywords
        ]
        score = detector._score_double_block(messages)
        # Both indicator types present -> adds PATTERN_WEIGHT
        assert score >= detector.PATTERN_WEIGHT

    def test_only_autistic_indicators(self, detector):
        """Only autistic indicators without activation does not add pattern weight."""
        messages = [
            "i feel stuck",
            "i'm frozen",
        ]
        score_autistic_only = detector._score_double_block(messages)

        messages_both = [
            "i feel stuck",
            "i should do it later",
        ]
        score_both = detector._score_double_block(messages_both)

        assert score_both > score_autistic_only

    def test_score_capped_at_one(self, detector):
        """Score is capped at 1.0."""
        messages = [
            "should but can't, stuck and tired, overwhelmed and bored",
            "want to but shouldn't, too much and not enough",
            "stuck frozen should later procrastinate overwhelmed",
        ]
        score = detector._score_double_block(messages)
        assert score <= 1.0

    def test_empty_messages(self, detector):
        """Empty message list returns 0."""
        score = detector._score_double_block([])
        assert score == 0.0


# =============================================================================
# TestGetRecommendedIntervention
# =============================================================================

class TestGetRecommendedIntervention:
    """Test the _get_recommended_intervention() method."""

    # High severity (> 0.8)

    def test_high_severity_autistic_inertia(self, detector):
        """High severity autistic inertia returns protocol with sensory rest."""
        intervention = detector._get_recommended_intervention(
            InertiaType.AUTISTIC_INERTIA, 0.85,
        )
        assert "AUTISTIC INERTIA PROTOCOL" in intervention

    def test_high_severity_activation_deficit(self, detector):
        """High severity activation deficit returns body doubling protocol."""
        intervention = detector._get_recommended_intervention(
            InertiaType.ACTIVATION_DEFICIT, 0.9,
        )
        assert "ACTIVATION PROTOCOL" in intervention

    def test_high_severity_double_block(self, detector):
        """High severity double block returns double block protocol."""
        intervention = detector._get_recommended_intervention(
            InertiaType.DOUBLE_BLOCK, 0.85,
        )
        assert "DOUBLE BLOCK PROTOCOL" in intervention

    # Medium severity (> 0.5)

    def test_medium_severity_autistic_inertia(self, detector):
        """Medium severity autistic inertia recommends reducing decisions."""
        intervention = detector._get_recommended_intervention(
            InertiaType.AUTISTIC_INERTIA, 0.6,
        )
        assert "single-option" in intervention.lower() or "decision" in intervention.lower()

    def test_medium_severity_activation_deficit(self, detector):
        """Medium severity activation deficit recommends smallest step."""
        intervention = detector._get_recommended_intervention(
            InertiaType.ACTIVATION_DEFICIT, 0.6,
        )
        assert "smallest" in intervention.lower() or "break" in intervention.lower()

    def test_medium_severity_double_block(self, detector):
        """Medium severity double block checks sensory first."""
        intervention = detector._get_recommended_intervention(
            InertiaType.DOUBLE_BLOCK, 0.6,
        )
        assert "sensory" in intervention.lower()

    # Low severity (<= 0.5)

    def test_low_severity_gentle_prompt(self, detector):
        """Low severity returns gentle prompt."""
        intervention = detector._get_recommended_intervention(
            InertiaType.AUTISTIC_INERTIA, 0.3,
        )
        assert "gentle" in intervention.lower() or "prompt" in intervention.lower()

    def test_boundary_just_above_high(self, detector):
        """Severity just above 0.8 triggers high protocol."""
        intervention = detector._get_recommended_intervention(
            InertiaType.AUTISTIC_INERTIA, 0.81,
        )
        assert "AUTISTIC INERTIA PROTOCOL" in intervention

    def test_boundary_exactly_0_5(self, detector):
        """Severity exactly 0.5 falls into low tier (not > 0.5)."""
        intervention = detector._get_recommended_intervention(
            InertiaType.AUTISTIC_INERTIA, 0.5,
        )
        assert "gentle" in intervention.lower() or "prompt" in intervention.lower()


# =============================================================================
# TestInertiaTypeEnum
# =============================================================================

class TestInertiaTypeEnum:
    """Test the InertiaType enum values."""

    def test_autistic_inertia_value(self):
        """AUTISTIC_INERTIA has correct string value."""
        assert InertiaType.AUTISTIC_INERTIA.value == "autistic_inertia"

    def test_activation_deficit_value(self):
        """ACTIVATION_DEFICIT has correct string value."""
        assert InertiaType.ACTIVATION_DEFICIT.value == "activation_deficit"

    def test_double_block_value(self):
        """DOUBLE_BLOCK has correct string value."""
        assert InertiaType.DOUBLE_BLOCK.value == "double_block"

    def test_three_inertia_types(self):
        """There are exactly three inertia types."""
        assert len(InertiaType) == 3
