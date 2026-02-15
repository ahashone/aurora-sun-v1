"""
REST API Layer for Aurora Sun V1 Mobile App.

Implements ROADMAP 5.4: Mobile App Preparation

Provides:
- FastAPI application with CORS middleware
- REST API endpoints for all pillars (Vision-to-Task, Second Brain, Money Tracker)
- Health check, authentication, energy, wearables, calendar, user profile
- API versioning under /api/v1 prefix

Reference: ROADMAP 5.4, ARCHITECTURE.md Section 14 (SW-14: REST API)
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.lib.security import create_security_middleware

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Includes:
    - CORS middleware with configurable origins via AURORA_CORS_ORIGINS env var
    - API v1 router with all endpoints
    - Root-level health check for Docker/load balancer probes

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title="Aurora Sun V1",
        description="AI coaching for neurodivergent people",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # -------------------------------------------------------------------------
    # CORS Middleware
    # -------------------------------------------------------------------------
    # Configurable via AURORA_CORS_ORIGINS environment variable.
    # Format: comma-separated list of origins, e.g. "http://localhost:3000,https://app.example.com"
    # Default: empty (no cross-origin requests allowed).
    cors_origins_env = os.getenv("AURORA_CORS_ORIGINS", "")
    cors_origins: list[str] = [
        origin.strip()
        for origin in cors_origins_env.split(",")
        if origin.strip()
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

    if cors_origins:
        logger.info("CORS enabled for origins: %s", cors_origins)
    else:
        logger.info("CORS: no origins configured (restrictive default)")

    # -------------------------------------------------------------------------
    # CODEX-CRIT-1 + SEC-007: Security Headers + Rate Limiting Middleware
    # Adds X-Content-Type-Options, X-Frame-Options, HSTS, CSP, etc.
    # to all API responses.
    # -------------------------------------------------------------------------
    create_security_middleware(app)

    # -------------------------------------------------------------------------
    # SEC-008: HTTPS Redirect Middleware (production only)
    # -------------------------------------------------------------------------
    environment = os.getenv("AURORA_ENVIRONMENT", "development")
    if environment == "production":
        from starlette.middleware.base import BaseHTTPMiddleware

        from src.infra.middleware import HTTPSRedirectMiddleware
        app.add_middleware(
            BaseHTTPMiddleware,
            dispatch=HTTPSRedirectMiddleware(),
        )

    # -------------------------------------------------------------------------
    # Include API v1 router (all routes under /api/v1)
    # -------------------------------------------------------------------------
    app.include_router(router)

    # -------------------------------------------------------------------------
    # Root-level health check (for Docker healthcheck / load balancer probes)
    # This is separate from the versioned /api/v1/health endpoint.
    # -------------------------------------------------------------------------
    @app.get("/health")
    async def root_health_check() -> dict[str, str]:
        """Root health check for infrastructure probes (Docker, Caddy, etc.)."""
        return {"status": "ok"}

    return app


__all__ = ["create_app", "router"]
