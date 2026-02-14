"""
Infrastructure module for Aurora Sun V1.

This module provides production infrastructure components:
- Health checks for all services (PG, Redis, Neo4j, Qdrant, Letta)
- Prometheus metrics integration
- RBAC (Role-Based Access Control)
- Security middleware (headers, correlation IDs, LLM cost limiter)
- Backup/restore strategy

All components are designed for production hardening (Phase 4.6).

References:
    - ROADMAP.md Phase 4.6 (Production Hardening)
    - ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
"""

from src.infra.backup import BackupService, RestoreService
from src.infra.health import HealthCheckService, ServiceStatus
from src.infra.middleware import (
    CorrelationIDMiddleware,
    LLMCostLimiterMiddleware,
    SecurityHeadersMiddleware,
)
from src.infra.monitoring import PrometheusMetrics, record_llm_cost, record_request
from src.infra.rbac import Permission, Role, check_permission, require_permission

__all__ = [
    # Health
    "HealthCheckService",
    "ServiceStatus",
    # Monitoring
    "PrometheusMetrics",
    "record_request",
    "record_llm_cost",
    # RBAC
    "Role",
    "Permission",
    "check_permission",
    "require_permission",
    # Middleware
    "SecurityHeadersMiddleware",
    "CorrelationIDMiddleware",
    "LLMCostLimiterMiddleware",
    # Backup
    "BackupService",
    "RestoreService",
]
