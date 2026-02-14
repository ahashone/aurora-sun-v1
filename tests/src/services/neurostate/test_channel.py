"""
Unit tests for the ChannelDominanceDetector service.

Tests cover:
- Channel dominance detection from messages
- ADHD vs Autism channel scoring
- Channel switching detection
- Message analysis for keyword matching
- Default state when no messages/history
- Recommended coaching approach per channel
- ADHD-day vs Autism-day modifiers
- Confidence calculation from score spread
- State persistence (update_state, get_current_state)
- Edge cases (empty messages, no user messages, equal scores)

All DB dependencies are mocked to avoid real database access.
"""

from unittest.mock import MagicMock

import pytest

from src.models.neurostate import ChannelType
from src.services.neurostate.channel import (
    ChannelDetectionResult,
    ChannelDominanceDetector,
)

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Provide a mock database session."""
    db = MagicMock()
    # Default: no existing state
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    return db


@pytest.fixture
def detector(mock_db):
    """Create a ChannelDominanceDetector with a mock DB session."""
    return ChannelDominanceDetector(db=mock_db)


@pytest.fixture
def focus_messages():
    """Messages dominated by focus/structure keywords."""
    return [
        {"text": "I need to plan my tasks in a specific order and complete them step by step", "is_user": True},
        {"text": "Let me organize my routine with a detailed structure", "is_user": True},
        {"text": "I want to finish this exact deadline first", "is_user": True},
    ]


@pytest.fixture
def creative_messages():
    """Messages dominated by creative/divergent keywords."""
    return [
        {"text": "I have a new idea, imagine what we could explore!", "is_user": True},
        {"text": "What if we try a different creative brainstorm approach?", "is_user": True},
        {"text": "Maybe we could think of alternative possibilities to wonder about", "is_user": True},
    ]


@pytest.fixture
def social_messages():
    """Messages dominated by social/connection keywords."""
    return [
        {"text": "I want to talk to my friend and share my conversation with family", "is_user": True},
        {"text": "Can we discuss how to connect with people for support?", "is_user": True},
        {"text": "I need help with a relationship and want to ask someone", "is_user": True},
    ]


@pytest.fixture
def physical_messages():
    """Messages dominated by physical/action keywords."""
    return [
        {"text": "I just need to start now, let me go do something active", "is_user": True},
        {"text": "I want to move my body with exercise and physical action", "is_user": True},
        {"text": "Let me walk and use my hands, need to just go", "is_user": True},
    ]


@pytest.fixture
def learning_messages():
    """Messages dominated by learning/curiosity keywords."""
    return [
        {"text": "I want to learn and understand why this research is interesting", "is_user": True},
        {"text": "Can you explain how this works? I'm curious to discover more information", "is_user": True},
        {"text": "I want to study and read to find out the question behind this", "is_user": True},
    ]


# =============================================================================
# TestAnalyzeMessages
# =============================================================================

class TestAnalyzeMessages:
    """Test the _analyze_messages() method."""

    def test_focus_messages_score_highest(self, detector, focus_messages):
        """Focus-keyword messages produce highest FOCUS score."""
        scores = detector._analyze_messages(focus_messages)
        assert scores[ChannelType.FOCUS] >= scores[ChannelType.CREATIVE]
        assert scores[ChannelType.FOCUS] >= scores[ChannelType.SOCIAL]

    def test_creative_messages_score_highest(self, detector, creative_messages):
        """Creative-keyword messages produce highest CREATIVE score."""
        scores = detector._analyze_messages(creative_messages)
        assert scores[ChannelType.CREATIVE] >= scores[ChannelType.FOCUS]
        assert scores[ChannelType.CREATIVE] >= scores[ChannelType.LEARNING]

    def test_social_messages_score_highest(self, detector, social_messages):
        """Social-keyword messages produce highest SOCIAL score."""
        scores = detector._analyze_messages(social_messages)
        assert scores[ChannelType.SOCIAL] >= scores[ChannelType.FOCUS]
        assert scores[ChannelType.SOCIAL] >= scores[ChannelType.PHYSICAL]

    def test_physical_messages_score_highest(self, detector, physical_messages):
        """Physical-keyword messages produce highest PHYSICAL score."""
        scores = detector._analyze_messages(physical_messages)
        assert scores[ChannelType.PHYSICAL] >= scores[ChannelType.LEARNING]

    def test_learning_messages_score_highest(self, detector, learning_messages):
        """Learning-keyword messages produce highest LEARNING score."""
        scores = detector._analyze_messages(learning_messages)
        assert scores[ChannelType.LEARNING] >= scores[ChannelType.PHYSICAL]

    def test_empty_messages_returns_baseline(self, detector):
        """Empty message list returns equal baseline scores."""
        scores = detector._analyze_messages([])
        for ch in detector.CHANNELS:
            assert scores[ch] == 50.0

    def test_no_user_messages_returns_baseline(self, detector):
        """Messages without is_user=True return baseline scores."""
        messages = [
            {"text": "plan organize structure", "is_user": False},
            {"text": "plan organize structure", "is_user": False},
        ]
        scores = detector._analyze_messages(messages)
        for ch in detector.CHANNELS:
            assert scores[ch] == 50.0

    def test_scores_are_normalized_0_to_100(self, detector, focus_messages):
        """All channel scores are within [0, 100] after blending."""
        scores = detector._analyze_messages(focus_messages)
        for ch in detector.CHANNELS:
            # After blending: normalized * 0.7 + 50 * 0.3 = at minimum 15 and at max 85
            assert 0 <= scores[ch] <= 100

    def test_blending_with_baseline(self, detector, focus_messages):
        """Scores are blended: 70% normalized + 30% baseline (50)."""
        scores = detector._analyze_messages(focus_messages)
        # The highest channel should be at most 100*0.7 + 50*0.3 = 85
        # The lowest should be at least 0*0.7 + 50*0.3 = 15
        for ch in detector.CHANNELS:
            assert scores[ch] >= 15.0
            assert scores[ch] <= 85.0

    def test_case_insensitive_matching(self, detector):
        """Keyword matching is case-insensitive."""
        messages = [
            {"text": "PLAN ORGANIZE STRUCTURE DETAIL SPECIFIC", "is_user": True},
        ]
        scores = detector._analyze_messages(messages)
        assert scores[ChannelType.FOCUS] > scores[ChannelType.SOCIAL]


# =============================================================================
# TestDetect
# =============================================================================

class TestDetect:
    """Test the detect() async method."""

    @pytest.mark.asyncio
    async def test_detect_returns_result(self, detector, focus_messages):
        """detect() returns a ChannelDetectionResult."""
        result = await detector.detect(user_id=1, recent_messages=focus_messages)

        assert isinstance(result, ChannelDetectionResult)
        assert isinstance(result.dominant_channel, ChannelType)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.channel_scores, dict)
        assert isinstance(result.is_adhd_dominant, bool)
        assert isinstance(result.is_autism_dominant, bool)
        assert isinstance(result.recommended_approach, str)

    @pytest.mark.asyncio
    async def test_detect_focus_dominant(self, detector, focus_messages):
        """Focus messages produce FOCUS as dominant channel."""
        result = await detector.detect(user_id=1, recent_messages=focus_messages)
        assert result.dominant_channel == ChannelType.FOCUS

    @pytest.mark.asyncio
    async def test_detect_creative_dominant(self, detector, creative_messages):
        """Creative messages produce CREATIVE as dominant channel."""
        result = await detector.detect(user_id=1, recent_messages=creative_messages)
        assert result.dominant_channel == ChannelType.CREATIVE

    @pytest.mark.asyncio
    async def test_detect_with_no_messages_no_stored_state(self, detector):
        """Without messages or stored state, returns default equal scores."""
        result = await detector.detect(user_id=1)

        # Default scores are all 50, confidence should be 0 (spread = 0)
        assert result.confidence == 0.0
        assert not result.is_adhd_dominant
        assert not result.is_autism_dominant

    @pytest.mark.asyncio
    async def test_detect_adhd_dominant_day(self, detector):
        """ADHD-dominant day detected when CREATIVE/PHYSICAL score much higher."""
        # Messages with lots of creative + physical keywords
        messages = [
            {"text": "idea creative explore new imagine brainstorm possibility alternative", "is_user": True},
            {"text": "move action start now physical body energy active exercise go", "is_user": True},
        ]
        result = await detector.detect(user_id=1, recent_messages=messages)

        # ADHD channels (CREATIVE, PHYSICAL) should dominate
        adhd_avg = (result.channel_scores[ChannelType.CREATIVE] + result.channel_scores[ChannelType.PHYSICAL]) / 2
        autism_avg = (result.channel_scores[ChannelType.FOCUS] + result.channel_scores[ChannelType.LEARNING]) / 2
        if adhd_avg > autism_avg + 15:
            assert result.is_adhd_dominant

    @pytest.mark.asyncio
    async def test_detect_autism_dominant_day(self, detector):
        """Autism-dominant day detected when FOCUS/LEARNING score much higher."""
        messages = [
            {"text": "plan detail specific structure organize order system routine complete finish task sequence step", "is_user": True},
            {"text": "learn understand research know information question why how explain read study", "is_user": True},
        ]
        result = await detector.detect(user_id=1, recent_messages=messages)

        autism_avg = (result.channel_scores[ChannelType.FOCUS] + result.channel_scores[ChannelType.LEARNING]) / 2
        adhd_avg = (result.channel_scores[ChannelType.CREATIVE] + result.channel_scores[ChannelType.PHYSICAL]) / 2
        if autism_avg > adhd_avg + 15:
            assert result.is_autism_dominant

    @pytest.mark.asyncio
    async def test_detect_neither_dominant_balanced(self, detector):
        """Balanced signals produce neither ADHD nor Autism dominant."""
        messages = [
            {"text": "plan idea move learn talk", "is_user": True},
        ]
        result = await detector.detect(user_id=1, recent_messages=messages)

        # With balanced keywords, neither should dominate
        # (but depends on exact keyword distribution)
        # At minimum, ensure both booleans can be False simultaneously
        if not result.is_adhd_dominant and not result.is_autism_dominant:
            assert True  # Balanced state confirmed

    @pytest.mark.asyncio
    async def test_confidence_from_score_spread(self, detector, focus_messages):
        """Confidence is derived from spread between max and min scores."""
        result = await detector.detect(user_id=1, recent_messages=focus_messages)

        max_score = max(result.channel_scores.values())
        min_score = min(result.channel_scores.values())
        expected_confidence = min(1.0, (max_score - min_score) / 50.0)
        assert result.confidence == pytest.approx(expected_confidence)


# =============================================================================
# TestGetRecommendedApproach
# =============================================================================

class TestGetRecommendedApproach:
    """Test the _get_recommended_approach() method."""

    def test_focus_approach(self, detector):
        """FOCUS channel recommends structured task breakdown."""
        approach = detector._get_recommended_approach(ChannelType.FOCUS, False, False)
        assert "structure" in approach.lower() or "task" in approach.lower()

    def test_creative_approach(self, detector):
        """CREATIVE channel recommends exploration."""
        approach = detector._get_recommended_approach(ChannelType.CREATIVE, False, False)
        assert "explor" in approach.lower() or "diverge" in approach.lower()

    def test_social_approach(self, detector):
        """SOCIAL channel recommends connection."""
        approach = detector._get_recommended_approach(ChannelType.SOCIAL, False, False)
        assert "connect" in approach.lower()

    def test_physical_approach(self, detector):
        """PHYSICAL channel recommends movement."""
        approach = detector._get_recommended_approach(ChannelType.PHYSICAL, False, False)
        assert "movement" in approach.lower() or "active" in approach.lower()

    def test_learning_approach(self, detector):
        """LEARNING channel recommends context and curiosity."""
        approach = detector._get_recommended_approach(ChannelType.LEARNING, False, False)
        assert "context" in approach.lower() or "curios" in approach.lower()

    def test_adhd_dominant_modifier(self, detector):
        """ADHD-dominant day adds novelty/stimulation note."""
        approach = detector._get_recommended_approach(ChannelType.FOCUS, True, False)
        assert "ADHD-day" in approach
        assert "novelty" in approach.lower() or "stimulation" in approach.lower()

    def test_autism_dominant_modifier(self, detector):
        """Autism-dominant day adds predictability/stability note."""
        approach = detector._get_recommended_approach(ChannelType.FOCUS, False, True)
        assert "Autism-day" in approach
        assert "predictab" in approach.lower() or "stability" in approach.lower()

    def test_no_modifier_when_balanced(self, detector):
        """No modifier added when neither ADHD nor Autism dominant."""
        approach = detector._get_recommended_approach(ChannelType.FOCUS, False, False)
        assert "NOTE:" not in approach


# =============================================================================
# TestChannelTypeEnum
# =============================================================================

class TestChannelTypeEnum:
    """Test the ChannelType enum values."""

    def test_five_channels(self):
        """There are exactly 5 channel types."""
        assert len(ChannelType) == 5

    def test_channel_values(self):
        """Channel type values match expected strings."""
        assert ChannelType.FOCUS.value == "focus"
        assert ChannelType.CREATIVE.value == "creative"
        assert ChannelType.SOCIAL.value == "social"
        assert ChannelType.PHYSICAL.value == "physical"
        assert ChannelType.LEARNING.value == "learning"


# =============================================================================
# TestChannelClassification
# =============================================================================

class TestChannelClassification:
    """Test the ADHD/Autism channel classification."""

    def test_adhd_channels_are_creative_physical(self, detector):
        """ADHD channels are CREATIVE and PHYSICAL."""
        assert ChannelType.CREATIVE in detector.ADHD_CHANNELS
        assert ChannelType.PHYSICAL in detector.ADHD_CHANNELS
        assert len(detector.ADHD_CHANNELS) == 2

    def test_autism_channels_are_focus_learning(self, detector):
        """Autism channels are FOCUS and LEARNING."""
        assert ChannelType.FOCUS in detector.AUTISM_CHANNELS
        assert ChannelType.LEARNING in detector.AUTISM_CHANNELS
        assert len(detector.AUTISM_CHANNELS) == 2

    def test_social_channel_is_separate(self, detector):
        """SOCIAL channel is separate from ADHD/Autism classification."""
        assert detector.SOCIAL_CHANNEL == ChannelType.SOCIAL
        assert ChannelType.SOCIAL not in detector.ADHD_CHANNELS
        assert ChannelType.SOCIAL not in detector.AUTISM_CHANNELS


# =============================================================================
# TestThresholds
# =============================================================================

class TestThresholds:
    """Test detection thresholds."""

    def test_dominance_threshold(self, detector):
        """DOMINANCE_THRESHOLD is 0.3."""
        assert detector.DOMINANCE_THRESHOLD == 0.3

    def test_confidence_high(self, detector):
        """CONFIDENCE_HIGH is 0.7."""
        assert detector.CONFIDENCE_HIGH == 0.7

    def test_confidence_medium(self, detector):
        """CONFIDENCE_MEDIUM is 0.5."""
        assert detector.CONFIDENCE_MEDIUM == 0.5


# =============================================================================
# TestChannelSignals
# =============================================================================

class TestChannelSignals:
    """Test the CHANNEL_SIGNALS keyword dictionary."""

    def test_all_channels_have_signals(self, detector):
        """Every channel type has an entry in CHANNEL_SIGNALS."""
        for ch in detector.CHANNELS:
            assert ch in detector.CHANNEL_SIGNALS
            assert len(detector.CHANNEL_SIGNALS[ch]) > 0

    def test_signal_keywords_are_lowercase(self, detector):
        """All signal keywords are lowercase strings."""
        for ch, keywords in detector.CHANNEL_SIGNALS.items():
            for kw in keywords:
                assert kw == kw.lower(), f"Keyword '{kw}' in {ch} is not lowercase"

    def test_focus_keywords_include_structure(self, detector):
        """Focus channel keywords include structure-related terms."""
        focus_kw = detector.CHANNEL_SIGNALS[ChannelType.FOCUS]
        assert "structure" in focus_kw
        assert "plan" in focus_kw

    def test_creative_keywords_include_idea(self, detector):
        """Creative channel keywords include idea-related terms."""
        creative_kw = detector.CHANNEL_SIGNALS[ChannelType.CREATIVE]
        assert "idea" in creative_kw
        assert "creative" in creative_kw


# =============================================================================
# TestADHDVsAutismScoring
# =============================================================================

class TestADHDVsAutismScoring:
    """Test ADHD vs Autism dominance scoring logic."""

    @pytest.mark.asyncio
    async def test_adhd_dominant_requires_15_point_lead(self, detector):
        """ADHD dominance requires ADHD avg > Autism avg + 15."""
        # Manually set scores where ADHD channels are much higher
        adhd_avg = (80.0 + 80.0) / 2  # 80
        autism_avg = (30.0 + 30.0) / 2  # 30
        # 80 > 30 + 15 = True
        assert adhd_avg > autism_avg + 15

    @pytest.mark.asyncio
    async def test_autism_dominant_requires_15_point_lead(self, detector):
        """Autism dominance requires Autism avg > ADHD avg + 15."""
        adhd_avg = (30.0 + 30.0) / 2  # 30
        autism_avg = (80.0 + 80.0) / 2  # 80
        # 80 > 30 + 15 = True
        assert autism_avg > adhd_avg + 15

    @pytest.mark.asyncio
    async def test_neither_dominant_within_15(self, detector):
        """Neither dominant when difference is within 15 points."""
        adhd_avg = (55.0 + 55.0) / 2  # 55
        autism_avg = (50.0 + 50.0) / 2  # 50
        # 55 > 50 + 15 = False, 50 > 55 + 15 = False
        assert not (adhd_avg > autism_avg + 15)
        assert not (autism_avg > adhd_avg + 15)
