"""
Tests for custom exception hierarchy (REFACTOR-012).

Verifies:
- All exceptions are subclasses of AuroraSunException
- All exceptions are subclasses of Exception
- Exception messages work correctly
- isinstance checks work for the hierarchy
"""

from __future__ import annotations

import pytest

from src.lib.exceptions import (
    AuroraSunException,
    ConfigurationError,
    DatabaseError,
    EncryptionError,
    GDPRError,
    ModuleError,
    SecurityError,
    ServiceError,
    WorkflowError,
)

# All concrete exception classes (excluding the base)
EXCEPTION_CLASSES = [
    ConfigurationError,
    EncryptionError,
    GDPRError,
    SecurityError,
    WorkflowError,
    ModuleError,
    ServiceError,
    DatabaseError,
]


class TestExceptionHierarchy:
    """Test the exception class hierarchy."""

    def test_base_is_subclass_of_exception(self) -> None:
        """AuroraSunException must be a subclass of Exception."""
        assert issubclass(AuroraSunException, Exception)

    @pytest.mark.parametrize("exc_class", EXCEPTION_CLASSES)
    def test_all_are_subclass_of_aurora_sun_exception(
        self, exc_class: type[AuroraSunException]
    ) -> None:
        """Every custom exception must be a subclass of AuroraSunException."""
        assert issubclass(exc_class, AuroraSunException)

    @pytest.mark.parametrize("exc_class", EXCEPTION_CLASSES)
    def test_all_are_subclass_of_exception(
        self, exc_class: type[AuroraSunException]
    ) -> None:
        """Every custom exception must also be a subclass of built-in Exception."""
        assert issubclass(exc_class, Exception)

    @pytest.mark.parametrize("exc_class", EXCEPTION_CLASSES)
    def test_all_are_not_base_exception_directly(
        self, exc_class: type[AuroraSunException]
    ) -> None:
        """No custom exception should bypass AuroraSunException."""
        # Verify the MRO includes AuroraSunException
        assert AuroraSunException in exc_class.__mro__


class TestExceptionMessages:
    """Test that exception messages are preserved correctly."""

    @pytest.mark.parametrize("exc_class", EXCEPTION_CLASSES)
    def test_message_preserved(
        self, exc_class: type[AuroraSunException]
    ) -> None:
        """Exception message should be accessible via str()."""
        msg = f"Test error for {exc_class.__name__}"
        exc = exc_class(msg)
        assert str(exc) == msg

    @pytest.mark.parametrize("exc_class", EXCEPTION_CLASSES)
    def test_empty_message(
        self, exc_class: type[AuroraSunException]
    ) -> None:
        """Exception with no message should work."""
        exc = exc_class()
        assert str(exc) == ""

    @pytest.mark.parametrize("exc_class", EXCEPTION_CLASSES)
    def test_args_preserved(
        self, exc_class: type[AuroraSunException]
    ) -> None:
        """Exception args tuple should be preserved."""
        exc = exc_class("msg", 42, "extra")
        assert exc.args == ("msg", 42, "extra")

    def test_base_exception_message(self) -> None:
        """AuroraSunException itself should carry messages."""
        exc = AuroraSunException("base error")
        assert str(exc) == "base error"


class TestIsInstanceChecks:
    """Test isinstance behavior across the hierarchy."""

    @pytest.mark.parametrize("exc_class", EXCEPTION_CLASSES)
    def test_isinstance_own_type(
        self, exc_class: type[AuroraSunException]
    ) -> None:
        """An instance should match its own type."""
        exc = exc_class("test")
        assert isinstance(exc, exc_class)

    @pytest.mark.parametrize("exc_class", EXCEPTION_CLASSES)
    def test_isinstance_base(
        self, exc_class: type[AuroraSunException]
    ) -> None:
        """An instance should match AuroraSunException."""
        exc = exc_class("test")
        assert isinstance(exc, AuroraSunException)

    @pytest.mark.parametrize("exc_class", EXCEPTION_CLASSES)
    def test_isinstance_builtin_exception(
        self, exc_class: type[AuroraSunException]
    ) -> None:
        """An instance should match built-in Exception."""
        exc = exc_class("test")
        assert isinstance(exc, Exception)

    def test_different_types_are_not_isinstance(self) -> None:
        """ConfigurationError should not be isinstance of DatabaseError etc."""
        exc = ConfigurationError("config problem")
        assert not isinstance(exc, DatabaseError)
        assert not isinstance(exc, EncryptionError)
        assert not isinstance(exc, ServiceError)


class TestExceptionCatching:
    """Test that exceptions can be caught at various hierarchy levels."""

    def test_catch_by_specific_type(self) -> None:
        """Catching by specific type should work."""
        with pytest.raises(ConfigurationError, match="missing env"):
            raise ConfigurationError("missing env var")

    def test_catch_by_base_type(self) -> None:
        """Catching AuroraSunException should catch all subtypes."""
        with pytest.raises(AuroraSunException):
            raise DatabaseError("connection failed")

    def test_catch_by_builtin_exception(self) -> None:
        """Catching Exception should catch all Aurora exceptions."""
        with pytest.raises(Exception):
            raise SecurityError("unauthorized")

    def test_catch_specific_does_not_catch_sibling(self) -> None:
        """Catching ConfigurationError should not catch DatabaseError."""
        with pytest.raises(DatabaseError):
            try:
                raise DatabaseError("db down")
            except ConfigurationError:
                pytest.fail("ConfigurationError handler caught DatabaseError")


class TestExceptionDocstrings:
    """Test that all exceptions have docstrings."""

    @pytest.mark.parametrize(
        "exc_class", [AuroraSunException, *EXCEPTION_CLASSES]
    )
    def test_has_docstring(
        self, exc_class: type[AuroraSunException]
    ) -> None:
        """Every exception class should have a docstring."""
        assert exc_class.__doc__ is not None
        assert len(exc_class.__doc__.strip()) > 0
