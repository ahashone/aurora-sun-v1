"""
Segment Configuration for Aurora Sun V1.

This module defines the segment codes used internally and their user-facing display names.
Internal codes (AD, AU, AH, NT, CU) are NEVER shown to users - always use display names.

Segment Architecture:
- AD: ADHD (Momentum-based, novelty-first, dopamin-optimized)
- AU: Autism (Structure-based, routine-first, sensorische Ruhe)
- AH: AuDHD (Hybrid, flexible structure, ICNU-charging, channel dominance)
- NT: Neurotypical (Adaptive baseline, standard productivity)
- CU: Custom (Individually configured)

Reference: ARCHITECTURE.md Section 3 (Neurotype Segmentation)
"""

from __future__ import annotations

from typing import Literal

# Internal codes -> User-facing display names
# NEVER show internal codes to users
SEGMENT_DISPLAY_NAMES: dict[str, str] = {
    "AD": "ADHD",
    "AU": "Autism",
    "AH": "AuDHD",
    "NT": "Neurotypical",
    "CU": "Custom"
}

# Segment codes (internal use only)
SegmentCode = Literal["AD", "AU", "AH", "NT", "CU"]

# Supported segment codes
VALID_SEGMENTS: set[SegmentCode] = {"AD", "AU", "AH", "NT", "CU"}

# Default segment for new users
DEFAULT_SEGMENT: SegmentCode = "NT"


def get_display_name(segment_code: str) -> str:
    """
    Get the user-facing display name for a segment code.

    Args:
        segment_code: Internal segment code (AD, AU, AH, NT, CU)

    Returns:
        User-facing display name (ADHD, Autism, AuDHD, Neurotypical, Custom)

    Example:
        >>> get_display_name("AD")
        "ADHD"
        >>> get_display_name("AU")
        "Autism"
    """
    return SEGMENT_DISPLAY_NAMES.get(segment_code, segment_code)


def is_valid_segment(segment_code: str) -> bool:
    """Check if a segment code is valid."""
    return segment_code in VALID_SEGMENTS
