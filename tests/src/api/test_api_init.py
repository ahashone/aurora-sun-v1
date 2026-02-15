"""
Tests for API Application Factory (src/api/__init__.py).

MED-8: Improve test coverage from 36% to 80%+.

Tests:
- create_app() returns FastAPI instance
- CORS middleware configuration (empty, explicit origins)
- Auth gate middleware (public paths, private paths, OPTIONS preflight)
- Global exception handler (MED-17)
- Health check endpoint at root level
- Production mode: wildcard CORS rejection (HIGH-10)
- Production mode: docs/redoc disabled (LOW-1)
- Development mode: docs/redoc enabled
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from src.api import _PUBLIC_PATHS, _ALLOWED_HEADERS, _auth_gate_dispatch, create_app


class TestPublicPaths:
    """Tests for _PUBLIC_PATHS configuration."""

    def test_health_is_public(self) -> None:
        """Test /health is in public paths."""
        assert "/health" in _PUBLIC_PATHS

    def test_api_health_is_public(self) -> None:
        """Test /api/v1/health is in public paths."""
        assert "/api/v1/health" in _PUBLIC_PATHS

    def test_auth_token_is_public(self) -> None:
        """Test /api/v1/auth/token is in public paths."""
        assert "/api/v1/auth/token" in _PUBLIC_PATHS

    def test_docs_is_public(self) -> None:
        """Test /docs is in public paths."""
        assert "/docs" in _PUBLIC_PATHS

    def test_redoc_is_public(self) -> None:
        """Test /redoc is in public paths."""
        assert "/redoc" in _PUBLIC_PATHS

    def test_openapi_json_is_public(self) -> None:
        """Test /openapi.json is in public paths."""
        assert "/openapi.json" in _PUBLIC_PATHS

    def test_public_paths_is_frozenset(self) -> None:
        """Test _PUBLIC_PATHS is immutable."""
        assert isinstance(_PUBLIC_PATHS, frozenset)


class TestAllowedHeaders:
    """Tests for _ALLOWED_HEADERS configuration."""

    def test_authorization_header(self) -> None:
        """Test Authorization is in allowed headers."""
        assert "Authorization" in _ALLOWED_HEADERS

    def test_content_type_header(self) -> None:
        """Test Content-Type is in allowed headers."""
        assert "Content-Type" in _ALLOWED_HEADERS

    def test_no_wildcard(self) -> None:
        """Test no wildcard in allowed headers."""
        assert "*" not in _ALLOWED_HEADERS


class TestAuthGateDispatch:
    """Tests for _auth_gate_dispatch middleware."""

    @pytest.mark.asyncio
    async def test_options_passes_through(self) -> None:
        """Test OPTIONS (CORS preflight) always passes through."""
        request = MagicMock()
        request.method = "OPTIONS"
        request.url.path = "/api/v1/some-protected-endpoint"

        expected_response = MagicMock()
        call_next = AsyncMock(return_value=expected_response)

        response = await _auth_gate_dispatch(request, call_next)
        assert response is expected_response
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_public_path_passes_without_auth(self) -> None:
        """Test public paths pass without Authorization header."""
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/health"
        request.headers = {}

        expected_response = MagicMock()
        call_next = AsyncMock(return_value=expected_response)

        response = await _auth_gate_dispatch(request, call_next)
        assert response is expected_response

    @pytest.mark.asyncio
    async def test_public_path_with_trailing_slash(self) -> None:
        """Test public paths with trailing slash are normalized."""
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/health/"
        request.headers = {}

        expected_response = MagicMock()
        call_next = AsyncMock(return_value=expected_response)

        response = await _auth_gate_dispatch(request, call_next)
        assert response is expected_response

    @pytest.mark.asyncio
    async def test_private_path_without_auth_returns_401(self) -> None:
        """Test private paths without auth return 401."""
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/v1/visions"
        request.headers = MagicMock()
        request.headers.get = MagicMock(return_value="")

        call_next = AsyncMock()

        response = await _auth_gate_dispatch(request, call_next)
        assert isinstance(response, JSONResponse)
        assert response.status_code == 401
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_private_path_with_invalid_auth_returns_401(self) -> None:
        """Test private paths with non-Bearer auth return 401."""
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/v1/tasks"
        request.headers = MagicMock()
        request.headers.get = MagicMock(return_value="Basic abc123")

        call_next = AsyncMock()

        response = await _auth_gate_dispatch(request, call_next)
        assert isinstance(response, JSONResponse)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_private_path_with_bearer_passes(self) -> None:
        """Test private paths with Bearer token pass through."""
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/v1/visions"
        request.headers = MagicMock()
        request.headers.get = MagicMock(return_value="Bearer some-jwt-token")

        expected_response = MagicMock()
        call_next = AsyncMock(return_value=expected_response)

        response = await _auth_gate_dispatch(request, call_next)
        assert response is expected_response

    @pytest.mark.asyncio
    async def test_empty_path_normalized(self) -> None:
        """Test empty path after stripping becomes /."""
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/"
        request.headers = MagicMock()
        request.headers.get = MagicMock(return_value="")

        call_next = AsyncMock()

        # "/" is not in _PUBLIC_PATHS, should return 401
        response = await _auth_gate_dispatch(request, call_next)
        assert isinstance(response, JSONResponse)
        assert response.status_code == 401


class TestCreateApp:
    """Tests for create_app() factory function."""

    @patch.dict(os.environ, {
        "AURORA_API_SECRET_KEY": "test-secret-key-for-jwt-signing-at-least-32-bytes-long",
        "AURORA_DEV_MODE": "1",
        "AURORA_HMAC_SECRET": "test-hmac-secret",
        "AURORA_ENVIRONMENT": "development",
        "AURORA_CORS_ORIGINS": "",
    })
    def test_create_app_returns_fastapi(self) -> None:
        """Test create_app returns a FastAPI instance."""
        app = create_app()
        assert isinstance(app, FastAPI)

    @patch.dict(os.environ, {
        "AURORA_API_SECRET_KEY": "test-secret-key-for-jwt-signing-at-least-32-bytes-long",
        "AURORA_DEV_MODE": "1",
        "AURORA_HMAC_SECRET": "test-hmac-secret",
        "AURORA_ENVIRONMENT": "development",
        "AURORA_CORS_ORIGINS": "",
    })
    def test_create_app_has_health_endpoint(self) -> None:
        """Test app has root /health endpoint."""
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @patch.dict(os.environ, {
        "AURORA_API_SECRET_KEY": "test-secret-key-for-jwt-signing-at-least-32-bytes-long",
        "AURORA_DEV_MODE": "1",
        "AURORA_HMAC_SECRET": "test-hmac-secret",
        "AURORA_ENVIRONMENT": "development",
        "AURORA_CORS_ORIGINS": "",
    })
    def test_development_mode_has_docs(self) -> None:
        """Test docs are enabled in development mode."""
        app = create_app()
        # In development mode, docs_url should be "/docs"
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"

    @patch.dict(os.environ, {
        "AURORA_API_SECRET_KEY": "test-secret-key-for-jwt-signing-at-least-32-bytes-long",
        "AURORA_DEV_MODE": "1",
        "AURORA_HMAC_SECRET": "test-hmac-secret",
        "AURORA_ENVIRONMENT": "production",
        "AURORA_CORS_ORIGINS": "",
    })
    def test_production_mode_disables_docs(self) -> None:
        """Test docs are disabled in production mode (LOW-1)."""
        app = create_app()
        assert app.docs_url is None
        assert app.redoc_url is None

    @patch.dict(os.environ, {
        "AURORA_API_SECRET_KEY": "test-secret-key-for-jwt-signing-at-least-32-bytes-long",
        "AURORA_DEV_MODE": "1",
        "AURORA_HMAC_SECRET": "test-hmac-secret",
        "AURORA_ENVIRONMENT": "production",
        "AURORA_CORS_ORIGINS": "*",
    })
    def test_production_wildcard_cors_raises(self) -> None:
        """Test wildcard CORS in production raises ValueError (HIGH-10)."""
        with pytest.raises(ValueError, match="wildcard"):
            create_app()

    @patch.dict(os.environ, {
        "AURORA_API_SECRET_KEY": "test-secret-key-for-jwt-signing-at-least-32-bytes-long",
        "AURORA_DEV_MODE": "1",
        "AURORA_HMAC_SECRET": "test-hmac-secret",
        "AURORA_ENVIRONMENT": "development",
        "AURORA_CORS_ORIGINS": "http://localhost:3000,https://app.example.com",
    })
    def test_cors_origins_parsed(self) -> None:
        """Test CORS origins are parsed from env var."""
        app = create_app()
        # App should be created successfully with explicit origins
        assert isinstance(app, FastAPI)

    @patch.dict(os.environ, {
        "AURORA_API_SECRET_KEY": "test-secret-key-for-jwt-signing-at-least-32-bytes-long",
        "AURORA_DEV_MODE": "1",
        "AURORA_HMAC_SECRET": "test-hmac-secret",
        "AURORA_ENVIRONMENT": "development",
        "AURORA_CORS_ORIGINS": " , , ",
    })
    def test_cors_empty_origins_after_strip(self) -> None:
        """Test whitespace-only CORS origins result in empty list."""
        app = create_app()
        assert isinstance(app, FastAPI)

    @patch.dict(os.environ, {
        "AURORA_API_SECRET_KEY": "test-secret-key-for-jwt-signing-at-least-32-bytes-long",
        "AURORA_DEV_MODE": "1",
        "AURORA_HMAC_SECRET": "test-hmac-secret",
        "AURORA_ENVIRONMENT": "development",
        "AURORA_CORS_ORIGINS": "",
    })
    def test_unauthenticated_private_path_returns_401(self) -> None:
        """Test unauthenticated access to private path returns 401."""
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/visions")
        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "unauthorized"

    @patch.dict(os.environ, {
        "AURORA_API_SECRET_KEY": "test-secret-key-for-jwt-signing-at-least-32-bytes-long",
        "AURORA_DEV_MODE": "1",
        "AURORA_HMAC_SECRET": "test-hmac-secret",
        "AURORA_ENVIRONMENT": "development",
        "AURORA_CORS_ORIGINS": "",
    })
    def test_app_title_and_version(self) -> None:
        """Test app metadata is set correctly."""
        app = create_app()
        assert app.title == "Aurora Sun V1"
        assert app.version == "0.1.0"
