"""
Tests for ModuleResponse.

Covers:
- Response creation (text-only, with buttons, with state transition)
- Button management
- Side effect management
- Class methods (text_only, with_buttons, end_flow, transition)
- Response modifiers
"""

import pytest

from src.core.buttons import Button
from src.core.module_response import ModuleResponse
from src.core.side_effects import SideEffect, SideEffectType


def test_module_response_basic_creation():
    """Test creating a basic module response."""
    response = ModuleResponse(text="Hello, world!")

    assert response.text == "Hello, world!"
    assert response.buttons is None
    assert response.next_state is None
    assert response.side_effects is None
    assert response.metadata == {}
    assert response.is_end_of_flow is False
    assert response.should_trigger_daily_workflow is False


def test_module_response_with_all_fields():
    """Test creating a response with all fields."""
    buttons = [Button(text="OK", callback_data="ok")]
    side_effects = [SideEffect(effect_type=SideEffectType.SAVE_TASK, payload={"task": "data"})]

    response = ModuleResponse(
        text="Response text",
        buttons=buttons,
        next_state="next_state",
        side_effects=side_effects,
        metadata={"key": "value"},
        is_end_of_flow=True,
        should_trigger_daily_workflow=True,
    )

    assert response.text == "Response text"
    assert response.buttons == buttons
    assert response.next_state == "next_state"
    assert response.side_effects == side_effects
    assert response.metadata == {"key": "value"}
    assert response.is_end_of_flow is True
    assert response.should_trigger_daily_workflow is True


def test_add_button():
    """Test adding a button to response."""
    response = ModuleResponse(text="Test")

    assert response.buttons is None

    response.add_button(text="Button 1", callback_data="btn1")

    assert response.buttons is not None
    assert len(response.buttons) == 1
    assert response.buttons[0].text == "Button 1"
    assert response.buttons[0].callback_data == "btn1"


def test_add_multiple_buttons():
    """Test adding multiple buttons."""
    response = ModuleResponse(text="Test")

    response.add_button(text="Button 1", callback_data="btn1")
    response.add_button(text="Button 2", callback_data="btn2")
    response.add_button(text="Button 3", url="https://example.com")

    assert len(response.buttons) == 3
    assert response.buttons[1].text == "Button 2"
    assert response.buttons[2].url == "https://example.com"


def test_add_side_effect():
    """Test adding a side effect to response."""
    response = ModuleResponse(text="Test")

    assert response.side_effects is None

    response.add_side_effect(SideEffectType.SAVE_TASK, {"task_id": 123})

    assert response.side_effects is not None
    assert len(response.side_effects) == 1
    assert response.side_effects[0].effect_type == SideEffectType.SAVE_TASK
    assert response.side_effects[0].payload == {"task_id": 123}


def test_add_side_effect_with_string_type():
    """Test adding a side effect with string type."""
    response = ModuleResponse(text="Test")

    response.add_side_effect("save_task", {"task_id": 456})

    assert len(response.side_effects) == 1
    assert response.side_effects[0].effect_type == SideEffectType.SAVE_TASK


def test_add_multiple_side_effects():
    """Test adding multiple side effects."""
    response = ModuleResponse(text="Test")

    response.add_side_effect(SideEffectType.SAVE_TASK, {"task": 1})
    response.add_side_effect(SideEffectType.SAVE_GOAL, {"goal": 2})
    response.add_side_effect(SideEffectType.UPDATE_SESSION, {"session": 3})

    assert len(response.side_effects) == 3
    assert response.side_effects[0].effect_type == SideEffectType.SAVE_TASK
    assert response.side_effects[1].effect_type == SideEffectType.SAVE_GOAL
    assert response.side_effects[2].effect_type == SideEffectType.UPDATE_SESSION


def test_text_only_class_method():
    """Test creating a text-only response."""
    response = ModuleResponse.text_only("Simple text")

    assert response.text == "Simple text"
    assert response.buttons is None
    assert response.next_state is None
    assert response.side_effects is None


def test_with_buttons_class_method():
    """Test creating a response with buttons."""
    buttons = [
        Button(text="Yes", callback_data="yes"),
        Button(text="No", callback_data="no"),
    ]

    response = ModuleResponse.with_buttons("Choose one:", buttons)

    assert response.text == "Choose one:"
    assert response.buttons == buttons
    assert len(response.buttons) == 2


def test_end_flow_class_method():
    """Test creating an end-of-flow response."""
    response = ModuleResponse.end_flow("All done!")

    assert response.text == "All done!"
    assert response.is_end_of_flow is True
    assert response.buttons is None
    assert response.next_state is None


def test_transition_class_method():
    """Test creating a response with state transition."""
    response = ModuleResponse.transition("Moving to next state", "awaiting_input")

    assert response.text == "Moving to next state"
    assert response.next_state == "awaiting_input"
    assert response.is_end_of_flow is False


def test_metadata_usage():
    """Test using metadata field."""
    response = ModuleResponse(
        text="Test",
        metadata={
            "intent": "planning.start",
            "user_segment": "AD",
            "timestamp": "2024-01-01T00:00:00Z",
        }
    )

    assert response.metadata["intent"] == "planning.start"
    assert response.metadata["user_segment"] == "AD"
    assert "timestamp" in response.metadata


def test_response_modifiers():
    """Test response modifier flags."""
    # Default values
    response1 = ModuleResponse(text="Test")
    assert response1.is_end_of_flow is False
    assert response1.should_trigger_daily_workflow is False

    # Set flags
    response2 = ModuleResponse(
        text="Test",
        is_end_of_flow=True,
        should_trigger_daily_workflow=True,
    )
    assert response2.is_end_of_flow is True
    assert response2.should_trigger_daily_workflow is True


def test_chaining_operations():
    """Test chaining add_button and add_side_effect operations."""
    response = ModuleResponse(text="Test")

    response.add_button("Button 1", "btn1")
    response.add_button("Button 2", "btn2")
    response.add_side_effect(SideEffectType.SAVE_TASK, {"id": 1})
    response.add_side_effect(SideEffectType.UPDATE_SESSION, {"id": 2})

    assert len(response.buttons) == 2
    assert len(response.side_effects) == 2


def test_response_with_empty_metadata():
    """Test response with empty metadata."""
    response = ModuleResponse(text="Test")
    assert response.metadata == {}

    # Should be able to add to it
    response.metadata["key"] = "value"
    assert response.metadata["key"] == "value"


def test_response_with_none_values():
    """Test response with explicitly None values."""
    response = ModuleResponse(
        text="Test",
        buttons=None,
        next_state=None,
        side_effects=None,
    )

    assert response.buttons is None
    assert response.next_state is None
    assert response.side_effects is None


def test_complex_response_scenario():
    """Test a complex response scenario."""
    response = ModuleResponse(
        text="Task saved! What would you like to do next?",
        next_state="awaiting_next_action",
    )

    # Add buttons
    response.add_button("Add another task", "task.add_another")
    response.add_button("View all tasks", "task.view_all")
    response.add_button("Done for now", "task.done")

    # Add side effects
    response.add_side_effect(SideEffectType.SAVE_TASK, {
        "title": "Complete project",
        "priority": 1,
    })
    response.add_side_effect(SideEffectType.UPDATE_SESSION, {
        "last_action": "task_created",
    })

    # Add metadata
    response.metadata["task_count"] = 5
    response.metadata["module"] = "planning"

    # Verify
    assert len(response.buttons) == 3
    assert len(response.side_effects) == 2
    assert response.next_state == "awaiting_next_action"
    assert response.metadata["task_count"] == 5


def test_end_flow_with_side_effects():
    """Test that end_flow can still have side effects."""
    response = ModuleResponse.end_flow("Session complete!")

    response.add_side_effect(SideEffectType.END_SESSION, {"session_id": 123})

    assert response.is_end_of_flow is True
    assert len(response.side_effects) == 1


def test_transition_with_buttons():
    """Test that transition can have buttons."""
    buttons = [Button(text="Continue", callback_data="continue")]

    response = ModuleResponse.transition("Ready to continue?", "next_step")
    response.buttons = buttons

    assert response.next_state == "next_step"
    assert len(response.buttons) == 1
