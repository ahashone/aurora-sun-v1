"""
Tests for side effects system.

Covers:
- SideEffectType enum
- SideEffect creation and validation
- SideEffect class methods (save_task, complete_habit, etc.)
- SideEffectBatch operations
- Priority-based sorting
"""


from src.core.side_effects import SideEffect, SideEffectBatch, SideEffectType

# =============================================================================
# SideEffectType Tests
# =============================================================================


def test_side_effect_type_enum():
    """Test SideEffectType enum values."""
    # Database operations
    assert SideEffectType.SAVE_TASK.value == "save_task"
    assert SideEffectType.UPDATE_TASK.value == "update_task"
    assert SideEffectType.DELETE_TASK.value == "delete_task"

    # Habit operations
    assert SideEffectType.CREATE_HABIT.value == "create_habit"
    assert SideEffectType.COMPLETE_HABIT.value == "complete_habit"

    # Session operations
    assert SideEffectType.START_SESSION.value == "start_session"
    assert SideEffectType.END_SESSION.value == "end_session"


# =============================================================================
# SideEffect Tests
# =============================================================================


def test_side_effect_creation():
    """Test creating a side effect."""
    effect = SideEffect(
        effect_type=SideEffectType.SAVE_TASK,
        payload={"task_id": 123, "title": "Test task"},
    )

    assert effect.effect_type == SideEffectType.SAVE_TASK
    assert effect.payload == {"task_id": 123, "title": "Test task"}
    assert effect.id is not None
    assert effect.created_at is not None
    assert effect.priority == 0


def test_side_effect_with_priority():
    """Test creating a side effect with custom priority."""
    effect = SideEffect(
        effect_type=SideEffectType.SAVE_GOAL,
        payload={"goal_id": 456},
        priority=5,
    )

    assert effect.priority == 5


def test_side_effect_auto_generates_id():
    """Test that side effect auto-generates unique IDs."""
    effect1 = SideEffect(effect_type=SideEffectType.SAVE_TASK, payload={})
    effect2 = SideEffect(effect_type=SideEffectType.SAVE_TASK, payload={})

    assert effect1.id != effect2.id


def test_side_effect_with_string_type():
    """Test creating a side effect with string type (auto-conversion)."""
    effect = SideEffect(
        effect_type="save_task",  # type: ignore
        payload={"task_id": 789},
    )

    assert effect.effect_type == SideEffectType.SAVE_TASK


def test_side_effect_with_invalid_string_type():
    """Test creating a side effect with invalid string type."""
    effect = SideEffect(
        effect_type="invalid_type",  # type: ignore
        payload={},
    )

    # Should convert to CUSTOM
    assert effect.effect_type == SideEffectType.CUSTOM


def test_side_effect_save_task_class_method():
    """Test SideEffect.save_task class method."""
    task_data = {
        "title": "Complete project",
        "priority": 1,
        "user_id": 123,
    }

    effect = SideEffect.save_task(task_data)

    assert effect.effect_type == SideEffectType.SAVE_TASK
    assert effect.payload == task_data
    assert effect.priority == 0


def test_side_effect_save_task_with_priority():
    """Test SideEffect.save_task with custom priority."""
    effect = SideEffect.save_task({"task": "data"}, priority=10)

    assert effect.priority == 10


def test_side_effect_complete_habit_class_method():
    """Test SideEffect.complete_habit class method."""
    effect = SideEffect.complete_habit("habit_123")

    assert effect.effect_type == SideEffectType.COMPLETE_HABIT
    assert effect.payload == {"habit_id": "habit_123"}
    assert effect.priority == 0


def test_side_effect_save_transaction_class_method():
    """Test SideEffect.save_transaction class method."""
    transaction_data = {
        "amount": 100.50,
        "category": "food",
        "description": "Groceries",
    }

    effect = SideEffect.save_transaction(transaction_data)

    assert effect.effect_type == SideEffectType.SAVE_TRANSACTION
    assert effect.payload == transaction_data


def test_side_effect_custom_class_method():
    """Test SideEffect.custom class method."""
    effect = SideEffect.custom(
        "my_custom_effect",
        {"data": "value"},
        priority=3,
    )

    assert effect.effect_type == SideEffectType.CUSTOM
    assert effect.payload["effect_name"] == "my_custom_effect"
    assert effect.payload["data"] == "value"
    assert effect.priority == 3


def test_side_effect_empty_payload():
    """Test side effect with empty payload."""
    effect = SideEffect(effect_type=SideEffectType.SAVE_TASK)

    assert effect.payload == {}


# =============================================================================
# SideEffectBatch Tests
# =============================================================================


def test_side_effect_batch_creation():
    """Test creating a side effect batch."""
    batch = SideEffectBatch()

    assert batch.effects == []
    assert batch.user_id is None
    assert batch.session_id is None
    assert batch.source_module is None
    assert batch.source_state is None


def test_side_effect_batch_with_metadata():
    """Test creating a batch with metadata."""
    batch = SideEffectBatch(
        user_id=123,
        session_id="session_456",
        source_module="planning",
        source_state="awaiting_task",
    )

    assert batch.user_id == 123
    assert batch.session_id == "session_456"
    assert batch.source_module == "planning"
    assert batch.source_state == "awaiting_task"


def test_side_effect_batch_add():
    """Test adding effects to a batch."""
    batch = SideEffectBatch()
    effect = SideEffect(effect_type=SideEffectType.SAVE_TASK, payload={"id": 1})

    batch.add(effect)

    assert len(batch) == 1
    assert batch.effects[0] == effect


def test_side_effect_batch_add_save_task():
    """Test batch.add_save_task helper."""
    batch = SideEffectBatch()
    task_data = {"title": "Test", "priority": 1}

    batch.add_save_task(task_data)

    assert len(batch) == 1
    assert batch.effects[0].effect_type == SideEffectType.SAVE_TASK
    assert batch.effects[0].payload == task_data


def test_side_effect_batch_add_complete_habit():
    """Test batch.add_complete_habit helper."""
    batch = SideEffectBatch()

    batch.add_complete_habit("habit_123")

    assert len(batch) == 1
    assert batch.effects[0].effect_type == SideEffectType.COMPLETE_HABIT
    assert batch.effects[0].payload["habit_id"] == "habit_123"


def test_side_effect_batch_add_save_transaction():
    """Test batch.add_save_transaction helper."""
    batch = SideEffectBatch()
    transaction_data = {"amount": 50.0}

    batch.add_save_transaction(transaction_data)

    assert len(batch) == 1
    assert batch.effects[0].effect_type == SideEffectType.SAVE_TRANSACTION


def test_side_effect_batch_multiple_effects():
    """Test adding multiple effects to a batch."""
    batch = SideEffectBatch()

    batch.add_save_task({"task": 1})
    batch.add_complete_habit("habit_1")
    batch.add_save_transaction({"amount": 100})

    assert len(batch) == 3
    assert batch.effects[0].effect_type == SideEffectType.SAVE_TASK
    assert batch.effects[1].effect_type == SideEffectType.COMPLETE_HABIT
    assert batch.effects[2].effect_type == SideEffectType.SAVE_TRANSACTION


def test_side_effect_batch_sort_by_priority():
    """Test sorting effects by priority."""
    batch = SideEffectBatch()

    # Add effects with different priorities
    batch.add(SideEffect(effect_type=SideEffectType.SAVE_TASK, priority=5))
    batch.add(SideEffect(effect_type=SideEffectType.UPDATE_TASK, priority=1))
    batch.add(SideEffect(effect_type=SideEffectType.DELETE_TASK, priority=3))

    # Sort by priority
    batch.sort_by_priority()

    # Should be in order: 1, 3, 5
    assert batch.effects[0].priority == 1
    assert batch.effects[1].priority == 3
    assert batch.effects[2].priority == 5


def test_side_effect_batch_is_empty():
    """Test batch.is_empty method."""
    batch = SideEffectBatch()
    assert batch.is_empty() is True

    batch.add_save_task({"task": 1})
    assert batch.is_empty() is False


def test_side_effect_batch_len():
    """Test batch length."""
    batch = SideEffectBatch()
    assert len(batch) == 0

    batch.add_save_task({"task": 1})
    assert len(batch) == 1

    batch.add_complete_habit("habit_1")
    assert len(batch) == 2


def test_side_effect_batch_with_initial_effects():
    """Test creating a batch with initial effects."""
    effects = [
        SideEffect(effect_type=SideEffectType.SAVE_TASK, payload={"id": 1}),
        SideEffect(effect_type=SideEffectType.SAVE_GOAL, payload={"id": 2}),
    ]

    batch = SideEffectBatch(effects=effects)

    assert len(batch) == 2
    assert batch.effects == effects


# =============================================================================
# Priority Ordering Tests
# =============================================================================


def test_priority_ordering_low_first():
    """Test that lower priority executes first."""
    batch = SideEffectBatch()

    # Add in reverse priority order
    batch.add(SideEffect(effect_type=SideEffectType.SAVE_TASK, priority=10))
    batch.add(SideEffect(effect_type=SideEffectType.SAVE_TASK, priority=5))
    batch.add(SideEffect(effect_type=SideEffectType.SAVE_TASK, priority=1))

    batch.sort_by_priority()

    # After sorting, should be 1, 5, 10
    priorities = [e.priority for e in batch.effects]
    assert priorities == [1, 5, 10]


def test_priority_default_is_zero():
    """Test that default priority is 0."""
    effect = SideEffect(effect_type=SideEffectType.SAVE_TASK)
    assert effect.priority == 0


def test_mixed_priority_sorting():
    """Test sorting with mixed positive and zero priorities."""
    batch = SideEffectBatch()

    batch.add(SideEffect(effect_type=SideEffectType.SAVE_TASK, priority=3))
    batch.add(SideEffect(effect_type=SideEffectType.SAVE_TASK, priority=0))
    batch.add(SideEffect(effect_type=SideEffectType.SAVE_TASK, priority=1))
    batch.add(SideEffect(effect_type=SideEffectType.SAVE_TASK, priority=0))

    batch.sort_by_priority()

    priorities = [e.priority for e in batch.effects]
    assert priorities == [0, 0, 1, 3]


# =============================================================================
# Integration Tests
# =============================================================================


def test_complete_side_effect_workflow():
    """Test a complete workflow with batch."""
    # Create a batch for a user action
    batch = SideEffectBatch(
        user_id=123,
        session_id="session_456",
        source_module="planning",
        source_state="task_creation",
    )

    # Add effects in order of execution priority
    batch.add(SideEffect.save_task(
        {"title": "Task 1", "priority": 1},
        priority=0,  # Execute first
    ))
    batch.add(SideEffect(
        effect_type=SideEffectType.UPDATE_SESSION,
        payload={"last_action": "task_created"},
        priority=1,  # Execute second
    ))
    batch.add(SideEffect(
        effect_type=SideEffectType.TRIGGER_DAILY_WORKFLOW,
        payload={},
        priority=2,  # Execute last
    ))

    # Sort by priority
    batch.sort_by_priority()

    # Verify execution order
    assert len(batch) == 3
    assert batch.effects[0].effect_type == SideEffectType.SAVE_TASK
    assert batch.effects[1].effect_type == SideEffectType.UPDATE_SESSION
    assert batch.effects[2].effect_type == SideEffectType.TRIGGER_DAILY_WORKFLOW


def test_batch_metadata_preservation():
    """Test that batch metadata is preserved through operations."""
    batch = SideEffectBatch(
        user_id=999,
        session_id="test_session",
        source_module="habits",
    )

    batch.add_complete_habit("habit_1")
    batch.add_save_task({"task": "data"})
    batch.sort_by_priority()

    # Metadata should still be there
    assert batch.user_id == 999
    assert batch.session_id == "test_session"
    assert batch.source_module == "habits"
