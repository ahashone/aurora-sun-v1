"""
Tests for health check service.

Test coverage:
- Individual service health checks (PostgreSQL, Redis, Neo4j, Qdrant, Letta)
- Overall system health aggregation
- Timeout handling
- Error handling
- Status determination logic
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infra.health import (
    HealthCheckResult,
    HealthCheckService,
    ServiceStatus,
    SystemHealthReport,
    check_system_health,
)

# =============================================================================
# Individual Service Health Check Tests
# =============================================================================


@pytest.mark.asyncio
async def test_check_postgres_healthy() -> None:
    """Test PostgreSQL health check when service is healthy."""
    service = HealthCheckService(db_url="postgresql://test")

    with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect:
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)
        mock_conn.close = AsyncMock()
        mock_connect.return_value = mock_conn

        result = await service.check_postgres()

        assert result.service_name == "postgresql"
        assert result.status == ServiceStatus.HEALTHY
        assert result.response_time_ms > 0
        assert "successful" in result.message.lower()


@pytest.mark.asyncio
async def test_check_postgres_timeout() -> None:
    """Test PostgreSQL health check timeout."""
    service = HealthCheckService(db_url="postgresql://test", timeout_seconds=0.1)

    with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect:
        # Simulate timeout
        async def slow_connect(*args: object, **kwargs: object) -> None:
            await asyncio.sleep(1.0)

        mock_connect.side_effect = slow_connect

        result = await service.check_postgres()

        assert result.status == ServiceStatus.UNHEALTHY
        assert "timeout" in result.message.lower()


@pytest.mark.asyncio
async def test_check_postgres_connection_failed() -> None:
    """Test PostgreSQL health check when connection fails."""
    service = HealthCheckService(db_url="postgresql://test")

    with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.side_effect = ConnectionError("Connection refused")

        result = await service.check_postgres()

        assert result.status == ServiceStatus.UNHEALTHY
        assert "failed" in result.message.lower()


@pytest.mark.asyncio
async def test_check_postgres_no_url() -> None:
    """Test PostgreSQL health check when URL not configured."""
    service = HealthCheckService(db_url=None)

    result = await service.check_postgres()

    assert result.status == ServiceStatus.UNKNOWN
    assert "not configured" in result.message.lower()


@pytest.mark.asyncio
async def test_check_redis_healthy() -> None:
    """Test Redis health check when service is healthy."""
    service = HealthCheckService(redis_url="redis://localhost:6379")

    with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.close = AsyncMock()
        mock_from_url.return_value = mock_client

        result = await service.check_redis()

        assert result.service_name == "redis"
        assert result.status == ServiceStatus.HEALTHY
        assert result.response_time_ms > 0


@pytest.mark.asyncio
async def test_check_redis_timeout() -> None:
    """Test Redis health check timeout."""
    service = HealthCheckService(redis_url="redis://localhost", timeout_seconds=0.1)

    with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:

        async def slow_connect(*args: object, **kwargs: object) -> AsyncMock:
            await asyncio.sleep(1.0)
            return AsyncMock()

        mock_from_url.side_effect = slow_connect

        result = await service.check_redis()

        assert result.status == ServiceStatus.UNHEALTHY
        assert "timeout" in result.message.lower()


@pytest.mark.asyncio
async def test_check_neo4j_healthy() -> None:
    """Test Neo4j health check when service is healthy."""
    service = HealthCheckService(neo4j_url="neo4j://localhost:7687")

    with patch("neo4j.AsyncGraphDatabase.driver") as mock_driver:
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_record = {"num": 1}
        mock_result.single = AsyncMock(return_value=mock_record)
        mock_session.run = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        mock_driver_instance = MagicMock()
        mock_driver_instance.session = MagicMock(return_value=mock_session)
        mock_driver_instance.close = AsyncMock()
        mock_driver.return_value = mock_driver_instance

        result = await service.check_neo4j()

        assert result.service_name == "neo4j"
        assert result.status == ServiceStatus.HEALTHY


@pytest.mark.asyncio
async def test_check_qdrant_healthy() -> None:
    """Test Qdrant health check when service is healthy."""
    service = HealthCheckService(qdrant_url="http://localhost:6333")

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await service.check_qdrant()

        assert result.service_name == "qdrant"
        assert result.status == ServiceStatus.HEALTHY


@pytest.mark.asyncio
async def test_check_letta_healthy() -> None:
    """Test Letta health check when service is healthy."""
    service = HealthCheckService(letta_url="http://localhost:8080")

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await service.check_letta()

        assert result.service_name == "letta"
        assert result.status == ServiceStatus.HEALTHY


# =============================================================================
# System Health Aggregation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_check_all_healthy() -> None:
    """Test overall system health when all services are healthy."""
    service = HealthCheckService(
        db_url="postgresql://test",
        redis_url="redis://test",
        neo4j_url="neo4j://test",
        qdrant_url="http://test",
        letta_url="http://test",
    )

    # Mock all checks to return healthy
    with (
        patch.object(service, "check_postgres", return_value=HealthCheckResult(
            service_name="postgresql",
            status=ServiceStatus.HEALTHY,
            message="OK",
            response_time_ms=10.0,
            timestamp=datetime.now(UTC),
        )),
        patch.object(service, "check_redis", return_value=HealthCheckResult(
            service_name="redis",
            status=ServiceStatus.HEALTHY,
            message="OK",
            response_time_ms=5.0,
            timestamp=datetime.now(UTC),
        )),
        patch.object(service, "check_neo4j", return_value=HealthCheckResult(
            service_name="neo4j",
            status=ServiceStatus.HEALTHY,
            message="OK",
            response_time_ms=15.0,
            timestamp=datetime.now(UTC),
        )),
        patch.object(service, "check_qdrant", return_value=HealthCheckResult(
            service_name="qdrant",
            status=ServiceStatus.HEALTHY,
            message="OK",
            response_time_ms=8.0,
            timestamp=datetime.now(UTC),
        )),
        patch.object(service, "check_letta", return_value=HealthCheckResult(
            service_name="letta",
            status=ServiceStatus.HEALTHY,
            message="OK",
            response_time_ms=12.0,
            timestamp=datetime.now(UTC),
        )),
    ):
        report = await service.check_all()

        assert report.status == ServiceStatus.HEALTHY
        assert len(report.services) == 5


@pytest.mark.asyncio
async def test_check_all_degraded() -> None:
    """Test system health when one service is unhealthy."""
    service = HealthCheckService(
        db_url="postgresql://test",
        redis_url="redis://test",
    )

    with (
        patch.object(service, "check_postgres", return_value=HealthCheckResult(
            service_name="postgresql",
            status=ServiceStatus.HEALTHY,
            message="OK",
            response_time_ms=10.0,
            timestamp=datetime.now(UTC),
        )),
        patch.object(service, "check_redis", return_value=HealthCheckResult(
            service_name="redis",
            status=ServiceStatus.UNHEALTHY,
            message="Connection failed",
            response_time_ms=0.0,
            timestamp=datetime.now(UTC),
        )),
        patch.object(service, "check_neo4j", return_value=HealthCheckResult(
            service_name="neo4j",
            status=ServiceStatus.HEALTHY,
            message="OK",
            response_time_ms=15.0,
            timestamp=datetime.now(UTC),
        )),
        patch.object(service, "check_qdrant", return_value=HealthCheckResult(
            service_name="qdrant",
            status=ServiceStatus.HEALTHY,
            message="OK",
            response_time_ms=8.0,
            timestamp=datetime.now(UTC),
        )),
        patch.object(service, "check_letta", return_value=HealthCheckResult(
            service_name="letta",
            status=ServiceStatus.HEALTHY,
            message="OK",
            response_time_ms=12.0,
            timestamp=datetime.now(UTC),
        )),
    ):
        report = await service.check_all()

        assert report.status == ServiceStatus.DEGRADED
        assert any(s.status == ServiceStatus.UNHEALTHY for s in report.services)


# =============================================================================
# Serialization Tests
# =============================================================================


def test_health_check_result_to_dict() -> None:
    """Test HealthCheckResult serialization."""
    result = HealthCheckResult(
        service_name="test",
        status=ServiceStatus.HEALTHY,
        message="Test message",
        response_time_ms=10.5,
        timestamp=datetime(2026, 2, 14, 12, 0, 0),
        details={"key": "value"},
    )

    data = result.to_dict()

    assert data["service"] == "test"
    assert data["status"] == "healthy"
    assert data["message"] == "Test message"
    assert data["response_time_ms"] == 10.5
    assert data["details"] == {"key": "value"}


def test_system_health_report_to_dict() -> None:
    """Test SystemHealthReport serialization."""
    result1 = HealthCheckResult(
        service_name="service1",
        status=ServiceStatus.HEALTHY,
        message="OK",
        response_time_ms=5.0,
        timestamp=datetime.now(UTC),
    )

    report = SystemHealthReport(
        status=ServiceStatus.HEALTHY,
        services=[result1],
        timestamp=datetime.now(UTC),
    )

    data = report.to_dict()

    assert data["status"] == "healthy"
    assert len(data["services"]) == 1
    assert data["services"][0]["service"] == "service1"


# =============================================================================
# Convenience Function Tests
# =============================================================================


@pytest.mark.asyncio
async def test_check_system_health_convenience() -> None:
    """Test check_system_health convenience function."""
    with patch.object(HealthCheckService, "check_all") as mock_check_all:
        mock_check_all.return_value = SystemHealthReport(
            status=ServiceStatus.HEALTHY,
            services=[],
            timestamp=datetime.now(UTC),
        )

        report = await check_system_health(db_url="postgresql://test")

        assert report.status == ServiceStatus.HEALTHY
        mock_check_all.assert_called_once()
