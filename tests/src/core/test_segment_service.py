"""
Tests for SegmentService.

Covers:
- Getting segment contexts for all 5 segments
- Cache behavior
- Validation of segment codes
- Helper methods (is_valid_segment, get_all_segments, etc.)
"""

import pytest

from src.core.segment_service import SegmentService


def test_get_segment_context_ad():
    """Test getting ADHD segment context."""
    context = SegmentService.get_segment_context("AD")

    assert context.core.code == "AD"
    assert context.core.max_priorities == 2
    assert context.core.sprint_minutes == 25
    assert context.features.icnu_enabled is True


def test_get_segment_context_au():
    """Test getting Autism segment context."""
    context = SegmentService.get_segment_context("AU")

    assert context.core.code == "AU"
    assert context.core.max_priorities == 3
    assert context.neuro.sensory_accumulation is True
    assert context.features.sensory_check_required is True


def test_get_segment_context_ah():
    """Test getting AuDHD segment context."""
    context = SegmentService.get_segment_context("AH")

    assert context.core.code == "AH"
    assert context.neuro.masking_model == "double_exponential"
    assert context.features.channel_dominance_enabled is True
    assert context.features.icnu_enabled is True
    assert context.features.spoon_drawer_enabled is True


def test_get_segment_context_nt():
    """Test getting Neurotypical segment context."""
    context = SegmentService.get_segment_context("NT")

    assert context.core.code == "NT"
    assert context.core.max_priorities == 3


def test_get_segment_context_cu():
    """Test getting Custom segment context."""
    context = SegmentService.get_segment_context("CU")

    assert context.core.code == "CU"
    # Custom starts with NT baseline
    assert context.core.max_priorities == 3


def test_get_segment_context_case_insensitive():
    """Test that segment codes are case-insensitive."""
    context_upper = SegmentService.get_segment_context("AD")
    context_lower = SegmentService.get_segment_context("ad")
    context_mixed = SegmentService.get_segment_context("Ad")

    assert context_upper.core.code == "AD"
    assert context_lower.core.code == "AD"
    assert context_mixed.core.code == "AD"


def test_get_segment_context_invalid_code():
    """Test getting segment context with invalid code."""
    with pytest.raises(ValueError, match="Invalid segment code"):
        SegmentService.get_segment_context("INVALID")


def test_get_segment_context_caching():
    """Test that segment contexts are cached."""
    # Clear cache first
    SegmentService.clear_cache()

    # Get context twice
    context1 = SegmentService.get_segment_context("AD")
    context2 = SegmentService.get_segment_context("AD")

    # Should be the same object (cached)
    assert context1 is context2


def test_get_segment_context_caching_different_segments():
    """Test that different segments are cached separately."""
    SegmentService.clear_cache()

    context_ad = SegmentService.get_segment_context("AD")
    context_au = SegmentService.get_segment_context("AU")
    context_ah = SegmentService.get_segment_context("AH")

    # Should be different objects
    assert context_ad is not context_au
    assert context_au is not context_ah
    assert context_ad is not context_ah

    # But should be cached
    assert SegmentService.get_segment_context("AD") is context_ad
    assert SegmentService.get_segment_context("AU") is context_au


def test_is_valid_segment():
    """Test is_valid_segment method."""
    assert SegmentService.is_valid_segment("AD") is True
    assert SegmentService.is_valid_segment("AU") is True
    assert SegmentService.is_valid_segment("AH") is True
    assert SegmentService.is_valid_segment("NT") is True
    assert SegmentService.is_valid_segment("CU") is True

    # Case insensitive
    assert SegmentService.is_valid_segment("ad") is True
    assert SegmentService.is_valid_segment("au") is True

    # Invalid codes
    assert SegmentService.is_valid_segment("INVALID") is False
    assert SegmentService.is_valid_segment("XX") is False
    assert SegmentService.is_valid_segment("") is False


def test_get_all_segments():
    """Test get_all_segments method."""
    segments = SegmentService.get_all_segments()

    assert segments == ["AD", "AU", "AH", "NT", "CU"]
    assert len(segments) == 5


def test_get_default_segment():
    """Test get_default_segment method."""
    default = SegmentService.get_default_segment()
    assert default == "NT"


def test_clear_cache():
    """Test clear_cache method."""
    # Get a context to populate cache
    context1 = SegmentService.get_segment_context("AD")

    # Clear cache
    SegmentService.clear_cache()

    # Get again - should populate cache again
    context2 = SegmentService.get_segment_context("AD")

    # Both should be valid AD contexts (pre-built singletons from _SEGMENT_CONTEXTS)
    assert context1.core.code == "AD"
    assert context2.core.code == "AD"


def test_all_segments_have_valid_contexts():
    """Test that all segment codes return valid contexts."""
    SegmentService.clear_cache()

    for segment_code in SegmentService.get_all_segments():
        context = SegmentService.get_segment_context(segment_code)

        assert context is not None
        assert context.core.code == segment_code
        assert context.core is not None
        assert context.ux is not None
        assert context.neuro is not None
        assert context.features is not None


def test_segment_context_structure_ad():
    """Test ADHD segment context structure."""
    context = SegmentService.get_segment_context("AD")

    # Core config
    assert hasattr(context.core, "max_priorities")
    assert hasattr(context.core, "sprint_minutes")

    # UX config
    assert hasattr(context.ux, "notification_strategy")

    # Neuro config
    assert hasattr(context.neuro, "inertia_type")
    assert hasattr(context.neuro, "burnout_model")

    # Features
    assert hasattr(context.features, "icnu_enabled")
    assert hasattr(context.features, "sensory_check_required")


def test_segment_context_structure_au():
    """Test Autism segment context structure."""
    context = SegmentService.get_segment_context("AU")

    # Neuro-specific
    assert hasattr(context.neuro, "sensory_accumulation")
    assert context.neuro.sensory_accumulation is True

    # Features
    assert hasattr(context.features, "routine_anchoring")
    assert context.features.routine_anchoring is True


def test_segment_context_structure_ah():
    """Test AuDHD segment context structure."""
    context = SegmentService.get_segment_context("AH")

    # Neuro-specific (has both ADHD and Autism features)
    assert hasattr(context.neuro, "masking_model")
    assert hasattr(context.neuro, "sensory_accumulation")
    assert context.neuro.masking_model == "double_exponential"

    # Features (has both)
    assert hasattr(context.features, "icnu_enabled")
    assert hasattr(context.features, "spoon_drawer_enabled")


def test_cache_persists_across_calls():
    """Test that cache persists across multiple calls."""
    SegmentService.clear_cache()

    # Get all segments
    contexts = {}
    for code in ["AD", "AU", "AH", "NT", "CU"]:
        contexts[code] = SegmentService.get_segment_context(code)

    # Get them again
    for code in ["AD", "AU", "AH", "NT", "CU"]:
        assert SegmentService.get_segment_context(code) is contexts[code]


def test_segment_codes_uppercase_in_cache():
    """Test that lowercase codes are normalized to uppercase in cache."""
    SegmentService.clear_cache()

    # Request with lowercase
    context_lower = SegmentService.get_segment_context("ad")

    # Request with uppercase
    context_upper = SegmentService.get_segment_context("AD")

    # Should be the same cached object
    assert context_lower is context_upper


def test_invalid_codes_list():
    """Test various invalid segment codes."""
    invalid_codes = [
        "ADHD",  # Display name, not code
        "Autism",  # Display name
        "AuDHD",  # Display name
        "A",  # Too short
    "ABC",  # Too long
        "12",  # Numbers
        "A1",  # Mixed
        "",  # Empty
        " AD ",  # With spaces (note: might work due to strip)
    ]

    for code in invalid_codes:
        # Should either raise ValueError or return False for is_valid_segment
        if code.strip().upper() in ["AD", "AU", "AH", "NT", "CU"]:
            continue  # This would be valid after strip

        assert SegmentService.is_valid_segment(code) is False

        with pytest.raises(ValueError):
            SegmentService.get_segment_context(code)
