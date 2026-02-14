"""
Tests for API schemas (src/api/schemas.py).

Tests cover validation, edge cases, field constraints, type coercion,
and error handling for all Pydantic schemas.

Reference: CRITICAL gap #1 — 181 lines untested, 0% coverage
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from src.api.schemas import (
    APIError,
    BalanceResponse,
    CalendarEventCreate,
    CalendarEventResponse,
    CaptureCreate,
    CaptureResponse,
    CaptureType,
    EnergyLevel,
    EnergyLogCreate,
    EnergyLogResponse,
    GoalCreate,
    GoalResponse,
    HealthCheckResponse,
    RecallQuery,
    RecallResponse,
    RecallResult,
    TaskCreate,
    TaskResponse,
    TransactionCreate,
    TransactionResponse,
    TransactionType,
    UserPreferencesUpdate,
    UserProfile,
    VisionCreate,
    VisionResponse,
    WearableDataSubmit,
)

# =============================================================================
# Common Schemas
# =============================================================================


def test_api_error_minimal():
    """Test APIError with minimal required fields."""
    error = APIError(error_code="TEST_ERROR", message="Test message")
    assert error.error_code == "TEST_ERROR"
    assert error.message == "Test message"
    assert error.details is None


def test_api_error_with_details():
    """Test APIError with optional details."""
    error = APIError(
        error_code="VALIDATION_ERROR",
        message="Invalid input",
        details={"field": "email", "reason": "invalid format"},
    )
    assert error.details == {"field": "email", "reason": "invalid format"}


def test_health_check_response():
    """Test HealthCheckResponse."""
    now = datetime.now()
    response = HealthCheckResponse(status="healthy", version="1.0.0", timestamp=now)
    assert response.status == "healthy"
    assert response.version == "1.0.0"
    assert response.timestamp == now


# =============================================================================
# Vision-to-Task Schemas
# =============================================================================


def test_vision_create_minimal():
    """Test VisionCreate with minimal fields."""
    vision = VisionCreate(title="My Vision")
    assert vision.title == "My Vision"
    assert vision.description is None
    assert vision.timeframe_months is None


def test_vision_create_full():
    """Test VisionCreate with all fields."""
    vision = VisionCreate(
        title="Launch Startup",
        description="Build and launch a SaaS product",
        timeframe_months=12,
    )
    assert vision.title == "Launch Startup"
    assert vision.description == "Build and launch a SaaS product"
    assert vision.timeframe_months == 12


def test_vision_create_title_too_short():
    """Test VisionCreate rejects empty title."""
    with pytest.raises(ValidationError) as exc_info:
        VisionCreate(title="")
    errors = exc_info.value.errors()
    assert any(e["type"] == "string_too_short" for e in errors)


def test_vision_create_title_too_long():
    """Test VisionCreate rejects title > 200 chars."""
    with pytest.raises(ValidationError) as exc_info:
        VisionCreate(title="x" * 201)
    errors = exc_info.value.errors()
    assert any(e["type"] == "string_too_long" for e in errors)


def test_vision_create_description_too_long():
    """Test VisionCreate rejects description > 2000 chars."""
    with pytest.raises(ValidationError) as exc_info:
        VisionCreate(title="Test", description="x" * 2001)
    errors = exc_info.value.errors()
    assert any(e["type"] == "string_too_long" for e in errors)


def test_vision_create_timeframe_negative():
    """Test VisionCreate rejects negative timeframe."""
    with pytest.raises(ValidationError) as exc_info:
        VisionCreate(title="Test", timeframe_months=-1)
    errors = exc_info.value.errors()
    assert any(e["type"] == "greater_than_equal" for e in errors)


def test_vision_create_timeframe_too_large():
    """Test VisionCreate rejects timeframe > 120 months."""
    with pytest.raises(ValidationError) as exc_info:
        VisionCreate(title="Test", timeframe_months=121)
    errors = exc_info.value.errors()
    assert any(e["type"] == "less_than_equal" for e in errors)


def test_vision_response():
    """Test VisionResponse."""
    now = datetime.now()
    response = VisionResponse(
        id=1,
        user_id=42,
        title="Vision",
        description="Desc",
        timeframe_months=6,
        created_at=now,
        updated_at=now,
    )
    assert response.id == 1
    assert response.user_id == 42


def test_goal_create_minimal():
    """Test GoalCreate with minimal fields."""
    goal = GoalCreate(title="My Goal")
    assert goal.title == "My Goal"
    assert goal.vision_id is None
    assert goal.description is None
    assert goal.deadline is None


def test_goal_create_full():
    """Test GoalCreate with all fields."""
    deadline = datetime.now() + timedelta(days=30)
    goal = GoalCreate(
        vision_id=1, title="Q1 Goal", description="First quarter goal", deadline=deadline
    )
    assert goal.vision_id == 1
    assert goal.deadline == deadline


def test_goal_create_title_too_short():
    """Test GoalCreate rejects empty title."""
    with pytest.raises(ValidationError):
        GoalCreate(title="")


def test_goal_response():
    """Test GoalResponse."""
    now = datetime.now()
    response = GoalResponse(
        id=2,
        user_id=42,
        vision_id=1,
        title="Goal",
        description=None,
        deadline=now,
        status="active",
        created_at=now,
        updated_at=now,
    )
    assert response.status == "active"


def test_task_create_minimal():
    """Test TaskCreate with minimal fields."""
    task = TaskCreate(title="My Task")
    assert task.title == "My Task"
    assert task.priority == 1  # default
    assert task.goal_id is None


def test_task_create_full():
    """Test TaskCreate with all fields."""
    due = datetime.now() + timedelta(days=7)
    task = TaskCreate(
        goal_id=2, title="Task", description="Do the thing", priority=2, due_date=due
    )
    assert task.goal_id == 2
    assert task.priority == 2
    assert task.due_date == due


def test_task_create_priority_validation():
    """Test TaskCreate priority constraints."""
    # Valid priorities
    TaskCreate(title="P1", priority=1)
    TaskCreate(title="P2", priority=2)
    TaskCreate(title="P3", priority=3)

    # Invalid: too low
    with pytest.raises(ValidationError):
        TaskCreate(title="Test", priority=0)

    # Invalid: too high
    with pytest.raises(ValidationError):
        TaskCreate(title="Test", priority=4)


def test_task_response():
    """Test TaskResponse."""
    now = datetime.now()
    response = TaskResponse(
        id=3,
        user_id=42,
        goal_id=2,
        title="Task",
        description=None,
        priority=1,
        status="todo",
        due_date=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    assert response.status == "todo"


# =============================================================================
# Second Brain Schemas
# =============================================================================


def test_capture_create_minimal():
    """Test CaptureCreate with minimal fields."""
    capture = CaptureCreate(content="Quick note")
    assert capture.content == "Quick note"
    assert capture.capture_type == CaptureType.TEXT
    assert capture.tags == []


def test_capture_create_voice():
    """Test CaptureCreate with voice type."""
    capture = CaptureCreate(
        content="Meeting notes",
        capture_type=CaptureType.VOICE,
        voice_url="https://example.com/voice.mp3",
        transcription="Transcribed text",
        tags=["meeting", "work"],
    )
    assert capture.capture_type == CaptureType.VOICE
    assert capture.voice_url == "https://example.com/voice.mp3"
    assert capture.transcription == "Transcribed text"
    assert "meeting" in capture.tags


def test_capture_create_empty_content():
    """Test CaptureCreate rejects empty content."""
    with pytest.raises(ValidationError):
        CaptureCreate(content="")


def test_capture_type_enum():
    """Test CaptureType enum values."""
    assert CaptureType.TEXT == "text"
    assert CaptureType.VOICE == "voice"
    assert CaptureType.LINK == "link"
    assert CaptureType.IMAGE == "image"


def test_capture_response():
    """Test CaptureResponse."""
    now = datetime.now()
    response = CaptureResponse(
        id=5,
        user_id=42,
        content="Content",
        capture_type="text",
        voice_url=None,
        transcription=None,
        tags=["tag1"],
        created_at=now,
    )
    assert response.id == 5


def test_recall_query_minimal():
    """Test RecallQuery with minimal fields."""
    query = RecallQuery(query="search term")
    assert query.query == "search term"
    assert query.limit == 10  # default


def test_recall_query_custom_limit():
    """Test RecallQuery with custom limit."""
    query = RecallQuery(query="test", limit=50)
    assert query.limit == 50


def test_recall_query_limit_validation():
    """Test RecallQuery limit constraints."""
    # Valid: min
    RecallQuery(query="test", limit=1)

    # Valid: max
    RecallQuery(query="test", limit=100)

    # Invalid: too low
    with pytest.raises(ValidationError):
        RecallQuery(query="test", limit=0)

    # Invalid: too high
    with pytest.raises(ValidationError):
        RecallQuery(query="test", limit=101)


def test_recall_result():
    """Test RecallResult."""
    now = datetime.now()
    result = RecallResult(
        content="Found content",
        relevance_score=0.95,
        created_at=now,
        tags=["important"],
    )
    assert result.relevance_score == 0.95


def test_recall_response():
    """Test RecallResponse."""
    now = datetime.now()
    results = [
        RecallResult(
            content="Result 1", relevance_score=0.9, created_at=now, tags=[]
        ),
        RecallResult(
            content="Result 2", relevance_score=0.8, created_at=now, tags=[]
        ),
    ]
    response = RecallResponse(query="test query", results=results, total_results=2)
    assert response.query == "test query"
    assert len(response.results) == 2
    assert response.total_results == 2


# =============================================================================
# Money Tracker Schemas
# =============================================================================


def test_transaction_type_enum():
    """Test TransactionType enum values."""
    assert TransactionType.INCOME == "income"
    assert TransactionType.EXPENSE == "expense"


def test_transaction_create_minimal():
    """Test TransactionCreate with minimal fields."""
    tx = TransactionCreate(transaction_type=TransactionType.EXPENSE, amount=50.0)
    assert tx.transaction_type == TransactionType.EXPENSE
    assert tx.amount == 50.0
    assert tx.category is None


def test_transaction_create_full():
    """Test TransactionCreate with all fields."""
    now = datetime.now()
    tx = TransactionCreate(
        transaction_type=TransactionType.INCOME,
        amount=1500.0,
        category="Salary",
        description="Monthly paycheck",
        transaction_date=now,
    )
    assert tx.category == "Salary"
    assert tx.description == "Monthly paycheck"
    assert tx.transaction_date == now


def test_transaction_create_zero_amount():
    """Test TransactionCreate rejects zero amount."""
    with pytest.raises(ValidationError):
        TransactionCreate(transaction_type=TransactionType.EXPENSE, amount=0.0)


def test_transaction_create_negative_amount():
    """Test TransactionCreate rejects negative amount."""
    with pytest.raises(ValidationError):
        TransactionCreate(transaction_type=TransactionType.EXPENSE, amount=-10.0)


def test_transaction_response():
    """Test TransactionResponse."""
    now = datetime.now()
    response = TransactionResponse(
        id=10,
        user_id=42,
        transaction_type="income",
        amount=1000.0,
        category="Work",
        description="Payment",
        transaction_date=now,
        created_at=now,
    )
    assert response.amount == 1000.0


def test_balance_response():
    """Test BalanceResponse."""
    now = datetime.now()
    balance = BalanceResponse(
        user_id=42,
        total_income=5000.0,
        total_expenses=3000.0,
        balance=2000.0,
        last_transaction=now,
    )
    assert balance.balance == 2000.0


# =============================================================================
# Energy & Neurostate Schemas
# =============================================================================


def test_energy_level_enum():
    """Test EnergyLevel enum values."""
    assert EnergyLevel.VERY_LOW == "very_low"
    assert EnergyLevel.LOW == "low"
    assert EnergyLevel.MEDIUM == "medium"
    assert EnergyLevel.HIGH == "high"
    assert EnergyLevel.VERY_HIGH == "very_high"


def test_energy_log_create_minimal():
    """Test EnergyLogCreate with minimal fields."""
    log = EnergyLogCreate(level=EnergyLevel.MEDIUM)
    assert log.level == EnergyLevel.MEDIUM
    assert log.context is None
    assert log.from_wearable is False


def test_energy_log_create_with_wearable():
    """Test EnergyLogCreate with wearable data."""
    log = EnergyLogCreate(
        level=EnergyLevel.HIGH,
        context="After workout",
        from_wearable=True,
        wearable_data={"heart_rate": 75, "steps": 8000},
    )
    assert log.from_wearable is True
    assert log.wearable_data["steps"] == 8000


def test_energy_log_response():
    """Test EnergyLogResponse."""
    now = datetime.now()
    response = EnergyLogResponse(
        id=15,
        user_id=42,
        level="medium",
        context="Morning",
        from_wearable=False,
        logged_at=now,
        created_at=now,
    )
    assert response.level == "medium"


def test_wearable_data_submit():
    """Test WearableDataSubmit."""
    now = datetime.now() - timedelta(hours=1)
    data = WearableDataSubmit(
        device_type="apple_watch",
        data_type="heart_rate",
        value=72.5,
        unit="bpm",
        measured_at=now,
    )
    assert data.device_type == "apple_watch"
    assert data.value == 72.5


def test_wearable_data_future_timestamp():
    """Test WearableDataSubmit rejects future timestamp."""
    future = datetime.now() + timedelta(hours=1)
    with pytest.raises(ValidationError) as exc_info:
        WearableDataSubmit(
            device_type="fitbit",
            data_type="steps",
            value=5000,
            unit="steps",
            measured_at=future,
        )
    errors = exc_info.value.errors()
    assert any("future" in str(e).lower() for e in errors)


# =============================================================================
# Calendar Integration Schemas
# =============================================================================


def test_calendar_event_create_minimal():
    """Test CalendarEventCreate with minimal fields."""
    start = datetime.now()
    end = start + timedelta(hours=1)
    event = CalendarEventCreate(title="Meeting", start_time=start, end_time=end)
    assert event.title == "Meeting"
    assert event.description is None
    assert event.location is None


def test_calendar_event_create_full():
    """Test CalendarEventCreate with all fields."""
    start = datetime.now()
    end = start + timedelta(hours=2)
    event = CalendarEventCreate(
        title="Team Standup",
        description="Daily sync",
        start_time=start,
        end_time=end,
        location="Conference Room A",
    )
    assert event.description == "Daily sync"
    assert event.location == "Conference Room A"


def test_calendar_event_end_before_start():
    """Test CalendarEventCreate rejects end_time before start_time."""
    start = datetime.now()
    end = start - timedelta(hours=1)
    with pytest.raises(ValidationError) as exc_info:
        CalendarEventCreate(title="Event", start_time=start, end_time=end)
    errors = exc_info.value.errors()
    assert any("after" in str(e).lower() for e in errors)


def test_calendar_event_end_equals_start():
    """Test CalendarEventCreate rejects end_time equal to start_time."""
    start = datetime.now()
    with pytest.raises(ValidationError):
        CalendarEventCreate(title="Event", start_time=start, end_time=start)


def test_calendar_event_response():
    """Test CalendarEventResponse."""
    now = datetime.now()
    response = CalendarEventResponse(
        id=20,
        user_id=42,
        title="Event",
        description="Desc",
        start_time=now,
        end_time=now + timedelta(hours=1),
        location="Office",
        created_at=now,
    )
    assert response.id == 20


# =============================================================================
# User Profile Schemas
# =============================================================================


def test_user_profile():
    """Test UserProfile."""
    now = datetime.now()
    profile = UserProfile(
        user_id=42,
        telegram_id=123456789,
        name="Test User",
        language="en",
        segment="AD",
        timezone="Europe/Berlin",
        created_at=now,
    )
    assert profile.user_id == 42
    assert profile.language == "en"
    assert profile.segment == "AD"


def test_user_preferences_update_minimal():
    """Test UserPreferencesUpdate with no fields (all optional)."""
    prefs = UserPreferencesUpdate()
    assert prefs.language is None
    assert prefs.timezone is None
    assert prefs.notification_enabled is None


def test_user_preferences_update_partial():
    """Test UserPreferencesUpdate with some fields."""
    prefs = UserPreferencesUpdate(language="de", notification_enabled=True)
    assert prefs.language == "de"
    assert prefs.notification_enabled is True
    assert prefs.timezone is None


def test_user_preferences_update_full():
    """Test UserPreferencesUpdate with all fields."""
    prefs = UserPreferencesUpdate(
        language="sr", timezone="Europe/Belgrade", notification_enabled=False
    )
    assert prefs.language == "sr"
    assert prefs.timezone == "Europe/Belgrade"
    assert prefs.notification_enabled is False
