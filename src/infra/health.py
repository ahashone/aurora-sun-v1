"""
Health Check Service for Aurora Sun V1.

Provides health check endpoints for all infrastructure services:
- PostgreSQL (main database)
- Redis (caching/rate limiting)
- Neo4j (knowledge graph)
- Qdrant (vector store)
- Letta (memory service)

Used by:
- Docker healthchecks
- Kubernetes liveness/readiness probes
- Monitoring systems (Prometheus, Grafana)

References:
    - ROADMAP.md Phase 4.6 (Production Hardening)
    - docker-compose.prod.yml healthcheck configuration
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Service health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a health check for a single service."""

    service_name: str
    status: ServiceStatus
    message: str
    response_time_ms: float
    timestamp: datetime
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "service": self.service_name,
            "status": self.status.value,
            "message": self.message,
            "response_time_ms": self.response_time_ms,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details or {},
        }


@dataclass
class SystemHealthReport:
    """Overall system health report."""

    status: ServiceStatus
    services: list[HealthCheckResult]
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "services": [s.to_dict() for s in self.services],
        }


class HealthCheckService:
    """
    Health check service for all infrastructure components.

    This service provides:
    - Individual service health checks
    - Overall system health aggregation
    - Async parallel checks for performance
    - Detailed error reporting

    Example:
        >>> service = HealthCheckService(
        ...     db_url="postgresql://...",
        ...     redis_url="redis://localhost:6379"
        ... )
        >>> report = await service.check_all()
        >>> print(report.status)
        ServiceStatus.HEALTHY
    """

    def __init__(
        self,
        db_url: str | None = None,
        redis_url: str | None = None,
        neo4j_url: str | None = None,
        qdrant_url: str | None = None,
        letta_url: str | None = None,
        timeout_seconds: float = 5.0,
    ):
        """
        Initialize health check service.

        Args:
            db_url: PostgreSQL connection URL
            redis_url: Redis connection URL
            neo4j_url: Neo4j connection URL
            qdrant_url: Qdrant HTTP URL
            letta_url: Letta HTTP URL
            timeout_seconds: Maximum time to wait for each check
        """
        self.db_url = db_url
        self.redis_url = redis_url
        self.neo4j_url = neo4j_url
        self.qdrant_url = qdrant_url
        self.letta_url = letta_url
        self.timeout = timeout_seconds

    async def check_postgres(self) -> HealthCheckResult:
        """
        Check PostgreSQL health.

        Tests:
        - Connection establishment
        - Simple query execution
        - Response time

        Returns:
            HealthCheckResult with connection status
        """
        start_time = asyncio.get_event_loop().time()

        if not self.db_url:
            return HealthCheckResult(
                service_name="postgresql",
                status=ServiceStatus.UNKNOWN,
                message="Database URL not configured",
                response_time_ms=0.0,
                timestamp=datetime.utcnow(),
            )

        try:
            import asyncpg  # type: ignore[import-untyped]

            conn = await asyncio.wait_for(
                asyncpg.connect(self.db_url), timeout=self.timeout
            )

            try:
                # Simple query to verify connection
                result = await conn.fetchval("SELECT 1")
                if result != 1:
                    raise ValueError(f"Unexpected query result: {result}")

                response_time = (asyncio.get_event_loop().time() - start_time) * 1000

                return HealthCheckResult(
                    service_name="postgresql",
                    status=ServiceStatus.HEALTHY,
                    message="Database connection successful",
                    response_time_ms=response_time,
                    timestamp=datetime.utcnow(),
                    details={"query": "SELECT 1"},
                )

            finally:
                await conn.close()

        except TimeoutError:
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            return HealthCheckResult(
                service_name="postgresql",
                status=ServiceStatus.UNHEALTHY,
                message=f"Connection timeout after {self.timeout}s",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
            )

        except Exception as e:
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.exception("PostgreSQL health check failed")
            return HealthCheckResult(
                service_name="postgresql",
                status=ServiceStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
            )

    async def check_redis(self) -> HealthCheckResult:
        """
        Check Redis health.

        Tests:
        - Connection establishment
        - PING command
        - Response time

        Returns:
            HealthCheckResult with connection status
        """
        start_time = asyncio.get_event_loop().time()

        if not self.redis_url:
            return HealthCheckResult(
                service_name="redis",
                status=ServiceStatus.UNKNOWN,
                message="Redis URL not configured",
                response_time_ms=0.0,
                timestamp=datetime.utcnow(),
            )

        try:
            import redis.asyncio as redis

            client = await asyncio.wait_for(
                redis.from_url(self.redis_url), timeout=self.timeout  # type: ignore[no-untyped-call]
            )

            try:
                # PING command
                pong = await asyncio.wait_for(client.ping(), timeout=self.timeout)
                if not pong:
                    raise ValueError("PING command failed")

                response_time = (asyncio.get_event_loop().time() - start_time) * 1000

                return HealthCheckResult(
                    service_name="redis",
                    status=ServiceStatus.HEALTHY,
                    message="Redis connection successful",
                    response_time_ms=response_time,
                    timestamp=datetime.utcnow(),
                    details={"command": "PING"},
                )

            finally:
                await client.close()

        except TimeoutError:
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            return HealthCheckResult(
                service_name="redis",
                status=ServiceStatus.UNHEALTHY,
                message=f"Connection timeout after {self.timeout}s",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
            )

        except Exception as e:
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.exception("Redis health check failed")
            return HealthCheckResult(
                service_name="redis",
                status=ServiceStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
            )

    async def check_neo4j(self) -> HealthCheckResult:
        """
        Check Neo4j health.

        Tests:
        - Connection establishment
        - Simple query execution
        - Response time

        Returns:
            HealthCheckResult with connection status
        """
        start_time = asyncio.get_event_loop().time()

        if not self.neo4j_url:
            return HealthCheckResult(
                service_name="neo4j",
                status=ServiceStatus.UNKNOWN,
                message="Neo4j URL not configured",
                response_time_ms=0.0,
                timestamp=datetime.utcnow(),
            )

        try:
            from neo4j import AsyncGraphDatabase

            driver = AsyncGraphDatabase.driver(self.neo4j_url)

            try:
                async with driver.session() as session:
                    # Simple query to verify connection
                    result = await asyncio.wait_for(
                        session.run("RETURN 1 AS num"), timeout=self.timeout
                    )
                    record = await result.single()
                    if not record or record["num"] != 1:
                        raise ValueError(f"Unexpected query result: {record}")

                response_time = (asyncio.get_event_loop().time() - start_time) * 1000

                return HealthCheckResult(
                    service_name="neo4j",
                    status=ServiceStatus.HEALTHY,
                    message="Neo4j connection successful",
                    response_time_ms=response_time,
                    timestamp=datetime.utcnow(),
                    details={"query": "RETURN 1 AS num"},
                )

            finally:
                await driver.close()

        except TimeoutError:
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            return HealthCheckResult(
                service_name="neo4j",
                status=ServiceStatus.UNHEALTHY,
                message=f"Connection timeout after {self.timeout}s",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
            )

        except Exception as e:
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.exception("Neo4j health check failed")
            return HealthCheckResult(
                service_name="neo4j",
                status=ServiceStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
            )

    async def check_qdrant(self) -> HealthCheckResult:
        """
        Check Qdrant health.

        Tests:
        - HTTP connection
        - Health endpoint
        - Response time

        Returns:
            HealthCheckResult with connection status
        """
        start_time = asyncio.get_event_loop().time()

        if not self.qdrant_url:
            return HealthCheckResult(
                service_name="qdrant",
                status=ServiceStatus.UNKNOWN,
                message="Qdrant URL not configured",
                response_time_ms=0.0,
                timestamp=datetime.utcnow(),
            )

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await asyncio.wait_for(
                    client.get(f"{self.qdrant_url}/health"), timeout=self.timeout
                )

                if response.status_code != 200:
                    raise ValueError(f"Unexpected status code: {response.status_code}")

                response_time = (asyncio.get_event_loop().time() - start_time) * 1000

                return HealthCheckResult(
                    service_name="qdrant",
                    status=ServiceStatus.HEALTHY,
                    message="Qdrant connection successful",
                    response_time_ms=response_time,
                    timestamp=datetime.utcnow(),
                    details={"endpoint": "/health"},
                )

        except TimeoutError:
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            return HealthCheckResult(
                service_name="qdrant",
                status=ServiceStatus.UNHEALTHY,
                message=f"Connection timeout after {self.timeout}s",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
            )

        except Exception as e:
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.exception("Qdrant health check failed")
            return HealthCheckResult(
                service_name="qdrant",
                status=ServiceStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
            )

    async def check_letta(self) -> HealthCheckResult:
        """
        Check Letta health.

        Tests:
        - HTTP connection
        - Health/status endpoint
        - Response time

        Returns:
            HealthCheckResult with connection status
        """
        start_time = asyncio.get_event_loop().time()

        if not self.letta_url:
            return HealthCheckResult(
                service_name="letta",
                status=ServiceStatus.UNKNOWN,
                message="Letta URL not configured",
                response_time_ms=0.0,
                timestamp=datetime.utcnow(),
            )

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await asyncio.wait_for(
                    client.get(f"{self.letta_url}/health"), timeout=self.timeout
                )

                if response.status_code != 200:
                    raise ValueError(f"Unexpected status code: {response.status_code}")

                response_time = (asyncio.get_event_loop().time() - start_time) * 1000

                return HealthCheckResult(
                    service_name="letta",
                    status=ServiceStatus.HEALTHY,
                    message="Letta connection successful",
                    response_time_ms=response_time,
                    timestamp=datetime.utcnow(),
                    details={"endpoint": "/health"},
                )

        except TimeoutError:
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            return HealthCheckResult(
                service_name="letta",
                status=ServiceStatus.UNHEALTHY,
                message=f"Connection timeout after {self.timeout}s",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
            )

        except Exception as e:
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.exception("Letta health check failed")
            return HealthCheckResult(
                service_name="letta",
                status=ServiceStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                response_time_ms=response_time,
                timestamp=datetime.utcnow(),
            )

    async def check_all(self) -> SystemHealthReport:
        """
        Check all configured services in parallel.

        Returns:
            SystemHealthReport with aggregated health status

        Example:
            >>> report = await service.check_all()
            >>> if report.status == ServiceStatus.HEALTHY:
            ...     print("All systems operational")
        """
        # Run all checks in parallel
        results = await asyncio.gather(
            self.check_postgres(),
            self.check_redis(),
            self.check_neo4j(),
            self.check_qdrant(),
            self.check_letta(),
            return_exceptions=True,
        )

        # Filter out exceptions
        health_results: list[HealthCheckResult] = []
        for result in results:
            if isinstance(result, HealthCheckResult):
                health_results.append(result)
            elif isinstance(result, Exception):
                logger.exception("Health check failed with exception", exc_info=result)

        # Determine overall status
        if not health_results:
            overall_status = ServiceStatus.UNKNOWN
        elif all(r.status == ServiceStatus.HEALTHY for r in health_results):
            overall_status = ServiceStatus.HEALTHY
        elif any(r.status == ServiceStatus.UNHEALTHY for r in health_results):
            overall_status = ServiceStatus.DEGRADED
        else:
            overall_status = ServiceStatus.UNKNOWN

        return SystemHealthReport(
            status=overall_status,
            services=health_results,
            timestamp=datetime.utcnow(),
        )


# Convenience function for quick health check
async def check_system_health(
    db_url: str | None = None,
    redis_url: str | None = None,
    neo4j_url: str | None = None,
    qdrant_url: str | None = None,
    letta_url: str | None = None,
) -> SystemHealthReport:
    """
    Quick system health check convenience function.

    Args:
        db_url: PostgreSQL connection URL
        redis_url: Redis connection URL
        neo4j_url: Neo4j connection URL
        qdrant_url: Qdrant HTTP URL
        letta_url: Letta HTTP URL

    Returns:
        SystemHealthReport

    Example:
        >>> report = await check_system_health(db_url="postgresql://...")
        >>> print(report.to_dict())
    """
    service = HealthCheckService(
        db_url=db_url,
        redis_url=redis_url,
        neo4j_url=neo4j_url,
        qdrant_url=qdrant_url,
        letta_url=letta_url,
    )
    return await service.check_all()
