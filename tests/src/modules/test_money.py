"""
Unit tests for the Money Management Module.

Covers:
- State machine transitions per segment (AD, AU, AH, NT)
- Transaction capture from natural language
- Anti-budget calculation
- Pattern detection per segment type
- Shame-free language validation
- Encryption of financial data
- GDPR export (decrypt before export) and delete
- Energy gating behavior

30+ tests organized by feature area.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import date

import pytest

# Environment setup before application imports
os.environ.setdefault("AURORA_DEV_MODE", "1")
os.environ.setdefault(
    "AURORA_HASH_SALT",
    base64.b64encode(b"test-salt-for-hashing-32bytes!!").decode(),
)

from src.core.module_context import ModuleContext
from src.core.segment_context import SegmentContext
from src.lib.encryption import EncryptionService
from src.modules.money import (
    SHAME_WORDS,
    MoneyModule,
    MoneyState,
    ParsedTransaction,
    PatternType,
    calculate_safe_to_spend,
    check_energy_gate,
    detect_patterns,
    enforce_shame_free,
    get_pipeline_for_segment,
    is_essential_category,
    next_state,
    parse_transaction_from_nl,
    validate_shame_free,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def encryption_svc() -> EncryptionService:
    """Provide an EncryptionService with a deterministic test key."""
    return EncryptionService(master_key=b"test-master-key-for-aurora-sun!!")


@pytest.fixture()
def money_module(encryption_svc: EncryptionService) -> MoneyModule:
    """Provide a MoneyModule backed by the test EncryptionService."""
    return MoneyModule(encryption_service=encryption_svc)


@pytest.fixture()
def ad_context() -> SegmentContext:
    """ADHD segment context."""
    return SegmentContext.from_code("AD")


@pytest.fixture()
def au_context() -> SegmentContext:
    """Autism segment context."""
    return SegmentContext.from_code("AU")


@pytest.fixture()
def ah_context() -> SegmentContext:
    """AuDHD segment context."""
    return SegmentContext.from_code("AH")


@pytest.fixture()
def nt_context() -> SegmentContext:
    """Neurotypical segment context."""
    return SegmentContext.from_code("NT")


def _make_ctx(
    segment: SegmentContext,
    state: str = "capture",
    user_id: int = 1,
    energy_state: str = "green",
) -> ModuleContext:
    """Helper: create a ModuleContext for the money module."""
    return ModuleContext(
        user_id=user_id,
        segment_context=segment,
        state=state,
        session_id="test-session",
        language="en",
        module_name="money",
        metadata={"energy_state": energy_state},
    )


# =============================================================================
# 1. State Machine Transitions Per Segment
# =============================================================================


class TestStateMachine:
    """Test segment-adaptive state machine pipelines."""

    def test_ad_pipeline_has_3_steps(self, ad_context: SegmentContext) -> None:
        """ADHD segment should have 3 steps: CAPTURE -> CLASSIFY -> DONE."""
        pipeline = get_pipeline_for_segment(ad_context.ux.money_steps)
        assert len(pipeline) == 3
        assert pipeline == [MoneyState.CAPTURE, MoneyState.CLASSIFY, MoneyState.DONE]

    def test_au_pipeline_has_7_steps(self, au_context: SegmentContext) -> None:
        """Autism segment should have 7 steps (full pipeline)."""
        pipeline = get_pipeline_for_segment(au_context.ux.money_steps)
        assert len(pipeline) == 7
        assert MoneyState.VERIFY in pipeline
        assert MoneyState.PATTERN_CHECK in pipeline

    def test_ah_pipeline_has_6_steps(self, ah_context: SegmentContext) -> None:
        """AuDHD segment should have 6 steps (no VERIFY)."""
        pipeline = get_pipeline_for_segment(ah_context.ux.money_steps)
        assert len(pipeline) == 6
        assert MoneyState.VERIFY not in pipeline
        assert MoneyState.PATTERN_CHECK in pipeline

    def test_nt_pipeline_has_4_steps(self, nt_context: SegmentContext) -> None:
        """NT segment should have 4 steps: CAPTURE -> CLASSIFY -> BUDGET_CHECK -> DONE."""
        pipeline = get_pipeline_for_segment(nt_context.ux.money_steps)
        assert len(pipeline) == 4
        assert pipeline == [
            MoneyState.CAPTURE,
            MoneyState.CLASSIFY,
            MoneyState.BUDGET_CHECK,
            MoneyState.DONE,
        ]

    def test_next_state_ad(self, ad_context: SegmentContext) -> None:
        """next_state advances correctly for ADHD pipeline."""
        steps = ad_context.ux.money_steps
        assert next_state(MoneyState.CAPTURE, steps) == MoneyState.CLASSIFY
        assert next_state(MoneyState.CLASSIFY, steps) == MoneyState.DONE

    def test_next_state_au(self, au_context: SegmentContext) -> None:
        """next_state advances correctly for Autism pipeline."""
        steps = au_context.ux.money_steps
        assert next_state(MoneyState.CAPTURE, steps) == MoneyState.CLASSIFY
        assert next_state(MoneyState.CLASSIFY, steps) == MoneyState.CATEGORIZE
        assert next_state(MoneyState.CATEGORIZE, steps) == MoneyState.VERIFY
        assert next_state(MoneyState.VERIFY, steps) == MoneyState.BUDGET_CHECK
        assert next_state(MoneyState.BUDGET_CHECK, steps) == MoneyState.PATTERN_CHECK
        assert next_state(MoneyState.PATTERN_CHECK, steps) == MoneyState.DONE

    def test_next_state_done_stays_done(self) -> None:
        """DONE state stays DONE regardless of money_steps."""
        assert next_state(MoneyState.DONE, 3) == MoneyState.DONE
        assert next_state(MoneyState.DONE, 7) == MoneyState.DONE

    def test_fallback_for_unknown_steps(self) -> None:
        """Unknown money_steps value falls back to closest known pipeline."""
        pipeline_5 = get_pipeline_for_segment(5)
        # 5 is closest to 4 or 6; should pick one
        assert len(pipeline_5) in (4, 6)

    def test_all_pipelines_start_with_capture(self) -> None:
        """All pipelines start with CAPTURE."""
        for steps in (3, 4, 6, 7):
            pipeline = get_pipeline_for_segment(steps)
            assert pipeline[0] == MoneyState.CAPTURE

    def test_all_pipelines_end_with_done(self) -> None:
        """All pipelines end with DONE."""
        for steps in (3, 4, 6, 7):
            pipeline = get_pipeline_for_segment(steps)
            assert pipeline[-1] == MoneyState.DONE


# =============================================================================
# 2. Transaction Capture from Natural Language
# =============================================================================


class TestNaturalLanguageParser:
    """Test natural language transaction parsing."""

    def test_euros_for_sushi(self) -> None:
        """Parse '12 euros for sushi' correctly."""
        result = parse_transaction_from_nl("12 euros for sushi")
        assert result is not None
        assert result.amount == 12.0
        assert result.currency == "EUR"
        assert result.category == "food"
        assert result.is_income is False

    def test_euro_symbol(self) -> None:
        """Parse amount with euro symbol."""
        result = parse_transaction_from_nl("spent 25.50\u20ac on groceries")
        assert result is not None
        assert result.amount == 25.50
        assert result.currency == "EUR"

    def test_dollar_amount(self) -> None:
        """Parse dollar amounts."""
        result = parse_transaction_from_nl("15 dollars for coffee")
        assert result is not None
        assert result.amount == 15.0
        assert result.currency == "USD"

    def test_income_detection(self) -> None:
        """Detect income correctly."""
        result = parse_transaction_from_nl("earned 500 euros from freelance")
        assert result is not None
        assert result.is_income is True
        assert result.amount == 500.0
        assert result.category == "income"

    def test_no_amount_returns_none(self) -> None:
        """Return None when no amount found."""
        result = parse_transaction_from_nl("just checking my balance")
        assert result is None

    def test_health_category(self) -> None:
        """Detect health category."""
        result = parse_transaction_from_nl("45 euros for doctor visit")
        assert result is not None
        assert result.category == "health"

    def test_transport_category(self) -> None:
        """Detect transport category."""
        result = parse_transaction_from_nl("paid 12 euros for taxi")
        assert result is not None
        assert result.category == "transport"

    def test_leisure_category(self) -> None:
        """Detect leisure category."""
        result = parse_transaction_from_nl("15 euros for netflix subscription")
        assert result is not None
        # Should detect subscription or leisure
        assert result.category in ("subscription", "leisure")

    def test_comma_decimal(self) -> None:
        """Parse comma-separated decimal amounts (European format)."""
        result = parse_transaction_from_nl("12,50 euros for lunch")
        assert result is not None
        assert result.amount == 12.5

    def test_transaction_date_is_today(self) -> None:
        """Default transaction date is today."""
        result = parse_transaction_from_nl("5 euros for snack")
        assert result is not None
        assert result.transaction_date == date.today()


# =============================================================================
# 3. Anti-Budget Calculation
# =============================================================================


class TestAntiBudget:
    """Test the anti-budget (safe-to-spend) calculation."""

    def test_basic_calculation(self) -> None:
        """safe_to_spend = income - committed."""
        result = calculate_safe_to_spend(income=2000.0, committed=1500.0)
        assert result.safe_amount == 500.0
        assert result.income == 2000.0
        assert result.committed == 1500.0

    def test_zero_committed(self) -> None:
        """All income is safe to spend when no commitments."""
        result = calculate_safe_to_spend(income=1000.0, committed=0.0)
        assert result.safe_amount == 1000.0

    def test_negative_safe_capped_at_zero(self) -> None:
        """Committed exceeds income results in safe_amount = 0."""
        result = calculate_safe_to_spend(income=500.0, committed=800.0)
        assert result.safe_amount == 0.0

    def test_zero_income(self) -> None:
        """Zero income gives zero safe amount."""
        result = calculate_safe_to_spend(income=0.0, committed=200.0)
        assert result.safe_amount == 0.0

    @pytest.mark.asyncio
    async def test_module_safe_to_spend(
        self,
        money_module: MoneyModule,
        encryption_svc: EncryptionService,
    ) -> None:
        """Module's get_safe_to_spend integrates with stored data."""
        user_id = 42

        # Add income transaction
        money_module._transactions[user_id] = []
        amount_enc = json.dumps({"plaintext_fallback": "3000"})
        money_module._transactions[user_id].append({
            "amount_encrypted": amount_enc,
            "currency": "EUR",
            "category": "income",
            "description_encrypted": "",
            "is_income": True,
            "transaction_date": date.today().isoformat(),
        })

        # Add recurring expense
        money_module._recurring[user_id] = []
        rec_enc = json.dumps({"plaintext_fallback": "800"})
        money_module._recurring[user_id].append({
            "name_encrypted": json.dumps({"plaintext_fallback": "Rent"}),
            "amount_encrypted": rec_enc,
            "frequency": "monthly",
        })

        result = await money_module.get_safe_to_spend(user_id)
        assert result.income == 3000.0
        assert result.committed == 800.0
        assert result.safe_amount == 2200.0


# =============================================================================
# 4. Pattern Detection Per Segment
# =============================================================================


class TestPatternDetection:
    """Test money pattern detection per neurotype."""

    def test_adhd_spending_burst(self, ad_context: SegmentContext) -> None:
        """ADHD: detect spending_burst when a spend > 2x average."""
        transactions = [
            ParsedTransaction(10, "EUR", "food", "", False, date.today()),
            ParsedTransaction(12, "EUR", "food", "", False, date.today()),
            ParsedTransaction(15, "EUR", "food", "", False, date.today()),
            ParsedTransaction(80, "EUR", "leisure", "", False, date.today()),  # burst
        ]
        patterns = detect_patterns(transactions, ad_context)
        assert len(patterns) >= 1
        assert any(p.pattern_type == PatternType.SPENDING_BURST for p in patterns)

    def test_adhd_no_burst_uniform(self, ad_context: SegmentContext) -> None:
        """ADHD: no burst detected for uniform spending."""
        transactions = [
            ParsedTransaction(10, "EUR", "food", "", False, date.today()),
            ParsedTransaction(11, "EUR", "food", "", False, date.today()),
            ParsedTransaction(12, "EUR", "food", "", False, date.today()),
        ]
        patterns = detect_patterns(transactions, ad_context)
        burst_patterns = [p for p in patterns if p.pattern_type == PatternType.SPENDING_BURST]
        assert len(burst_patterns) == 0

    def test_autism_routine_deviation(self, au_context: SegmentContext) -> None:
        """Autism: detect routine_deviation for high variance."""
        transactions = [
            ParsedTransaction(10, "EUR", "food", "", False, date.today()),
            ParsedTransaction(50, "EUR", "food", "", False, date.today()),
            ParsedTransaction(5, "EUR", "food", "", False, date.today()),
            ParsedTransaction(100, "EUR", "food", "", False, date.today()),
        ]
        patterns = detect_patterns(transactions, au_context)
        assert any(p.pattern_type == PatternType.ROUTINE_DEVIATION for p in patterns)

    def test_audhd_bimodal_spending(self, ah_context: SegmentContext) -> None:
        """AuDHD: detect bimodal spending pattern."""
        transactions = [
            ParsedTransaction(5, "EUR", "food", "", False, date.today()),
            ParsedTransaction(6, "EUR", "food", "", False, date.today()),
            ParsedTransaction(50, "EUR", "leisure", "", False, date.today()),
            ParsedTransaction(55, "EUR", "leisure", "", False, date.today()),
        ]
        patterns = detect_patterns(transactions, ah_context)
        assert any(p.pattern_type == PatternType.BIMODAL for p in patterns)

    def test_nt_no_segment_specific_patterns(self, nt_context: SegmentContext) -> None:
        """NT: no segment-specific patterns detected (no boom_bust, no routine_anchoring, no channel_dominance)."""
        transactions = [
            ParsedTransaction(10, "EUR", "food", "", False, date.today()),
            ParsedTransaction(50, "EUR", "food", "", False, date.today()),
            ParsedTransaction(5, "EUR", "food", "", False, date.today()),
            ParsedTransaction(100, "EUR", "food", "", False, date.today()),
        ]
        patterns = detect_patterns(transactions, nt_context)
        assert len(patterns) == 0

    def test_empty_transactions_no_patterns(self, ad_context: SegmentContext) -> None:
        """No transactions produces no patterns."""
        patterns = detect_patterns([], ad_context)
        assert len(patterns) == 0

    def test_pattern_descriptions_are_shame_free(self, ad_context: SegmentContext) -> None:
        """All pattern descriptions pass shame-free validation."""
        transactions = [
            ParsedTransaction(10, "EUR", "food", "", False, date.today()),
            ParsedTransaction(12, "EUR", "food", "", False, date.today()),
            ParsedTransaction(15, "EUR", "food", "", False, date.today()),
            ParsedTransaction(80, "EUR", "leisure", "", False, date.today()),
        ]
        patterns = detect_patterns(transactions, ad_context)
        for p in patterns:
            assert validate_shame_free(p.description), (
                f"Pattern description contains shame word: {p.description}"
            )


# =============================================================================
# 5. Shame-Free Language Validation
# =============================================================================


class TestShameFreeLanguage:
    """Test shame-free language enforcement."""

    @pytest.mark.parametrize("shame_word", list(SHAME_WORDS))
    def test_shame_words_detected(self, shame_word: str) -> None:
        """Each individual shame word is caught by validation."""
        text = f"You {shame_word} this month."
        assert validate_shame_free(text) is False

    def test_clean_text_passes(self) -> None:
        """Shame-free text passes validation."""
        text = "Let's look at your spending pattern together."
        assert validate_shame_free(text) is True

    def test_enforce_raises_on_shame_word(self) -> None:
        """enforce_shame_free raises ValueError for shaming text."""
        with pytest.raises(ValueError, match="shame language"):
            enforce_shame_free("You overspent this month.")

    def test_enforce_returns_clean_text(self) -> None:
        """enforce_shame_free returns text unchanged when clean."""
        text = "Here is your spending summary."
        assert enforce_shame_free(text) == text

    @pytest.mark.asyncio
    async def test_on_enter_is_shame_free(
        self,
        money_module: MoneyModule,
        ad_context: SegmentContext,
    ) -> None:
        """on_enter response is shame-free for all segments."""
        for code in ("AD", "AU", "AH", "NT"):
            ctx_seg = SegmentContext.from_code(code)  # type: ignore[arg-type]
            ctx = _make_ctx(ctx_seg)
            response = await money_module.on_enter(ctx)
            assert validate_shame_free(response.text), (
                f"on_enter for {code} contains shame: {response.text}"
            )

    @pytest.mark.asyncio
    async def test_handle_response_is_shame_free(
        self,
        money_module: MoneyModule,
        ad_context: SegmentContext,
    ) -> None:
        """handle response is shame-free."""
        ctx = _make_ctx(ad_context)
        response = await money_module.handle("12 euros for sushi", ctx)
        assert validate_shame_free(response.text)


# =============================================================================
# 6. Encryption of Financial Data
# =============================================================================


class TestEncryption:
    """Test that financial data is encrypted when stored."""

    @pytest.mark.asyncio
    async def test_transaction_amount_encrypted(
        self,
        money_module: MoneyModule,
        ad_context: SegmentContext,
        encryption_svc: EncryptionService,
    ) -> None:
        """Transaction amounts are stored encrypted."""
        ctx = _make_ctx(ad_context, user_id=100)
        await money_module.handle("25 euros for groceries", ctx)

        # Verify stored data is encrypted (not plaintext)
        stored = money_module._transactions.get(100, [])
        assert len(stored) == 1
        amount_json = stored[0]["amount_encrypted"]
        data = json.loads(amount_json)
        # Should be an EncryptedField dict with ciphertext, not plaintext
        assert "ciphertext" in data
        assert "classification" in data
        assert data["classification"] == "financial"

    @pytest.mark.asyncio
    async def test_encrypted_amount_decrypts_correctly(
        self,
        money_module: MoneyModule,
        ad_context: SegmentContext,
        encryption_svc: EncryptionService,
    ) -> None:
        """Encrypted amount can be decrypted back to original value."""
        ctx = _make_ctx(ad_context, user_id=101)
        await money_module.handle("30 euros for lunch", ctx)

        stored = money_module._transactions.get(101, [])
        assert len(stored) == 1

        from src.lib.encryption import EncryptedField

        amount_json = stored[0]["amount_encrypted"]
        data = json.loads(amount_json)
        encrypted = EncryptedField.from_db_dict(data)
        decrypted = encryption_svc.decrypt_field(encrypted, user_id=101, field_name="amount")
        assert decrypted == "30.0"

    @pytest.mark.asyncio
    async def test_description_encrypted(
        self,
        money_module: MoneyModule,
        ad_context: SegmentContext,
    ) -> None:
        """Transaction descriptions are stored encrypted."""
        ctx = _make_ctx(ad_context, user_id=102)
        await money_module.handle("18 euros for dinner", ctx)

        stored = money_module._transactions.get(102, [])
        assert len(stored) == 1
        desc_json = stored[0]["description_encrypted"]
        data = json.loads(desc_json)
        assert "ciphertext" in data


# =============================================================================
# 7. GDPR Export and Delete
# =============================================================================


class TestGDPR:
    """Test GDPR export, delete, freeze, and unfreeze."""

    @pytest.mark.asyncio
    async def test_export_returns_decrypted_data(
        self,
        money_module: MoneyModule,
        ad_context: SegmentContext,
    ) -> None:
        """GDPR export returns decrypted transaction data."""
        user_id = 200
        ctx = _make_ctx(ad_context, user_id=user_id)
        await money_module.handle("50 euros for restaurant", ctx)

        exported = await money_module.export_user_data(user_id)
        assert "transactions" in exported
        assert len(exported["transactions"]) == 1
        tx = exported["transactions"][0]
        # Amount should be decrypted (readable)
        assert tx["amount"] == "50.0"
        assert tx["currency"] == "EUR"

    @pytest.mark.asyncio
    async def test_export_empty_user(self, money_module: MoneyModule) -> None:
        """GDPR export for non-existent user returns empty data."""
        exported = await money_module.export_user_data(999)
        assert exported["transactions"] == []
        assert exported["recurring_expenses"] == []

    @pytest.mark.asyncio
    async def test_delete_removes_all_data(
        self,
        money_module: MoneyModule,
        ad_context: SegmentContext,
    ) -> None:
        """GDPR delete removes all user data."""
        user_id = 201
        ctx = _make_ctx(ad_context, user_id=user_id)
        await money_module.handle("10 euros for coffee", ctx)

        # Verify data exists
        assert len(money_module._transactions.get(user_id, [])) == 1

        # Delete
        await money_module.delete_user_data(user_id)

        # Verify all data removed
        assert money_module._transactions.get(user_id) is None
        assert money_module._budgets.get(user_id) is None
        assert money_module._patterns.get(user_id) is None

    @pytest.mark.asyncio
    async def test_freeze_blocks_processing(
        self,
        money_module: MoneyModule,
        ad_context: SegmentContext,
    ) -> None:
        """Frozen user gets a pause message."""
        user_id = 202
        await money_module.freeze_user_data(user_id)
        ctx = _make_ctx(ad_context, user_id=user_id)
        ctx.is_frozen = True
        response = await money_module.handle("10 euros for snack", ctx)
        assert "paused" in response.text.lower()
        assert response.is_end_of_flow is True

    @pytest.mark.asyncio
    async def test_unfreeze_allows_processing(
        self,
        money_module: MoneyModule,
        ad_context: SegmentContext,
    ) -> None:
        """Unfreezing restores normal processing."""
        user_id = 203
        await money_module.freeze_user_data(user_id)
        await money_module.unfreeze_user_data(user_id)
        assert user_id not in money_module._frozen_users


# =============================================================================
# 8. Energy Gating
# =============================================================================


class TestEnergyGating:
    """Test energy-based purchase gating."""

    def test_green_allows_non_essential(self) -> None:
        """GREEN energy allows non-essential purchases."""
        assert check_energy_gate("green", is_essential=False) is True

    def test_yellow_allows_non_essential(self) -> None:
        """YELLOW energy allows non-essential purchases."""
        assert check_energy_gate("yellow", is_essential=False) is True

    def test_red_blocks_non_essential(self) -> None:
        """RED energy blocks non-essential purchases."""
        assert check_energy_gate("red", is_essential=False) is False

    def test_red_allows_essential(self) -> None:
        """RED energy allows essential purchases."""
        assert check_energy_gate("red", is_essential=True) is True

    def test_food_is_essential(self) -> None:
        """Food is classified as essential."""
        assert is_essential_category("food") is True

    def test_health_is_essential(self) -> None:
        """Health is classified as essential."""
        assert is_essential_category("health") is True

    def test_leisure_is_not_essential(self) -> None:
        """Leisure is NOT essential."""
        assert is_essential_category("leisure") is False

    @pytest.mark.asyncio
    async def test_energy_gate_in_pipeline(
        self,
        money_module: MoneyModule,
        nt_context: SegmentContext,
    ) -> None:
        """Energy gating triggers during budget_check in pipeline."""
        ctx = _make_ctx(nt_context, user_id=300, energy_state="red")
        response = await money_module.handle("50 euros for cinema", ctx)
        # Cinema = leisure = non-essential, RED energy -> should be gated
        assert response.metadata.get("energy_gated") is True
        assert "low" in response.text.lower() or "energy" in response.text.lower()

    @pytest.mark.asyncio
    async def test_essential_not_gated_on_red(
        self,
        money_module: MoneyModule,
        nt_context: SegmentContext,
    ) -> None:
        """Essential purchase goes through even on RED energy."""
        ctx = _make_ctx(nt_context, user_id=301, energy_state="red")
        response = await money_module.handle("8 euros for groceries", ctx)
        # Groceries = food = essential, should NOT be gated
        assert response.metadata.get("energy_gated") is not True


# =============================================================================
# 9. Module Integration
# =============================================================================


class TestModuleIntegration:
    """Test full module handle flow per segment."""

    @pytest.mark.asyncio
    async def test_ad_full_flow(
        self,
        money_module: MoneyModule,
        ad_context: SegmentContext,
    ) -> None:
        """ADHD: full 3-step flow completes with is_end_of_flow."""
        ctx = _make_ctx(ad_context, user_id=400)
        response = await money_module.handle("12 euros for sushi", ctx)
        assert response.is_end_of_flow is True
        assert response.next_state == MoneyState.DONE
        assert response.metadata.get("transaction_stored") is True

    @pytest.mark.asyncio
    async def test_au_full_flow(
        self,
        money_module: MoneyModule,
        au_context: SegmentContext,
    ) -> None:
        """Autism: full 7-step flow completes."""
        ctx = _make_ctx(au_context, user_id=401)
        response = await money_module.handle("20 euros for groceries", ctx)
        assert response.is_end_of_flow is True
        assert "Verification" in response.text  # AU has verify step

    @pytest.mark.asyncio
    async def test_ah_full_flow(
        self,
        money_module: MoneyModule,
        ah_context: SegmentContext,
    ) -> None:
        """AuDHD: full 6-step flow completes."""
        ctx = _make_ctx(ah_context, user_id=402)
        response = await money_module.handle("15 euros for coffee", ctx)
        assert response.is_end_of_flow is True
        assert "Verification" not in response.text  # AH has no verify step

    @pytest.mark.asyncio
    async def test_nt_full_flow(
        self,
        money_module: MoneyModule,
        nt_context: SegmentContext,
    ) -> None:
        """NT: full 4-step flow completes."""
        ctx = _make_ctx(nt_context, user_id=403)
        response = await money_module.handle("10 euros for bus", ctx)
        assert response.is_end_of_flow is True

    @pytest.mark.asyncio
    async def test_unparseable_message(
        self,
        money_module: MoneyModule,
        ad_context: SegmentContext,
    ) -> None:
        """Unparseable message returns helpful prompt without shaming."""
        ctx = _make_ctx(ad_context, user_id=404)
        response = await money_module.handle("hello there", ctx)
        assert not response.is_end_of_flow
        assert validate_shame_free(response.text)

    @pytest.mark.asyncio
    async def test_module_protocol_properties(self, money_module: MoneyModule) -> None:
        """Module has required protocol properties."""
        assert money_module.name == "money"
        assert money_module.pillar == "money"
        assert len(money_module.intents) > 0

    @pytest.mark.asyncio
    async def test_on_exit_clears_metadata(
        self,
        money_module: MoneyModule,
        ad_context: SegmentContext,
    ) -> None:
        """on_exit clears parsed_transaction from metadata."""
        ctx = _make_ctx(ad_context)
        ctx.metadata["parsed_transaction"] = {"amount": 10}
        await money_module.on_exit(ctx)
        assert "parsed_transaction" not in ctx.metadata

    @pytest.mark.asyncio
    async def test_daily_workflow_hooks(self, money_module: MoneyModule) -> None:
        """Module provides daily workflow hooks."""
        hooks = money_module.get_daily_workflow_hooks()
        assert hooks.hook_name == "money"
        assert hooks.evening_review is not None
        assert hooks.has_any_hook() is True
