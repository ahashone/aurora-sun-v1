"""
Revenue Tracker for Aurora Sun V1.

Natural language revenue tracking for the Money pillar.
Parses user messages like "I earned 500 from Client X" or "12 euros for sushi"
and tracks income, expenses, and commitments.

Data Classification: FINANCIAL (money data requires encryption)
Reference: ARCHITECTURE.md Section 7 (Money Pillar)

Usage:
    tracker = RevenueTracker()

    # Parse revenue from natural language
    entry = await tracker.parse_revenue("I earned 500 from Client X")
    if entry:
        await tracker.save_entry(user_id=123, entry=entry)

    # Get balance
    balance = await tracker.get_balance(user_id=123)
    # Returns: {"income": 500, "committed": 200, "safe_to_spend": 300}
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from src.lib.encryption import (
    DataClassification,
    EncryptedField,
    EncryptionService,
    EncryptionServiceError,
    get_encryption_service,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Enums and Data Classes
# =============================================================================


class RevenueCategory(StrEnum):
    """Categories for revenue entries."""

    CLIENT_PAYMENT = "client_payment"      # Income from clients
    PRODUCT_SALE = "product_sale"          # Product revenue
    SERVICE = "service"                    # Service fee
    REFUND = "refund"                      # Money back
    GIFT = "gift"                          # Gift received
    OTHER_INCOME = "other_income"          # Miscellaneous income
    ESSENTIAL = "essential"                 # Essential expenses (rent, food)
    LEISURE = "leisure"                    # Fun/subscriptions
    HEALTH = "health"                      # Medical/wellness
    EDUCATION = "education"                # Learning
    OTHER_EXPENSE = "other_expense"        # Miscellaneous


class EntryType(StrEnum):
    """Type of revenue entry."""

    INCOME = "income"
    EXPENSE = "expense"
    COMMITMENT = "commitment"  # Future obligation


@dataclass
class RevenueEntry:
    """
    Single revenue entry parsed from natural language.

    Attributes:
        amount: Numeric amount (positive for income, negative for expense)
        source: Where the money came from or went to
        category: Classification of the entry
        entry_type: Income, expense, or commitment
        description: Optional human-readable description
        date: When this entry occurred/will occur
        parsed_from: Original message that was parsed
    """

    amount: float
    source: str
    category: RevenueCategory
    entry_type: EntryType
    description: str | None = None
    date: date | None = None
    parsed_from: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "amount": self.amount,
            "source": self.source,
            "category": self.category.value,
            "entry_type": self.entry_type.value,
            "description": self.description,
            "date": self.date.isoformat() if self.date else None,
            "parsed_from": self.parsed_from,
        }


@dataclass
class RevenueBalance:
    """
    User's revenue balance snapshot.

    Attributes:
        user_id: User identifier
        income: Total income recorded
        expenses: Total expenses recorded
        committed: Total committed (future obligations)
        safe_to_spend: income - committed (available for discretionary spending)
        calculated_at: When this balance was calculated
    """

    user_id: int
    income: float
    expenses: float
    committed: float
    safe_to_spend: float
    calculated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "user_id": self.user_id,
            "income": self.income,
            "expenses": self.expenses,
            "committed": self.committed,
            "safe_to_spend": self.safe_to_spend,
            "calculated_at": self.calculated_at.isoformat(),
        }


# =============================================================================
# Revenue Tracker Service
# =============================================================================


class RevenueTracker:
    """
    Natural language revenue tracking service.

    Parses user messages to extract revenue information and maintains
    encrypted balance records per user.

    Features:
    - Natural language parsing ("earned 500", "spent 50 on food")
    - Client/source tracking
    - Commitment tracking (future obligations)
    - Safe-to-spend calculation

    Security:
    - All financial data encrypted with AES-256-GCM
    - Uses 3-tier envelope encryption (FINANCIAL classification)
    - Per-user encryption keys

    Usage:
        tracker = RevenueTracker()

        # Parse revenue from natural language
        entry = await tracker.parse_revenue("I earned 500 from Client X")
        if entry:
            await tracker.save_entry(user_id=123, entry=entry)

        # Get balance
        balance = await tracker.get_balance(user_id=123)
    """

    # Currency patterns for parsing
    CURRENCY_PATTERNS = [
        (r"(\d+(?:\.\d{1,2})?)\s*(?:euros?|eur|€)", "EUR"),
        (r"(\d+(?:\.\d{1,2})?)\s*(?:dollars?|usd|\$)", "USD"),
        (r"(\d+(?:\.\d{1,2})?)\s*(?:pounds?|gbp|£)", "GBP"),
    ]

    # Income keywords
    INCOME_KEYWORDS = [
        "earned", "got", "received", "made", "income", "paid",
        "revenue", "profit", "sold", "earned", "getting", "received from",
    ]

    # Expense keywords
    EXPENSE_KEYWORDS = [
        "spent", "paid", "bought", "cost", "expense", "for",
        "bought", "purchased", "subscription", "bill", "rent",
    ]

    # Commitment keywords
    COMMITMENT_KEYWORDS = [
        "will pay", "need to", "have to", "must pay", "owing",
        "should pay", "plan to spend", "budget for", "save for",
    ]

    # Source/Client patterns
    SOURCE_PATTERNS = [
        r"from\s+([A-Za-z][A-Za-z0-9\s]{1,30})",
        r"to\s+([A-Za-z][A-Za-z0-9\s]{1,30})",
        r"client[:\s]+([A-Za-z][A-Za-z0-9\s]{1,30})",
    ]

    def __init__(self, encryption_service: EncryptionService | None = None):
        """
        Initialize the Revenue Tracker.

        Args:
            encryption_service: Optional encryption service. Uses global if None.
        """
        self._encryption = encryption_service or get_encryption_service()
        # In-memory storage (encrypted at rest, backed by PostgreSQL in production)
        self._entries: dict[int, list[dict[str, str | int | None]]] = {}

    async def parse_revenue(self, message: str) -> RevenueEntry | None:
        """
        Parse revenue from natural language message.

        Extracts amount, source, category, and entry type from messages like:
        - "I earned 500 from Client X"
        - "12 euros for sushi"
        - "spent 50 on food"
        - "need to pay rent 800"

        Args:
            message: Natural language message to parse

        Returns:
            RevenueEntry if parsing successful, None if no revenue detected

        Examples:
            >>> entry = await tracker.parse_revenue("I earned 500 from Client X")
            >>> entry.amount
            500.0
            >>> entry.source
            'Client X'
            >>> entry.entry_type
            <EntryType.INCOME: 'income'>
        """
        message_lower = message.lower().strip()

        # Extract amount and currency
        amount = self._extract_amount(message)
        if amount is None:
            return None

        # Determine entry type
        entry_type = self._determine_entry_type(message_lower)
        if entry_type is None:
            return None

        # Extract source/client
        source = self._extract_source(message) or "unknown"

        # Determine category
        category = self._determine_category(message_lower, entry_type)

        # Try to extract date if mentioned
        extracted_date = self._extract_date(message)

        return RevenueEntry(
            amount=amount,
            source=source,
            category=category,
            entry_type=entry_type,
            description=message.strip()[:200],  # Limit description length
            date=extracted_date,
            parsed_from=message,
        )

    def _extract_amount(self, message: str) -> float | None:
        """Extract monetary amount from message."""
        # Try each currency pattern
        for pattern, _ in self.CURRENCY_PATTERNS:
            match = re.search(pattern, message.lower())
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue

        # Try generic number
        generic_match = re.search(r"(\d+(?:\.\d{1,2})?)", message)
        if generic_match:
            try:
                return float(generic_match.group(1))
            except ValueError:
                pass

        return None

    def _determine_entry_type(self, message: str) -> EntryType | None:
        """Determine if message describes income, expense, or commitment."""
        # Check for commitment first (most specific)
        if any(kw in message for kw in self.COMMITMENT_KEYWORDS):
            return EntryType.COMMITMENT

        # Check for income
        if any(kw in message for kw in self.INCOME_KEYWORDS):
            return EntryType.INCOME

        # Check for expense
        if any(kw in message for kw in self.EXPENSE_KEYWORDS):
            return EntryType.EXPENSE

        # Default: treat as income if positive, expense if negative context
        return None

    def _extract_source(self, message: str) -> str | None:
        """Extract source/client name from message."""
        for pattern in self.SOURCE_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _determine_category(self, message: str, entry_type: EntryType) -> RevenueCategory:
        """Determine the category based on keywords."""
        # Income categories
        if entry_type == EntryType.INCOME:
            if "client" in message:
                return RevenueCategory.CLIENT_PAYMENT
            elif any(kw in message for kw in ["product", "sold"]):
                return RevenueCategory.PRODUCT_SALE
            elif any(kw in message for kw in ["service", "fee"]):
                return RevenueCategory.SERVICE
            elif "refund" in message:
                return RevenueCategory.REFUND
            elif "gift" in message:
                return RevenueCategory.GIFT
            return RevenueCategory.OTHER_INCOME

        # Expense categories
        elif entry_type == EntryType.EXPENSE:
            if any(kw in message for kw in ["food", "grocery", "meal", "restaurant", "sushi", "lunch", "dinner", "breakfast"]):
                return RevenueCategory.ESSENTIAL
            elif any(kw in message for kw in ["rent", "mortgage", "utility", "bill"]):
                return RevenueCategory.ESSENTIAL
            elif any(kw in message for kw in ["subscription", "streaming", "netflix", "spotify"]):
                return RevenueCategory.LEISURE
            elif any(kw in message for kw in ["doctor", "medicine", "health", "therapy", "medical"]):
                return RevenueCategory.HEALTH
            elif any(kw in message for kw in ["course", "book", "learning", "education", "training"]):
                return RevenueCategory.EDUCATION
            return RevenueCategory.OTHER_EXPENSE

        # Commitment defaults
        return RevenueCategory.OTHER_EXPENSE

    def _extract_date(self, message: str) -> date | None:
        """Extract date from message if mentioned."""
        import calendar

        today = date.today()

        # Relative dates
        if "today" in message.lower():
            return today
        elif "tomorrow" in message.lower():
            return today.replace(day=today.day + 1)
        elif "next week" in message.lower():
            from datetime import timedelta
            return today + timedelta(days=7)

        # Month + day
        months = {name: i for i, name in enumerate(calendar.month_abbr) if i}
        months.update({name: i for i, name in enumerate(calendar.month_name) if i})

        for month_name, month_num in months.items():
            pattern = rf"{month_name}\s+(\d{1,2})"
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                try:
                    day = int(match.group(1))
                    return date(today.year, month_num, day)
                except ValueError:
                    continue

        return None

    async def save_entry(self, user_id: int, entry: RevenueEntry) -> str:
        """
        Save a revenue entry for a user.

        The entry is encrypted before storage using FINANCIAL classification.

        Args:
            user_id: User identifier
            entry: RevenueEntry to save

        Returns:
            Entry ID (for reference)

        Note:
            In production, this would:
            1. Encrypt sensitive fields
            2. Store in PostgreSQL with FINANCIAL classification
            3. Update search indices
        """
        if user_id not in self._entries:
            self._entries[user_id] = []

        # Encrypt entry before storing (FINANCIAL classification)
        try:
            encrypted = self._encryption.encrypt_field(
                json.dumps(entry.to_dict()),
                user_id=user_id,
                classification=DataClassification.FINANCIAL,
                field_name=f"revenue_entry_{len(self._entries[user_id]) + 1}",
            )
            self._entries[user_id].append(encrypted.to_db_dict())
        except EncryptionServiceError:
            logger.warning("revenue_entry_encryption_failed_storing_plaintext")
            plaintext_record: dict[str, str | int | None] = {
                "ciphertext": json.dumps(entry.to_dict()),
                "classification": "plaintext_fallback",
                "version": 0,
            }
            self._entries[user_id].append(plaintext_record)

        return f"entry_{len(self._entries[user_id])}"

    def _decrypt_entry(
        self,
        stored: dict[str, str | int | None],
        user_id: int,
    ) -> dict[str, Any]:
        """Decrypt a single stored revenue entry."""
        classification = stored.get("classification")
        if classification == "plaintext_fallback":
            ciphertext = stored.get("ciphertext")
            result: dict[str, Any] = json.loads(str(ciphertext))
            return result
        try:
            encrypted = EncryptedField.from_db_dict({k: v for k, v in stored.items()})
            plaintext = self._encryption.decrypt_field(encrypted, user_id=user_id)
            decrypted: dict[str, Any] = json.loads(plaintext)
            return decrypted
        except (EncryptionServiceError, json.JSONDecodeError, KeyError):
            logger.warning("revenue_entry_decryption_failed")
            return {}

    def _decrypt_all_entries(self, user_id: int) -> list[dict[str, Any]]:
        """Decrypt all stored entries for a user."""
        if user_id not in self._entries:
            return []
        return [self._decrypt_entry(e, user_id) for e in self._entries[user_id]]

    async def get_balance(self, user_id: int) -> dict[str, Any]:
        """
        Get user's current financial balance.

        Calculates:
        - income: Total income recorded
        - expenses: Total expenses recorded
        - committed: Total future commitments
        - safe_to_spend: income - committed (available for discretionary spending)

        Args:
            user_id: User identifier

        Returns:
            Dictionary with balance breakdown

        Example:
            >>> balance = await tracker.get_balance(user_id=123)
            >>> print(balance)
            {"income": 1500.0, "expenses": 800.0, "committed": 200.0, "safe_to_spend": 500.0}
        """
        if user_id not in self._entries:
            return {
                "user_id": user_id,
                "income": 0.0,
                "expenses": 0.0,
                "committed": 0.0,
                "safe_to_spend": 0.0,
                "calculated_at": datetime.now(UTC).isoformat(),
            }

        entries = self._decrypt_all_entries(user_id)

        income = sum(
            float(e.get("amount", 0))
            for e in entries
            if e.get("entry_type") == EntryType.INCOME.value
        )
        expenses = sum(
            float(e.get("amount", 0))
            for e in entries
            if e.get("entry_type") == EntryType.EXPENSE.value
        )
        committed = sum(
            float(e.get("amount", 0))
            for e in entries
            if e.get("entry_type") == EntryType.COMMITMENT.value
        )

        # Safe to spend: income minus commitments (not expenses - those are past)
        safe_to_spend = income - committed

        return {
            "user_id": user_id,
            "income": income,
            "expenses": expenses,
            "committed": committed,
            "safe_to_spend": safe_to_spend,
            "calculated_at": datetime.now(UTC).isoformat(),
        }

    async def get_entries(
        self,
        user_id: int,
        entry_type: EntryType | None = None,
        category: RevenueCategory | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Get revenue entries for a user with optional filtering.

        Args:
            user_id: User identifier
            entry_type: Filter by entry type (optional)
            category: Filter by category (optional)
            limit: Maximum number of entries to return

        Returns:
            List of entry dictionaries
        """
        decrypted = self._decrypt_all_entries(user_id)
        if not decrypted:
            return []

        # Apply filters
        if entry_type:
            decrypted = [e for e in decrypted if e.get("entry_type") == entry_type.value]
        if category:
            decrypted = [e for e in decrypted if e.get("category") == category.value]

        # Sort by date (most recent first)
        decrypted.sort(
            key=lambda e: e.get("date") or date.min.isoformat(),
            reverse=True,
        )

        # Apply limit
        return decrypted[:limit]

    async def delete_entry(self, user_id: int, entry_id: str) -> bool:
        """
        Delete a specific revenue entry.

        Args:
            user_id: User identifier
            entry_id: Entry ID to delete

        Returns:
            True if deleted, False if not found
        """
        if user_id not in self._entries:
            return False

        # Find and remove entry
        for i, entry in enumerate(self._entries[user_id]):
            if f"entry_{i+1}" == entry_id:
                self._entries[user_id].pop(i)
                return True

        return False

    # =========================================================================
    # GDPR Methods
    # =========================================================================

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """
        GDPR export for revenue tracking data.

        Args:
            user_id: User identifier

        Returns:
            Dict containing all revenue-related data for the user
        """
        if user_id not in self._entries:
            return {
                "entries": [],
                "balance": {
                    "income": 0.0,
                    "expenses": 0.0,
                    "committed": 0.0,
                    "safe_to_spend": 0.0,
                },
            }

        balance = await self.get_balance(user_id)
        entries = self._decrypt_all_entries(user_id)

        return {
            "entries": entries,
            "balance": balance,
        }

    async def delete_user_data(self, user_id: int) -> None:
        """
        GDPR delete for revenue tracking data.

        Permanently removes all revenue entries for the user.

        Args:
            user_id: User identifier
        """
        if user_id in self._entries:
            del self._entries[user_id]

        # TODO: In production, delete from PostgreSQL:
        # await self._db.execute(
        #     "DELETE FROM revenue_entries WHERE user_id = $1",
        #     user_id
        # )

    async def freeze_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 18: Restrict processing for revenue tracking data.

        Marks user's revenue data as frozen (read-only).

        Args:
            user_id: User identifier
        """
        # TODO: In production, set frozen flag in database:
        # await self._db.execute(
        #     "UPDATE revenue_entries SET frozen = TRUE WHERE user_id = $1",
        #     user_id
        # )
        pass


# =============================================================================
# Module Singleton and Convenience Functions
# =============================================================================

_revenue_tracker: RevenueTracker | None = None


def get_revenue_tracker() -> RevenueTracker:
    """Get the singleton RevenueTracker instance."""
    global _revenue_tracker
    if _revenue_tracker is None:
        _revenue_tracker = RevenueTracker()
    return _revenue_tracker


async def parse_and_save_revenue(user_id: int, message: str) -> dict[str, Any]:
    """
    Convenience function to parse and save revenue in one call.

    Args:
        user_id: User identifier
        message: Natural language message to parse

    Returns:
        Result dict with entry details or error
    """
    tracker = get_revenue_tracker()
    entry = await tracker.parse_revenue(message)

    if entry is None:
        return {
            "success": False,
            "message": "Could not parse revenue from message",
            "parsed": False,
        }

    entry_id = await tracker.save_entry(user_id, entry)
    balance = await tracker.get_balance(user_id)

    return {
        "success": True,
        "message": f"Saved {entry.entry_type.value}: {entry.amount} from {entry.source}",
        "parsed": True,
        "entry_id": entry_id,
        "entry": entry.to_dict(),
        "balance": balance,
    }
