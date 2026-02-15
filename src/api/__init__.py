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
from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.api.auth import validate_secrets
from src.api.routes import router
from src.lib.security import create_security_middleware

logger = logging.getLogger(__name__)

# MED-18: Allowed CORS headers (restricted from ["*"])
_ALLOWED_HEADERS: list[str] = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Accept-Language",
    "X-Request-ID",
]

# CRIT-2: Paths that do NOT require authentication
_PUBLIC_PATHS: frozenset[str] = frozenset({
    "/health",
    "/api/v1/health",
    "/api/v1/auth/token",
    "/docs",
    "/redoc",
    "/openapi.json",
})


async def _auth_gate_dispatch(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """CRIT-2: Catch-all auth middleware — deny unauthenticated requests by default."""
    # CORS preflight (OPTIONS) must pass through
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path.rstrip("/") or "/"
    if path not in _PUBLIC_PATHS:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "unauthorized", "message": "Authentication required."},
                headers={"WWW-Authenticate": "Bearer"},
            )
    return await call_next(request)


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Includes:
    - CORS middleware with configurable origins via AURORA_CORS_ORIGINS env var
    - Catch-all auth middleware (CRIT-2: deny unauthenticated by default)
    - Global exception handlers (MED-17)
    - API v1 router with all endpoints
    - Root-level health check for Docker/load balancer probes
    - Production: /docs and /redoc disabled (LOW-1)

    Returns:
        Configured FastAPI application instance.
    """
    validate_secrets()

    environment = os.getenv("AURORA_ENVIRONMENT", "development")
    is_production = environment == "production"

    app = FastAPI(
        title="Aurora Sun V1",
        description="AI coaching for neurodivergent people",
        version="0.1.0",
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
    )

    # -------------------------------------------------------------------------
    # MED-17: Global exception handlers
    # -------------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception,
    ) -> JSONResponse:
        logger.exception(
            "Unhandled exception on %s %s", request.method, request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "An unexpected error occurred.",
            },
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

    # HIGH-10: Validate CORS origins at startup — reject wildcard in production
    if is_production and "*" in cors_origins:
        raise ValueError(
            "AURORA_CORS_ORIGINS contains wildcard '*' which is forbidden in production. "
            "Specify explicit origins instead."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=_ALLOWED_HEADERS,
    )

    if cors_origins:
        logger.info("CORS enabled for origins: %s", cors_origins)
    else:
        logger.info("CORS: no origins configured (restrictive default)")

    # -------------------------------------------------------------------------
    # CRIT-2: Catch-all auth middleware (deny unauthenticated by default)
    # -------------------------------------------------------------------------
    app.add_middleware(BaseHTTPMiddleware, dispatch=_auth_gate_dispatch)

    # -------------------------------------------------------------------------
    # CODEX-CRIT-1 + SEC-007: Security Headers + Rate Limiting Middleware
    # Adds X-Content-Type-Options, X-Frame-Options, HSTS, CSP, etc.
    # to all API responses.
    # -------------------------------------------------------------------------
    create_security_middleware(app)

    # -------------------------------------------------------------------------
    # SEC-008: HTTPS Redirect Middleware (production only)
    # -------------------------------------------------------------------------
    if is_production:
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
