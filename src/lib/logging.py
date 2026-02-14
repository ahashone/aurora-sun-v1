"""
Structured logging configuration for Aurora Sun V1.

Configures structlog to work alongside stdlib logging so that both
`logging.getLogger()` and `structlog.get_logger()` produce consistent,
structured JSON output in production and human-readable output in dev.

Usage:
    from src.lib.logging import setup_logging

    setup_logging()  # Call once at application startup
"""

import logging
import os
import sys

import structlog


def setup_logging() -> None:
    """
    Configure structlog and stdlib logging for the application.

    In development (AURORA_DEV_MODE=1): human-readable colored console output.
    In production: JSON-formatted structured logs.
    """
    dev_mode = os.environ.get("AURORA_DEV_MODE") == "1"
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Shared processors for both structlog and stdlib
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if dev_mode:
        # Human-readable output for development
        renderer = structlog.dev.ConsoleRenderer()
    else:
        # JSON output for production (machine-parseable)
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog formatting
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Quiet noisy third-party loggers
    for noisy_logger in ("httpx", "httpcore", "telegram", "urllib3"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
