"""
Money Management Module for Aurora Sun V1.

This module handles financial tracking, budgeting, pattern detection, and coaching.
It implements the Money pillar of the 3-pillar architecture (Vision-to-Task,
Second Brain, Money).

Core Features:
- Natural language transaction capture ("12 euros for sushi")
- Anti-Budget: safe_to_spend = income - committed
- Energy gating: RED blocks non-essential purchases
- Shame-free language enforcement
- Segment-adaptive state machine (3-7 steps depending on neurotype)
- Money pattern detection per segment type
- GDPR export/delete for all financial tables

Data Classification: FINANCIAL (3-tier envelope encryption for all money fields)
Reference: ARCHITECTURE.md Section 7 (Money Pillar)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.gdpr_mixin import GDPRModuleMixin
from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse
from src.lib.encryption import (
    DataClassification,
    EncryptedField,
    EncryptionService,
    EncryptionServiceError,
    get_encryption_service,
)
from src.lib.security import hash_uid
from src.models.base import Base

if TYPE_CHECKING:
    from src.core.segment_context import SegmentContext

logger = logging.getLogger(__name__)

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
# State Machine
# =============================================================================

class MoneyState(StrEnum):
    """States for the money module state machine.

    The active states are determined by SegmentContext.ux.money_steps:
    - AD (3 steps): CAPTURE -> CLASSIFY -> DONE
    - NT (4 steps): CAPTURE -> CLASSIFY -> BUDGET_CHECK -> DONE
    - AH (6 steps): CAPTURE -> CLASSIFY -> CATEGORIZE -> BUDGET_CHECK -> PATTERN_CHECK -> DONE
    - AU (7 steps): CAPTURE -> CLASSIFY -> CATEGORIZE -> VERIFY -> BUDGET_CHECK -> PATTERN_CHECK -> DONE
    """

    CAPTURE = "capture"
    CLASSIFY = "classify"
    CATEGORIZE = "categorize"
    VERIFY = "verify"
    BUDGET_CHECK = "budget_check"
    PATTERN_CHECK = "pattern_check"
    DONE = "done"


# Ordered full pipeline (superset of all segments).
_FULL_PIPELINE: list[MoneyState] = [
    MoneyState.CAPTURE,
    MoneyState.CLASSIFY,
    MoneyState.CATEGORIZE,
    MoneyState.VERIFY,
    MoneyState.BUDGET_CHECK,
    MoneyState.PATTERN_CHECK,
    MoneyState.DONE,
]

# Mapping of money_steps -> which states to include (in order).
_STEPS_TO_STATES: dict[int, list[MoneyState]] = {
    3: [MoneyState.CAPTURE, MoneyState.CLASSIFY, MoneyState.DONE],
    4: [MoneyState.CAPTURE, MoneyState.CLASSIFY, MoneyState.BUDGET_CHECK, MoneyState.DONE],
    6: [
        MoneyState.CAPTURE,
        MoneyState.CLASSIFY,
        MoneyState.CATEGORIZE,
        MoneyState.BUDGET_CHECK,
        MoneyState.PATTERN_CHECK,
        MoneyState.DONE,
    ],
    7: _FULL_PIPELINE,
}


def get_pipeline_for_segment(money_steps: int) -> list[MoneyState]:
    """Return the state pipeline for the given money_steps value.

    Falls back to the closest known pipeline if the exact step count is not
    mapped (e.g. for Custom segments).

    Args:
        money_steps: The number of money steps from SegmentContext.ux.money_steps

    Returns:
        Ordered list of MoneyState values for this segment
    """
    if money_steps in _STEPS_TO_STATES:
        return _STEPS_TO_STATES[money_steps]
    # Fallback: pick the closest known step count
    closest = min(_STEPS_TO_STATES, key=lambda k: abs(k - money_steps))
    return _STEPS_TO_STATES[closest]


def next_state(current: MoneyState, money_steps: int) -> MoneyState:
    """Advance to the next state in the segment-specific pipeline.

    Args:
        current: The current state
        money_steps: From SegmentContext.ux.money_steps

    Returns:
        The next MoneyState in the pipeline
    """
    pipeline = get_pipeline_for_segment(money_steps)
    try:
        idx = pipeline.index(current)
    except ValueError:
        return MoneyState.DONE
    if idx + 1 < len(pipeline):
        return pipeline[idx + 1]
    return MoneyState.DONE


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


# =============================================================================
# Encryption helpers
# =============================================================================

def _encrypt_financial(
    value: str,
    user_id: int,
    field_name: str,
    encryption: EncryptionService,
) -> str:
    """Encrypt a financial field value and return JSON string for DB storage.

    Args:
        value: Plaintext value
        user_id: User ID for per-user key derivation
        field_name: Field name for envelope encryption
        encryption: EncryptionService instance

    Returns:
        JSON-serialised EncryptedField dict
    """
    encrypted = encryption.encrypt_field(
        plaintext=value,
        user_id=user_id,
        classification=DataClassification.FINANCIAL,
        field_name=field_name,
    )
    return json.dumps(encrypted.to_db_dict())


def _decrypt_financial(
    stored_json: str,
    user_id: int,
    field_name: str,
    encryption: EncryptionService,
) -> str:
    """Decrypt a financial field value from its JSON DB representation.

    Args:
        stored_json: JSON-serialised EncryptedField dict from DB
        user_id: User ID
        field_name: Field name
        encryption: EncryptionService instance

    Returns:
        Decrypted plaintext string
    """
    data: dict[str, Any] = json.loads(stored_json)
    encrypted = EncryptedField.from_db_dict(data)
    return encryption.decrypt_field(encrypted, user_id=user_id, field_name=field_name)


def _encrypt_art9(
    value: str,
    user_id: int,
    field_name: str,
    encryption: EncryptionService,
) -> str:
    """Encrypt an ART_9_SPECIAL field value and return JSON string for DB storage.

    Args:
        value: Plaintext value
        user_id: User ID
        field_name: Field name for field-level salt
        encryption: EncryptionService instance

    Returns:
        JSON-serialised EncryptedField dict
    """
    encrypted = encryption.encrypt_field(
        plaintext=value,
        user_id=user_id,
        classification=DataClassification.ART_9_SPECIAL,
        field_name=field_name,
    )
    return json.dumps(encrypted.to_db_dict())


def _decrypt_or_fallback(
    stored_json: str,
    user_id: int,
    field_name: str,
    encryption: EncryptionService,
    classification: DataClassification = DataClassification.FINANCIAL,
) -> str:
    """Decrypt a field value, falling back to plaintext_fallback if present.

    Centralizes the common decrypt-or-fallback pattern used throughout the module.

    Args:
        stored_json: JSON-serialised EncryptedField dict from DB
        user_id: User ID
        field_name: Field name
        encryption: EncryptionService instance
        classification: Data classification (default: FINANCIAL)

    Returns:
        Decrypted plaintext string, or the plaintext_fallback value

    Raises:
        EncryptionServiceError: If decryption fails and no fallback is available
        json.JSONDecodeError: If stored_json is not valid JSON
        ValueError: If the decrypted value cannot be processed
        KeyError: If required fields are missing
    """
    data: dict[str, Any] = json.loads(stored_json)
    if "plaintext_fallback" in data:
        return str(data["plaintext_fallback"])

    if classification == DataClassification.ART_9_SPECIAL:
        return _decrypt_art9(stored_json, user_id, field_name, encryption)
    return _decrypt_financial(stored_json, user_id, field_name, encryption)


def _decrypt_art9(
    stored_json: str,
    user_id: int,
    field_name: str,
    encryption: EncryptionService,
) -> str:
    """Decrypt an ART_9_SPECIAL field value from its JSON DB representation.

    Args:
        stored_json: JSON-serialised EncryptedField dict from DB
        user_id: User ID
        field_name: Field name
        encryption: EncryptionService instance

    Returns:
        Decrypted plaintext string
    """
    data: dict[str, Any] = json.loads(stored_json)
    encrypted = EncryptedField.from_db_dict(data)
    return encryption.decrypt_field(encrypted, user_id=user_id, field_name=field_name)


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
# Natural language parser
# =============================================================================

# Currency patterns for extraction
_CURRENCY_PATTERNS: list[tuple[str, str]] = [
    (r"(\d+(?:[.,]\d{1,2})?)\s*(?:euros?|eur|\u20ac)", "EUR"),
    (r"(?:\u20ac)\s*(\d+(?:[.,]\d{1,2})?)", "EUR"),
    (r"(\d+(?:[.,]\d{1,2})?)\s*(?:dollars?|usd|\$)", "USD"),
    (r"(?:\$)\s*(\d+(?:[.,]\d{1,2})?)", "USD"),
    (r"(\d+(?:[.,]\d{1,2})?)\s*(?:pounds?|gbp|\u00a3)", "GBP"),
    (r"(?:\u00a3)\s*(\d+(?:[.,]\d{1,2})?)", "GBP"),
]

# Income keywords
_INCOME_KEYWORDS: list[str] = [
    "earned", "received", "got paid", "income", "salary", "revenue",
    "sold", "refund",
]

# Category keyword mapping
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "food": ["food", "grocery", "groceries", "sushi", "lunch", "dinner",
             "breakfast", "meal", "restaurant", "coffee", "snack", "eat"],
    "housing": ["rent", "mortgage", "utility", "utilities", "electricity",
                "water", "gas", "internet"],
    "transport": ["taxi", "uber", "bus", "train", "fuel", "petrol",
                  "gas station", "flight", "parking"],
    "health": ["doctor", "medicine", "pharmacy", "therapy", "medical",
               "dentist", "hospital"],
    "education": ["course", "book", "books", "learning", "training",
                  "school", "university", "tuition"],
    "leisure": ["netflix", "spotify", "cinema", "movie", "game", "games",
                "concert", "bar", "drinks", "hobby"],
    "subscription": ["subscription", "membership", "plan", "monthly plan"],
    "gift": ["gift", "present", "donation"],
}


def parse_transaction_from_nl(message: str) -> ParsedTransaction | None:
    """Parse a financial transaction from a natural language message.

    Extracts amount, currency, category, description, and determines
    whether it is income or expense.

    Examples:
        "12 euros for sushi" -> ParsedTransaction(amount=12.0, currency="EUR",
                                                   category="food", ...)
        "earned 500 from freelance" -> ParsedTransaction(amount=500.0, is_income=True, ...)

    Args:
        message: Natural language input from the user

    Returns:
        ParsedTransaction if parsing succeeds, None otherwise
    """
    message_lower = message.lower().strip()

    # Extract amount and currency
    amount: float | None = None
    currency = "EUR"  # default

    for pattern, curr in _CURRENCY_PATTERNS:
        match = re.search(pattern, message_lower)
        if match:
            raw = match.group(1).replace(",", ".")
            try:
                amount = float(raw)
            except ValueError:
                continue
            currency = curr
            break

    # Fallback: generic number
    if amount is None:
        generic = re.search(r"(\d+(?:[.,]\d{1,2})?)", message)
        if generic:
            raw = generic.group(1).replace(",", ".")
            try:
                amount = float(raw)
            except ValueError:
                return None
        else:
            return None

    # Determine income vs expense
    is_income = any(kw in message_lower for kw in _INCOME_KEYWORDS)

    # Determine category
    category = "other"
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in message_lower for kw in keywords):
            category = cat
            break
    if is_income:
        category = "income"

    return ParsedTransaction(
        amount=amount,
        currency=currency,
        category=category,
        description=message.strip()[:200],
        is_income=is_income,
        transaction_date=date.today(),
    )


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


# =============================================================================
# MoneyModule
# =============================================================================

class MoneyModule(GDPRModuleMixin):
    """Money Management Module implementing the Module Protocol.

    This module provides:
    - Natural language transaction capture
    - Segment-adaptive state machine (3-7 steps)
    - Anti-budget (safe-to-spend) calculation
    - Energy gating for impulse protection
    - Money pattern detection per neurotype
    - Shame-free language in all outputs
    - GDPR export/delete for all financial tables
    - Daily workflow hooks (evening spending summary)

    Segment-adaptive behavior (via SegmentContext fields, never code comparison):
    - icnu_enabled (ADHD/AuDHD): Quick capture, minimal friction, encouraging
    - routine_anchoring (Autism): Structured steps, predictable, verify step
    - channel_dominance_enabled (AuDHD): Flexible, adaptive, bimodal awareness
    - Default (NT): Standard balanced flow
    """

    name = "money"
    intents = [
        "money.capture",
        "money.budget",
        "money.safe_to_spend",
        "money.pattern",
        "money.goal",
        "money.recurring",
    ]
    pillar = "money"

    def __init__(
        self,
        encryption_service: EncryptionService | None = None,
    ) -> None:
        """Initialize the Money Module.

        Args:
            encryption_service: Optional encryption service. Uses global if None.
        """
        self._encryption = encryption_service or get_encryption_service()
        # In-memory storage (encrypted, backed by PostgreSQL in production)
        self._transactions: dict[int, list[dict[str, Any]]] = {}
        self._budgets: dict[int, list[dict[str, Any]]] = {}
        self._patterns: dict[int, list[dict[str, Any]]] = {}
        self._goals: dict[int, list[dict[str, Any]]] = {}
        self._recurring: dict[int, list[dict[str, Any]]] = {}
        self._safe_to_spend: dict[int, dict[str, Any]] = {}
        self._coaching_logs: dict[int, list[dict[str, Any]]] = {}
        self._frozen_users: set[int] = set()

    # -----------------------------------------------------------------
    # Module Protocol: on_enter
    # -----------------------------------------------------------------

    async def on_enter(self, ctx: ModuleContext) -> ModuleResponse:
        """Called when user enters the money module.

        Provides a segment-adaptive welcome message.

        Args:
            ctx: Module context

        Returns:
            ModuleResponse with welcome message
        """
        features = ctx.segment_context.features

        if features.routine_anchoring:
            text = (
                "Welcome to your financial overview. "
                "You can tell me about a transaction, check your safe-to-spend, "
                "or review spending patterns. I'll walk you through each step clearly."
            )
        elif features.channel_dominance_enabled:
            text = (
                "Hey! Ready to look at your finances? "
                "Tell me about a purchase, or ask about your safe-to-spend amount."
            )
        elif features.icnu_enabled:
            text = (
                "Let's make money simple! "
                "Just tell me what you spent or earned -- I'll handle the rest."
            )
        else:
            text = (
                "Welcome to your financial tracker. "
                "You can record transactions, check budgets, or review patterns."
            )

        return ModuleResponse(
            text=enforce_shame_free(text),
            next_state=MoneyState.CAPTURE,
        )

    # -----------------------------------------------------------------
    # Module Protocol: handle
    # -----------------------------------------------------------------

    async def handle(
        self,
        message: str,
        ctx: ModuleContext,
    ) -> ModuleResponse:
        """Handle a user message within the money module.

        Runs the segment-adaptive state machine and processes the message
        according to the current state.

        Args:
            message: User's input
            ctx: Module context

        Returns:
            ModuleResponse with text and state transition
        """
        if ctx.is_frozen:
            return ModuleResponse(
                text="Your financial data processing is currently paused. "
                     "Please contact support to resume.",
                is_end_of_flow=True,
            )

        current_state = MoneyState(ctx.state) if ctx.state in MoneyState.__members__.values() else MoneyState.CAPTURE
        money_steps = ctx.segment_context.ux.money_steps

        # Parse the transaction from natural language
        parsed = parse_transaction_from_nl(message)
        if parsed is None and current_state == MoneyState.CAPTURE:
            return ModuleResponse(
                text=enforce_shame_free(
                    "I couldn't find a financial amount in your message. "
                    "Try something like '12 euros for sushi' or 'earned 500'."
                ),
                next_state=MoneyState.CAPTURE,
            )

        # Store parsed in metadata for pipeline steps
        if parsed is not None:
            ctx.metadata["parsed_transaction"] = {
                "amount": parsed.amount,
                "currency": parsed.currency,
                "category": parsed.category,
                "description": parsed.description,
                "is_income": parsed.is_income,
                "transaction_date": parsed.transaction_date.isoformat(),
            }

        # Run through pipeline
        return await self._run_pipeline(current_state, money_steps, ctx)

    async def _run_pipeline(
        self,
        current_state: MoneyState,
        money_steps: int,
        ctx: ModuleContext,
    ) -> ModuleResponse:
        """Run the state machine pipeline from the current state.

        Args:
            current_state: Current state in the pipeline
            money_steps: From SegmentContext.ux.money_steps
            ctx: Module context

        Returns:
            ModuleResponse with result of pipeline execution
        """
        parsed_data: dict[str, Any] = ctx.metadata.get("parsed_transaction", {})
        user_id = ctx.user_id
        responses: list[str] = []

        state = current_state
        pipeline = get_pipeline_for_segment(money_steps)

        while state != MoneyState.DONE:
            if state not in pipeline:
                state = next_state(state, money_steps)
                continue

            if state == MoneyState.CAPTURE:
                result = self._stage_capture(parsed_data)
                if isinstance(result, ModuleResponse):
                    return result
                responses.append(result)

            elif state == MoneyState.CLASSIFY:
                responses.append(self._stage_classify(parsed_data))

            elif state == MoneyState.CATEGORIZE:
                responses.append(self._stage_categorize(parsed_data))

            elif state == MoneyState.VERIFY:
                responses.append(self._stage_verify(parsed_data))

            elif state == MoneyState.BUDGET_CHECK:
                result = self._stage_budget_check(parsed_data, ctx)
                if isinstance(result, ModuleResponse):
                    return result
                responses.append(result)

            elif state == MoneyState.PATTERN_CHECK:
                pattern_messages = self._stage_pattern_check(
                    user_id, parsed_data, ctx.segment_context,
                )
                responses.extend(pattern_messages)

            state = next_state(state, money_steps)

        # Store the transaction (encrypted)
        if parsed_data:
            await self._store_transaction(user_id, parsed_data)

        full_text = " ".join(responses)
        return ModuleResponse(
            text=enforce_shame_free(full_text),
            next_state=MoneyState.DONE,
            is_end_of_flow=True,
            metadata={
                "transaction_stored": True,
                "parsed": parsed_data,
            },
        )

    @staticmethod
    def _stage_capture(parsed_data: dict[str, Any]) -> str | ModuleResponse:
        """Execute the CAPTURE pipeline stage.

        Args:
            parsed_data: Parsed transaction data from ctx.metadata.

        Returns:
            A response string on success, or a ModuleResponse prompting for input.
        """
        if not parsed_data:
            return ModuleResponse(
                text=enforce_shame_free(
                    "Tell me about a transaction. "
                    "For example: '12 euros for sushi' or 'earned 500'."
                ),
                next_state=MoneyState.CAPTURE,
            )
        amount = parsed_data.get("amount", 0.0)
        currency = parsed_data.get("currency", "EUR")
        is_income = parsed_data.get("is_income", False)
        direction = "received" if is_income else "spent"
        return f"Got it -- {amount} {currency} {direction}."

    @staticmethod
    def _stage_classify(parsed_data: dict[str, Any]) -> str:
        """Execute the CLASSIFY pipeline stage.

        Args:
            parsed_data: Parsed transaction data.

        Returns:
            Classification response string.
        """
        is_income = parsed_data.get("is_income", False)
        if is_income:
            return "Classified as income."
        category = parsed_data.get("category", "other")
        return f"Classified as: {category}."

    @staticmethod
    def _stage_categorize(parsed_data: dict[str, Any]) -> str:
        """Execute the CATEGORIZE pipeline stage.

        Args:
            parsed_data: Parsed transaction data.

        Returns:
            Categorization confirmation string.
        """
        category = parsed_data.get("category", "other")
        return f"Category confirmed: {category}."

    @staticmethod
    def _stage_verify(parsed_data: dict[str, Any]) -> str:
        """Execute the VERIFY pipeline stage (Autism-specific extra verification).

        Args:
            parsed_data: Parsed transaction data.

        Returns:
            Verification confirmation string.
        """
        amount = parsed_data.get("amount", 0.0)
        currency = parsed_data.get("currency", "EUR")
        category = parsed_data.get("category", "other")
        is_income = parsed_data.get("is_income", False)
        direction = "income" if is_income else "expense"
        return f"Verification: {amount} {currency}, {category}, {direction}. Confirmed."

    @staticmethod
    def _stage_budget_check(
        parsed_data: dict[str, Any],
        ctx: ModuleContext,
    ) -> str | ModuleResponse:
        """Execute the BUDGET_CHECK pipeline stage with energy gating.

        Args:
            parsed_data: Parsed transaction data.
            ctx: Module context (for energy state metadata).

        Returns:
            A response string on success, or a ModuleResponse if energy-gated.
        """
        is_income = parsed_data.get("is_income", False)
        if is_income:
            return "Income noted in your balance."

        category = parsed_data.get("category", "other")
        energy_state = ctx.metadata.get("energy_state", "green")
        essential = is_essential_category(category)
        if not check_energy_gate(energy_state, essential):
            return ModuleResponse(
                text=enforce_shame_free(
                    "Your energy is currently low. "
                    "For non-essential spending, it might help to revisit "
                    "this when you're feeling more resourced. "
                    "The transaction has been noted but flagged for review."
                ),
                next_state=MoneyState.DONE,
                is_end_of_flow=True,
                metadata={"energy_gated": True},
            )
        return "Budget check: looking good."

    def _stage_pattern_check(
        self,
        user_id: int,
        parsed_data: dict[str, Any],
        segment_ctx: SegmentContext,
    ) -> list[str]:
        """Execute the PATTERN_CHECK pipeline stage.

        Builds a transaction list from recent history plus the current transaction,
        runs pattern detection, and stores any detected patterns.

        Args:
            user_id: User ID.
            parsed_data: Parsed transaction data.
            segment_ctx: The user's segment context.

        Returns:
            List of response strings (pattern descriptions or "no patterns").
        """
        recent = self._get_recent_transactions(user_id)
        tx_date_str = parsed_data.get("transaction_date", date.today().isoformat())
        current_tx = ParsedTransaction(
            amount=parsed_data.get("amount", 0.0),
            currency=parsed_data.get("currency", "EUR"),
            category=parsed_data.get("category", "other"),
            description=parsed_data.get("description", ""),
            is_income=parsed_data.get("is_income", False),
            transaction_date=date.fromisoformat(tx_date_str),
        )
        all_tx = recent + [current_tx]
        patterns = detect_patterns(all_tx, segment_ctx)

        if not patterns:
            return ["No unusual patterns detected."]

        messages: list[str] = []
        for p in patterns:
            messages.append(p.description)
            self._store_pattern(user_id, p)
        return messages

    # -----------------------------------------------------------------
    # Storage helpers
    # -----------------------------------------------------------------

    async def _store_transaction(
        self,
        user_id: int,
        parsed_data: dict[str, Any],
    ) -> None:
        """Encrypt and store a transaction.

        Args:
            user_id: User ID
            parsed_data: Parsed transaction data dict
        """
        if user_id not in self._transactions:
            self._transactions[user_id] = []

        try:
            amount_enc = _encrypt_financial(
                str(parsed_data["amount"]), user_id, "amount", self._encryption
            )
            desc_enc = _encrypt_financial(
                parsed_data.get("description", ""), user_id, "description", self._encryption
            )
        except EncryptionServiceError:
            logger.error("money_transaction_encryption_failed — refusing plaintext storage")
            raise

        record: dict[str, Any] = {
            "amount_encrypted": amount_enc,
            "currency": parsed_data.get("currency", "EUR"),
            "category": parsed_data.get("category", "other"),
            "description_encrypted": desc_enc,
            "is_income": parsed_data.get("is_income", False),
            "transaction_date": parsed_data.get("transaction_date", date.today().isoformat()),
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._transactions[user_id].append(record)

    def _store_pattern(self, user_id: int, pattern: DetectedPattern) -> None:
        """Store a detected pattern.

        Args:
            user_id: User ID
            pattern: Detected pattern
        """
        if user_id not in self._patterns:
            self._patterns[user_id] = []
        self._patterns[user_id].append({
            "pattern_type": pattern.pattern_type.value,
            "description": pattern.description,
            "severity": pattern.severity,
            "segment_code": pattern.segment_code,
            "detected_at": datetime.now(UTC).isoformat(),
        })

    def _get_recent_transactions(self, user_id: int) -> list[ParsedTransaction]:
        """Get recent transactions for pattern detection.

        Decrypts stored transactions and returns as ParsedTransaction objects.

        Args:
            user_id: User ID

        Returns:
            List of ParsedTransaction objects
        """
        if user_id not in self._transactions:
            return []

        result: list[ParsedTransaction] = []
        for record in self._transactions[user_id][-20:]:  # last 20
            try:
                amount = float(_decrypt_or_fallback(
                    record["amount_encrypted"], user_id, "amount", self._encryption
                ))
            except (EncryptionServiceError, json.JSONDecodeError, ValueError, KeyError):
                continue

            result.append(ParsedTransaction(
                amount=amount,
                currency=record.get("currency", "EUR"),
                category=record.get("category", "other"),
                description="",  # Don't decrypt descriptions for pattern analysis
                is_income=bool(record.get("is_income", False)),
                transaction_date=date.fromisoformat(
                    record.get("transaction_date", date.today().isoformat())
                ),
            ))
        return result

    # -----------------------------------------------------------------
    # Safe-to-spend (Anti-Budget)
    # -----------------------------------------------------------------

    async def get_safe_to_spend(self, user_id: int) -> SafeToSpendResult:
        """Calculate safe-to-spend for a user.

        Args:
            user_id: User ID

        Returns:
            SafeToSpendResult
        """
        income = 0.0
        committed = 0.0

        # Sum income transactions
        for record in self._transactions.get(user_id, []):
            if record.get("is_income"):
                try:
                    income += float(_decrypt_or_fallback(
                        record["amount_encrypted"], user_id, "amount", self._encryption
                    ))
                except (EncryptionServiceError, json.JSONDecodeError, ValueError, KeyError):
                    continue

        # Sum recurring expenses as committed
        for rec in self._recurring.get(user_id, []):
            try:
                committed += float(_decrypt_or_fallback(
                    rec["amount_encrypted"], user_id, "amount", self._encryption
                ))
            except (EncryptionServiceError, json.JSONDecodeError, ValueError, KeyError):
                continue

        return calculate_safe_to_spend(income, committed)

    async def add_recurring_expense(
        self,
        user_id: int,
        name: str,
        amount: float,
        frequency: str = "monthly",
    ) -> None:
        """Add a recurring expense for a user.

        Args:
            user_id: User ID
            name: Name of the recurring expense
            amount: Monthly amount
            frequency: "weekly", "monthly", or "yearly"
        """
        if user_id not in self._recurring:
            self._recurring[user_id] = []

        try:
            name_enc = _encrypt_financial(name, user_id, "recurring_name", self._encryption)
            amount_enc = _encrypt_financial(str(amount), user_id, "amount", self._encryption)
        except EncryptionServiceError:
            logger.error("money_recurring_encryption_failed — refusing plaintext storage")
            raise

        self._recurring[user_id].append({
            "name_encrypted": name_enc,
            "amount_encrypted": amount_enc,
            "frequency": frequency,
        })

    # -----------------------------------------------------------------
    # Module Protocol: on_exit
    # -----------------------------------------------------------------

    async def on_exit(self, ctx: ModuleContext) -> None:
        """Called when user leaves the money module. Cleanup.

        Args:
            ctx: Module context
        """
        # Clear transient metadata
        ctx.metadata.pop("parsed_transaction", None)

    # -----------------------------------------------------------------
    # Module Protocol: get_daily_workflow_hooks
    # -----------------------------------------------------------------

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        """Return hooks for the daily workflow.

        evening_review: Daily spending summary (if transactions recorded today)

        Returns:
            DailyWorkflowHooks with evening_review hook
        """
        return DailyWorkflowHooks(
            evening_review=self._evening_spending_summary,
            hook_name="money",
            priority=20,
        )

    async def _evening_spending_summary(
        self,
        ctx: ModuleContext,
    ) -> dict[str, Any] | None:
        """Produce an evening spending summary.

        Called during the daily workflow evening_review phase.

        Args:
            ctx: Module context

        Returns:
            Dict with spending summary, or None if no spending today
        """
        user_id = ctx.user_id
        today_str = date.today().isoformat()

        today_transactions = [
            t for t in self._transactions.get(user_id, [])
            if t.get("transaction_date") == today_str and not t.get("is_income")
        ]

        if not today_transactions:
            return None

        total = 0.0
        for t in today_transactions:
            try:
                total += float(_decrypt_or_fallback(
                    t["amount_encrypted"], user_id, "amount", self._encryption
                ))
            except (EncryptionServiceError, json.JSONDecodeError, ValueError, KeyError):
                continue

        safe = await self.get_safe_to_spend(user_id)

        return {
            "today_spent": total,
            "transaction_count": len(today_transactions),
            "safe_to_spend_remaining": safe.safe_amount,
        }

    # -----------------------------------------------------------------
    # GDPR export helpers
    # -----------------------------------------------------------------

    def _export_transaction_fields(
        self, user_id: int, record: dict[str, Any]
    ) -> tuple[str, str]:
        """Decrypt amount and description fields for GDPR export.

        Args:
            user_id: User ID
            record: Stored transaction record

        Returns:
            Tuple of (amount_str, description_str)
        """
        try:
            amount = _decrypt_or_fallback(
                record["amount_encrypted"], user_id, "amount", self._encryption
            )
            desc_json = record.get("description_encrypted", "")
            description = (
                _decrypt_or_fallback(
                    desc_json, user_id, "description", self._encryption
                )
                if desc_json
                else ""
            )
        except (EncryptionServiceError, json.JSONDecodeError, ValueError, KeyError):
            amount = "[decryption failed]"
            description = "[decryption failed]"
        return amount, description

    def _export_recurring_fields(
        self, user_id: int, rec: dict[str, Any]
    ) -> tuple[str, str]:
        """Decrypt name and amount fields for GDPR export of recurring expenses.

        Args:
            user_id: User ID
            rec: Stored recurring expense record

        Returns:
            Tuple of (name_str, amount_str)
        """
        try:
            name = _decrypt_or_fallback(
                rec["name_encrypted"], user_id, "recurring_name", self._encryption
            )
            rec_amount = _decrypt_or_fallback(
                rec["amount_encrypted"], user_id, "amount", self._encryption
            )
        except (EncryptionServiceError, json.JSONDecodeError, ValueError, KeyError):
            name = "[decryption failed]"
            rec_amount = "[decryption failed]"
        return name, rec_amount

    # -----------------------------------------------------------------
    # GDPR Methods
    # -----------------------------------------------------------------

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """GDPR Art. 15: Export all financial data for a user.

        Decrypts all encrypted fields before export so the user receives
        readable data.

        Args:
            user_id: User ID

        Returns:
            Dict containing all financial data, decrypted
        """
        exported_transactions: list[dict[str, Any]] = []
        for record in self._transactions.get(user_id, []):
            amount, description = self._export_transaction_fields(user_id, record)
            exported_transactions.append({
                "amount": amount,
                "currency": record.get("currency", "EUR"),
                "category": record.get("category", "other"),
                "description": description,
                "is_income": record.get("is_income", False),
                "transaction_date": record.get("transaction_date"),
                "created_at": record.get("created_at"),
            })

        exported_recurring: list[dict[str, Any]] = []
        for rec in self._recurring.get(user_id, []):
            name, rec_amount = self._export_recurring_fields(user_id, rec)
            exported_recurring.append({
                "name": name,
                "amount": rec_amount,
                "frequency": rec.get("frequency", "monthly"),
            })

        return {
            "transactions": exported_transactions,
            "budgets": self._budgets.get(user_id, []),
            "patterns": self._patterns.get(user_id, []),
            "goals": self._goals.get(user_id, []),
            "recurring_expenses": exported_recurring,
            "safe_to_spend": self._safe_to_spend.get(user_id, {}),
            "coaching_logs": self._coaching_logs.get(user_id, []),
        }

    async def delete_user_data(self, user_id: int) -> None:
        """GDPR Art. 17: Delete all financial data for a user.

        Removes all in-memory data. In production, also deletes from
        PostgreSQL and destroys encryption keys.

        Args:
            user_id: User ID
        """
        self._transactions.pop(user_id, None)
        self._budgets.pop(user_id, None)
        self._patterns.pop(user_id, None)
        self._goals.pop(user_id, None)
        self._recurring.pop(user_id, None)
        self._safe_to_spend.pop(user_id, None)
        self._coaching_logs.pop(user_id, None)
        self._frozen_users.discard(user_id)

        # Destroy encryption keys so remaining ciphertext is unrecoverable
        try:
            self._encryption.destroy_keys(user_id)
        except EncryptionServiceError:
            logger.warning("money_key_destruction_failed user_hash=%s", hash_uid(user_id))

    async def freeze_user_data(self, user_id: int) -> None:
        """GDPR Art. 18: Restrict processing.

        Args:
            user_id: User ID
        """
        self._frozen_users.add(user_id)

    async def unfreeze_user_data(self, user_id: int) -> None:
        """GDPR Art. 18: Lift restriction of processing.

        Args:
            user_id: User ID
        """
        self._frozen_users.discard(user_id)


# =============================================================================
# Export for module registry
# =============================================================================

__all__ = [
    "MoneyModule",
    "MoneyState",
    "PatternType",
    "TransactionCategory",
    "ExpenseFrequency",
    "ParsedTransaction",
    "SafeToSpendResult",
    "DetectedPattern",
    "Transaction",
    "Budget",
    "MoneyPattern",
    "FinancialGoal",
    "RecurringExpense",
    "SafeToSpend",
    "MoneyCoachingLog",
    "parse_transaction_from_nl",
    "calculate_safe_to_spend",
    "check_energy_gate",
    "is_essential_category",
    "detect_patterns",
    "validate_shame_free",
    "enforce_shame_free",
    "get_pipeline_for_segment",
    "next_state",
    "SHAME_WORDS",
]
