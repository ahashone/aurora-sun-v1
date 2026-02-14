"""
Unit tests for the GDPR compliance module.

These tests verify the functionality of:
- DataClassification enum
- RetentionPolicyConfig (retention days, expiry logic)
- GDPRService (export, delete, freeze, unfreeze, retention check)

Mock modules implementing GDPRModuleInterface are used to test the
service orchestration across registered modules.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.lib.gdpr import (
    DataClassification,
    GDPRService,
    ProcessingRestriction,
    RecordsToDelete,
    RetentionPolicyConfig,
)

# =============================================================================
# Mock Module Helpers
# =============================================================================


class MockGDPRModule:
    """Mock module implementing GDPRModuleInterface for testing."""

    def __init__(
        self,
        name: str = "mock_module",
        export_data: dict[str, Any] | None = None,
        fail_on_export: bool = False,
        fail_on_delete: bool = False,
        fail_on_freeze: bool = False,
        fail_on_unfreeze: bool = False,
    ):
        self.name = name
        self._export_data = export_data or {"key": "value"}
        self._fail_on_export = fail_on_export
        self._fail_on_delete = fail_on_delete
        self._fail_on_freeze = fail_on_freeze
        self._fail_on_unfreeze = fail_on_unfreeze
        self.export_called_with: list[int] = []
        self.delete_called_with: list[int] = []
        self.freeze_called_with: list[int] = []
        self.unfreeze_called_with: list[int] = []

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        self.export_called_with.append(user_id)
        if self._fail_on_export:
            raise RuntimeError(f"Export failed for {self.name}")
        return self._export_data

    async def delete_user_data(self, user_id: int) -> None:
        self.delete_called_with.append(user_id)
        if self._fail_on_delete:
            raise RuntimeError(f"Delete failed for {self.name}")

    async def freeze_user_data(self, user_id: int) -> None:
        self.freeze_called_with.append(user_id)
        if self._fail_on_freeze:
            raise RuntimeError(f"Freeze failed for {self.name}")

    async def unfreeze_user_data(self, user_id: int) -> None:
        self.unfreeze_called_with.append(user_id)
        if self._fail_on_unfreeze:
            raise RuntimeError(f"Unfreeze failed for {self.name}")


# =============================================================================
# TestDataClassification
# =============================================================================


class TestDataClassification:
    """Test the DataClassification enum values."""

    def test_has_five_members(self):
        """DataClassification has exactly 5 members."""
        assert len(DataClassification) == 5

    def test_public_value(self):
        """PUBLIC classification has correct value."""
        assert DataClassification.PUBLIC.value == "public"

    def test_internal_value(self):
        """INTERNAL classification has correct value."""
        assert DataClassification.INTERNAL.value == "internal"

    def test_sensitive_value(self):
        """SENSITIVE classification has correct value."""
        assert DataClassification.SENSITIVE.value == "sensitive"

    def test_art_9_special_value(self):
        """ART_9_SPECIAL classification has correct value."""
        assert DataClassification.ART_9_SPECIAL.value == "art_9"

    def test_financial_value(self):
        """FINANCIAL classification has correct value."""
        assert DataClassification.FINANCIAL.value == "financial"

    def test_all_members_accessible(self):
        """All enum members can be accessed by name."""
        members = [
            DataClassification.PUBLIC,
            DataClassification.INTERNAL,
            DataClassification.SENSITIVE,
            DataClassification.ART_9_SPECIAL,
            DataClassification.FINANCIAL,
        ]
        assert len(members) == 5


# =============================================================================
# TestRetentionPolicyConfig
# =============================================================================


class TestRetentionPolicyConfig:
    """Test the RetentionPolicyConfig defaults and methods."""

    @pytest.fixture
    def policy(self):
        """Create a default RetentionPolicyConfig."""
        return RetentionPolicyConfig()

    # ---- Default retention values ----

    def test_default_public_retention(self, policy: RetentionPolicyConfig):
        """PUBLIC defaults to -1 (indefinite)."""
        assert policy.retention_days[DataClassification.PUBLIC] == -1

    def test_default_internal_retention(self, policy: RetentionPolicyConfig):
        """INTERNAL defaults to -1 (indefinite)."""
        assert policy.retention_days[DataClassification.INTERNAL] == -1

    def test_default_sensitive_retention(self, policy: RetentionPolicyConfig):
        """SENSITIVE defaults to 0 (delete while active)."""
        assert policy.retention_days[DataClassification.SENSITIVE] == 0

    def test_default_art_9_retention(self, policy: RetentionPolicyConfig):
        """ART_9_SPECIAL defaults to 0 (delete while active)."""
        assert policy.retention_days[DataClassification.ART_9_SPECIAL] == 0

    def test_default_financial_retention(self, policy: RetentionPolicyConfig):
        """FINANCIAL defaults to 0 (delete while active)."""
        assert policy.retention_days[DataClassification.FINANCIAL] == 0

    def test_consent_retention_days(self, policy: RetentionPolicyConfig):
        """CONSENT_RETENTION_DAYS is 1825 (5 years)."""
        assert policy.CONSENT_RETENTION_DAYS == 1825

    # ---- get_retention_days ----

    def test_get_retention_days_public(self, policy: RetentionPolicyConfig):
        """get_retention_days returns -1 for PUBLIC."""
        assert policy.get_retention_days(DataClassification.PUBLIC) == -1

    def test_get_retention_days_internal(self, policy: RetentionPolicyConfig):
        """get_retention_days returns -1 for INTERNAL."""
        assert policy.get_retention_days(DataClassification.INTERNAL) == -1

    def test_get_retention_days_sensitive(self, policy: RetentionPolicyConfig):
        """get_retention_days returns 0 for SENSITIVE."""
        assert policy.get_retention_days(DataClassification.SENSITIVE) == 0

    def test_get_retention_days_art_9(self, policy: RetentionPolicyConfig):
        """get_retention_days returns 0 for ART_9_SPECIAL."""
        assert policy.get_retention_days(DataClassification.ART_9_SPECIAL) == 0

    def test_get_retention_days_financial(self, policy: RetentionPolicyConfig):
        """get_retention_days returns 0 for FINANCIAL."""
        assert policy.get_retention_days(DataClassification.FINANCIAL) == 0

    # ---- is_expired ----

    def test_is_expired_indefinite_never_expires(self, policy: RetentionPolicyConfig):
        """Records with -1 retention (indefinite) are never expired."""
        old_date = datetime(2020, 1, 1, tzinfo=UTC)
        assert policy.is_expired(DataClassification.PUBLIC, old_date) is False
        assert policy.is_expired(DataClassification.INTERNAL, old_date) is False

    def test_is_expired_zero_always_expired(self, policy: RetentionPolicyConfig):
        """Records with 0 retention are always expired (True)."""
        now = datetime.now(UTC)
        assert policy.is_expired(DataClassification.SENSITIVE, now) is True
        assert policy.is_expired(DataClassification.ART_9_SPECIAL, now) is True
        assert policy.is_expired(DataClassification.FINANCIAL, now) is True

    def test_is_expired_positive_retention_not_expired(self):
        """Record within positive retention period is not expired."""
        policy = RetentionPolicyConfig(
            retention_days={
                DataClassification.PUBLIC: -1,
                DataClassification.INTERNAL: -1,
                DataClassification.SENSITIVE: 365,
                DataClassification.ART_9_SPECIAL: 0,
                DataClassification.FINANCIAL: 0,
            }
        )
        recent_date = datetime.now(UTC) - timedelta(days=100)
        assert policy.is_expired(DataClassification.SENSITIVE, recent_date) is False

    def test_is_expired_positive_retention_expired(self):
        """Record exceeding positive retention period is expired."""
        policy = RetentionPolicyConfig(
            retention_days={
                DataClassification.PUBLIC: -1,
                DataClassification.INTERNAL: -1,
                DataClassification.SENSITIVE: 30,
                DataClassification.ART_9_SPECIAL: 0,
                DataClassification.FINANCIAL: 0,
            }
        )
        old_date = datetime.now(UTC) - timedelta(days=31)
        assert policy.is_expired(DataClassification.SENSITIVE, old_date) is True

    def test_is_expired_positive_retention_boundary(self):
        """Record exactly at retention boundary is not expired (uses > not >=)."""
        policy = RetentionPolicyConfig(
            retention_days={
                DataClassification.PUBLIC: -1,
                DataClassification.INTERNAL: -1,
                DataClassification.SENSITIVE: 30,
                DataClassification.ART_9_SPECIAL: 0,
                DataClassification.FINANCIAL: 0,
            }
        )
        # Exactly 30 days ago -- days_since == 30, check is days_since > 30
        boundary_date = datetime.now(UTC) - timedelta(days=30)
        assert policy.is_expired(DataClassification.SENSITIVE, boundary_date) is False

    # ---- Custom retention policy ----

    def test_custom_retention_policy(self):
        """Custom retention policy overrides defaults."""
        custom = RetentionPolicyConfig(
            retention_days={
                DataClassification.PUBLIC: -1,
                DataClassification.INTERNAL: -1,
                DataClassification.SENSITIVE: 90,
                DataClassification.ART_9_SPECIAL: 180,
                DataClassification.FINANCIAL: 3650,
            }
        )
        assert custom.get_retention_days(DataClassification.SENSITIVE) == 90
        assert custom.get_retention_days(DataClassification.ART_9_SPECIAL) == 180
        assert custom.get_retention_days(DataClassification.FINANCIAL) == 3650


# =============================================================================
# TestGDPRService
# =============================================================================


class TestGDPRServiceInit:
    """Test GDPRService initialization."""

    def test_init_with_no_args(self):
        """GDPRService can be created with no arguments."""
        service = GDPRService()
        assert service.db is None
        assert service.redis is None
        assert service.neo4j is None
        assert service.qdrant is None
        assert service.letta is None
        assert isinstance(service.retention_policy, RetentionPolicyConfig)

    def test_init_with_all_args(self):
        """GDPRService stores all provided connections."""
        mock_db = object()
        mock_redis = object()
        mock_neo4j = object()
        mock_qdrant = object()
        mock_letta = object()
        custom_policy = RetentionPolicyConfig()

        service = GDPRService(
            db_pool=mock_db,
            redis=mock_redis,
            neo4j_driver=mock_neo4j,
            qdrant_client=mock_qdrant,
            letta_client=mock_letta,
            retention_policy=custom_policy,
        )

        assert service.db is mock_db
        assert service.redis is mock_redis
        assert service.neo4j is mock_neo4j
        assert service.qdrant is mock_qdrant
        assert service.letta is mock_letta
        assert service.retention_policy is custom_policy

    def test_init_default_retention_policy(self):
        """GDPRService uses default RetentionPolicyConfig when none provided."""
        service = GDPRService()
        assert service.retention_policy.CONSENT_RETENTION_DAYS == 1825

    def test_init_custom_retention_policy(self):
        """GDPRService uses provided retention policy."""
        custom = RetentionPolicyConfig(
            retention_days={
                DataClassification.PUBLIC: -1,
                DataClassification.INTERNAL: -1,
                DataClassification.SENSITIVE: 999,
                DataClassification.ART_9_SPECIAL: 0,
                DataClassification.FINANCIAL: 0,
            }
        )
        service = GDPRService(retention_policy=custom)
        assert service.retention_policy.get_retention_days(DataClassification.SENSITIVE) == 999


class TestGDPRServiceRegisterModule:
    """Test GDPRService module registration."""

    def test_register_single_module(self):
        """Register a single module."""
        service = GDPRService()
        module = MockGDPRModule(name="test")
        service.register_module("test", module)
        assert "test" in service._modules
        assert service._modules["test"] is module

    def test_register_multiple_modules(self):
        """Register multiple modules."""
        service = GDPRService()
        mod_a = MockGDPRModule(name="mod_a")
        mod_b = MockGDPRModule(name="mod_b")
        mod_c = MockGDPRModule(name="mod_c")

        service.register_module("mod_a", mod_a)
        service.register_module("mod_b", mod_b)
        service.register_module("mod_c", mod_c)

        assert len(service._modules) == 3

    def test_register_overwrites_same_name(self):
        """Registering with the same name overwrites the previous module."""
        service = GDPRService()
        mod1 = MockGDPRModule(name="same")
        mod2 = MockGDPRModule(name="same")

        service.register_module("same", mod1)
        service.register_module("same", mod2)

        assert service._modules["same"] is mod2


class TestGDPRServiceExport:
    """Test GDPRService.export_user_data()."""

    @pytest.fixture
    def service_with_modules(self):
        """Create a GDPRService with two registered mock modules."""
        service = GDPRService()
        mod_a = MockGDPRModule(name="mod_a", export_data={"items": [1, 2, 3]})
        mod_b = MockGDPRModule(name="mod_b", export_data={"profile": "data"})
        service.register_module("mod_a", mod_a)
        service.register_module("mod_b", mod_b)
        return service, mod_a, mod_b

    @pytest.mark.asyncio
    async def test_export_returns_metadata(self, service_with_modules):
        """Export returns export_metadata with user_id and timestamp."""
        service, _, _ = service_with_modules
        result = await service.export_user_data(user_id=42)

        assert "export_metadata" in result
        assert result["export_metadata"]["user_id"] == 42
        assert result["export_metadata"]["aurora_version"] == "v1"
        assert result["export_metadata"]["exported_at"] is not None

    @pytest.mark.asyncio
    async def test_export_returns_modules_data(self, service_with_modules):
        """Export returns data from each registered module."""
        service, _, _ = service_with_modules
        result = await service.export_user_data(user_id=42)

        assert "modules" in result
        assert "mod_a" in result["modules"]
        assert "mod_b" in result["modules"]
        assert result["modules"]["mod_a"]["data"] == {"items": [1, 2, 3]}
        assert result["modules"]["mod_b"]["data"] == {"profile": "data"}

    @pytest.mark.asyncio
    async def test_export_calls_modules_with_user_id(self, service_with_modules):
        """Export calls export_user_data() on each module with correct user_id."""
        service, mod_a, mod_b = service_with_modules
        await service.export_user_data(user_id=99)

        assert 99 in mod_a.export_called_with
        assert 99 in mod_b.export_called_with

    @pytest.mark.asyncio
    async def test_export_handles_module_error_gracefully(self):
        """Module export failure is logged but does not stop other modules."""
        service = GDPRService()
        failing_mod = MockGDPRModule(name="failing", fail_on_export=True)
        working_mod = MockGDPRModule(name="working", export_data={"ok": True})
        service.register_module("failing", failing_mod)
        service.register_module("working", working_mod)

        result = await service.export_user_data(user_id=1)

        # Working module should still be in exports
        assert "working" in result["modules"]
        assert result["modules"]["working"]["data"] == {"ok": True}

        # Failing module should not be in modules
        assert "failing" not in result["modules"]

        # Errors should be reported in metadata
        assert result["export_metadata"]["errors"] is not None
        assert any("failing" in err for err in result["export_metadata"]["errors"])

    @pytest.mark.asyncio
    async def test_export_total_records_count(self, service_with_modules):
        """Export metadata total_records reflects number of successful exports."""
        service, _, _ = service_with_modules
        result = await service.export_user_data(user_id=42)

        assert result["export_metadata"]["total_records"] == 2

    @pytest.mark.asyncio
    async def test_export_no_modules_registered(self):
        """Export with no registered modules returns empty modules dict."""
        service = GDPRService()
        result = await service.export_user_data(user_id=1)

        assert result["modules"] == {}
        assert result["export_metadata"]["total_records"] == 0

    @pytest.mark.asyncio
    async def test_export_errors_none_when_no_errors(self, service_with_modules):
        """Export metadata errors is None when all modules succeed."""
        service, _, _ = service_with_modules
        result = await service.export_user_data(user_id=42)

        assert result["export_metadata"]["errors"] is None


class TestGDPRServiceDelete:
    """Test GDPRService.delete_user_data()."""

    @pytest.fixture
    def service_with_modules(self):
        """Create a GDPRService with two registered mock modules."""
        service = GDPRService()
        mod_a = MockGDPRModule(name="mod_a")
        mod_b = MockGDPRModule(name="mod_b")
        service.register_module("mod_a", mod_a)
        service.register_module("mod_b", mod_b)
        return service, mod_a, mod_b

    @pytest.mark.asyncio
    async def test_delete_returns_report(self, service_with_modules):
        """Delete returns a deletion report with user_id and deleted_at."""
        service, _, _ = service_with_modules
        result = await service.delete_user_data(user_id=42)

        assert result["user_id"] == 42
        assert result["deleted_at"] is not None
        assert "components" in result

    @pytest.mark.asyncio
    async def test_delete_calls_all_modules(self, service_with_modules):
        """Delete calls delete_user_data() on each registered module."""
        service, mod_a, mod_b = service_with_modules
        await service.delete_user_data(user_id=55)

        assert 55 in mod_a.delete_called_with
        assert 55 in mod_b.delete_called_with

    @pytest.mark.asyncio
    async def test_delete_all_success_overall_status(self, service_with_modules):
        """overall_status is 'success' when all modules delete successfully."""
        service, _, _ = service_with_modules
        result = await service.delete_user_data(user_id=42)

        assert result["overall_status"] == "success"
        for comp in result["components"].values():
            assert comp["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_partial_on_module_error(self):
        """overall_status is 'partial' when a module fails."""
        service = GDPRService()
        working_mod = MockGDPRModule(name="working")
        failing_mod = MockGDPRModule(name="failing", fail_on_delete=True)
        service.register_module("working", working_mod)
        service.register_module("failing", failing_mod)

        result = await service.delete_user_data(user_id=1)

        assert result["overall_status"] == "partial"
        assert result["components"]["working"]["status"] == "deleted"
        assert result["components"]["failing"]["status"] == "error"
        assert "error" in result["components"]["failing"]

    @pytest.mark.asyncio
    async def test_delete_no_modules(self):
        """Delete with no modules returns success (vacuously true)."""
        service = GDPRService()
        result = await service.delete_user_data(user_id=1)

        assert result["overall_status"] == "success"
        assert result["components"] == {}


class TestGDPRServiceFreeze:
    """Test GDPRService.freeze_user_data()."""

    @pytest.mark.asyncio
    async def test_freeze_returns_restriction_restricted(self):
        """Freeze report contains restriction value 'restricted'."""
        service = GDPRService()
        module = MockGDPRModule(name="test_mod")
        service.register_module("test_mod", module)

        result = await service.freeze_user_data(user_id=10)

        assert result["restriction"] == ProcessingRestriction.RESTRICTED.value
        assert result["restriction"] == "restricted"
        assert result["user_id"] == 10
        assert "frozen_at" in result

    @pytest.mark.asyncio
    async def test_freeze_calls_modules(self):
        """Freeze calls freeze_user_data() on each registered module."""
        service = GDPRService()
        mod = MockGDPRModule(name="mod")
        service.register_module("mod", mod)

        await service.freeze_user_data(user_id=7)

        assert 7 in mod.freeze_called_with

    @pytest.mark.asyncio
    async def test_freeze_handles_module_error(self):
        """Freeze continues despite module errors."""
        service = GDPRService()
        failing = MockGDPRModule(name="failing", fail_on_freeze=True)
        working = MockGDPRModule(name="working")
        service.register_module("failing", failing)
        service.register_module("working", working)

        result = await service.freeze_user_data(user_id=3)

        assert result["components"]["failing"]["status"] == "error"
        assert result["components"]["working"]["status"] == "restricted"


class TestGDPRServiceUnfreeze:
    """Test GDPRService.unfreeze_user_data()."""

    @pytest.mark.asyncio
    async def test_unfreeze_returns_restriction_active(self):
        """Unfreeze report contains restriction value 'active'."""
        service = GDPRService()
        module = MockGDPRModule(name="test_mod")
        service.register_module("test_mod", module)

        result = await service.unfreeze_user_data(user_id=10)

        assert result["restriction"] == ProcessingRestriction.ACTIVE.value
        assert result["restriction"] == "active"
        assert result["user_id"] == 10
        assert "unfrozen_at" in result

    @pytest.mark.asyncio
    async def test_unfreeze_calls_modules(self):
        """Unfreeze calls unfreeze_user_data() on each registered module."""
        service = GDPRService()
        mod = MockGDPRModule(name="mod")
        service.register_module("mod", mod)

        await service.unfreeze_user_data(user_id=8)

        assert 8 in mod.unfreeze_called_with

    @pytest.mark.asyncio
    async def test_unfreeze_handles_module_error(self):
        """Unfreeze continues despite module errors."""
        service = GDPRService()
        failing = MockGDPRModule(name="failing", fail_on_unfreeze=True)
        working = MockGDPRModule(name="working")
        service.register_module("failing", failing)
        service.register_module("working", working)

        result = await service.unfreeze_user_data(user_id=4)

        assert result["components"]["failing"]["status"] == "error"
        assert result["components"]["working"]["status"] == "active"


class TestGDPRServiceCheckRetention:
    """Test GDPRService.check_retention()."""

    @pytest.mark.asyncio
    async def test_check_retention_returns_empty_list(self):
        """check_retention returns an empty list (placeholder implementation)."""
        service = GDPRService()
        result = await service.check_retention()

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_check_retention_return_type(self):
        """check_retention returns list[RecordsToDelete]."""
        service = GDPRService()
        result = await service.check_retention()

        # Verify the type annotation is satisfied
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, RecordsToDelete)


# =============================================================================
# TestRecordsToDelete
# =============================================================================


class TestRecordsToDelete:
    """Test the RecordsToDelete dataclass."""

    def test_create_records_to_delete(self):
        """RecordsToDelete can be instantiated with all fields."""
        record = RecordsToDelete(
            table_name="sessions",
            record_id=42,
            classification=DataClassification.SENSITIVE,
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            days_since_creation=400,
            reason="Retention period exceeded",
        )

        assert record.table_name == "sessions"
        assert record.record_id == 42
        assert record.classification == DataClassification.SENSITIVE
        assert record.days_since_creation == 400
        assert record.reason == "Retention period exceeded"


# =============================================================================
# TestProcessingRestriction
# =============================================================================


class TestProcessingRestriction:
    """Test the ProcessingRestriction enum."""

    def test_active_value(self):
        """ACTIVE has value 'active'."""
        assert ProcessingRestriction.ACTIVE.value == "active"

    def test_restricted_value(self):
        """RESTRICTED has value 'restricted'."""
        assert ProcessingRestriction.RESTRICTED.value == "restricted"

    def test_has_two_members(self):
        """ProcessingRestriction has exactly 2 members."""
        assert len(ProcessingRestriction) == 2
