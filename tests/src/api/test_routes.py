"""
Tests for API Routes (src/api/routes.py).

Tests:
- Health check endpoint
- Auth token endpoint
- Vision/Goal/Task endpoints
- Capture/Recall endpoints
- Transaction/Balance endpoints
- Energy/Wearable endpoints
- Calendar endpoints
- User profile/preferences endpoints
"""

import pytest

from src.api.routes import router


class TestAPIRoutes:
    """Tests for API routes."""

    def test_router_has_health_endpoint(self) -> None:
        """Test that router has health endpoint."""
        routes = router.get_routes()
        assert "GET /health" in routes

    def test_router_has_auth_endpoint(self) -> None:
        """Test that router has auth endpoint."""
        routes = router.get_routes()
        assert "POST /auth/token" in routes

    def test_router_has_vision_endpoints(self) -> None:
        """Test that router has vision endpoints."""
        routes = router.get_routes()
        assert "GET /visions" in routes
        assert "POST /visions" in routes

    def test_router_has_goal_endpoints(self) -> None:
        """Test that router has goal endpoints."""
        routes = router.get_routes()
        assert "GET /goals" in routes
        assert "POST /goals" in routes

    def test_router_has_task_endpoints(self) -> None:
        """Test that router has task endpoints."""
        routes = router.get_routes()
        assert "GET /tasks" in routes
        assert "POST /tasks" in routes

    def test_router_has_capture_endpoints(self) -> None:
        """Test that router has capture endpoints."""
        routes = router.get_routes()
        assert "POST /captures" in routes
        assert "POST /captures/voice" in routes

    def test_router_has_recall_endpoint(self) -> None:
        """Test that router has recall endpoint."""
        routes = router.get_routes()
        assert "POST /recall" in routes

    def test_router_has_transaction_endpoints(self) -> None:
        """Test that router has transaction endpoints."""
        routes = router.get_routes()
        assert "GET /transactions" in routes
        assert "POST /transactions" in routes
        assert "GET /balance" in routes

    def test_router_has_energy_endpoint(self) -> None:
        """Test that router has energy endpoint."""
        routes = router.get_routes()
        assert "POST /energy" in routes

    def test_router_has_wearable_endpoint(self) -> None:
        """Test that router has wearable endpoint."""
        routes = router.get_routes()
        assert "POST /wearables" in routes

    def test_router_has_calendar_endpoints(self) -> None:
        """Test that router has calendar endpoints."""
        routes = router.get_routes()
        assert "GET /calendar/events" in routes
        assert "POST /calendar/events" in routes

    def test_router_has_user_endpoints(self) -> None:
        """Test that router has user endpoints."""
        routes = router.get_routes()
        assert "GET /user/profile" in routes
        assert "PUT /user/preferences" in routes

    @pytest.mark.asyncio
    async def test_health_check_endpoint(self) -> None:
        """Test health check endpoint returns envelope with status ok."""
        routes = router.get_routes()
        health_handler = routes["GET /health"]["handler"]
        result = await health_handler()

        # Verify envelope structure
        assert result["success"] is True
        assert result["data"]["status"] == "ok"
        assert result["error"] is None
        assert "timestamp" in result["meta"]

    @pytest.mark.asyncio
    async def test_auth_token_endpoint(self) -> None:
        """Test auth token endpoint returns NOT_IMPLEMENTED error envelope."""
        routes = router.get_routes()
        auth_handler = routes["POST /auth/token"]["handler"]
        result = await auth_handler(telegram_id=12345)

        # Verify error envelope structure
        assert result["success"] is False
        assert result["error"]["code"] == "NOT_IMPLEMENTED"
        assert result["data"] is None

    def test_all_routes_have_handlers(self) -> None:
        """Test that all routes have handler functions."""
        routes = router.get_routes()
        for route_key, route_data in routes.items():
            assert "handler" in route_data
            assert callable(route_data["handler"])
            assert "method" in route_data
