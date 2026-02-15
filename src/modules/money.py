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
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.gdpr_mixin import GDPRModuleMixin
from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse
from src.lib.encryption import (
    EncryptionService,
    EncryptionServiceError,
    get_encryption_service,
)
from src.lib.security import hash_uid

# Import from sub-modules
from src.modules.money_encryption import (
    decrypt_or_fallback as _decrypt_or_fallback,
    encrypt_financial as _encrypt_financial,
)
from src.modules.money_models import (
    SHAME_WORDS,
    Budget,
    DetectedPattern,
    ExpenseFrequency,
    FinancialGoal,
    MoneyCoachingLog,
    MoneyPattern,
    ParsedTransaction,
    PatternType,
    RecurringExpense,
    SafeToSpend,
    SafeToSpendResult,
    Transaction,
    TransactionCategory,
)
from src.modules.money_parsing import parse_transaction_from_nl
from src.modules.money_patterns import (
    calculate_safe_to_spend,
    check_energy_gate,
    detect_patterns,
    enforce_shame_free,
    is_essential_category,
    validate_shame_free,
)
from src.modules.money_state import (
    MoneyState,
    get_pipeline_for_segment,
    next_state,
)

if TYPE_CHECKING:
    from src.core.segment_context import SegmentContext

logger = logging.getLogger(__name__)


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
        """Execute the CAPTURE pipeline stage."""
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
        """Execute the CLASSIFY pipeline stage."""
        is_income = parsed_data.get("is_income", False)
        if is_income:
            return "Classified as income."
        category = parsed_data.get("category", "other")
        return f"Classified as: {category}."

    @staticmethod
    def _stage_categorize(parsed_data: dict[str, Any]) -> str:
        """Execute the CATEGORIZE pipeline stage."""
        category = parsed_data.get("category", "other")
        return f"Category confirmed: {category}."

    @staticmethod
    def _stage_verify(parsed_data: dict[str, Any]) -> str:
        """Execute the VERIFY pipeline stage (Autism-specific extra verification)."""
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
        """Execute the BUDGET_CHECK pipeline stage with energy gating."""
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
        """Execute the PATTERN_CHECK pipeline stage."""
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

    async def _store_transaction(self, user_id: int, parsed_data: dict[str, Any]) -> None:
        """Encrypt and store a transaction."""
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
        """Store a detected pattern."""
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
        """Get recent transactions for pattern detection."""
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
        """Calculate safe-to-spend for a user."""
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
        self, user_id: int, name: str, amount: float, frequency: str = "monthly",
    ) -> None:
        """Add a recurring expense for a user."""
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
        """Called when user leaves the money module. Cleanup."""
        ctx.metadata.pop("parsed_transaction", None)

    # -----------------------------------------------------------------
    # Module Protocol: get_daily_workflow_hooks
    # -----------------------------------------------------------------

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        """Return hooks for the daily workflow."""
        return DailyWorkflowHooks(
            evening_review=self._evening_spending_summary,
            hook_name="money",
            priority=20,
        )

    async def _evening_spending_summary(self, ctx: ModuleContext) -> dict[str, Any] | None:
        """Produce an evening spending summary."""
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
        """Decrypt amount and description fields for GDPR export."""
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
        """Decrypt name and amount fields for GDPR export of recurring expenses."""
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
        """GDPR Art. 15: Export all financial data for a user."""
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
        """GDPR Art. 17: Delete all financial data for a user."""
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
        """GDPR Art. 18: Restrict processing."""
        self._frozen_users.add(user_id)

    async def unfreeze_user_data(self, user_id: int) -> None:
        """GDPR Art. 18: Lift restriction of processing."""
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
