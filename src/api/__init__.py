"""
REST API Layer for Aurora Sun V1 Mobile App.

Implements ROADMAP 5.4: Mobile App Preparation

Provides REST API endpoints for:
- Vision-to-Task (Goal decomposition, task management)
- Second Brain (Capture, recall, knowledge graph)
- Money Tracker (Income/expense tracking, revenue tracking)
- Voice input for captures
- Calendar integration
- Wearable data as energy signal

Reference: ROADMAP 5.4, ARCHITECTURE.md Section 14 (SW-14: REST API)
"""

from __future__ import annotations

__all__ = ["get_api_router"]


def get_api_router() -> None:
    """
    Get the main API router.

    Returns:
        FastAPI router with all endpoints
    """
    # This will be implemented when FastAPI is integrated
    # For now, this is a placeholder
    raise NotImplementedError("API router not yet implemented")
