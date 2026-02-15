"""
Tests for Graceful Shutdown Handler (src/workflows/shutdown.py).

MED-8: Improve test coverage from 23% to 80%+.

Tests:
- Initialization defaults
- should_shutdown property
- current_step property and setter
- install() with no running loop (sync fallback)
- install() idempotency (double install)
- uninstall() with no running loop
- uninstall() idempotency (double uninstall)
- Signal handling (_handle_signal and _handle_signal_sync)
- wait_for_shutdown() with no event
- wait_for_shutdown() with immediate shutdown
- wait_for_shutdown() with timeout
- reset()
- get_shutdown_handler() singleton
"""

from __future__ import annotations

import asyncio
import signal
from unittest.mock import patch

import pytest

from src.workflows.shutdown import (
    GracefulShutdownHandler,
    _shutdown_handler,
    get_shutdown_handler,
)


class TestGracefulShutdownHandlerInit:
    """Tests for GracefulShutdownHandler initialization."""

    def test_initial_state(self) -> None:
        """Test handler is initialized with correct defaults."""
        handler = GracefulShutdownHandler()
        assert handler.should_shutdown is False
        assert handler.current_step is None
        assert handler._installed is False
        assert handler._shutdown_event is None
        assert handler._original_sigterm is None
        assert handler._original_sigint is None

    def test_should_shutdown_property(self) -> None:
        """Test should_shutdown property reflects internal state."""
        handler = GracefulShutdownHandler()
        assert handler.should_shutdown is False

        handler._should_shutdown = True
        assert handler.should_shutdown is True

    def test_current_step_property(self) -> None:
        """Test current_step property reflects internal state."""
        handler = GracefulShutdownHandler()
        assert handler.current_step is None

        handler._current_step = "step_1"
        assert handler.current_step == "step_1"


class TestSetCurrentStep:
    """Tests for set_current_step method."""

    def test_set_step_name(self) -> None:
        """Test setting a step name."""
        handler = GracefulShutdownHandler()
        handler.set_current_step("processing_data")
        assert handler.current_step == "processing_data"

    def test_set_step_name_to_none(self) -> None:
        """Test clearing step name."""
        handler = GracefulShutdownHandler()
        handler.set_current_step("step_1")
        handler.set_current_step(None)
        assert handler.current_step is None

    def test_set_multiple_steps(self) -> None:
        """Test updating step name multiple times."""
        handler = GracefulShutdownHandler()
        handler.set_current_step("step_1")
        assert handler.current_step == "step_1"
        handler.set_current_step("step_2")
        assert handler.current_step == "step_2"


class TestInstallSync:
    """Tests for install() in synchronous context (no running loop)."""

    def test_install_sets_installed_flag(self) -> None:
        """Test install sets _installed to True."""
        handler = GracefulShutdownHandler()
        handler.install()
        try:
            assert handler._installed is True
        finally:
            handler.uninstall()

    def test_install_creates_shutdown_event(self) -> None:
        """Test install creates an asyncio.Event."""
        handler = GracefulShutdownHandler()
        handler.install()
        try:
            assert handler._shutdown_event is not None
            assert isinstance(handler._shutdown_event, asyncio.Event)
        finally:
            handler.uninstall()

    def test_install_saves_original_handlers(self) -> None:
        """Test install saves original signal handlers."""
        handler = GracefulShutdownHandler()
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)
        handler.install()
        try:
            assert handler._original_sigterm == original_sigterm
            assert handler._original_sigint == original_sigint
        finally:
            handler.uninstall()

    def test_install_idempotent(self) -> None:
        """Test double install does not re-install."""
        handler = GracefulShutdownHandler()
        handler.install()
        try:
            first_event = handler._shutdown_event
            first_sigterm = handler._original_sigterm
            # Second install should be no-op
            handler.install()
            assert handler._shutdown_event is first_event
            assert handler._original_sigterm is first_sigterm
        finally:
            handler.uninstall()


class TestUninstall:
    """Tests for uninstall()."""

    def test_uninstall_restores_handlers(self) -> None:
        """Test uninstall restores original signal handlers."""
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)
        handler = GracefulShutdownHandler()
        handler.install()
        handler.uninstall()

        assert handler._installed is False
        assert handler._original_sigterm is None
        assert handler._original_sigint is None
        # Original handlers should be restored
        assert signal.getsignal(signal.SIGTERM) == original_sigterm
        assert signal.getsignal(signal.SIGINT) == original_sigint

    def test_uninstall_idempotent(self) -> None:
        """Test double uninstall does not error."""
        handler = GracefulShutdownHandler()
        handler.install()
        handler.uninstall()
        # Second uninstall should be no-op
        handler.uninstall()
        assert handler._installed is False


class TestHandleSignal:
    """Tests for _handle_signal and _handle_signal_sync."""

    def test_handle_signal_sets_should_shutdown(self) -> None:
        """Test _handle_signal sets the shutdown flag."""
        handler = GracefulShutdownHandler()
        handler._shutdown_event = asyncio.Event()
        handler._handle_signal(signal.SIGTERM)
        assert handler.should_shutdown is True

    def test_handle_signal_sets_event(self) -> None:
        """Test _handle_signal sets the shutdown event."""
        handler = GracefulShutdownHandler()
        handler._shutdown_event = asyncio.Event()
        handler._handle_signal(signal.SIGTERM)
        assert handler._shutdown_event.is_set()

    def test_handle_signal_with_current_step(self) -> None:
        """Test _handle_signal logs step name when a step is in progress."""
        handler = GracefulShutdownHandler()
        handler._shutdown_event = asyncio.Event()
        handler.set_current_step("processing_data")
        handler._handle_signal(signal.SIGINT)
        assert handler.should_shutdown is True
        assert handler.current_step == "processing_data"

    def test_handle_signal_without_current_step(self) -> None:
        """Test _handle_signal logs generic message when no step."""
        handler = GracefulShutdownHandler()
        handler._shutdown_event = asyncio.Event()
        handler._handle_signal(signal.SIGTERM)
        assert handler.should_shutdown is True
        assert handler.current_step is None

    def test_handle_signal_without_event(self) -> None:
        """Test _handle_signal works when shutdown_event is None."""
        handler = GracefulShutdownHandler()
        # No event set
        handler._handle_signal(signal.SIGTERM)
        assert handler.should_shutdown is True

    def test_handle_signal_sync_delegates(self) -> None:
        """Test _handle_signal_sync delegates to _handle_signal."""
        handler = GracefulShutdownHandler()
        handler._shutdown_event = asyncio.Event()
        handler._handle_signal_sync(signal.SIGTERM, None)
        assert handler.should_shutdown is True
        assert handler._shutdown_event.is_set()


class TestWaitForShutdown:
    """Tests for wait_for_shutdown()."""

    @pytest.mark.asyncio
    async def test_wait_returns_immediately_when_no_event(self) -> None:
        """Test wait_for_shutdown returns current state if no event."""
        handler = GracefulShutdownHandler()
        # No event, should_shutdown is False
        result = await handler.wait_for_shutdown(timeout=0.1)
        assert result is False

    @pytest.mark.asyncio
    async def test_wait_returns_true_when_already_shutdown(self) -> None:
        """Test wait returns True when already shut down and no event."""
        handler = GracefulShutdownHandler()
        handler._should_shutdown = True
        result = await handler.wait_for_shutdown(timeout=0.1)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_returns_true_when_event_set(self) -> None:
        """Test wait returns True when event is set."""
        handler = GracefulShutdownHandler()
        handler._shutdown_event = asyncio.Event()
        handler._shutdown_event.set()
        result = await handler.wait_for_shutdown(timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_timeout_returns_false(self) -> None:
        """Test wait returns False on timeout."""
        handler = GracefulShutdownHandler()
        handler._shutdown_event = asyncio.Event()
        # Event never set, should timeout
        result = await handler.wait_for_shutdown(timeout=0.05)
        assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_shutdown_signal_during_wait(self) -> None:
        """Test wait completes when signal arrives during wait."""
        handler = GracefulShutdownHandler()
        handler._shutdown_event = asyncio.Event()

        async def trigger_shutdown():
            await asyncio.sleep(0.02)
            handler._handle_signal(signal.SIGTERM)

        task = asyncio.create_task(trigger_shutdown())
        result = await handler.wait_for_shutdown(timeout=1.0)
        assert result is True
        await task


class TestReset:
    """Tests for reset()."""

    def test_reset_clears_shutdown_flag(self) -> None:
        """Test reset clears the should_shutdown flag."""
        handler = GracefulShutdownHandler()
        handler._should_shutdown = True
        handler.reset()
        assert handler.should_shutdown is False

    def test_reset_clears_current_step(self) -> None:
        """Test reset clears the current step."""
        handler = GracefulShutdownHandler()
        handler.set_current_step("step_1")
        handler.reset()
        assert handler.current_step is None

    def test_reset_clears_event(self) -> None:
        """Test reset clears the shutdown event."""
        handler = GracefulShutdownHandler()
        handler._shutdown_event = asyncio.Event()
        handler._shutdown_event.set()
        handler.reset()
        assert not handler._shutdown_event.is_set()

    def test_reset_without_event(self) -> None:
        """Test reset works when there is no event."""
        handler = GracefulShutdownHandler()
        handler._should_shutdown = True
        handler.set_current_step("step_1")
        handler.reset()
        assert handler.should_shutdown is False
        assert handler.current_step is None


class TestGetShutdownHandler:
    """Tests for get_shutdown_handler() global singleton."""

    def test_returns_handler_instance(self) -> None:
        """Test get_shutdown_handler returns a GracefulShutdownHandler."""
        import src.workflows.shutdown as mod

        # Reset global state
        mod._shutdown_handler = None
        handler = get_shutdown_handler()
        assert isinstance(handler, GracefulShutdownHandler)

    def test_returns_same_instance(self) -> None:
        """Test get_shutdown_handler returns the same instance on repeated calls."""
        import src.workflows.shutdown as mod

        mod._shutdown_handler = None
        handler1 = get_shutdown_handler()
        handler2 = get_shutdown_handler()
        assert handler1 is handler2

    def test_creates_new_instance_when_none(self) -> None:
        """Test get_shutdown_handler creates a new instance when global is None."""
        import src.workflows.shutdown as mod

        mod._shutdown_handler = None
        handler = get_shutdown_handler()
        assert handler is not None
        assert mod._shutdown_handler is handler


class TestInstallAsync:
    """Tests for install() in async context."""

    @pytest.mark.asyncio
    async def test_install_uses_loop_signal_handlers(self) -> None:
        """Test install uses loop.add_signal_handler when in async context."""
        handler = GracefulShutdownHandler()
        try:
            handler.install()
            assert handler._installed is True
            # In async context with loop support, original handlers may not be saved
            # (they go through loop.add_signal_handler instead).
        finally:
            handler.uninstall()

    @pytest.mark.asyncio
    async def test_uninstall_removes_loop_signal_handlers(self) -> None:
        """Test uninstall removes signal handlers in async context."""
        handler = GracefulShutdownHandler()
        handler.install()
        handler.uninstall()
        assert handler._installed is False

    @pytest.mark.asyncio
    async def test_install_fallback_on_not_implemented(self) -> None:
        """Test install falls back to signal.signal when add_signal_handler not supported."""
        handler = GracefulShutdownHandler()
        loop = asyncio.get_running_loop()

        # Simulate NotImplementedError (e.g., Windows)
        original_add = loop.add_signal_handler
        def raise_not_impl(*args, **kwargs):
            raise NotImplementedError("not supported on this platform")

        loop.add_signal_handler = raise_not_impl
        try:
            handler.install()
            assert handler._installed is True
            # Should fall back to signal.signal and save originals
            assert handler._original_sigterm is not None
            assert handler._original_sigint is not None
        finally:
            handler.uninstall()
            loop.add_signal_handler = original_add
