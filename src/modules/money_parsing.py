"""
Money Module Natural Language Parser.

Handles parsing financial transactions from natural language messages.
Extracts amount, currency, category, description, and income/expense classification.

Examples:
    "12 euros for sushi" -> ParsedTransaction(amount=12.0, currency="EUR", category="food", ...)
    "earned 500 from freelance" -> ParsedTransaction(amount=500.0, is_income=True, ...)

Reference: money.py (main module)
"""

from __future__ import annotations

import re
from datetime import date

from src.modules.money_models import ParsedTransaction


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
