"""
Money Module Data Models.

SQLAlchemy ORM models, dataclasses, enums, and constants for the Money Module.
All FINANCIAL columns use 3-tier envelope encryption.

Data Classification: FINANCIAL / ART_9_SPECIAL (coaching logs)
Reference: ARCHITECTURE.md Section 7 (Money Pillar)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from src.models.base import Base


# =============================================================================
# Constants
# =============================================================================

# Shame-free language: these words must NEVER appear in any user-facing text.
# CI-enforced. In the DNA.
SHAME_WORDS: frozenset[str] = frozenset({
    "overspent",
    "wasted",
    "blew",
    "irresponsible",
    "bad with money",
    "can't afford",
    "guilty",
    "shame",
})


# =============================================================================
# Enums
# =============================================================================

class TransactionCategory(StrEnum):
    """Categories for financial transactions."""

    FOOD = "food"
    HOUSING = "housing"
    TRANSPORT = "transport"
    HEALTH = "health"
    EDUCATION = "education"
    LEISURE = "leisure"
    SUBSCRIPTION = "subscription"
    INCOME = "income"
    GIFT = "gift"
    OTHER = "other"


class PatternType(StrEnum):
    """Types of detected money patterns.

    Each pattern maps to a specific neurotype's tendencies:
    - spending_burst: ADHD boom-bust cycle (SegmentContext.neuro.burnout_model == "boom_bust")
    - routine_deviation: Autism routine anchoring (SegmentContext.features.routine_anchoring)
    - bimodal: AuDHD channel dominance (SegmentContext.features.channel_dominance_enabled)
    """

    SPENDING_BURST = "spending_burst"
    ROUTINE_DEVIATION = "routine_deviation"
    BIMODAL = "bimodal"


class ExpenseFrequency(StrEnum):
    """Frequency for recurring expenses."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


# =============================================================================
# SQLAlchemy Models (all FINANCIAL columns encrypted)
# =============================================================================

class Transaction(Base):
    """Recorded financial transaction.

    Data Classification: FINANCIAL
    - amount_encrypted: 3-tier envelope encryption
    - description_encrypted: 3-tier envelope encryption
    """

    __tablename__ = "money_transactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount_encrypted = Column(Text, nullable=False)
    currency = Column(String(3), nullable=False, default="EUR")
    category = Column(String(50), nullable=False, default="other")
    description_encrypted = Column(Text, nullable=True)
    transaction_date = Column(DateTime, nullable=False)
    is_income = Column(Integer, default=0)  # 0 = expense, 1 = income
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    user_relationship = relationship("User", foreign_keys=[user_id], lazy="select")


class Budget(Base):
    """Budget per category with encrypted limits.

    Data Classification: FINANCIAL
    """

    __tablename__ = "money_budgets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String(50), nullable=False)
    monthly_limit_encrypted = Column(Text, nullable=False)
    current_spend_encrypted = Column(Text, nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    user_relationship = relationship("User", foreign_keys=[user_id], lazy="select")


class MoneyPattern(Base):
    """Detected spending pattern for a user.

    Data Classification: INTERNAL (pattern_type and severity are not PII)
    """

    __tablename__ = "money_patterns"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    pattern_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(Float, nullable=False, default=0.0)
    detected_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    segment_code = Column(String(2), nullable=False)


class FinancialGoal(Base):
    """User-defined financial goal with encrypted amounts.

    Data Classification: FINANCIAL
    """

    __tablename__ = "money_financial_goals"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name_encrypted = Column(Text, nullable=False)
    target_amount_encrypted = Column(Text, nullable=False)
    current_amount_encrypted = Column(Text, nullable=False)
    deadline = Column(DateTime, nullable=True)
    is_active = Column(Integer, default=1)

    user_relationship = relationship("User", foreign_keys=[user_id], lazy="select")


class RecurringExpense(Base):
    """Recurring expense (rent, subscriptions, etc.) with encrypted amounts.

    Data Classification: FINANCIAL
    """

    __tablename__ = "money_recurring_expenses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name_encrypted = Column(Text, nullable=False)
    amount_encrypted = Column(Text, nullable=False)
    frequency = Column(String(20), nullable=False, default="monthly")
    next_due = Column(DateTime, nullable=True)

    user_relationship = relationship("User", foreign_keys=[user_id], lazy="select")


class SafeToSpend(Base):
    """Snapshot of the anti-budget calculation.

    Data Classification: FINANCIAL
    """

    __tablename__ = "money_safe_to_spend"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    income_encrypted = Column(Text, nullable=False)
    committed_encrypted = Column(Text, nullable=False)
    safe_amount_encrypted = Column(Text, nullable=False)
    calculated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class MoneyCoachingLog(Base):
    """Coaching messages sent to the user regarding their finances.

    Data Classification: ART_9_SPECIAL (coaching_text may reference health/neuro context)
    """

    __tablename__ = "money_coaching_log"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    coaching_text_encrypted = Column(Text, nullable=False)
    trigger_pattern = Column(String(50), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


# =============================================================================
# Data classes for in-memory processing
# =============================================================================

@dataclass
class ParsedTransaction:
    """Transaction parsed from natural language before storage."""

    amount: float
    currency: str
    category: str
    description: str
    is_income: bool
    transaction_date: date


@dataclass
class SafeToSpendResult:
    """Result of the anti-budget calculation."""

    income: float
    committed: float
    safe_amount: float


@dataclass
class DetectedPattern:
    """A detected money pattern for a specific segment."""

    pattern_type: PatternType
    description: str
    severity: float  # 0.0 to 1.0
    segment_code: str
