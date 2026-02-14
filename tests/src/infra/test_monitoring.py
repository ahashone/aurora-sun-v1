"""
Tests for Prometheus monitoring.

Test coverage:
- Metric recording functions
- Context managers for automatic tracking
- Metrics export
- Counter/Histogram/Gauge operations
"""

from __future__ import annotations

from src.infra.monitoring import (
    PrometheusMetrics,
    record_crisis_intervention,
    record_crisis_signal,
    record_db_query,
    record_llm_call,
    record_llm_cost,
    record_module_invocation,
    record_request,
    track_db_query,
    track_llm_call,
    track_module,
    track_request,
    update_active_users,
    update_daily_active_users,
    update_db_connections,
    update_service_health,
    update_system_health,
)

# =============================================================================
# HTTP Request Metrics Tests
# =============================================================================


def test_record_request() -> None:
    """Test recording HTTP request metrics."""
    # This should not raise
    record_request(
        method="POST",
        endpoint="/api/message",
        status=200,
        duration_seconds=0.5,
    )

    record_request(
        method="GET",
        endpoint="/health",
        status=500,
        duration_seconds=1.0,
        error_type="internal_error",
    )


def test_track_request_context_manager() -> None:
    """Test track_request context manager."""
    with track_request("POST", "/api/test") as ctx:
        ctx["status"] = 201

    # Should not raise


# =============================================================================
# LLM Metrics Tests
# =============================================================================


def test_record_llm_call() -> None:
    """Test recording LLM API call metrics."""
    record_llm_call(
        provider="anthropic",
        model="claude-opus-4-6",
        agent="aurora",
        duration_seconds=2.5,
        cost_dollars=0.015,
        input_tokens=1000,
        output_tokens=500,
    )


def test_record_llm_cost() -> None:
    """Test recording LLM cost only."""
    record_llm_cost(
        provider="openai",
        model="gpt-4",
        agent="tron",
        cost_dollars=0.05,
    )


def test_track_llm_call_context_manager() -> None:
    """Test track_llm_call context manager."""
    with track_llm_call("anthropic", "claude-opus-4-6", "aurora") as ctx:
        ctx["cost_dollars"] = 0.01
        ctx["input_tokens"] = 500
        ctx["output_tokens"] = 200


# =============================================================================
# Database Metrics Tests
# =============================================================================


def test_record_db_query() -> None:
    """Test recording database query metrics."""
    record_db_query(
        operation="SELECT",
        table="users",
        duration_seconds=0.05,
    )

    record_db_query(
        operation="INSERT",
        table="tasks",
        duration_seconds=0.02,
    )


def test_track_db_query_context_manager() -> None:
    """Test track_db_query context manager."""
    with track_db_query("SELECT", "sessions"):
        # Simulate query
        pass


# =============================================================================
# Module Metrics Tests
# =============================================================================


def test_record_module_invocation() -> None:
    """Test recording module invocation metrics."""
    record_module_invocation(
        module="gratitude-journal",
        segment="AD",
        duration_seconds=1.5,
    )

    record_module_invocation(
        module="spoon-drawer",
        segment="AH",
        duration_seconds=0.8,
        error_type="validation_error",
    )


def test_track_module_context_manager() -> None:
    """Test track_module context manager."""
    with track_module("capture", "AU") as ctx:
        # Simulate module execution
        pass

    with track_module("crisis", "AD") as ctx:
        ctx["error_type"] = "timeout"


# =============================================================================
# Crisis Metrics Tests
# =============================================================================


def test_record_crisis_signal() -> None:
    """Test recording crisis signal detection."""
    record_crisis_signal(
        level="watch",
        source="message",
    )

    record_crisis_signal(
        level="crisis",
        source="inertia",
    )


def test_record_crisis_intervention() -> None:
    """Test recording crisis intervention."""
    record_crisis_intervention(level="concern")
    record_crisis_intervention(level="crisis")


# =============================================================================
# Gauge Metrics Tests
# =============================================================================


def test_update_active_users() -> None:
    """Test updating active user count."""
    update_active_users(segment="AD", count=15)
    update_active_users(segment="AU", count=20)


def test_update_daily_active_users() -> None:
    """Test updating daily active users."""
    update_daily_active_users(count=100)


def test_update_db_connections() -> None:
    """Test updating database connections count."""
    update_db_connections(count=5)


def test_update_system_health() -> None:
    """Test updating system health status."""
    update_system_health(status=1.0)  # Healthy
    update_system_health(status=0.5)  # Degraded
    update_system_health(status=0.0)  # Unhealthy


def test_update_service_health() -> None:
    """Test updating individual service health."""
    update_service_health(service="postgresql", is_healthy=True)
    update_service_health(service="redis", is_healthy=False)


# =============================================================================
# Metrics Export Tests
# =============================================================================


def test_prometheus_metrics_generate() -> None:
    """Test Prometheus metrics generation."""
    metrics = PrometheusMetrics.generate_metrics()

    assert isinstance(metrics, bytes)
    assert len(metrics) > 0


def test_prometheus_metrics_as_text() -> None:
    """Test Prometheus metrics as text."""
    metrics_text = PrometheusMetrics.get_metrics_as_text()

    assert isinstance(metrics_text, str)
    assert len(metrics_text) > 0
