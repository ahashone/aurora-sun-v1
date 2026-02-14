"""
Prometheus Monitoring for Aurora Sun V1.

Provides Prometheus metrics integration for:
- HTTP request latency and error rates
- LLM API call costs and latency
- Active user counts
- Database query performance
- Module invocation metrics
- Crisis detection metrics

Used by:
- Prometheus scraping
- Grafana dashboards
- Alertmanager rules

References:
    - ROADMAP.md Phase 4.6 (Production Hardening)
    - Prometheus best practices
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, generate_latest

logger = logging.getLogger(__name__)


# =============================================================================
# Metrics Definitions
# =============================================================================

# HTTP Request Metrics
http_requests_total = Counter(
    "aurora_http_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "aurora_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

http_request_errors_total = Counter(
    "aurora_http_request_errors_total",
    "Total HTTP request errors",
    ["method", "endpoint", "error_type"],
)

# LLM API Metrics
llm_api_calls_total = Counter(
    "aurora_llm_api_calls_total",
    "Total LLM API calls",
    ["provider", "model", "agent"],
)

llm_api_duration_seconds = Histogram(
    "aurora_llm_api_duration_seconds",
    "LLM API call latency in seconds",
    ["provider", "model"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

llm_api_cost_dollars = Counter(
    "aurora_llm_api_cost_dollars_total",
    "Total LLM API cost in USD",
    ["provider", "model", "agent"],
)

llm_tokens_used = Counter(
    "aurora_llm_tokens_used_total",
    "Total LLM tokens used",
    ["provider", "model", "token_type"],
)

# User Metrics
active_users_gauge = Gauge(
    "aurora_active_users",
    "Number of active users",
    ["segment"],
)

daily_active_users = Gauge(
    "aurora_daily_active_users",
    "Number of daily active users",
)

# Database Metrics
db_query_duration_seconds = Histogram(
    "aurora_db_query_duration_seconds",
    "Database query latency in seconds",
    ["operation", "table"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

db_connections_active = Gauge(
    "aurora_db_connections_active",
    "Number of active database connections",
)

# Module Metrics
module_invocations_total = Counter(
    "aurora_module_invocations_total",
    "Total module invocations",
    ["module", "segment"],
)

module_duration_seconds = Histogram(
    "aurora_module_duration_seconds",
    "Module execution time in seconds",
    ["module"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

module_errors_total = Counter(
    "aurora_module_errors_total",
    "Total module errors",
    ["module", "error_type"],
)

# Crisis Detection Metrics
crisis_signals_detected = Counter(
    "aurora_crisis_signals_detected_total",
    "Total crisis signals detected",
    ["level", "source"],
)

crisis_interventions_triggered = Counter(
    "aurora_crisis_interventions_triggered_total",
    "Total crisis interventions triggered",
    ["level"],
)

# System Metrics
system_health_status = Gauge(
    "aurora_system_health_status",
    "Overall system health (1=healthy, 0.5=degraded, 0=unhealthy)",
)

service_health_status = Gauge(
    "aurora_service_health_status",
    "Individual service health (1=healthy, 0=unhealthy)",
    ["service"],
)


# =============================================================================
# Metrics Recording Functions
# =============================================================================


def record_request(
    method: str,
    endpoint: str,
    status: int,
    duration_seconds: float,
    error_type: str | None = None,
) -> None:
    """
    Record HTTP request metrics.

    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: Request endpoint
        status: HTTP status code
        duration_seconds: Request duration in seconds
        error_type: Optional error type if request failed
    """
    http_requests_total.labels(method=method, endpoint=endpoint, status=str(status)).inc()
    http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(
        duration_seconds
    )

    if error_type:
        http_request_errors_total.labels(
            method=method, endpoint=endpoint, error_type=error_type
        ).inc()


def record_llm_call(
    provider: str,
    model: str,
    agent: str,
    duration_seconds: float,
    cost_dollars: float,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """
    Record LLM API call metrics.

    Args:
        provider: LLM provider (anthropic, openai, groq)
        model: Model name (claude-opus-4-6, etc.)
        agent: Agent name (aurora, tron, avicenna)
        duration_seconds: Call duration in seconds
        cost_dollars: Call cost in USD
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
    """
    llm_api_calls_total.labels(provider=provider, model=model, agent=agent).inc()
    llm_api_duration_seconds.labels(provider=provider, model=model).observe(duration_seconds)
    llm_api_cost_dollars.labels(provider=provider, model=model, agent=agent).inc(cost_dollars)
    llm_tokens_used.labels(provider=provider, model=model, token_type="input").inc(
        input_tokens
    )
    llm_tokens_used.labels(provider=provider, model=model, token_type="output").inc(
        output_tokens
    )


def record_llm_cost(
    provider: str,
    model: str,
    agent: str,
    cost_dollars: float,
) -> None:
    """
    Record LLM cost only (for cases where full metrics aren't available).

    Args:
        provider: LLM provider
        model: Model name
        agent: Agent name
        cost_dollars: Call cost in USD
    """
    llm_api_cost_dollars.labels(provider=provider, model=model, agent=agent).inc(cost_dollars)


def record_db_query(
    operation: str,
    table: str,
    duration_seconds: float,
) -> None:
    """
    Record database query metrics.

    Args:
        operation: SQL operation (SELECT, INSERT, UPDATE, DELETE)
        table: Table name
        duration_seconds: Query duration in seconds
    """
    db_query_duration_seconds.labels(operation=operation, table=table).observe(
        duration_seconds
    )


def record_module_invocation(
    module: str,
    segment: str,
    duration_seconds: float,
    error_type: str | None = None,
) -> None:
    """
    Record module invocation metrics.

    Args:
        module: Module name
        segment: User segment (AD, AU, AH, NT, CU)
        duration_seconds: Execution time in seconds
        error_type: Optional error type if invocation failed
    """
    module_invocations_total.labels(module=module, segment=segment).inc()
    module_duration_seconds.labels(module=module).observe(duration_seconds)

    if error_type:
        module_errors_total.labels(module=module, error_type=error_type).inc()


def record_crisis_signal(
    level: str,
    source: str,
) -> None:
    """
    Record crisis signal detection.

    Args:
        level: Crisis level (watch, concern, crisis)
        source: Detection source (message, inertia, burnout)
    """
    crisis_signals_detected.labels(level=level, source=source).inc()


def record_crisis_intervention(
    level: str,
) -> None:
    """
    Record crisis intervention trigger.

    Args:
        level: Crisis level that triggered intervention
    """
    crisis_interventions_triggered.labels(level=level).inc()


def update_active_users(
    segment: str,
    count: int,
) -> None:
    """
    Update active user count for a segment.

    Args:
        segment: User segment (AD, AU, AH, NT, CU)
        count: Number of active users
    """
    active_users_gauge.labels(segment=segment).set(count)


def update_daily_active_users(count: int) -> None:
    """
    Update daily active users count.

    Args:
        count: Number of daily active users
    """
    daily_active_users.set(count)


def update_db_connections(count: int) -> None:
    """
    Update active database connections count.

    Args:
        count: Number of active connections
    """
    db_connections_active.set(count)


def update_system_health(
    status: float,
) -> None:
    """
    Update overall system health status.

    Args:
        status: Health value (1.0=healthy, 0.5=degraded, 0.0=unhealthy)
    """
    system_health_status.set(status)


def update_service_health(
    service: str,
    is_healthy: bool,
) -> None:
    """
    Update individual service health status.

    Args:
        service: Service name (postgresql, redis, neo4j, qdrant, letta)
        is_healthy: Whether service is healthy
    """
    service_health_status.labels(service=service).set(1.0 if is_healthy else 0.0)


# =============================================================================
# Context Managers for Automatic Timing
# =============================================================================


@contextmanager
def track_request(
    method: str,
    endpoint: str,
) -> Iterator[dict[str, Any]]:
    """
    Context manager for tracking HTTP request metrics.

    Usage:
        >>> with track_request("POST", "/api/message") as ctx:
        ...     # Handle request
        ...     ctx["status"] = 200
    """
    start_time = time.time()
    ctx: dict[str, Any] = {"status": 500, "error_type": None}

    try:
        yield ctx
    finally:
        duration = time.time() - start_time
        record_request(
            method=method,
            endpoint=endpoint,
            status=ctx.get("status", 500),
            duration_seconds=duration,
            error_type=ctx.get("error_type"),
        )


@contextmanager
def track_llm_call(
    provider: str,
    model: str,
    agent: str,
) -> Iterator[dict[str, Any]]:
    """
    Context manager for tracking LLM API call metrics.

    Usage:
        >>> with track_llm_call("anthropic", "claude-opus-4-6", "aurora") as ctx:
        ...     result = await llm_api_call()
        ...     ctx["cost_dollars"] = 0.015
        ...     ctx["input_tokens"] = 1000
        ...     ctx["output_tokens"] = 500
    """
    start_time = time.time()
    ctx: dict[str, Any] = {
        "cost_dollars": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }

    try:
        yield ctx
    finally:
        duration = time.time() - start_time
        record_llm_call(
            provider=provider,
            model=model,
            agent=agent,
            duration_seconds=duration,
            cost_dollars=ctx.get("cost_dollars", 0.0),
            input_tokens=ctx.get("input_tokens", 0),
            output_tokens=ctx.get("output_tokens", 0),
        )


@contextmanager
def track_db_query(
    operation: str,
    table: str,
) -> Iterator[None]:
    """
    Context manager for tracking database query metrics.

    Usage:
        >>> with track_db_query("SELECT", "users"):
        ...     result = session.query(User).all()
    """
    start_time = time.time()

    try:
        yield
    finally:
        duration = time.time() - start_time
        record_db_query(
            operation=operation,
            table=table,
            duration_seconds=duration,
        )


@contextmanager
def track_module(
    module: str,
    segment: str,
) -> Iterator[dict[str, Any]]:
    """
    Context manager for tracking module invocation metrics.

    Usage:
        >>> with track_module("gratitude-journal", "AD") as ctx:
        ...     result = await module.process()
        ...     # ctx["error_type"] = "validation_error" (if error)
    """
    start_time = time.time()
    ctx: dict[str, Any] = {"error_type": None}

    try:
        yield ctx
    finally:
        duration = time.time() - start_time
        record_module_invocation(
            module=module,
            segment=segment,
            duration_seconds=duration,
            error_type=ctx.get("error_type"),
        )


# =============================================================================
# Prometheus Metrics Export
# =============================================================================


class PrometheusMetrics:
    """
    Prometheus metrics exporter.

    Provides a /metrics endpoint for Prometheus scraping.
    """

    @staticmethod
    def generate_metrics() -> bytes:
        """
        Generate Prometheus metrics in text format.

        Returns:
            Metrics in Prometheus text exposition format
        """
        return generate_latest()

    @staticmethod
    def get_metrics_as_text() -> str:
        """
        Get metrics as text string.

        Returns:
            Metrics in Prometheus text format
        """
        return PrometheusMetrics.generate_metrics().decode("utf-8")
