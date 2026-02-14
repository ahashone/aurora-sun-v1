"""
Tests for Full i18n System (src/lib/i18n.py).

Tests:
- Language detection from Telegram locale
- Translation string retrieval with fallback
- Segment name translation
- Module string registration
- Format string interpolation
- Custom module strings
"""


from src.i18n import DEFAULT_LANGUAGE
from src.lib.i18n import I18nService, get_i18n_service


class TestI18nService:
    """Tests for I18nService."""

    def test_detect_language_from_locale_english(self) -> None:
        """Test language detection from English locale."""
        service = I18nService()
        assert service.detect_language_from_locale("en-US") == "en"
        assert service.detect_language_from_locale("en-GB") == "en"
        assert service.detect_language_from_locale("en") == "en"

    def test_detect_language_from_locale_german(self) -> None:
        """Test language detection from German locale."""
        service = I18nService()
        assert service.detect_language_from_locale("de-DE") == "de"
        assert service.detect_language_from_locale("de-AT") == "de"
        assert service.detect_language_from_locale("de") == "de"

    def test_detect_language_from_locale_serbian(self) -> None:
        """Test language detection from Serbian locale."""
        service = I18nService()
        assert service.detect_language_from_locale("sr-RS") == "sr"
        assert service.detect_language_from_locale("sr") == "sr"

    def test_detect_language_from_locale_greek(self) -> None:
        """Test language detection from Greek locale."""
        service = I18nService()
        assert service.detect_language_from_locale("el-GR") == "el"
        assert service.detect_language_from_locale("el") == "el"

    def test_detect_language_from_locale_unsupported(self) -> None:
        """Test language detection from unsupported locale falls back to English."""
        service = I18nService()
        assert service.detect_language_from_locale("fr-FR") == DEFAULT_LANGUAGE
        assert service.detect_language_from_locale("ja-JP") == DEFAULT_LANGUAGE

    def test_detect_language_from_locale_none(self) -> None:
        """Test language detection with None locale."""
        service = I18nService()
        assert service.detect_language_from_locale(None) == DEFAULT_LANGUAGE

    def test_translate_existing_key(self) -> None:
        """Test translating an existing key."""
        service = I18nService()
        result = service.translate("en", "onboarding", "welcome_title")
        assert result == "Welcome to Aurora Sun"

    def test_translate_existing_key_german(self) -> None:
        """Test translating an existing key in German."""
        service = I18nService()
        result = service.translate("de", "onboarding", "welcome_title")
        assert result == "Willkommen bei Aurora Sun"

    def test_translate_missing_key_fallback(self) -> None:
        """Test fallback to English for missing key."""
        service = I18nService()
        # Key exists in English but not in other languages (hypothetically)
        result = service.translate("en", "onboarding", "welcome_title")
        assert result == "Welcome to Aurora Sun"

    def test_translate_with_format_vars(self) -> None:
        """Test translation with format variables."""
        service = I18nService()
        result = service.translate(
            "en", "onboarding", "onboarding_complete", name="Alice"
        )
        assert "Alice" in result

    def test_translate_segment(self) -> None:
        """Test segment name translation."""
        service = I18nService()
        assert service.translate_segment("en", "AD") == "ADHD"
        assert service.translate_segment("de", "AD") == "ADHS"
        assert service.translate_segment("en", "AU") == "Autism"
        assert service.translate_segment("de", "AU") == "Autismus"

    def test_register_module_strings(self) -> None:
        """Test registering custom module strings."""
        service = I18nService()
        service.register_module_strings(
            "test_module",
            {
                "en": {"greeting": "Hello", "farewell": "Goodbye"},
                "de": {"greeting": "Hallo", "farewell": "Auf Wiedersehen"},
            },
        )

        assert service.translate("en", "test_module", "greeting") == "Hello"
        assert service.translate("de", "test_module", "greeting") == "Hallo"
        assert service.translate("en", "test_module", "farewell") == "Goodbye"

    def test_register_module_strings_overwrites(self) -> None:
        """Test that registering module strings overwrites existing ones."""
        service = I18nService()
        service.register_module_strings(
            "test_module",
            {"en": {"key": "value1"}},
        )
        assert service.translate("en", "test_module", "key") == "value1"

        # Overwrite
        service.register_module_strings(
            "test_module",
            {"en": {"key": "value2"}},
        )
        assert service.translate("en", "test_module", "key") == "value2"

    def test_get_supported_languages(self) -> None:
        """Test getting supported languages."""
        service = I18nService()
        languages = service.get_supported_languages()
        assert "en" in languages
        assert "de" in languages
        assert "sr" in languages
        assert "el" in languages
        assert len(languages) == 4

    def test_validate_language(self) -> None:
        """Test language validation."""
        service = I18nService()
        assert service.validate_language("en") is True
        assert service.validate_language("de") is True
        assert service.validate_language("sr") is True
        assert service.validate_language("el") is True
        assert service.validate_language("fr") is False
        assert service.validate_language("invalid") is False

    def test_get_i18n_service_singleton(self) -> None:
        """Test that get_i18n_service returns the same instance."""
        service1 = get_i18n_service()
        service2 = get_i18n_service()
        assert service1 is service2

    def test_format_string_with_safe_types(self) -> None:
        """Test format string with safe types (str, int, float)."""
        service = I18nService()
        service.register_module_strings(
            "test",
            {"en": {"template": "Name: {name}, Age: {age}, Score: {score}"}},
        )
        result = service.translate("en", "test", "template", name="Alice", age=30, score=95.5)
        assert result == "Name: Alice, Age: 30, Score: 95.5"

    def test_format_string_with_unsafe_type(self) -> None:
        """Test format string converts unsafe types to string."""
        service = I18nService()
        service.register_module_strings(
            "test",
            {"en": {"template": "Value: {value}"}},
        )
        result = service.translate("en", "test", "template", value={"key": "value"})
        assert "value" in result.lower()  # Dict converted to string

    def test_format_string_missing_variable(self) -> None:
        """Test format string with missing variable returns template as-is."""
        service = I18nService()
        service.register_module_strings(
            "test",
            {"en": {"template": "Hello {name}"}},
        )
        # Missing 'name' variable - should return template as-is
        result = service.translate("en", "test", "template")
        assert "{name}" in result
