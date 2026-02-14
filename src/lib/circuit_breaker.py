"""
Circuit Breaker pattern for external service calls.

Provides fault tolerance for external dependencies (LLM APIs, databases, etc.)
by detecting failures and short-circuiting calls to unhealthy services.

States:
- CLOSED: Normal operation, calls pass through.
- OPEN: Service is unhealthy, calls are rejected immediately.
- HALF_OPEN: Testing recovery, limited calls allowed.

Usage:
    # As a decorator
    @circuit_breaker(name="openai_api")
    async def call_openai(prompt: str) -> str:
        ...

    # As a context manager
    cb = CircuitBreaker(name="redis")
    async with cb:
        await redis.get("key")

    # Direct usage
    cb = CircuitBreaker(name="postgres")
    if cb.allow_request():
        try:
            result = await db.execute(query)
            cb.record_success()
        except Exception as e:
            cb.record_failure()
            raise

Reference: ARCHITECTURE.md (Resilience Patterns)
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class CircuitState(StrEnum):
    """Possible states for a circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """Raised when a call is rejected because the circuit is open."""

    def __init__(self, name: str, state: CircuitState, retry_after: float) -> None:
        self.name = name
        self.state = state
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker '{name}' is {state.value}. "
            f"Retry after {retry_after:.1f}s."
        )


class CircuitBreaker:
    """
    Circuit breaker for external service calls.

    Thread-safe with asyncio.Lock. Tracks consecutive failures and
    transitions between CLOSED, OPEN, and HALF_OPEN states.

    Args:
        name: Identifier for the protected service (used in logging).
        failure_threshold: Number of consecutive failures before opening.
        recovery_timeout: Seconds to wait in OPEN before transitioning to HALF_OPEN.
        half_open_max_calls: Number of test calls allowed in HALF_OPEN state.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._half_open_calls: int = 0
        self._last_failure_time: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Return the current circuit state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Return the current consecutive failure count."""
        return self._failure_count

    def _time_since_last_failure(self) -> float:
        """Return seconds elapsed since the last recorded failure."""
        if self._last_failure_time == 0.0:
            return float("inf")
        return time.monotonic() - self._last_failure_time

    def _should_attempt_recovery(self) -> bool:
        """Check whether enough time has passed to attempt recovery."""
        return self._time_since_last_failure() >= self.recovery_timeout

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state with logging."""
        old_state = self._state
        if old_state == new_state:
            return
        self._state = new_state
        logger.info(
            "Circuit breaker '%s' state transition: %s -> %s",
            self.name,
            old_state.value,
            new_state.value,
        )

    async def allow_request(self) -> bool:
        """
        Check whether a request should be allowed through the circuit.

        Returns:
            True if the request is allowed, False if it should be rejected.
        """
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                if self._should_attempt_recovery():
                    self._transition_to(CircuitState.HALF_OPEN)
                    self._half_open_calls = 0
                    return True
                return False

            # HALF_OPEN: allow limited calls
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    async def record_success(self) -> None:
        """Record a successful call. Resets failure count and closes circuit if HALF_OPEN."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                logger.info(
                    "Circuit breaker '%s' successful test call in HALF_OPEN "
                    "(%d/%d). Closing circuit.",
                    self.name,
                    self._success_count,
                    self.half_open_max_calls,
                )
                self._transition_to(CircuitState.CLOSED)
                self._failure_count = 0
                self._success_count = 0
                self._half_open_calls = 0
            elif self._state == CircuitState.CLOSED:
                # Reset consecutive failure count on any success
                self._failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed call. May open the circuit if threshold is reached."""
        async with self._lock:
            self._last_failure_time = time.monotonic()
            self._failure_count += 1

            if self._state == CircuitState.HALF_OPEN:
                logger.warning(
                    "Circuit breaker '%s' failed in HALF_OPEN. Reopening circuit.",
                    self.name,
                )
                self._transition_to(CircuitState.OPEN)
                self._half_open_calls = 0
                self._success_count = 0

            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    logger.warning(
                        "Circuit breaker '%s' failure threshold reached "
                        "(%d/%d). Opening circuit.",
                        self.name,
                        self._failure_count,
                        self.failure_threshold,
                    )
                    self._transition_to(CircuitState.OPEN)

    def retry_after_seconds(self) -> float:
        """Return seconds until the circuit may attempt recovery."""
        if self._state != CircuitState.OPEN:
            return 0.0
        elapsed = self._time_since_last_failure()
        remaining = self.recovery_timeout - elapsed
        return max(0.0, remaining)

    async def __aenter__(self) -> CircuitBreaker:
        """Async context manager entry. Raises CircuitBreakerError if circuit is open."""
        allowed = await self.allow_request()
        if not allowed:
            raise CircuitBreakerError(
                name=self.name,
                state=self._state,
                retry_after=self.retry_after_seconds(),
            )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit. Records success or failure based on exception."""
        if exc_type is None:
            await self.record_success()
        else:
            await self.record_failure()

    async def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        async with self._lock:
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._last_failure_time = 0.0
            if old_state != CircuitState.CLOSED:
                logger.info(
                    "Circuit breaker '%s' manually reset from %s to CLOSED.",
                    self.name,
                    old_state.value,
                )


# =============================================================================
# Global registry of circuit breakers
# =============================================================================

_registry: dict[str, CircuitBreaker] = {}
_registry_lock: asyncio.Lock = asyncio.Lock()


async def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    half_open_max_calls: int = 1,
) -> CircuitBreaker:
    """
    Get or create a named circuit breaker from the global registry.

    Args:
        name: Unique name for the circuit breaker.
        failure_threshold: Failures before opening (only used on creation).
        recovery_timeout: Seconds before recovery attempt (only used on creation).
        half_open_max_calls: Test calls in HALF_OPEN (only used on creation).

    Returns:
        The named CircuitBreaker instance.
    """
    async with _registry_lock:
        if name not in _registry:
            _registry[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                half_open_max_calls=half_open_max_calls,
            )
        return _registry[name]


def get_all_circuit_breakers() -> dict[str, CircuitBreaker]:
    """Return a snapshot of all registered circuit breakers (for monitoring)."""
    return dict(_registry)


# =============================================================================
# Decorator
# =============================================================================

def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    half_open_max_calls: int = 1,
) -> Callable[[F], F]:
    """
    Decorator that wraps an async function with a circuit breaker.

    Usage:
        @circuit_breaker(name="openai_api", failure_threshold=3)
        async def call_openai(prompt: str) -> str:
            ...

    Args:
        name: Circuit breaker name (should match the external service).
        failure_threshold: Consecutive failures before opening the circuit.
        recovery_timeout: Seconds to wait before attempting recovery.
        half_open_max_calls: Test calls allowed in HALF_OPEN state.

    Returns:
        Decorated function with circuit breaker protection.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cb = await get_circuit_breaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                half_open_max_calls=half_open_max_calls,
            )

            async with cb:
                return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
