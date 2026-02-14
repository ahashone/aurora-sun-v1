"""
Pydantic Schemas for Aurora Sun V1 REST API.

Defines request/response schemas for all API endpoints.

Reference: ROADMAP 5.4, ARCHITECTURE.md Section 14
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from src.core.segment_context import WorkingStyleCode
from src.i18n import LanguageCode

# =============================================================================
# Common Schemas
# =============================================================================


class APIError(BaseModel):
    """Standard API error response."""

    error_code: str
    message: str
    details: dict[str, Any] | None = None


class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    timestamp: datetime


# =============================================================================
# Vision-to-Task Schemas
# =============================================================================


class VisionCreate(BaseModel):
    """Request schema for creating a vision."""

    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    timeframe_months: int | None = Field(None, ge=1, le=120)  # 1 month to 10 years


class VisionResponse(BaseModel):
    """Response schema for a vision."""

    id: int
    user_id: int
    title: str
    description: str | None
    timeframe_months: int | None
    created_at: datetime
    updated_at: datetime


class GoalCreate(BaseModel):
    """Request schema for creating a goal."""

    vision_id: int | None = None
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    deadline: datetime | None = None


class GoalResponse(BaseModel):
    """Response schema for a goal."""

    id: int
    user_id: int
    vision_id: int | None
    title: str
    description: str | None
    deadline: datetime | None
    status: str  # "active", "completed", "archived"
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    """Request schema for creating a task."""

    goal_id: int | None = None
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    priority: int = Field(1, ge=1, le=3)  # 1=high, 2=medium, 3=low
    due_date: datetime | None = None


class TaskResponse(BaseModel):
    """Response schema for a task."""

    id: int
    user_id: int
    goal_id: int | None
    title: str
    description: str | None
    priority: int
    status: str  # "todo", "in_progress", "completed"
    due_date: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Second Brain Schemas
# =============================================================================


class CaptureType(StrEnum):
    """Type of capture."""

    TEXT = "text"
    VOICE = "voice"  # Transcribed voice note
    LINK = "link"
    IMAGE = "image"


class CaptureCreate(BaseModel):
    """Request schema for creating a capture."""

    content: str = Field(..., min_length=1)
    capture_type: CaptureType = CaptureType.TEXT
    voice_url: str | None = None  # URL to voice file (if type=voice)
    transcription: str | None = None  # Transcription (if type=voice)
    tags: list[str] = Field(default_factory=list)


class CaptureResponse(BaseModel):
    """Response schema for a capture."""

    id: int
    user_id: int
    content: str
    capture_type: str
    voice_url: str | None
    transcription: str | None
    tags: list[str]
    created_at: datetime


class RecallQuery(BaseModel):
    """Request schema for knowledge graph recall."""

    query: str = Field(..., min_length=1)
    limit: int = Field(10, ge=1, le=100)


class RecallResult(BaseModel):
    """Single recall result."""

    content: str
    relevance_score: float
    created_at: datetime
    tags: list[str]


class RecallResponse(BaseModel):
    """Response schema for recall query."""

    query: str
    results: list[RecallResult]
    total_results: int


# =============================================================================
# Money Tracker Schemas
# =============================================================================


class TransactionType(StrEnum):
    """Transaction type."""

    INCOME = "income"
    EXPENSE = "expense"


class TransactionCreate(BaseModel):
    """Request schema for creating a transaction."""

    transaction_type: TransactionType
    amount: float = Field(..., gt=0)
    category: str | None = None
    description: str | None = Field(None, max_length=500)
    transaction_date: datetime | None = None


class TransactionResponse(BaseModel):
    """Response schema for a transaction."""

    id: int
    user_id: int
    transaction_type: str
    amount: float
    category: str | None
    description: str | None
    transaction_date: datetime
    created_at: datetime


class BalanceResponse(BaseModel):
    """Response schema for account balance."""

    user_id: int
    total_income: float
    total_expenses: float
    balance: float
    last_transaction: datetime | None


# =============================================================================
# Energy & Neurostate Schemas
# =============================================================================


class EnergyLevel(StrEnum):
    """Energy level."""

    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class EnergyLogCreate(BaseModel):
    """Request schema for logging energy."""

    level: EnergyLevel
    context: str | None = Field(None, max_length=500)
    from_wearable: bool = False  # True if from wearable data
    wearable_data: dict[str, Any] | None = None  # Raw wearable data


class EnergyLogResponse(BaseModel):
    """Response schema for energy log."""

    id: int
    user_id: int
    level: str
    context: str | None
    from_wearable: bool
    logged_at: datetime
    created_at: datetime


class WearableDataSubmit(BaseModel):
    """Request schema for submitting wearable data."""

    device_type: str  # "apple_watch", "fitbit", "garmin", etc.
    data_type: str  # "heart_rate", "steps", "sleep", etc.
    value: float
    unit: str
    measured_at: datetime

    @field_validator("measured_at")
    @classmethod
    def validate_measured_at(cls, v: datetime) -> datetime:
        """Validate that measured_at is not in the future."""
        if v > datetime.now():
            raise ValueError("measured_at cannot be in the future")
        return v


# =============================================================================
# Calendar Integration Schemas
# =============================================================================


class CalendarEventCreate(BaseModel):
    """Request schema for creating a calendar event."""

    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    start_time: datetime
    end_time: datetime
    location: str | None = Field(None, max_length=200)

    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v: datetime, info: Any) -> datetime:
        """Validate that end_time is after start_time."""
        if "start_time" in info.data and v <= info.data["start_time"]:
            raise ValueError("end_time must be after start_time")
        return v


class CalendarEventResponse(BaseModel):
    """Response schema for a calendar event."""

    id: int
    user_id: int
    title: str
    description: str | None
    start_time: datetime
    end_time: datetime
    location: str | None
    created_at: datetime


# =============================================================================
# User Profile Schemas
# =============================================================================


class UserProfile(BaseModel):
    """User profile response."""

    user_id: int
    telegram_id: int
    name: str
    language: LanguageCode
    segment: WorkingStyleCode
    timezone: str | None
    created_at: datetime


class UserPreferencesUpdate(BaseModel):
    """Request schema for updating user preferences."""

    language: LanguageCode | None = None
    timezone: str | None = None
    notification_enabled: bool | None = None


__all__ = [
    # Common
    "APIError",
    "HealthCheckResponse",
    # Vision-to-Task
    "VisionCreate",
    "VisionResponse",
    "GoalCreate",
    "GoalResponse",
    "TaskCreate",
    "TaskResponse",
    # Second Brain
    "CaptureCreate",
    "CaptureResponse",
    "RecallQuery",
    "RecallResponse",
    # Money Tracker
    "TransactionCreate",
    "TransactionResponse",
    "BalanceResponse",
    # Energy & Neurostate
    "EnergyLogCreate",
    "EnergyLogResponse",
    "WearableDataSubmit",
    # Calendar
    "CalendarEventCreate",
    "CalendarEventResponse",
    # User
    "UserProfile",
    "UserPreferencesUpdate",
]
