"""
Graceful Shutdown Handler for Aurora Sun V1 Workflows.

Handles SIGTERM/SIGINT signals to ensure in-progress workflow steps
complete before the process shuts down.

Reference:
- ARCHITECTURE.md Section 3 (Daily Workflow Engine)
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

logger = logging.getLogger(__name__)


class GracefulShutdownHandler:
    """Handles graceful shutdown for in-progress workflows.

    When a SIGTERM or SIGINT is received, the handler sets a flag that
    workflow runners check between steps. The current step is allowed to
    complete, but no new steps are started.

    Usage:
        handler = GracefulShutdownHandler()
        handler.install()

        # In workflow loop:
        for step in steps:
            if handler.should_shutdown:
                break
            await execute_step(step)

        handler.uninstall()
    """

    def __init__(self) -> None:
        """Initialize the shutdown handler."""
        self._should_shutdown = False
        self._shutdown_event: asyncio.Event | None = None
        self._original_sigterm: Any = None
        self._original_sigint: Any = None
        self._installed = False
        self._current_step: str | None = None

    @property
    def should_shutdown(self) -> bool:
        """Check if shutdown has been requested."""
        return self._should_shutdown

    @property
    def current_step(self) -> str | None:
        """Get the name of the currently executing step."""
        return self._current_step

    def set_current_step(self, step_name: str | None) -> None:
        """Set the name of the currently executing step.

        Args:
            step_name: Name of the step, or None when between steps
        """
        self._current_step = step_name

    def install(self) -> None:
        """Install signal handlers for SIGTERM and SIGINT.

        Saves the original handlers so they can be restored on uninstall.
        """
        if self._installed:
            return

        self._shutdown_event = asyncio.Event()

        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if loop is not None:
            # Running inside an async event loop: use loop.add_signal_handler
            try:
                loop.add_signal_handler(signal.SIGTERM, self._handle_signal, signal.SIGTERM)
                loop.add_signal_handler(signal.SIGINT, self._handle_signal, signal.SIGINT)
            except NotImplementedError:
                # Windows does not support add_signal_handler; fall back to signal.signal
                self._original_sigterm = signal.getsignal(signal.SIGTERM)
                self._original_sigint = signal.getsignal(signal.SIGINT)
                signal.signal(signal.SIGTERM, self._handle_signal_sync)
                signal.signal(signal.SIGINT, self._handle_signal_sync)
        else:
            # No running loop: use synchronous signal API
            self._original_sigterm = signal.getsignal(signal.SIGTERM)
            self._original_sigint = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGTERM, self._handle_signal_sync)
            signal.signal(signal.SIGINT, self._handle_signal_sync)

        self._installed = True
        logger.info("Graceful shutdown handler installed")

    def uninstall(self) -> None:
        """Restore original signal handlers."""
        if not self._installed:
            return

        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if loop is not None:
            try:
                loop.remove_signal_handler(signal.SIGTERM)
                loop.remove_signal_handler(signal.SIGINT)
            except (NotImplementedError, ValueError):
                pass

        # Restore original handlers if we saved them
        if self._original_sigterm is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm)
            self._original_sigterm = None
        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)
            self._original_sigint = None

        self._installed = False
        logger.info("Graceful shutdown handler uninstalled")

    def _handle_signal(self, signum: int) -> None:
        """Handle signal in async context (loop.add_signal_handler callback).

        Args:
            signum: The signal number received
        """
        sig_name = signal.Signals(signum).name
        if self._current_step:
            logger.info(
                "Received %s, completing current step '%s' before shutdown",
                sig_name, self._current_step,
            )
        else:
            logger.info("Received %s, initiating graceful shutdown", sig_name)

        self._should_shutdown = True
        if self._shutdown_event:
            self._shutdown_event.set()

    def _handle_signal_sync(self, signum: int, _frame: Any) -> None:
        """Handle signal in sync context (signal.signal callback).

        Args:
            signum: The signal number received
            _frame: The current stack frame (unused)
        """
        self._handle_signal(signum)

    async def wait_for_shutdown(self, timeout: float | None = None) -> bool:
        """Wait for a shutdown signal.

        Args:
            timeout: Maximum seconds to wait, or None for indefinite

        Returns:
            True if shutdown was requested, False if timeout elapsed
        """
        if self._shutdown_event is None:
            return self._should_shutdown

        try:
            await asyncio.wait_for(self._shutdown_event.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    def reset(self) -> None:
        """Reset the shutdown state. Useful for testing."""
        self._should_shutdown = False
        self._current_step = None
        if self._shutdown_event:
            self._shutdown_event.clear()


# Global shutdown handler instance
_shutdown_handler: GracefulShutdownHandler | None = None


def get_shutdown_handler() -> GracefulShutdownHandler:
    """Get the global shutdown handler instance.

    Returns:
        The global GracefulShutdownHandler instance
    """
    global _shutdown_handler
    if _shutdown_handler is None:
        _shutdown_handler = GracefulShutdownHandler()
    return _shutdown_handler


__all__ = [
    "GracefulShutdownHandler",
    "get_shutdown_handler",
]
