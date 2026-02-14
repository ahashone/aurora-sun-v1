"""
Tests for core models: User, Task, Goal, Vision, DailyPlan.

Covers:
- Model creation and relationships
- Encrypted field accessors
- Property methods
- Database constraints
- Cascading deletes
"""

from datetime import date

import pytest

from src.models.daily_plan import DailyPlan
from src.models.goal import Goal
from src.models.task import Task
from src.models.user import User
from src.models.vision import Vision

# =============================================================================
# User Model Tests
# =============================================================================


def test_user_creation(db_session):
    """Test creating a user."""
    user = User(
        telegram_id="hashed_telegram_id_123",
        language="en",
        timezone="Europe/Berlin",
        working_style_code="AD",
    )
    user.name = "Test User"

    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert user.telegram_id == "hashed_telegram_id_123"
    assert user.language == "en"
    assert user.timezone == "Europe/Berlin"
    assert user.working_style_code == "AD"
    assert user.name == "Test User"


def test_user_name_encryption(db_session, encryption_service):
    """Test user name encryption."""
    user = User(telegram_id="encrypted_test_123")
    db_session.add(user)
    db_session.commit()

    # Set name after user has ID
    user.name = "Encrypted Name"
    db_session.commit()

    # Retrieve and verify
    retrieved = db_session.query(User).filter_by(id=user.id).first()
    assert retrieved.name == "Encrypted Name"


def test_user_name_none(db_session):
    """Test user with no name."""
    user = User(telegram_id="no_name_123")
    db_session.add(user)
    db_session.commit()

    assert user.name is None


def test_user_segment_display_name(db_session):
    """Test segment display name conversion."""
    user = User(telegram_id="segment_test_123")
    db_session.add(user)
    db_session.commit()

    # Test all segments
    user.working_style_code = "AD"
    assert user.segment_display_name == "ADHD"

    user.working_style_code = "AU"
    assert user.segment_display_name == "Autism"

    user.working_style_code = "AH"
    assert user.segment_display_name == "AuDHD"

    user.working_style_code = "NT"
    assert user.segment_display_name == "Neurotypical"

    user.working_style_code = "CU"
    assert user.segment_display_name == "Custom"

    # Test None
    user.working_style_code = None
    assert user.segment_display_name == "Neurotypical"


def test_user_repr(db_session):
    """Test User repr."""
    user = User(telegram_id="repr_test_hashed_id_12345678", language="de")
    db_session.add(user)
    db_session.commit()

    # __repr__ shows telegram_id_hash= with first 8 chars of telegram_id
    assert "telegram_id_hash=repr_tes" in repr(user)
    assert "language=de" in repr(user)


def test_user_relationships(db_session):
    """Test user relationships with other models."""
    user = User(telegram_id="rel_test_123")
    db_session.add(user)
    db_session.commit()

    # Add related models
    vision = Vision(user_id=user.id, type="life")
    vision.content = "My ideal life"
    db_session.add(vision)

    goal = Goal(user_id=user.id, type="90d")
    goal.title = "Test Goal"
    db_session.add(goal)

    task = Task(user_id=user.id)
    task.title = "Test Task"
    db_session.add(task)

    daily_plan = DailyPlan(user_id=user.id, date=date.today())
    db_session.add(daily_plan)

    db_session.commit()

    # Verify relationships
    assert len(user.visions) == 1
    assert len(user.goals) == 1
    assert len(user.tasks) == 1
    assert len(user.daily_plans) == 1


def test_user_cascade_delete(db_session):
    """Test that deleting user cascades to related models."""
    user = User(telegram_id="cascade_test_123")
    db_session.add(user)
    db_session.commit()

    # Add related models
    vision = Vision(user_id=user.id, type="life")
    vision.content = "Test"
    goal = Goal(user_id=user.id, type="90d")
    goal.title = "Test"
    task = Task(user_id=user.id)
    task.title = "Test"

    db_session.add_all([vision, goal, task])
    db_session.commit()

    user_id = user.id

    # Delete user
    db_session.delete(user)
    db_session.commit()

    # Verify cascaded deletion
    assert db_session.query(Vision).filter_by(user_id=user_id).count() == 0
    assert db_session.query(Goal).filter_by(user_id=user_id).count() == 0
    assert db_session.query(Task).filter_by(user_id=user_id).count() == 0


# =============================================================================
# Vision Model Tests
# =============================================================================


def test_vision_creation(db_session):
    """Test creating a vision."""
    user = User(telegram_id="vision_test_123")
    db_session.add(user)
    db_session.commit()

    vision = Vision(user_id=user.id, type="life")
    vision.content = "Living a fulfilling life with meaningful work"

    db_session.add(vision)
    db_session.commit()

    assert vision.id is not None
    assert vision.user_id == user.id
    assert vision.type == "life"
    assert vision.content == "Living a fulfilling life with meaningful work"


def test_vision_content_encryption(db_session, encryption_service):
    """Test vision content encryption."""
    user = User(telegram_id="vision_enc_123")
    db_session.add(user)
    db_session.commit()

    vision = Vision(user_id=user.id, type="10y")
    vision.content = "Secret 10-year plan"

    db_session.add(vision)
    db_session.commit()

    # Retrieve and verify
    retrieved = db_session.query(Vision).filter_by(id=vision.id).first()
    assert retrieved.content == "Secret 10-year plan"


def test_vision_content_none(db_session):
    """Test vision with no content."""
    user = User(telegram_id="vision_none_123")
    db_session.add(user)
    db_session.commit()

    vision = Vision(user_id=user.id, type="3y")
    db_session.add(vision)
    db_session.commit()

    assert vision.content is None


def test_vision_types(db_session):
    """Test different vision types."""
    user = User(telegram_id="vision_types_123")
    db_session.add(user)
    db_session.commit()

    life = Vision(user_id=user.id, type="life")
    life.content = "Life vision"
    ten_year = Vision(user_id=user.id, type="10y")
    ten_year.content = "10 year vision"
    three_year = Vision(user_id=user.id, type="3y")
    three_year.content = "3 year vision"

    db_session.add_all([life, ten_year, three_year])
    db_session.commit()

    assert db_session.query(Vision).filter_by(user_id=user.id, type="life").count() == 1
    assert db_session.query(Vision).filter_by(user_id=user.id, type="10y").count() == 1
    assert db_session.query(Vision).filter_by(user_id=user.id, type="3y").count() == 1


def test_vision_repr(db_session):
    """Test Vision repr."""
    user = User(telegram_id="vision_repr_123")
    db_session.add(user)
    db_session.commit()

    vision = Vision(user_id=user.id, type="life")
    expected = f"<Vision(id={vision.id}, user_id={user.id}, type=life)>"
    assert repr(vision) == expected


# =============================================================================
# Goal Model Tests
# =============================================================================


def test_goal_creation(db_session):
    """Test creating a goal."""
    user = User(telegram_id="goal_test_123")
    db_session.add(user)
    db_session.commit()

    goal = Goal(user_id=user.id, type="90d", status="active")
    goal.title = "Complete project X"
    goal.key_results = '["KR1: Finish design", "KR2: Implement"]'

    db_session.add(goal)
    db_session.commit()

    assert goal.id is not None
    assert goal.user_id == user.id
    assert goal.type == "90d"
    assert goal.status == "active"
    assert goal.title == "Complete project X"
    assert goal.key_results == '["KR1: Finish design", "KR2: Implement"]'


def test_goal_title_encryption(db_session, encryption_service):
    """Test goal title encryption."""
    user = User(telegram_id="goal_enc_123")
    db_session.add(user)
    db_session.commit()

    goal = Goal(user_id=user.id, type="weekly")
    goal.title = "Encrypted goal title"

    db_session.add(goal)
    db_session.commit()

    # Retrieve and verify
    retrieved = db_session.query(Goal).filter_by(id=goal.id).first()
    assert retrieved.title == "Encrypted goal title"


def test_goal_key_results_encryption(db_session, encryption_service):
    """Test goal key results encryption."""
    user = User(telegram_id="goal_kr_enc_123")
    db_session.add(user)
    db_session.commit()

    goal = Goal(user_id=user.id, type="daily")
    goal.key_results = '["KR1", "KR2"]'

    db_session.add(goal)
    db_session.commit()

    # Retrieve and verify
    retrieved = db_session.query(Goal).filter_by(id=goal.id).first()
    assert retrieved.key_results == '["KR1", "KR2"]'


def test_goal_vision_relationship(db_session):
    """Test goal-vision relationship."""
    user = User(telegram_id="goal_vision_123")
    db_session.add(user)
    db_session.commit()

    vision = Vision(user_id=user.id, type="life")
    vision.content = "Life vision"
    db_session.add(vision)
    db_session.commit()

    goal = Goal(user_id=user.id, vision_id=vision.id, type="90d")
    goal.title = "Goal from vision"
    db_session.add(goal)
    db_session.commit()

    assert goal.vision_id == vision.id
    assert goal.vision == vision
    assert len(vision.goals) == 1


def test_goal_status_values(db_session):
    """Test different goal statuses."""
    user = User(telegram_id="goal_status_123")
    db_session.add(user)
    db_session.commit()

    active = Goal(user_id=user.id, type="90d", status="active")
    active.title = "Active"
    completed = Goal(user_id=user.id, type="90d", status="completed")
    completed.title = "Completed"
    archived = Goal(user_id=user.id, type="90d", status="archived")
    archived.title = "Archived"

    db_session.add_all([active, completed, archived])
    db_session.commit()

    assert db_session.query(Goal).filter_by(status="active").count() == 1
    assert db_session.query(Goal).filter_by(status="completed").count() == 1
    assert db_session.query(Goal).filter_by(status="archived").count() == 1


def test_goal_repr(db_session):
    """Test Goal repr."""
    user = User(telegram_id="goal_repr_123")
    db_session.add(user)
    db_session.commit()

    goal = Goal(user_id=user.id, type="weekly", status="active")
    expected = f"<Goal(id={goal.id}, user_id={user.id}, type=weekly, status=active)>"
    assert repr(goal) == expected


# =============================================================================
# Task Model Tests
# =============================================================================


def test_task_creation(db_session):
    """Test creating a task."""
    user = User(telegram_id="task_test_123")
    db_session.add(user)
    db_session.commit()

    task = Task(
        user_id=user.id,
        status="pending",
        priority=1,
        committed_date=date.today(),
    )
    task.title = "Complete task X"

    db_session.add(task)
    db_session.commit()

    assert task.id is not None
    assert task.user_id == user.id
    assert task.status == "pending"
    assert task.priority == 1
    assert task.title == "Complete task X"


def test_task_title_encryption(db_session, encryption_service):
    """Test task title encryption."""
    user = User(telegram_id="task_enc_123")
    db_session.add(user)
    db_session.commit()

    task = Task(user_id=user.id)
    task.title = "Secret task"

    db_session.add(task)
    db_session.commit()

    # Retrieve and verify
    retrieved = db_session.query(Task).filter_by(id=task.id).first()
    assert retrieved.title == "Secret task"


def test_task_goal_relationship(db_session):
    """Test task-goal relationship."""
    user = User(telegram_id="task_goal_123")
    db_session.add(user)
    db_session.commit()

    goal = Goal(user_id=user.id, type="90d")
    goal.title = "Parent Goal"
    db_session.add(goal)
    db_session.commit()

    task = Task(user_id=user.id, goal_id=goal.id)
    task.title = "Task from goal"
    db_session.add(task)
    db_session.commit()

    assert task.goal_id == goal.id
    assert task.goal == goal
    assert len(goal.tasks) == 1


def test_task_status_values(db_session):
    """Test different task statuses."""
    user = User(telegram_id="task_status_123")
    db_session.add(user)
    db_session.commit()

    pending = Task(user_id=user.id, status="pending")
    pending.title = "Pending"
    in_progress = Task(user_id=user.id, status="in_progress")
    in_progress.title = "In Progress"
    completed = Task(user_id=user.id, status="completed")
    completed.title = "Completed"

    db_session.add_all([pending, in_progress, completed])
    db_session.commit()

    assert db_session.query(Task).filter_by(status="pending").count() == 1
    assert db_session.query(Task).filter_by(status="in_progress").count() == 1
    assert db_session.query(Task).filter_by(status="completed").count() == 1


def test_task_priority_values(db_session):
    """Test task priority values."""
    user = User(telegram_id="task_priority_123")
    db_session.add(user)
    db_session.commit()

    for priority in [1, 2, 3, 4, 5]:
        task = Task(user_id=user.id, priority=priority)
        task.title = f"Priority {priority}"
        db_session.add(task)

    db_session.commit()

    for priority in [1, 2, 3, 4, 5]:
        assert db_session.query(Task).filter_by(priority=priority).count() == 1


def test_task_repr(db_session):
    """Test Task repr."""
    user = User(telegram_id="task_repr_123")
    db_session.add(user)
    db_session.commit()

    task = Task(user_id=user.id, status="pending", priority=2)
    expected = f"<Task(id={task.id}, user_id={user.id}, status=pending, priority=2)>"
    assert repr(task) == expected


# =============================================================================
# DailyPlan Model Tests
# =============================================================================


def test_daily_plan_creation(db_session):
    """Test creating a daily plan."""
    user = User(telegram_id="plan_test_123")
    db_session.add(user)
    db_session.commit()

    plan = DailyPlan(
        user_id=user.id,
        date=date.today(),
        vision_displayed=True,
        goals_reviewed=False,
        priorities_selected=False,
        tasks_committed=False,
        morning_energy=4,
    )

    db_session.add(plan)
    db_session.commit()

    assert plan.id is not None
    assert plan.user_id == user.id
    assert plan.date == date.today()
    assert plan.vision_displayed is True
    assert plan.goals_reviewed is False
    assert plan.morning_energy == 4


def test_daily_plan_reflection_encryption(db_session, encryption_service):
    """Test daily plan reflection encryption."""
    user = User(telegram_id="plan_enc_123")
    db_session.add(user)
    db_session.commit()

    plan = DailyPlan(user_id=user.id, date=date.today())
    plan.reflection_text = "Today was productive"

    db_session.add(plan)
    db_session.commit()

    # Retrieve and verify
    retrieved = db_session.query(DailyPlan).filter_by(id=plan.id).first()
    assert retrieved.reflection_text == "Today was productive"


def test_daily_plan_completion_percentage(db_session):
    """Test daily plan completion percentage calculation."""
    user = User(telegram_id="plan_comp_123")
    db_session.add(user)
    db_session.commit()

    plan = DailyPlan(user_id=user.id, date=date.today())
    db_session.add(plan)
    db_session.commit()

    # 0% complete
    assert plan.completion_percentage == 0.0

    # 25% complete
    plan.vision_displayed = True
    assert plan.completion_percentage == 25.0

    # 50% complete
    plan.goals_reviewed = True
    assert plan.completion_percentage == 50.0

    # 75% complete
    plan.priorities_selected = True
    assert plan.completion_percentage == 75.0

    # 100% complete
    plan.tasks_committed = True
    assert plan.completion_percentage == 100.0


def test_daily_plan_energy_tracking(db_session):
    """Test daily plan energy tracking."""
    user = User(telegram_id="plan_energy_123")
    db_session.add(user)
    db_session.commit()

    plan = DailyPlan(
        user_id=user.id,
        date=date.today(),
        morning_energy=3,
        evening_energy=4,
    )

    db_session.add(plan)
    db_session.commit()

    assert plan.morning_energy == 3
    assert plan.evening_energy == 4


def test_daily_plan_unique_constraint(db_session):
    """Test that user can have only one plan per date."""
    user = User(telegram_id="plan_unique_123")
    db_session.add(user)
    db_session.commit()

    today = date.today()

    plan1 = DailyPlan(user_id=user.id, date=today)
    db_session.add(plan1)
    db_session.commit()

    # Try to add another plan for the same date
    plan2 = DailyPlan(user_id=user.id, date=today)
    db_session.add(plan2)

    with pytest.raises(Exception):  # IntegrityError for unique constraint
        db_session.commit()


def test_daily_plan_repr(db_session):
    """Test DailyPlan repr."""
    user = User(telegram_id="plan_repr_123")
    db_session.add(user)
    db_session.commit()

    today = date.today()
    plan = DailyPlan(user_id=user.id, date=today)
    expected = f"<DailyPlan(id={plan.id}, user_id={user.id}, date={today})>"
    assert repr(plan) == expected


# =============================================================================
# Integration Tests
# =============================================================================


def test_full_user_workflow(db_session):
    """Test complete user workflow with all models."""
    # Create user
    user = User(telegram_id="workflow_123", working_style_code="AD")
    user.name = "Workflow User"
    db_session.add(user)
    db_session.commit()

    # Create vision
    vision = Vision(user_id=user.id, type="life")
    vision.content = "Build amazing things"
    db_session.add(vision)
    db_session.commit()

    # Create goal from vision
    goal = Goal(user_id=user.id, vision_id=vision.id, type="90d", status="active")
    goal.title = "Launch product"
    goal.key_results = '["KR1", "KR2"]'
    db_session.add(goal)
    db_session.commit()

    # Create task from goal
    task = Task(user_id=user.id, goal_id=goal.id, status="pending", priority=1)
    task.title = "Complete feature X"
    db_session.add(task)
    db_session.commit()

    # Create daily plan
    plan = DailyPlan(user_id=user.id, date=date.today())
    plan.vision_displayed = True
    plan.goals_reviewed = True
    plan.priorities_selected = True
    plan.tasks_committed = True
    db_session.add(plan)
    db_session.commit()

    # Verify everything is connected
    assert user.visions[0] == vision
    assert user.goals[0] == goal
    assert user.tasks[0] == task
    assert user.daily_plans[0] == plan
    assert goal.vision == vision
    assert task.goal == goal
    assert plan.completion_percentage == 100.0
