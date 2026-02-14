"""
Tests for CircuitBreaker (src/lib/circuit_breaker.py).

Tests cover all three states (CLOSED, OPEN, HALF_OPEN), state transitions,
failure counting, recovery timeout, concurrent failures, context manager usage,
decorator usage, and the global registry.

Reference: CRITICAL gap #2 — 131 untested lines, 23% coverage
"""

from __future__ import annotations

import asyncio

import pytest

from src.lib.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    circuit_breaker,
    get_all_circuit_breakers,
    get_circuit_breaker,
)

# =============================================================================
# Basic CircuitBreaker Tests
# =============================================================================


@pytest.mark.asyncio
async def test_initial_state():
    """Test circuit breaker starts in CLOSED state."""
    cb = CircuitBreaker(name="test")
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_allow_request_when_closed():
    """Test requests are allowed when circuit is CLOSED."""
    cb = CircuitBreaker(name="test")
    allowed = await cb.allow_request()
    assert allowed is True


@pytest.mark.asyncio
async def test_record_success_resets_failure_count():
    """Test successful call resets failure count in CLOSED state."""
    cb = CircuitBreaker(name="test", failure_threshold=3)

    # Record some failures
    await cb.record_failure()
    await cb.record_failure()
    assert cb.failure_count == 2

    # Success should reset
    await cb.record_success()
    assert cb.failure_count == 0
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_open_circuit_after_threshold():
    """Test circuit opens after reaching failure threshold."""
    cb = CircuitBreaker(name="test", failure_threshold=3)

    # Record failures up to threshold
    await cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    await cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    await cb.record_failure()
    # Should open after 3rd failure
    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == 3


@pytest.mark.asyncio
async def test_reject_requests_when_open():
    """Test requests are rejected when circuit is OPEN."""
    cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=60.0)

    # Open the circuit
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Requests should be rejected
    allowed = await cb.allow_request()
    assert allowed is False


@pytest.mark.asyncio
async def test_transition_to_half_open_after_recovery_timeout():
    """Test circuit transitions to HALF_OPEN after recovery timeout."""
    cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.1)

    # Open the circuit
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Wait for recovery timeout
    await asyncio.sleep(0.15)

    # Next request should transition to HALF_OPEN
    allowed = await cb.allow_request()
    assert allowed is True
    assert cb.state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_half_open_allows_limited_calls():
    """Test HALF_OPEN state allows only limited test calls."""
    cb = CircuitBreaker(
        name="test", failure_threshold=1, recovery_timeout=0.1, half_open_max_calls=2
    )

    # Open the circuit
    await cb.record_failure()
    await asyncio.sleep(0.15)

    # Transition to HALF_OPEN (first call) - this call resets counter and returns True
    allowed1 = await cb.allow_request()
    assert allowed1 is True
    assert cb.state == CircuitState.HALF_OPEN

    # Second call (counter goes 0 -> 1)
    allowed2 = await cb.allow_request()
    assert allowed2 is True

    # Third call (counter goes 1 -> 2)
    allowed3 = await cb.allow_request()
    assert allowed3 is True

    # Fourth call (counter is 2, 2 < 2 is False, rejected)
    allowed4 = await cb.allow_request()
    assert allowed4 is False


@pytest.mark.asyncio
async def test_half_open_success_closes_circuit():
    """Test successful call in HALF_OPEN closes the circuit."""
    cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.1)

    # Open and transition to HALF_OPEN
    await cb.record_failure()
    await asyncio.sleep(0.15)
    await cb.allow_request()
    assert cb.state == CircuitState.HALF_OPEN

    # Success should close the circuit
    await cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_half_open_failure_reopens_circuit():
    """Test failure in HALF_OPEN reopens the circuit."""
    cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.1)

    # Open and transition to HALF_OPEN
    await cb.record_failure()
    await asyncio.sleep(0.15)
    await cb.allow_request()
    assert cb.state == CircuitState.HALF_OPEN

    # Failure should reopen
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_retry_after_seconds():
    """Test retry_after_seconds calculation."""
    cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=5.0)

    # Circuit CLOSED: retry_after should be 0
    assert cb.retry_after_seconds() == 0.0

    # Open the circuit
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # retry_after should be ~5 seconds (recovery_timeout)
    retry_after = cb.retry_after_seconds()
    assert 4.5 <= retry_after <= 5.0


@pytest.mark.asyncio
async def test_manual_reset():
    """Test manual circuit reset."""
    cb = CircuitBreaker(name="test", failure_threshold=1)

    # Open the circuit
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == 1

    # Manual reset
    await cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


# =============================================================================
# Context Manager Tests
# =============================================================================


@pytest.mark.asyncio
async def test_context_manager_success():
    """Test context manager records success on normal exit."""
    cb = CircuitBreaker(name="test", failure_threshold=2)

    async with cb:
        pass  # Success

    assert cb.failure_count == 0
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_context_manager_failure():
    """Test context manager records failure on exception."""
    cb = CircuitBreaker(name="test", failure_threshold=2)

    with pytest.raises(ValueError):
        async with cb:
            raise ValueError("Test error")

    assert cb.failure_count == 1
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_context_manager_rejects_when_open():
    """Test context manager raises CircuitBreakerError when circuit is OPEN."""
    cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=60.0)

    # Open the circuit
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Context manager should raise CircuitBreakerError
    with pytest.raises(CircuitBreakerError) as exc_info:
        async with cb:
            pass

    assert exc_info.value.name == "test"
    assert exc_info.value.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_context_manager_full_cycle():
    """Test full circuit cycle with context manager."""
    cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=0.1)

    # First failure
    with pytest.raises(ValueError):
        async with cb:
            raise ValueError("Fail 1")
    assert cb.state == CircuitState.CLOSED

    # Second failure (opens circuit)
    with pytest.raises(ValueError):
        async with cb:
            raise ValueError("Fail 2")
    assert cb.state == CircuitState.OPEN

    # Wait for recovery
    await asyncio.sleep(0.15)

    # Success in HALF_OPEN (closes circuit)
    async with cb:
        pass
    assert cb.state == CircuitState.CLOSED


# =============================================================================
# Decorator Tests
# =============================================================================


@pytest.mark.asyncio
async def test_decorator_success():
    """Test circuit breaker decorator with successful calls."""

    @circuit_breaker(name="decorator_test", failure_threshold=2)
    async def successful_function():
        return "success"

    result = await successful_function()
    assert result == "success"

    cb = await get_circuit_breaker("decorator_test")
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_decorator_failure():
    """Test circuit breaker decorator with failing calls."""

    @circuit_breaker(name="decorator_fail_test", failure_threshold=2)
    async def failing_function():
        raise ValueError("Test error")

    # First failure
    with pytest.raises(ValueError):
        await failing_function()

    cb = await get_circuit_breaker("decorator_fail_test")
    assert cb.failure_count == 1
    assert cb.state == CircuitState.CLOSED

    # Second failure (opens circuit)
    with pytest.raises(ValueError):
        await failing_function()

    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_decorator_rejects_when_open():
    """Test decorator raises CircuitBreakerError when circuit is OPEN."""

    @circuit_breaker(name="decorator_open_test", failure_threshold=1)
    async def test_function():
        raise ValueError("Error")

    # Open the circuit
    with pytest.raises(ValueError):
        await test_function()

    cb = await get_circuit_breaker("decorator_open_test")
    assert cb.state == CircuitState.OPEN

    # Next call should raise CircuitBreakerError
    with pytest.raises(CircuitBreakerError):
        await test_function()


# =============================================================================
# Global Registry Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_circuit_breaker_creates_new():
    """Test get_circuit_breaker creates a new instance if not found."""
    cb = await get_circuit_breaker("new_circuit", failure_threshold=5)
    assert cb.name == "new_circuit"
    assert cb.failure_threshold == 5


@pytest.mark.asyncio
async def test_get_circuit_breaker_returns_existing():
    """Test get_circuit_breaker returns existing instance."""
    cb1 = await get_circuit_breaker("existing", failure_threshold=3)
    cb2 = await get_circuit_breaker("existing", failure_threshold=10)

    # Should return same instance (failure_threshold not updated)
    assert cb1 is cb2
    assert cb1.failure_threshold == 3  # Original value preserved


@pytest.mark.asyncio
async def test_get_all_circuit_breakers():
    """Test get_all_circuit_breakers returns snapshot of registry."""
    cb1 = await get_circuit_breaker("circuit_1")
    cb2 = await get_circuit_breaker("circuit_2")

    all_cbs = get_all_circuit_breakers()
    assert "circuit_1" in all_cbs
    assert "circuit_2" in all_cbs
    assert all_cbs["circuit_1"] is cb1
    assert all_cbs["circuit_2"] is cb2


# =============================================================================
# Concurrent Failures Tests
# =============================================================================


@pytest.mark.asyncio
async def test_concurrent_failures():
    """Test circuit breaker handles concurrent failures correctly."""
    cb = CircuitBreaker(name="concurrent_test", failure_threshold=5)

    # Simulate 10 concurrent failures
    async def fail():
        await cb.record_failure()

    await asyncio.gather(*[fail() for _ in range(10)])

    # Should be open after exceeding threshold
    assert cb.state == CircuitState.OPEN
    assert cb.failure_count >= 5


@pytest.mark.asyncio
async def test_concurrent_mixed_calls():
    """Test circuit breaker with concurrent successes and failures."""
    cb = CircuitBreaker(name="mixed_test", failure_threshold=10)

    async def succeed():
        await cb.record_success()

    async def fail():
        await cb.record_failure()

    # 5 failures, 10 successes (interleaved)
    tasks = [fail() for _ in range(5)] + [succeed() for _ in range(10)]
    await asyncio.gather(*tasks)

    # Should still be closed (successes reset failure count)
    assert cb.state == CircuitState.CLOSED


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_zero_failure_threshold():
    """Test circuit breaker with zero threshold (always closed)."""
    # Note: This is a degenerate case, but should not crash
    cb = CircuitBreaker(name="zero_threshold", failure_threshold=0)

    # Even with failures, should open immediately
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_very_short_recovery_timeout():
    """Test circuit breaker with very short recovery timeout."""
    cb = CircuitBreaker(name="short_timeout", failure_threshold=1, recovery_timeout=0.01)

    await cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Should almost immediately transition to HALF_OPEN
    await asyncio.sleep(0.02)
    allowed = await cb.allow_request()
    assert allowed is True
    assert cb.state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_error_attributes():
    """Test CircuitBreakerError contains correct attributes."""
    cb = CircuitBreaker(name="error_test", failure_threshold=1, recovery_timeout=5.0)

    await cb.record_failure()

    with pytest.raises(CircuitBreakerError) as exc_info:
        async with cb:
            pass

    error = exc_info.value
    assert error.name == "error_test"
    assert error.state == CircuitState.OPEN
    assert 4.5 <= error.retry_after <= 5.0
    assert "error_test" in str(error)
    assert "Retry after" in str(error)
