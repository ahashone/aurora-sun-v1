"""
Segment Service for Aurora Sun V1.

This module provides the SegmentService class for accessing segment configuration.
The service is the main entry point for modules that need segment-specific config.

Key principle: NEVER use `if segment == "AD"` in code.
Use SegmentContext fields instead.

Reference: ARCHITECTURE.md Section 3 (Neurotype Segmentation)
"""

from __future__ import annotations

from src.core.segment_context import (
    SegmentContext,
    WorkingStyleCode,
)


class SegmentService:
    """
    Service for accessing segment configuration.

    This is the primary entry point for getting segment context.
    Modules should use this service to get their segment-specific config.

    Example:
        >>> segment_service = SegmentService()
        >>> context = segment_service.get_segment_context("AD")
        >>> print(context.core.max_priorities)  # 2
        >>> print(context.features.icnu_enabled)  # True
    """

    # Cache of segment contexts for performance
    _context_cache: dict[str, SegmentContext] = {}

    @classmethod
    def get_segment_context(cls, segment_code: str) -> SegmentContext:
        """
        Get the complete segment context for a given segment code.

        This is the primary method for accessing segment configuration.
        Uses caching for performance.

        Args:
            segment_code: The user's segment code (AD, AU, AH, NT, CU).
                         Case-insensitive - "ad" and "AD" both work.

        Returns:
            Fully configured SegmentContext with all sub-objects

        Raises:
            ValueError: If the segment code is not recognized

        Example:
            >>> context = SegmentService.get_segment_context("AH")
            >>> context.neuro.sensory_accumulation  # True
            >>> context.features.spoon_drawer_enabled  # True
        """
        # Normalize to uppercase
        code = segment_code.upper()

        # Check cache first
        if code in cls._context_cache:
            return cls._context_cache[code]

        # Validate the segment code
        valid_codes = ("AD", "AU", "AH", "NT", "CU")
        if code not in valid_codes:
            raise ValueError(
                f"Invalid segment code: '{segment_code}'. "
                f"Valid codes are: {', '.join(valid_codes)}"
            )

        # Get context from SegmentContext
        context = SegmentContext.from_code(code)

        # Cache for future use
        cls._context_cache[code] = context

        return context

    @classmethod
    def is_valid_segment(cls, segment_code: str) -> bool:
        """
        Check if a segment code is valid.

        Args:
            segment_code: The segment code to validate

        Returns:
            True if valid, False otherwise
        """
        return segment_code.upper() in ("AD", "AU", "AH", "NT", "CU")

    @classmethod
    def get_all_segments(cls) -> list[str]:
        """
        Get all valid segment codes.

        Returns:
            List of all valid segment codes
        """
        return ["AD", "AU", "AH", "NT", "CU"]

    @classmethod
    def get_default_segment(cls) -> str:
        """
        Get the default segment for new users.

        Returns:
            Default segment code (NT for Neurotypical)
        """
        return "NT"

    @classmethod
    def clear_cache(cls) -> None:
        """
        Clear the segment context cache.

        Mainly useful for testing.
        """
        cls._context_cache.clear()
