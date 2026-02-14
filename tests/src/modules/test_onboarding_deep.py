"""
Tests for Deep Onboarding Module (src/modules/onboarding_deep.py).

Tests:
- Welcome message retrieval
- Path selection (Quick Start vs Deep Dive)
- Segment prompt generation
- Energy pattern prompts (segment-specific)
- Burnout history prompts (segment-specific)
- Completion messages
"""


from src.modules.onboarding_deep import (
    DeepOnboardingModule,
    OnboardingData,
    OnboardingPath,
)


class TestDeepOnboardingModule:
    """Tests for DeepOnboardingModule."""

    def test_get_welcome_message_english(self) -> None:
        """Test getting welcome message in English."""
        module = DeepOnboardingModule()
        message = module.get_welcome_message("en")
        assert "Aurora" in message
        assert len(message) > 0

    def test_get_welcome_message_german(self) -> None:
        """Test getting welcome message in German."""
        module = DeepOnboardingModule()
        message = module.get_welcome_message("de")
        assert "Aurora" in message
        assert len(message) > 0

    def test_get_path_selection_prompt_english(self) -> None:
        """Test getting path selection prompt in English."""
        module = DeepOnboardingModule()
        result = module.get_path_selection_prompt("en")

        assert "message" in result
        assert "options" in result
        assert "Quick Start" in result["message"]
        assert "Deep Dive" in result["message"]
        assert len(result["options"]) == 2
        assert result["options"][0]["value"] == OnboardingPath.QUICK_START
        assert result["options"][1]["value"] == OnboardingPath.DEEP_DIVE

    def test_get_path_selection_prompt_german(self) -> None:
        """Test getting path selection prompt in German."""
        module = DeepOnboardingModule()
        result = module.get_path_selection_prompt("de")

        assert "message" in result
        assert "options" in result
        assert "Schnellstart" in result["message"]
        assert len(result["options"]) == 2

    def test_get_segment_prompt_quick_start(self) -> None:
        """Test getting segment prompt for Quick Start."""
        module = DeepOnboardingModule()
        result = module.get_segment_prompt("en", OnboardingPath.QUICK_START)

        assert "message" in result
        assert "options" in result
        assert len(result["options"]) == 5  # AD, AU, AH, NT, CU

        # Check all segments are present
        codes = [opt["code"] for opt in result["options"]]
        assert "AD" in codes
        assert "AU" in codes
        assert "AH" in codes
        assert "NT" in codes
        assert "CU" in codes

    def test_get_segment_prompt_deep_dive(self) -> None:
        """Test getting segment prompt for Deep Dive."""
        module = DeepOnboardingModule()
        result = module.get_segment_prompt("en", OnboardingPath.DEEP_DIVE)

        assert "message" in result
        assert "options" in result
        assert "personalize" in result["message"].lower()
        assert len(result["options"]) == 5

    def test_get_segment_prompt_translations(self) -> None:
        """Test that segment display names are translated."""
        module = DeepOnboardingModule()

        # English
        result_en = module.get_segment_prompt("en", OnboardingPath.QUICK_START)
        ad_option = next(opt for opt in result_en["options"] if opt["code"] == "AD")
        assert ad_option["display_name"] == "ADHD"

        # German
        result_de = module.get_segment_prompt("de", OnboardingPath.QUICK_START)
        ad_option_de = next(opt for opt in result_de["options"] if opt["code"] == "AD")
        assert ad_option_de["display_name"] == "ADHS"

    def test_get_energy_pattern_prompt_adhd(self) -> None:
        """Test energy pattern prompt for ADHD segment."""
        module = DeepOnboardingModule()
        result = module.get_energy_pattern_prompt("en", "AD")

        assert "message" in result
        assert "options" in result
        assert "energy" in result["message"].lower()
        assert len(result["options"]) > 0

    def test_get_energy_pattern_prompt_autism(self) -> None:
        """Test energy pattern prompt for Autism segment."""
        module = DeepOnboardingModule()
        result = module.get_energy_pattern_prompt("en", "AU")

        assert "message" in result
        assert "options" in result
        assert "routine" in result["message"].lower() or "sensory" in result["message"].lower()
        assert len(result["options"]) > 0

    def test_get_energy_pattern_prompt_audhd(self) -> None:
        """Test energy pattern prompt for AuDHD segment."""
        module = DeepOnboardingModule()
        result = module.get_energy_pattern_prompt("en", "AH")

        assert "message" in result
        assert "options" in result
        assert "audhd" in result["message"].lower() or "channel" in result["message"].lower()
        assert len(result["options"]) > 0

    def test_get_energy_pattern_prompt_neurotypical(self) -> None:
        """Test energy pattern prompt for Neurotypical segment."""
        module = DeepOnboardingModule()
        result = module.get_energy_pattern_prompt("en", "NT")

        assert "message" in result
        assert "options" in result
        assert len(result["options"]) > 0

    def test_get_burnout_history_prompt_adhd(self) -> None:
        """Test burnout history prompt for ADHD segment."""
        module = DeepOnboardingModule()
        result = module.get_burnout_history_prompt("en", "AD")

        assert "message" in result
        assert "options" in result
        assert "boom-bust" in result["message"].lower() or "crash" in result["message"].lower()
        assert len(result["options"]) == 4  # none, occasional, frequent, current

    def test_get_burnout_history_prompt_autism(self) -> None:
        """Test burnout history prompt for Autism segment."""
        module = DeepOnboardingModule()
        result = module.get_burnout_history_prompt("en", "AU")

        assert "message" in result
        assert "options" in result
        assert "shutdown" in result["message"].lower()
        assert len(result["options"]) == 4

    def test_get_burnout_history_prompt_audhd(self) -> None:
        """Test burnout history prompt for AuDHD segment."""
        module = DeepOnboardingModule()
        result = module.get_burnout_history_prompt("en", "AH")

        assert "message" in result
        assert "options" in result
        assert "double" in result["message"].lower() or "both" in result["message"].lower()
        assert len(result["options"]) == 4

    def test_get_completion_message_quick_start(self) -> None:
        """Test completion message for Quick Start path."""
        module = DeepOnboardingModule()
        data = OnboardingData(
            language="en",
            name="Alice",
            segment="AD",
            path=OnboardingPath.QUICK_START,
            consent_given=True,
        )

        message = module.get_completion_message("en", data)
        assert "Alice" in message
        assert "ADHD" in message  # Segment display name
        assert len(message) > 0

    def test_get_completion_message_deep_dive(self) -> None:
        """Test completion message for Deep Dive path."""
        module = DeepOnboardingModule()
        data = OnboardingData(
            language="en",
            name="Bob",
            segment="AU",
            path=OnboardingPath.DEEP_DIVE,
            consent_given=True,
        )

        message = module.get_completion_message("en", data)
        assert "Bob" in message
        assert "Autism" in message  # Segment display name
        assert "thank" in message.lower() or "understanding" in message.lower()
        assert len(message) > 0

    def test_get_completion_message_german(self) -> None:
        """Test completion message in German."""
        module = DeepOnboardingModule()
        data = OnboardingData(
            language="de",
            name="Charlie",
            segment="AH",
            path=OnboardingPath.QUICK_START,
            consent_given=True,
        )

        message = module.get_completion_message("de", data)
        assert "Charlie" in message
        assert "AuDHD" in message
        assert len(message) > 0

    def test_onboarding_data_defaults(self) -> None:
        """Test OnboardingData default values."""
        data = OnboardingData()
        assert data.language == "en"
        assert data.name == ""
        assert data.segment is None
        assert data.path == OnboardingPath.QUICK_START
        assert data.consent_given is False
        assert data.energy_pattern is None
        assert data.work_style_details is None
        assert data.burnout_history is None
        assert data.sensory_preferences is None

    def test_onboarding_data_with_values(self) -> None:
        """Test OnboardingData with custom values."""
        data = OnboardingData(
            language="de",
            name="Test User",
            segment="AD",
            path=OnboardingPath.DEEP_DIVE,
            consent_given=True,
            energy_pattern="morning",
            burnout_history="occasional",
        )
        assert data.language == "de"
        assert data.name == "Test User"
        assert data.segment == "AD"
        assert data.path == OnboardingPath.DEEP_DIVE
        assert data.consent_given is True
        assert data.energy_pattern == "morning"
        assert data.burnout_history == "occasional"
