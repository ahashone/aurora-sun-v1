"""
Money Module Pattern Detection, Energy Gating, and Shame-Free Validation.

Handles:
- Spending pattern detection per neurotype segment
- Energy gating for impulse protection
- Anti-budget (safe-to-spend) calculation
- Shame-free language enforcement

Reference: money.py (main module)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.money_models import (
    SHAME_WORDS,
    DetectedPattern,
    ParsedTransaction,
    PatternType,
    SafeToSpendResult,
)

if TYPE_CHECKING:
    from src.core.segment_context import SegmentContext


# =============================================================================
# Shame-free language validator
# =============================================================================

def validate_shame_free(text: str) -> bool:
    """Check that the given text does not contain any shame words.

    Args:
        text: The text to validate

    Returns:
        True if the text is shame-free, False otherwise
    """
    text_lower = text.lower()
    return not any(word in text_lower for word in SHAME_WORDS)


def enforce_shame_free(text: str) -> str:
    """Return the text unchanged if shame-free, otherwise raise ValueError.

    Args:
        text: The response text to validate

    Returns:
        The original text if shame-free

    Raises:
        ValueError: If the text contains shame words
    """
    if not validate_shame_free(text):
        raise ValueError(
            f"Response contains shame language. "
            f"Shame words found in: {text!r}"
        )
    return text


# =============================================================================
# Anti-Budget calculator
# =============================================================================

def calculate_safe_to_spend(
    income: float,
    committed: float,
) -> SafeToSpendResult:
    """Calculate the anti-budget safe-to-spend amount.

    safe_to_spend = income - committed

    Args:
        income: Total income for the period
        committed: Total committed/recurring expenses

    Returns:
        SafeToSpendResult with income, committed, and safe_amount
    """
    safe = income - committed
    return SafeToSpendResult(
        income=income,
        committed=committed,
        safe_amount=max(safe, 0.0),
    )


# =============================================================================
# Energy gating
# =============================================================================

def check_energy_gate(
    energy_state: str,
    is_essential: bool,
) -> bool:
    """Check whether a purchase should be allowed given the energy state.

    When energy is RED, non-essential purchases are blocked to prevent
    impulsive spending.

    Args:
        energy_state: Current energy state ("green", "yellow", "red")
        is_essential: Whether the purchase is essential (food, health, housing)

    Returns:
        True if the purchase is allowed, False if blocked
    """
    if energy_state.lower() == "red" and not is_essential:
        return False
    return True


def is_essential_category(category: str) -> bool:
    """Determine if a spending category is essential.

    Essential categories are not blocked during RED energy state.

    Args:
        category: Transaction category string

    Returns:
        True if the category is essential
    """
    return category in {"food", "housing", "health", "transport"}


# =============================================================================
# Pattern detection
# =============================================================================

def detect_patterns(
    transactions: list[ParsedTransaction],
    segment_context: SegmentContext,
) -> list[DetectedPattern]:
    """Detect money patterns based on the user's segment context.

    Uses SegmentContext fields (never string comparison against segment codes):
    - neuro.burnout_model == "boom_bust" -> check for spending_burst
    - features.routine_anchoring -> check for routine_deviation
    - features.channel_dominance_enabled -> check for bimodal spending

    Args:
        transactions: List of recent transactions
        segment_context: The user's segment context

    Returns:
        List of detected patterns (may be empty)
    """
    patterns: list[DetectedPattern] = []

    if not transactions:
        return patterns

    amounts = [t.amount for t in transactions if not t.is_income]

    if not amounts:
        return patterns

    avg_spend = sum(amounts) / len(amounts) if amounts else 0.0

    # ADHD pattern: spending_burst (boom-bust)
    if segment_context.neuro.burnout_model == "boom_bust":
        # Detect burst: any single spend > 2x average
        bursts = [a for a in amounts if a > avg_spend * 2]
        if bursts and len(amounts) >= 3:
            severity = min(max(bursts) / (avg_spend * 3), 1.0) if avg_spend > 0 else 0.5
            patterns.append(DetectedPattern(
                pattern_type=PatternType.SPENDING_BURST,
                description=(
                    "There's a noticeable spike in recent spending. "
                    "Let's look at this pattern together."
                ),
                severity=severity,
                segment_code=segment_context.core.code,
            ))

    # Autism pattern: routine_deviation
    if segment_context.features.routine_anchoring:
        # Detect deviation: standard deviation relative to mean
        if len(amounts) >= 3:
            mean = sum(amounts) / len(amounts)
            variance = sum((a - mean) ** 2 for a in amounts) / len(amounts)
            std_dev = variance ** 0.5
            cv = std_dev / mean if mean > 0 else 0.0
            if cv > 0.5:  # coefficient of variation threshold
                patterns.append(DetectedPattern(
                    pattern_type=PatternType.ROUTINE_DEVIATION,
                    description=(
                        "Spending has deviated from the usual routine. "
                        "Here's a look at how the pattern has shifted."
                    ),
                    severity=min(cv, 1.0),
                    segment_code=segment_context.core.code,
                ))

    # AuDHD pattern: bimodal spending
    if segment_context.features.channel_dominance_enabled:
        # Detect bimodal: spending clusters around two distinct values
        if len(amounts) >= 4:
            sorted_amounts = sorted(amounts)
            mid = len(sorted_amounts) // 2
            lower_half = sorted_amounts[:mid]
            upper_half = sorted_amounts[mid:]
            lower_avg = sum(lower_half) / len(lower_half) if lower_half else 0.0
            upper_avg = sum(upper_half) / len(upper_half) if upper_half else 0.0
            if lower_avg > 0 and upper_avg / lower_avg > 2.5:
                severity = min((upper_avg / lower_avg) / 5.0, 1.0)
                patterns.append(DetectedPattern(
                    pattern_type=PatternType.BIMODAL,
                    description=(
                        "Spending seems to swing between two modes. "
                        "This is common with channel switching -- let's explore."
                    ),
                    severity=severity,
                    segment_code=segment_context.core.code,
                ))

    return patterns
