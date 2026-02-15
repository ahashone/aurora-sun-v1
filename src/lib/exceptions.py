"""
Custom exception hierarchy for Aurora Sun V1.

Provides structured exception types for all subsystems:
- Configuration, encryption, GDPR compliance
- Security, workflows, modules, services, databases

All exceptions inherit from AuroraSunException, enabling
catch-all for Aurora-specific errors while keeping the
ability to catch specific error types.

References:
    - REFACTOR-012 in TODO.md
    - ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
"""

from __future__ import annotations


class AuroraSunException(Exception):
    """Base exception for all Aurora Sun V1 errors."""


class ConfigurationError(AuroraSunException):
    """Missing environment variables, invalid config values, or startup failures."""


class EncryptionError(AuroraSunException):
    """Encryption or decryption failures (key errors, corrupted data, missing keys)."""


class GDPRError(AuroraSunException):
    """GDPR compliance failures (consent missing, erasure failed, export failed)."""


class SecurityError(AuroraSunException):
    """Authentication, authorization, rate limiting, or input validation failures."""


class WorkflowError(AuroraSunException):
    """Workflow execution failures (graph errors, node failures, state corruption)."""


class ModuleError(AuroraSunException):
    """Module-specific errors (module not found, initialization failed, processing errors)."""


class ServiceError(AuroraSunException):
    """External service failures (API errors, connection refused, unexpected responses)."""


class DatabaseError(AuroraSunException):
    """Database connection, query, or migration failures."""


class ValidationError(AuroraSunException):
    """Input validation, parsing, or type conversion failures."""


class SerializationError(AuroraSunException):
    """JSON encode/decode, data serialization/deserialization failures."""


class ExternalServiceError(ServiceError):
    """External API call failures (Redis, LLM providers, etc.)."""


class StateError(AuroraSunException):
    """Invalid state transitions, missing required state."""
