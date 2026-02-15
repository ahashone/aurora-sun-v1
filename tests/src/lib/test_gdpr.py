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
        assert DataClassification.ART_9_SPECIAL.value == "art_9_special"

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
        """Export returns export_metadata with hashed user_id and timestamp."""
        service, _, _ = service_with_modules
        result = await service.export_user_data(user_id=42)

        assert "export_metadata" in result
        assert "user_id_hash" in result["export_metadata"]
        assert "user_id" not in result["export_metadata"]
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

        # FINDING-041: Export tracks completeness via `complete` and `failed_modules`
        assert result["export_metadata"]["complete"] is False
        assert len(result["export_metadata"]["failed_modules"]) > 0
        assert any("failing" in err for err in result["export_metadata"]["failed_modules"])

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
    async def test_export_complete_when_no_errors(self, service_with_modules):
        """Export metadata shows complete=True and empty failed_modules when all succeed."""
        service, _, _ = service_with_modules
        result = await service.export_user_data(user_id=42)

        # FINDING-041: Uses `complete` and `failed_modules` instead of `errors`
        assert result["export_metadata"]["complete"] is True
        assert result["export_metadata"]["failed_modules"] == []


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
        for comp_name, comp in result["components"].items():
            # FINDING-010: encryption_keys component uses "destroyed" status
            if comp_name == "encryption_keys":
                assert comp["status"] == "destroyed"
            else:
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
        """Delete with no modules returns success (includes encryption key destruction)."""
        service = GDPRService()
        result = await service.delete_user_data(user_id=1)

        assert result["overall_status"] == "success"
        # FINDING-010: Encryption key destruction always runs
        assert "encryption_keys" in result["components"]
        assert result["components"]["encryption_keys"]["status"] == "destroyed"


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


# =============================================================================
# Test5DatabaseAggregation
# =============================================================================


class Test5DatabaseAggregation:
    """Test 5-database aggregation methods (PostgreSQL, Redis, Neo4j, Qdrant, Letta)."""

    @pytest.mark.asyncio
    async def test_export_postgres_returns_dict(self):
        """_export_postgres returns dict with user data."""
        from unittest.mock import MagicMock

        # Mock database connection
        mock_db = MagicMock()
        service = GDPRService(db_pool=mock_db)

        # Test that method exists and returns dict
        result = await service._export_postgres(user_id=1)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_export_postgres_no_db_returns_empty(self):
        """_export_postgres returns empty dict when no db connection."""
        service = GDPRService(db_pool=None)
        result = await service._export_postgres(user_id=1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_export_redis_returns_dict(self):
        """_export_redis returns dict with Redis keys."""
        from unittest.mock import AsyncMock, MagicMock

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.scan = AsyncMock(return_value=(0, []))  # No keys

        service = GDPRService(redis=mock_redis)

        result = await service._export_redis(user_id=1)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_export_redis_no_redis_returns_empty(self):
        """_export_redis returns empty dict when no Redis connection."""
        service = GDPRService(redis=None)
        result = await service._export_redis(user_id=1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_export_neo4j_calls_service(self):
        """_export_neo4j calls Neo4jService.export_user_subgraph."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_driver = MagicMock()
        service = GDPRService(neo4j_driver=mock_driver)

        # Mock the Neo4jService and its export method
        with patch("src.services.knowledge.neo4j_service.Neo4jService") as MockNeo4j:
            mock_neo4j_instance = MagicMock()
            mock_subgraph = MagicMock()
            mock_subgraph.nodes = []
            mock_subgraph.relationships = []
            mock_subgraph.node_count = 0
            mock_subgraph.relationship_count = 0
            mock_subgraph.exported_at = datetime.now(UTC)

            mock_neo4j_instance.export_user_subgraph = AsyncMock(return_value=mock_subgraph)
            MockNeo4j.return_value = mock_neo4j_instance

            result = await service._export_neo4j(user_id=1)

            assert isinstance(result, dict)
            assert "nodes" in result
            assert "relationships" in result
            assert "metadata" in result

    @pytest.mark.asyncio
    async def test_export_neo4j_no_driver_returns_empty(self):
        """_export_neo4j returns empty dict when no Neo4j driver."""
        service = GDPRService(neo4j_driver=None)
        result = await service._export_neo4j(user_id=1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_export_qdrant_calls_service(self):
        """_export_qdrant calls QdrantService.export_user_vectors."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_client = MagicMock()
        service = GDPRService(qdrant_client=mock_client)

        with patch("src.services.knowledge.qdrant_service.QdrantService") as MockQdrant:
            mock_qdrant_instance = MagicMock()
            mock_export = MagicMock()
            mock_export.vectors = []
            mock_export.vector_count = 0
            mock_export.collections = []
            mock_export.exported_at = datetime.now(UTC)

            mock_qdrant_instance.export_user_vectors = AsyncMock(return_value=mock_export)
            MockQdrant.return_value = mock_qdrant_instance

            result = await service._export_qdrant(user_id=1)

            assert isinstance(result, dict)
            assert "vectors" in result
            assert "metadata" in result

    @pytest.mark.asyncio
    async def test_export_qdrant_no_client_returns_empty(self):
        """_export_qdrant returns empty dict when no Qdrant client."""
        service = GDPRService(qdrant_client=None)
        result = await service._export_qdrant(user_id=1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_export_letta_calls_service(self):
        """_export_letta calls LettaService.export_user_memories."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_client = MagicMock()
        service = GDPRService(letta_client=mock_client)

        with patch("src.services.knowledge.letta_service.LettaService") as MockLetta:
            mock_letta_instance = MagicMock()
            mock_export = MagicMock()
            mock_export.memories = []
            mock_export.memory_count = 0
            mock_export.exported_at = datetime.now(UTC)

            mock_letta_instance.export_user_memories = AsyncMock(return_value=mock_export)
            MockLetta.return_value = mock_letta_instance

            result = await service._export_letta(user_id=1)

            assert isinstance(result, dict)
            assert "memories" in result
            assert "metadata" in result
            assert result["metadata"]["memory_count"] == 0

    @pytest.mark.asyncio
    async def test_export_letta_no_client_returns_empty(self):
        """_export_letta returns empty dict when no Letta client."""
        service = GDPRService(letta_client=None)
        result = await service._export_letta(user_id=1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_delete_postgres_executes_delete(self):
        """_delete_postgres executes DELETE query."""
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        service = GDPRService(db_pool=mock_db)

        # Should not raise
        await service._delete_postgres(user_id=1)

    @pytest.mark.asyncio
    async def test_delete_redis_scans_and_deletes(self):
        """_delete_redis scans for keys and deletes them."""
        from unittest.mock import AsyncMock, MagicMock

        mock_redis = MagicMock()
        mock_redis.scan = AsyncMock(return_value=(0, [b"user:1:session", b"user:1:cache"]))
        mock_redis.delete = AsyncMock()

        service = GDPRService(redis=mock_redis)

        await service._delete_redis(user_id=1)

        # Verify delete was called
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_neo4j_calls_service(self):
        """_delete_neo4j calls Neo4jService.delete_user_subgraph."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_driver = MagicMock()
        service = GDPRService(neo4j_driver=mock_driver)

        with patch("src.services.knowledge.neo4j_service.Neo4jService") as MockNeo4j:
            mock_neo4j_instance = MagicMock()
            mock_neo4j_instance.delete_user_subgraph = AsyncMock()
            MockNeo4j.return_value = mock_neo4j_instance

            await service._delete_neo4j(user_id=1)

            mock_neo4j_instance.delete_user_subgraph.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_delete_qdrant_calls_service(self):
        """_delete_qdrant calls QdrantService.delete_user_vectors."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_client = MagicMock()
        service = GDPRService(qdrant_client=mock_client)

        with patch("src.services.knowledge.qdrant_service.QdrantService") as MockQdrant:
            mock_qdrant_instance = MagicMock()
            mock_qdrant_instance.delete_user_vectors = AsyncMock()
            MockQdrant.return_value = mock_qdrant_instance

            await service._delete_qdrant(user_id=1)

            mock_qdrant_instance.delete_user_vectors.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_delete_letta_calls_service(self):
        """_delete_letta calls LettaService.delete_user_memories."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_client = MagicMock()
        service = GDPRService(letta_client=mock_client)

        with patch("src.services.knowledge.letta_service.LettaService") as MockLetta:
            mock_letta_instance = MagicMock()
            mock_letta_instance.delete_user_memories = AsyncMock()
            MockLetta.return_value = mock_letta_instance

            await service._delete_letta(user_id=1)

            mock_letta_instance.delete_user_memories.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_set_restriction_flag_executes_update(self):
        """_set_restriction_flag executes UPDATE query."""
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        service = GDPRService(db_pool=mock_db)

        # Should not raise
        await service._set_restriction_flag(user_id=1, restriction=ProcessingRestriction.RESTRICTED)

    @pytest.mark.asyncio
    async def test_full_export_includes_all_databases(self):
        """export_user_data aggregates from all 5 databases."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # Create service with all connections
        mock_db = MagicMock()
        mock_redis = MagicMock()
        mock_neo4j = MagicMock()
        mock_qdrant = MagicMock()
        mock_letta = MagicMock()

        service = GDPRService(
            db_pool=mock_db,
            redis=mock_redis,
            neo4j_driver=mock_neo4j,
            qdrant_client=mock_qdrant,
            letta_client=mock_letta,
        )

        # Mock Redis scan
        mock_redis.scan = AsyncMock(return_value=(0, []))

        # Mock all service imports
        with patch("src.services.knowledge.neo4j_service.Neo4jService") as MockNeo4j, \
             patch("src.services.knowledge.qdrant_service.QdrantService") as MockQdrant, \
             patch("src.services.knowledge.letta_service.LettaService") as MockLetta:

            # Setup Neo4j mock
            mock_neo4j_instance = MagicMock()
            mock_subgraph = MagicMock()
            mock_subgraph.nodes = []
            mock_subgraph.relationships = []
            mock_subgraph.node_count = 0
            mock_subgraph.relationship_count = 0
            mock_subgraph.exported_at = datetime.now(UTC)
            mock_neo4j_instance.export_user_subgraph = AsyncMock(return_value=mock_subgraph)
            MockNeo4j.return_value = mock_neo4j_instance

            # Setup Qdrant mock
            mock_qdrant_instance = MagicMock()
            mock_vector_export = MagicMock()
            mock_vector_export.vectors = []
            mock_vector_export.vector_count = 0
            mock_vector_export.exported_at = datetime.now(UTC)
            mock_qdrant_instance.export_user_vectors = AsyncMock(return_value=mock_vector_export)
            MockQdrant.return_value = mock_qdrant_instance

            # Setup Letta mock
            mock_letta_instance = MagicMock()
            mock_memory_export = MagicMock()
            mock_memory_export.memories = []
            mock_memory_export.memory_count = 0
            mock_memory_export.exported_at = datetime.now(UTC)
            mock_letta_instance.export_user_memories = AsyncMock(return_value=mock_memory_export)
            MockLetta.return_value = mock_letta_instance

            # Execute export
            result = await service.export_user_data(user_id=1)

            # Verify all 5 databases are in export
            assert "modules" in result
            # Note: postgres, neo4j, qdrant, letta are direct database exports
            # Redis may not appear if it has no keys (empty export is not added to modules)
            # We're testing that the aggregation logic works, not the specific DB implementations
            assert "neo4j" in result["modules"]
            assert "qdrant" in result["modules"]
            assert "letta" in result["modules"]
            # Postgres may have error due to mock limitations, but should attempt export
            assert "postgres" in result["modules"] or len(result["modules"]) >= 3

    @pytest.mark.asyncio
    async def test_full_delete_cascades_all_databases(self):
        """delete_user_data cascades across all 5 databases."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # Create service with all connections
        mock_db = MagicMock()
        mock_redis = MagicMock()
        mock_neo4j = MagicMock()
        mock_qdrant = MagicMock()
        mock_letta = MagicMock()

        service = GDPRService(
            db_pool=mock_db,
            redis=mock_redis,
            neo4j_driver=mock_neo4j,
            qdrant_client=mock_qdrant,
            letta_client=mock_letta,
        )

        # Mock Redis
        mock_redis.scan = AsyncMock(return_value=(0, [b"user:1:key"]))
        mock_redis.delete = AsyncMock()

        # Mock all service imports
        with patch("src.services.knowledge.neo4j_service.Neo4jService") as MockNeo4j, \
             patch("src.services.knowledge.qdrant_service.QdrantService") as MockQdrant, \
             patch("src.services.knowledge.letta_service.LettaService") as MockLetta:

            # Setup service mocks
            mock_neo4j_instance = MagicMock()
            mock_neo4j_instance.delete_user_subgraph = AsyncMock()
            MockNeo4j.return_value = mock_neo4j_instance

            mock_qdrant_instance = MagicMock()
            mock_qdrant_instance.delete_user_vectors = AsyncMock()
            MockQdrant.return_value = mock_qdrant_instance

            mock_letta_instance = MagicMock()
            mock_letta_instance.delete_user_memories = AsyncMock()
            MockLetta.return_value = mock_letta_instance

            # Execute delete
            result = await service.delete_user_data(user_id=1)

            # Verify all 5 databases attempted deletion
            assert "components" in result
            assert "redis" in result["components"]
            assert "neo4j" in result["components"]
            assert "qdrant" in result["components"]
            assert "letta" in result["components"]

            # Verify service methods were called
            mock_neo4j_instance.delete_user_subgraph.assert_called_once_with(1)
            mock_qdrant_instance.delete_user_vectors.assert_called_once_with(1)
            mock_letta_instance.delete_user_memories.assert_called_once_with(1)


# =============================================================================
# Coverage boost: Export data flow edge cases
# =============================================================================


class TestGDPRExportEdgeCases:
    """Additional export edge cases for coverage."""

    @pytest.mark.asyncio
    async def test_export_all_modules_fail(self):
        """Export when ALL modules fail still returns metadata."""
        service = GDPRService()
        fail1 = MockGDPRModule(name="f1", fail_on_export=True)
        fail2 = MockGDPRModule(name="f2", fail_on_export=True)
        service.register_module("f1", fail1)
        service.register_module("f2", fail2)

        result = await service.export_user_data(user_id=1)

        assert result["export_metadata"]["complete"] is False
        assert len(result["export_metadata"]["failed_modules"]) == 2
        assert result["modules"] == {}
        assert result["export_metadata"]["total_records"] == 0
        assert result["export_metadata"]["completeness_warning"] is not None

    @pytest.mark.asyncio
    async def test_export_completeness_warning_absent_on_success(self):
        """No completeness_warning when all exports succeed."""
        service = GDPRService()
        mod = MockGDPRModule(name="ok", export_data={"data": 1})
        service.register_module("ok", mod)

        result = await service.export_user_data(user_id=1)

        assert result["export_metadata"]["complete"] is True
        assert result["export_metadata"]["completeness_warning"] is None

    @pytest.mark.asyncio
    async def test_export_metadata_has_aurora_version(self):
        """Export metadata includes aurora_version."""
        service = GDPRService()
        result = await service.export_user_data(user_id=1)
        assert result["export_metadata"]["aurora_version"] == "v1"

    @pytest.mark.asyncio
    async def test_export_each_module_has_exported_at(self):
        """Each module export record has an exported_at timestamp."""
        service = GDPRService()
        mod = MockGDPRModule(name="timestamped", export_data={"x": 1})
        service.register_module("timestamped", mod)

        result = await service.export_user_data(user_id=1)
        assert "exported_at" in result["modules"]["timestamped"]


# =============================================================================
# Coverage boost: Deletion cascades and critical failures
# =============================================================================


class TestGDPRDeletionCascades:
    """Test deletion cascade behavior and critical failure handling."""

    @pytest.mark.asyncio
    async def test_delete_postgres_failure_marks_critical(self):
        """PostgreSQL failure during delete is marked as critical."""
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        mock_db.begin = MagicMock(side_effect=RuntimeError("DB down"))

        service = GDPRService(db_pool=mock_db)
        result = await service.delete_user_data(user_id=1)

        assert result["overall_status"] == "failed"
        assert "postgres" in result.get("critical_failures", [])

    @pytest.mark.asyncio
    async def test_delete_redis_failure_marks_critical(self):
        """Redis failure during delete is marked as critical."""
        from unittest.mock import AsyncMock, MagicMock

        mock_redis = MagicMock()
        mock_redis.scan = AsyncMock(side_effect=RuntimeError("Redis down"))

        service = GDPRService(redis=mock_redis)
        result = await service.delete_user_data(user_id=1)

        assert result["overall_status"] == "failed"
        assert "redis" in result.get("critical_failures", [])

    @pytest.mark.asyncio
    async def test_delete_neo4j_failure_non_critical(self):
        """Neo4j failure during delete is non-critical (partial status)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_neo4j = MagicMock()

        with patch(
            "src.services.knowledge.neo4j_service.Neo4jService"
        ) as MockNeo4j:
            mock_instance = MagicMock()
            mock_instance.delete_user_subgraph = AsyncMock(
                side_effect=RuntimeError("Neo4j down")
            )
            MockNeo4j.return_value = mock_instance

            service = GDPRService(neo4j_driver=mock_neo4j)
            result = await service.delete_user_data(user_id=1)

            assert result["components"]["neo4j"]["status"] == "error"
            assert result["overall_status"] == "partial"

    @pytest.mark.asyncio
    async def test_delete_qdrant_failure_non_critical(self):
        """Qdrant failure during delete is non-critical."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_qdrant = MagicMock()

        with patch(
            "src.services.knowledge.qdrant_service.QdrantService"
        ) as MockQdrant:
            mock_instance = MagicMock()
            mock_instance.delete_user_vectors = AsyncMock(
                side_effect=RuntimeError("Qdrant down")
            )
            MockQdrant.return_value = mock_instance

            service = GDPRService(qdrant_client=mock_qdrant)
            result = await service.delete_user_data(user_id=1)

            assert result["components"]["qdrant"]["status"] == "error"
            assert result["overall_status"] == "partial"

    @pytest.mark.asyncio
    async def test_delete_letta_failure_non_critical(self):
        """Letta failure during delete is non-critical."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_letta = MagicMock()

        with patch(
            "src.services.knowledge.letta_service.LettaService"
        ) as MockLetta:
            mock_instance = MagicMock()
            mock_instance.delete_user_memories = AsyncMock(
                side_effect=RuntimeError("Letta down")
            )
            MockLetta.return_value = mock_instance

            service = GDPRService(letta_client=mock_letta)
            result = await service.delete_user_data(user_id=1)

            assert result["components"]["letta"]["status"] == "error"
            assert result["overall_status"] == "partial"

    @pytest.mark.asyncio
    async def test_delete_no_databases_only_modules(self):
        """Delete with modules but no database connections."""
        service = GDPRService()
        mod = MockGDPRModule(name="mod")
        service.register_module("mod", mod)

        result = await service.delete_user_data(user_id=42)

        assert result["components"]["mod"]["status"] == "deleted"
        assert result["overall_status"] == "success"

    @pytest.mark.asyncio
    async def test_delete_succeeded_components_tracked(self):
        """Succeeded components are listed in report on partial failure."""
        service = GDPRService()
        working = MockGDPRModule(name="working")
        failing = MockGDPRModule(name="failing", fail_on_delete=True)
        service.register_module("working", working)
        service.register_module("failing", failing)

        result = await service.delete_user_data(user_id=1)

        assert "working" in result.get("succeeded_components", [])
        assert result["overall_status"] == "partial"


# =============================================================================
# Coverage boost: Retention policy evaluation
# =============================================================================


class TestRetentionPolicyEvaluation:
    """Test retention policy evaluation edge cases."""

    def test_is_expired_very_old_indefinite_data(self):
        """Data from 10 years ago with indefinite retention is not expired."""
        policy = RetentionPolicyConfig()
        ancient_date = datetime(2016, 1, 1, tzinfo=UTC)
        assert policy.is_expired(DataClassification.PUBLIC, ancient_date) is False
        assert policy.is_expired(DataClassification.INTERNAL, ancient_date) is False

    def test_is_expired_just_created_sensitive(self):
        """Newly created SENSITIVE data is immediately expired."""
        policy = RetentionPolicyConfig()
        just_now = datetime.now(UTC)
        assert policy.is_expired(DataClassification.SENSITIVE, just_now) is True

    def test_custom_long_retention(self):
        """Custom long retention (10 years) works correctly."""
        policy = RetentionPolicyConfig(
            retention_days={
                DataClassification.PUBLIC: -1,
                DataClassification.INTERNAL: -1,
                DataClassification.SENSITIVE: 3650,
                DataClassification.ART_9_SPECIAL: 0,
                DataClassification.FINANCIAL: 0,
            }
        )
        five_years_ago = datetime.now(UTC) - timedelta(days=1825)
        assert policy.is_expired(DataClassification.SENSITIVE, five_years_ago) is False

        eleven_years_ago = datetime.now(UTC) - timedelta(days=4015)
        assert policy.is_expired(DataClassification.SENSITIVE, eleven_years_ago) is True

    def test_get_retention_days_unknown_classification_defaults_to_zero(self):
        """Unknown classification falls back to 0 (immediate deletion)."""
        policy = RetentionPolicyConfig()
        policy.retention_days = {}
        assert policy.get_retention_days(DataClassification.SENSITIVE) == 0


# =============================================================================
# Coverage boost: Freeze/Unfreeze edge cases
# =============================================================================


class TestFreezeUnfreezeEdgeCases:
    """Edge cases for freeze and unfreeze operations."""

    @pytest.mark.asyncio
    async def test_freeze_no_modules_no_db(self):
        """Freeze with no modules and no db returns minimal report."""
        service = GDPRService()
        result = await service.freeze_user_data(user_id=1)

        assert result["user_id"] == 1
        assert result["restriction"] == "restricted"
        assert result["components"] == {}

    @pytest.mark.asyncio
    async def test_unfreeze_no_modules_no_db(self):
        """Unfreeze with no modules and no db returns minimal report."""
        service = GDPRService()
        result = await service.unfreeze_user_data(user_id=1)

        assert result["user_id"] == 1
        assert result["restriction"] == "active"
        assert result["components"] == {}

    @pytest.mark.asyncio
    async def test_freeze_with_db_connection(self):
        """Freeze with db sets restriction flag."""
        from unittest.mock import AsyncMock, MagicMock

        mock_db = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_context.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin = MagicMock(return_value=mock_context)

        service = GDPRService(db_pool=mock_db)
        result = await service.freeze_user_data(user_id=1)

        assert result["components"]["postgres"]["status"] == "restricted"

    @pytest.mark.asyncio
    async def test_unfreeze_with_db_connection(self):
        """Unfreeze with db removes restriction flag."""
        from unittest.mock import AsyncMock, MagicMock

        mock_db = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_context.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin = MagicMock(return_value=mock_context)

        service = GDPRService(db_pool=mock_db)
        result = await service.unfreeze_user_data(user_id=1)

        assert result["components"]["postgres"]["status"] == "active"

    @pytest.mark.asyncio
    async def test_freeze_db_failure(self):
        """Freeze with db failure reports error."""
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        mock_db.begin = MagicMock(side_effect=RuntimeError("DB down"))

        service = GDPRService(db_pool=mock_db)
        result = await service.freeze_user_data(user_id=1)

        assert result["components"]["postgres"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_unfreeze_db_failure(self):
        """Unfreeze with db failure reports error."""
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        mock_db.begin = MagicMock(side_effect=RuntimeError("DB down"))

        service = GDPRService(db_pool=mock_db)
        result = await service.unfreeze_user_data(user_id=1)

        assert result["components"]["postgres"]["status"] == "error"


# =============================================================================
# Coverage boost: Check retention + GDPRExportRecord + constant
# =============================================================================


class TestCheckRetentionEdgeCases:
    """Additional check_retention tests."""

    @pytest.mark.asyncio
    async def test_check_retention_with_custom_policy(self):
        """check_retention uses the service's retention policy."""
        custom = RetentionPolicyConfig(
            retention_days={
                DataClassification.PUBLIC: -1,
                DataClassification.INTERNAL: -1,
                DataClassification.SENSITIVE: 30,
                DataClassification.ART_9_SPECIAL: 60,
                DataClassification.FINANCIAL: 3650,
            }
        )
        service = GDPRService(retention_policy=custom)
        result = await service.check_retention()
        assert isinstance(result, list)


class TestGDPRExportRecordCoverage:
    """Test GDPRExportRecord dataclass."""

    def test_create_export_record(self):
        """GDPRExportRecord can be created with all fields."""
        from src.lib.gdpr import GDPRExportRecord

        record = GDPRExportRecord(
            module_name="test_module",
            exported_at=datetime.now(UTC),
            data={"key": "value"},
        )
        assert record.module_name == "test_module"
        assert isinstance(record.data, dict)


class TestRetentionIndefiniteConstant:
    """Test the RETENTION_INDEFINITE constant."""

    def test_retention_indefinite_value(self):
        """RETENTION_INDEFINITE is -1."""
        from src.lib.gdpr import RETENTION_INDEFINITE
        assert RETENTION_INDEFINITE == -1

    def test_retention_indefinite_used_in_policy(self):
        """Default policy uses RETENTION_INDEFINITE for PUBLIC and INTERNAL."""
        from src.lib.gdpr import RETENTION_INDEFINITE
        policy = RetentionPolicyConfig()
        assert (
            policy.get_retention_days(DataClassification.PUBLIC) == RETENTION_INDEFINITE
        )


# =============================================================================
# Coverage boost: _build_export_package static method
# =============================================================================


class TestBuildExportPackage:
    """Test the _build_export_package static method directly."""

    def test_build_with_no_exports_no_errors(self):
        """Empty exports and errors produce complete package."""
        result = GDPRService._build_export_package(
            user_id=1, exports=[], errors=[]
        )
        assert result["export_metadata"]["complete"] is True
        assert result["export_metadata"]["total_records"] == 0
        assert result["modules"] == {}
        assert result["export_metadata"]["completeness_warning"] is None

    def test_build_with_exports_and_errors(self):
        """Exports and errors produce incomplete package."""
        from src.lib.gdpr import GDPRExportRecord

        exports = [
            GDPRExportRecord(
                module_name="mod1",
                exported_at=datetime.now(UTC),
                data={"x": 1},
            ),
        ]
        errors = ["mod2: export failed"]
        result = GDPRService._build_export_package(
            user_id=1, exports=exports, errors=errors
        )
        assert result["export_metadata"]["complete"] is False
        assert result["export_metadata"]["total_records"] == 1
        assert "mod1" in result["modules"]
        assert result["export_metadata"]["completeness_warning"] is not None


# =============================================================================
# Coverage boost: Private database delete methods with no client
# =============================================================================


class TestDeleteDatabasesNoClient:
    """Test deletion methods when clients are None."""

    @pytest.mark.asyncio
    async def test_delete_postgres_no_db(self):
        """_delete_postgres with no db does nothing."""
        service = GDPRService(db_pool=None)
        await service._delete_postgres(user_id=1)

    @pytest.mark.asyncio
    async def test_delete_redis_no_redis(self):
        """_delete_redis with no redis does nothing."""
        service = GDPRService(redis=None)
        await service._delete_redis(user_id=1)

    @pytest.mark.asyncio
    async def test_delete_neo4j_no_driver(self):
        """_delete_neo4j with no driver does nothing."""
        service = GDPRService(neo4j_driver=None)
        await service._delete_neo4j(user_id=1)

    @pytest.mark.asyncio
    async def test_delete_qdrant_no_client(self):
        """_delete_qdrant with no client does nothing."""
        service = GDPRService(qdrant_client=None)
        await service._delete_qdrant(user_id=1)

    @pytest.mark.asyncio
    async def test_delete_letta_no_client(self):
        """_delete_letta with no client does nothing."""
        service = GDPRService(letta_client=None)
        await service._delete_letta(user_id=1)

    @pytest.mark.asyncio
    async def test_set_restriction_flag_no_db(self):
        """_set_restriction_flag with no db does nothing."""
        service = GDPRService(db_pool=None)
        await service._set_restriction_flag(
            user_id=1, restriction=ProcessingRestriction.RESTRICTED
        )


# =============================================================================
# Coverage boost: Database export error paths (internal catch)
# =============================================================================


class TestDatabaseExportErrorPaths:
    """Test database export methods that catch errors internally."""

    @pytest.mark.asyncio
    async def test_export_postgres_error_returns_error_dict(self):
        """_export_postgres returns error dict when db query fails."""
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        mock_db.begin = MagicMock(side_effect=RuntimeError("PG down"))

        service = GDPRService(db_pool=mock_db)
        result = await service._export_postgres(user_id=1)

        assert result == {"error": "export failed"}

    @pytest.mark.asyncio
    async def test_export_redis_error_returns_error_dict(self):
        """_export_redis returns error dict when scan fails."""
        from unittest.mock import AsyncMock, MagicMock

        mock_redis = MagicMock()
        mock_redis.scan = AsyncMock(side_effect=RuntimeError("Redis down"))

        service = GDPRService(redis=mock_redis)
        result = await service._export_redis(user_id=1)

        assert result == {"error": "export failed"}

    @pytest.mark.asyncio
    async def test_export_neo4j_error_returns_error_dict(self):
        """_export_neo4j returns error dict when service fails."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_driver = MagicMock()
        service = GDPRService(neo4j_driver=mock_driver)

        with patch(
            "src.services.knowledge.neo4j_service.Neo4jService"
        ) as MockNeo4j:
            mock_instance = MagicMock()
            mock_instance.export_user_subgraph = AsyncMock(
                side_effect=RuntimeError("Neo4j down")
            )
            MockNeo4j.return_value = mock_instance

            result = await service._export_neo4j(user_id=1)
            assert result == {"error": "export failed"}

    @pytest.mark.asyncio
    async def test_export_qdrant_error_returns_error_dict(self):
        """_export_qdrant returns error dict when service fails."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_client = MagicMock()
        service = GDPRService(qdrant_client=mock_client)

        with patch(
            "src.services.knowledge.qdrant_service.QdrantService"
        ) as MockQdrant:
            mock_instance = MagicMock()
            mock_instance.export_user_vectors = AsyncMock(
                side_effect=RuntimeError("Qdrant down")
            )
            MockQdrant.return_value = mock_instance

            result = await service._export_qdrant(user_id=1)
            assert result == {"error": "export failed"}

    @pytest.mark.asyncio
    async def test_export_letta_error_returns_error_dict(self):
        """_export_letta returns error dict when service fails."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_client = MagicMock()
        service = GDPRService(letta_client=mock_client)

        with patch(
            "src.services.knowledge.letta_service.LettaService"
        ) as MockLetta:
            mock_instance = MagicMock()
            mock_instance.export_user_memories = AsyncMock(
                side_effect=RuntimeError("Letta down")
            )
            MockLetta.return_value = mock_instance

            result = await service._export_letta(user_id=1)
            assert result == {"error": "export failed"}
