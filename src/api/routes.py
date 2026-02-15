"""
REST API Routes for Aurora Sun V1.

Implements all API endpoints for mobile app using FastAPI.
All responses use the ResponseEnvelope pattern (REFACTOR-005).

Endpoints (all under /api/v1 prefix):
- /health - Health check
- /auth/token - Get authentication token
- /visions - Vision management
- /goals - Goal management
- /tasks - Task management
- /captures - Second Brain captures
- /recall - Knowledge graph recall
- /transactions - Money tracker
- /energy - Energy logging
- /wearables - Wearable data submission
- /calendar - Calendar integration
- /user/profile - User profile
- /user/preferences - User preferences

Reference: ROADMAP 5.4, ARCHITECTURE.md Section 14 (SW-14: REST API)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter as FastAPIRouter
from pydantic import BaseModel, Field

from src.api.schemas import error_response, success_response
from src.lib.errors import AUTH_REQUIRED, NOT_IMPLEMENTED

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Request Models for API Input Validation
# =============================================================================


class CreateVisionRequest(BaseModel):
    """Validated input for creating a vision."""
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="", max_length=5000)
    segment: str | None = Field(default=None, max_length=10)


class CreateGoalRequest(BaseModel):
    """Validated input for creating a goal."""
    title: str = Field(..., min_length=1, max_length=500)
    vision_id: int | None = None
    description: str = Field(default="", max_length=5000)


class CreateTaskRequest(BaseModel):
    """Validated input for creating a task."""
    title: str = Field(..., min_length=1, max_length=500)
    goal_id: int | None = None
    description: str = Field(default="", max_length=5000)


class CreateCaptureRequest(BaseModel):
    """Validated input for creating a capture."""
    content: str = Field(..., min_length=1, max_length=10000)
    content_type: str = Field(default="note", max_length=50)
    source: str = Field(default="api", max_length=50)


class SendMessageRequest(BaseModel):
    """Validated input for sending a message to the coaching engine."""
    message: str = Field(..., min_length=1, max_length=4000)
    segment: str | None = Field(default=None, max_length=10)


class CreateTransactionRequest(BaseModel):
    """Validated input for creating a transaction."""
    amount: float
    description: str = Field(default="", max_length=5000)
    transaction_type: str = Field(default="expense", max_length=50)
    category: str = Field(default="", max_length=200)


class LogEnergyRequest(BaseModel):
    """Validated input for logging energy level."""
    level: float = Field(..., ge=0.0, le=1.0)
    note: str = Field(default="", max_length=2000)


class SubmitWearableDataRequest(BaseModel):
    """Validated input for submitting wearable data."""
    data_type: str = Field(..., max_length=100)
    value: float
    timestamp: str = Field(default="", max_length=50)


class CreateCalendarEventRequest(BaseModel):
    """Validated input for creating a calendar event."""
    title: str = Field(..., min_length=1, max_length=500)
    start_time: str = Field(..., max_length=50)
    end_time: str = Field(default="", max_length=50)
    description: str = Field(default="", max_length=5000)


class UpdatePreferencesRequest(BaseModel):
    """Validated input for updating user preferences."""
    language: str | None = Field(default=None, max_length=10)
    segment: str | None = Field(default=None, max_length=10)
    notification_enabled: bool | None = None
    theme: str | None = Field(default=None, max_length=50)


# =============================================================================
# FastAPI Router with /api/v1 prefix
# =============================================================================

router = FastAPIRouter(prefix="/api/v1")


# =============================================================================
# Health & Auth Endpoints
# =============================================================================


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Health check endpoint (unauthenticated).

    Returns only status, no version or internal details (information disclosure prevention).
    Detailed health info is available at /health/detailed (requires auth).

    Returns:
        Envelope with minimal health status
    """
    return success_response({"status": "ok"})


@router.get("/health/detailed")
async def health_check_detailed(user_id: int | None = None) -> dict[str, Any]:
    """
    Detailed health check endpoint (requires authentication/admin role).

    Detailed info separated from public /health (information disclosure prevention).

    Args:
        user_id: Authenticated admin user ID (placeholder for auth middleware)

    Returns:
        Envelope with detailed health status or error
    """
    from datetime import datetime

    # TODO: Add actual authentication/admin role check via middleware
    if user_id is None:
        return error_response(AUTH_REQUIRED, "Authentication required")

    return success_response({
        "status": "healthy",
        "version": "0.1.0",
        "timestamp": datetime.now().isoformat(),
    })


@router.post("/auth/token")
async def get_auth_token(telegram_id: int) -> dict[str, Any]:
    """
    Get authentication token for a Telegram user.

    This endpoint is disabled until proper authentication is
    implemented. Returns NOT_IMPLEMENTED error.

    Args:
        telegram_id: Telegram user ID

    Returns:
        Envelope with NOT_IMPLEMENTED error
    """
    return error_response(
        NOT_IMPLEMENTED,
        "Authentication not yet implemented. Use Telegram bot.",
    )


# =============================================================================
# Vision-to-Task Endpoints
# =============================================================================


@router.get("/visions")
async def list_visions(user_id: int) -> dict[str, Any]:
    """
    List all visions for a user.

    Args:
        user_id: User ID

    Returns:
        Envelope with list of visions
    """
    # Placeholder
    return success_response({"visions": [], "total": 0})


@router.post("/visions")
async def create_vision(user_id: int, data: CreateVisionRequest) -> dict[str, Any]:
    """
    Create a new vision.

    Input validated via CreateVisionRequest Pydantic model.

    Args:
        user_id: User ID
        data: Validated vision data

    Returns:
        Envelope with created vision
    """
    # Placeholder
    return success_response({"id": 1, "user_id": user_id, **data.model_dump(exclude_none=True)})


@router.get("/goals")
async def list_goals(user_id: int, vision_id: int | None = None) -> dict[str, Any]:
    """
    List all goals for a user.

    Args:
        user_id: User ID
        vision_id: Optional vision ID filter

    Returns:
        Envelope with list of goals
    """
    # Placeholder
    return success_response({"goals": [], "total": 0})


@router.post("/goals")
async def create_goal(user_id: int, data: CreateGoalRequest) -> dict[str, Any]:
    """
    Create a new goal.

    Input validated via CreateGoalRequest Pydantic model.

    Args:
        user_id: User ID
        data: Validated goal data

    Returns:
        Envelope with created goal
    """
    # Placeholder
    return success_response({"id": 1, "user_id": user_id, **data.model_dump(exclude_none=True)})


@router.get("/tasks")
async def list_tasks(
    user_id: int,
    goal_id: int | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """
    List all tasks for a user.

    Args:
        user_id: User ID
        goal_id: Optional goal ID filter
        status: Optional status filter

    Returns:
        Envelope with list of tasks
    """
    # Placeholder
    return success_response({"tasks": [], "total": 0})


@router.post("/tasks")
async def create_task(user_id: int, data: CreateTaskRequest) -> dict[str, Any]:
    """
    Create a new task.

    Input validated via CreateTaskRequest Pydantic model.

    Args:
        user_id: User ID
        data: Validated task data

    Returns:
        Envelope with created task
    """
    # Placeholder
    return success_response({"id": 1, "user_id": user_id, **data.model_dump(exclude_none=True)})


# =============================================================================
# Second Brain Endpoints
# =============================================================================


@router.post("/captures")
async def create_capture(user_id: int, data: CreateCaptureRequest) -> dict[str, Any]:
    """
    Create a new capture (text, voice, link, image).

    Input validated via CreateCaptureRequest Pydantic model.

    Args:
        user_id: User ID
        data: Validated capture data

    Returns:
        Envelope with created capture
    """
    # Placeholder
    return success_response({"id": 1, "user_id": user_id, **data.model_dump()})


@router.post("/captures/voice")
async def create_voice_capture(
    user_id: int,
    audio_data: bytes,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a voice capture (transcribed automatically).

    Args:
        user_id: User ID
        audio_data: Audio file data
        metadata: Capture metadata

    Returns:
        Envelope with created capture and transcription
    """
    # Placeholder - in production, transcribe audio using Whisper API
    return success_response({
        "id": 1,
        "user_id": user_id,
        "capture_type": "voice",
        "transcription": "[Transcription placeholder]",
        "voice_url": "https://example.com/voice/1.mp3",
    })


@router.post("/recall")
async def recall_knowledge(user_id: int, query: str, limit: int = 10) -> dict[str, Any]:
    """
    Query knowledge graph for relevant captures.

    Args:
        user_id: User ID
        query: Search query
        limit: Max results

    Returns:
        Envelope with recall results
    """
    # Placeholder - in production, query Neo4j/Qdrant for semantic search
    return success_response({"query": query, "results": [], "total": 0})


# =============================================================================
# Money Tracker Endpoints
# =============================================================================


@router.get("/transactions")
async def list_transactions(
    user_id: int,
    transaction_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    List transactions for a user.

    Args:
        user_id: User ID
        transaction_type: Optional filter (income/expense)
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        Envelope with list of transactions
    """
    # Placeholder
    return success_response({"transactions": [], "total": 0})


@router.post("/transactions")
async def create_transaction(user_id: int, data: CreateTransactionRequest) -> dict[str, Any]:
    """
    Create a new transaction.

    Input validated via CreateTransactionRequest Pydantic model.

    Args:
        user_id: User ID
        data: Validated transaction data

    Returns:
        Envelope with created transaction
    """
    # Placeholder
    return success_response({"id": 1, "user_id": user_id, **data.model_dump()})


@router.get("/balance")
async def get_balance(user_id: int) -> dict[str, Any]:
    """
    Get account balance for a user.

    Args:
        user_id: User ID

    Returns:
        Envelope with balance information
    """
    # Placeholder
    return success_response({
        "user_id": user_id,
        "total_income": 0.0,
        "total_expenses": 0.0,
        "balance": 0.0,
    })


# =============================================================================
# Energy & Neurostate Endpoints
# =============================================================================


@router.post("/energy")
async def log_energy(user_id: int, data: LogEnergyRequest) -> dict[str, Any]:
    """
    Log energy level.

    Input validated via LogEnergyRequest Pydantic model.

    Args:
        user_id: User ID
        data: Validated energy log data

    Returns:
        Envelope with created energy log
    """
    # Placeholder
    return success_response({"id": 1, "user_id": user_id, **data.model_dump()})


@router.post("/wearables")
async def submit_wearable_data(user_id: int, data: SubmitWearableDataRequest) -> dict[str, Any]:
    """
    Submit wearable data (heart rate, steps, sleep, etc.).

    Input validated via SubmitWearableDataRequest Pydantic model.

    Args:
        user_id: User ID
        data: Validated wearable data

    Returns:
        Envelope with acknowledgment
    """
    # Placeholder - in production, process wearable data for energy inference
    return success_response({"status": "received", "data_points": 1})


# =============================================================================
# Calendar Integration Endpoints
# =============================================================================


@router.get("/calendar/events")
async def list_calendar_events(
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    List calendar events.

    Args:
        user_id: User ID
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        Envelope with list of calendar events
    """
    # Placeholder
    return success_response({"events": [], "total": 0})


@router.post("/calendar/events")
async def create_calendar_event(user_id: int, data: CreateCalendarEventRequest) -> dict[str, Any]:
    """
    Create a calendar event.

    Input validated via CreateCalendarEventRequest Pydantic model.

    Args:
        user_id: User ID
        data: Validated event data

    Returns:
        Envelope with created event
    """
    # Placeholder
    return success_response({"id": 1, "user_id": user_id, **data.model_dump()})


# =============================================================================
# User Profile & Preferences Endpoints
# =============================================================================


@router.get("/user/profile")
async def get_user_profile(user_id: int) -> dict[str, Any]:
    """
    Get user profile.

    Args:
        user_id: User ID

    Returns:
        Envelope with user profile
    """
    # Placeholder
    return success_response({
        "user_id": user_id,
        "name": "User",
        "language": "en",
        "segment": "NT",
    })


@router.put("/user/preferences")
async def update_user_preferences(user_id: int, data: UpdatePreferencesRequest) -> dict[str, Any]:
    """
    Update user preferences.

    Input validated via UpdatePreferencesRequest Pydantic model.

    Args:
        user_id: User ID
        data: Validated preferences data

    Returns:
        Envelope with updated preferences
    """
    # Placeholder
    return success_response({"user_id": user_id, **data.model_dump(exclude_none=True)})


# =============================================================================
# Backward Compatibility: get_routes() for tests
# =============================================================================


def get_routes() -> dict[str, dict[str, Any]]:
    """
    Get all registered routes as a dictionary.

    This provides backward compatibility with the placeholder APIRouter.
    Tests and other code that relied on router.get_routes() can use this
    function or call router.get_routes() (which delegates here).

    Returns:
        Dictionary mapping "METHOD /path" to route info with handler and method.
    """
    routes: dict[str, dict[str, Any]] = {}
    prefix = router.prefix  # "/api/v1"
    valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
    for route in router.routes:
        # FastAPI APIRoute objects have .methods and .endpoint attributes
        if hasattr(route, "methods") and hasattr(route, "endpoint"):
            full_path = getattr(route, "path", "")
            # Strip the /api/v1 prefix to maintain backward-compatible keys
            if full_path.startswith(prefix):
                path = full_path[len(prefix):]
            else:
                path = full_path
            for method in route.methods:
                if method in valid_methods:
                    key = f"{method} {path}"
                    routes[key] = {
                        "handler": route.endpoint,
                        "method": method,
                    }
    return routes


# Attach get_routes as a method on the router instance for backward compatibility
router.get_routes = get_routes  # type: ignore[attr-defined]


__all__ = [
    "router",
    "get_routes",
    # Pydantic request models for input validation
    "CreateVisionRequest",
    "CreateGoalRequest",
    "CreateTaskRequest",
    "CreateCaptureRequest",
    "SendMessageRequest",
    "CreateTransactionRequest",
    "LogEnergyRequest",
    "SubmitWearableDataRequest",
    "CreateCalendarEventRequest",
    "UpdatePreferencesRequest",
]
