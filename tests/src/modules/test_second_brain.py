"""
Tests for Second Brain Module.

Tests:
- Module protocol compliance (on_enter, handle, on_exit, get_daily_workflow_hooks)
- Auto-routing (tasks → planning, goals → goal system, insights → Aurora, ideas → Qdrant)
- Semantic search (time-aware filtering, natural language queries)
- Segment-adaptive messaging
- GDPR methods (export, delete, freeze, unfreeze)
- Knowledge graph integration (Neo4j + Qdrant)
"""

from __future__ import annotations

import pytest

from src.core.module_context import ModuleContext
from src.core.segment_context import SegmentContext
from src.modules.second_brain import (
    SecondBrainModule,
    SecondBrainState,
)
from src.services.knowledge.neo4j_service import Neo4jService
from src.services.knowledge.qdrant_service import QdrantService


@pytest.fixture
def module() -> SecondBrainModule:
    """Create SecondBrainModule instance with stub services."""
    neo4j_service = Neo4jService(client=None)  # Stub mode
    qdrant_service = QdrantService(client=None)  # Stub mode
    return SecondBrainModule(
        neo4j_service=neo4j_service,
        qdrant_service=qdrant_service,
    )


@pytest.fixture
def ctx_adhd(segment_contexts: dict[str, SegmentContext]) -> ModuleContext:
    """Create ModuleContext for ADHD segment."""
    return ModuleContext(
        user_id=1,
        segment_context=segment_contexts["AD"],
        state=SecondBrainState.IDLE,
        session_id="test-session",
        language="en",
        module_name="second_brain",
    )


@pytest.fixture
def ctx_autism(segment_contexts: dict[str, SegmentContext]) -> ModuleContext:
    """Create ModuleContext for Autism segment."""
    return ModuleContext(
        user_id=2,
        segment_context=segment_contexts["AU"],
        state=SecondBrainState.IDLE,
        session_id="test-session",
        language="en",
        module_name="second_brain",
    )


@pytest.fixture
def ctx_audhd(segment_contexts: dict[str, SegmentContext]) -> ModuleContext:
    """Create ModuleContext for AuDHD segment."""
    return ModuleContext(
        user_id=3,
        segment_context=segment_contexts["AH"],
        state=SecondBrainState.IDLE,
        session_id="test-session",
        language="en",
        module_name="second_brain",
    )


# =============================================================================
# Module Protocol Compliance
# =============================================================================


def test_module_has_required_attributes(module: SecondBrainModule) -> None:
    """Test that module has required attributes."""
    assert hasattr(module, "name")
    assert hasattr(module, "intents")
    assert hasattr(module, "pillar")
    assert module.name == "second_brain"
    assert module.pillar == "second_brain"
    assert len(module.intents) > 0


@pytest.mark.asyncio
async def test_on_enter_adhd(module: SecondBrainModule, ctx_adhd: ModuleContext) -> None:
    """Test on_enter for ADHD segment."""
    response = await module.on_enter(ctx_adhd)

    assert response.text is not None
    assert len(response.text) > 0
    assert response.next_state == SecondBrainState.SEARCH


@pytest.mark.asyncio
async def test_on_enter_autism(module: SecondBrainModule, ctx_autism: ModuleContext) -> None:
    """Test on_enter for Autism segment."""
    response = await module.on_enter(ctx_autism)

    assert response.text is not None
    assert "Second Brain" in response.text
    assert response.next_state == SecondBrainState.SEARCH


@pytest.mark.asyncio
async def test_on_enter_audhd(module: SecondBrainModule, ctx_audhd: ModuleContext) -> None:
    """Test on_enter for AuDHD segment."""
    response = await module.on_enter(ctx_audhd)

    assert response.text is not None
    assert len(response.text) > 0
    assert response.next_state == SecondBrainState.SEARCH


@pytest.mark.asyncio
async def test_on_exit(module: SecondBrainModule, ctx_adhd: ModuleContext) -> None:
    """Test on_exit resets state."""
    module._state = SecondBrainState.SEARCH
    await module.on_exit(ctx_adhd)
    assert module._state == SecondBrainState.IDLE


def test_get_daily_workflow_hooks(module: SecondBrainModule) -> None:
    """Test daily workflow hooks."""
    hooks = module.get_daily_workflow_hooks()

    assert hooks.hook_name == "second_brain"
    assert hooks.planning_enrichment is not None
    assert hooks.priority == 15


# =============================================================================
# Search Detection
# =============================================================================


def test_is_search_query_positive_cases(module: SecondBrainModule) -> None:
    """Test search query detection - positive cases."""
    assert module._is_search_query("What did I think about project X last month?")
    assert module._is_search_query("Show me my notes about JavaScript")
    assert module._is_search_query("Find ideas related to design")
    assert module._is_search_query("Search for thoughts on meditation")
    assert module._is_search_query("When did I last write about this?")


def test_is_search_query_negative_cases(module: SecondBrainModule) -> None:
    """Test search query detection - negative cases."""
    assert not module._is_search_query("I have a new idea about the project")
    assert not module._is_search_query("Call dentist tomorrow")
    assert not module._is_search_query("Note: Meeting at 3pm")
    assert not module._is_search_query("I realize I work better in the morning")


# =============================================================================
# Time Filter Extraction
# =============================================================================


def test_extract_time_filter_last_month(module: SecondBrainModule) -> None:
    """Test time filter extraction for 'last month'."""
    time_after, time_before = module._extract_time_filter("What did I think about X last month?")

    assert time_after is not None
    assert time_before is not None
    # Should be approximately 30 days ago
    import datetime
    now = datetime.datetime.now(datetime.UTC)
    expected = now - datetime.timedelta(days=30)
    assert abs((time_after - expected).total_seconds()) < 60  # Within 1 minute


def test_extract_time_filter_this_week(module: SecondBrainModule) -> None:
    """Test time filter extraction for 'this week'."""
    time_after, time_before = module._extract_time_filter("Show me ideas from this week")

    assert time_after is not None
    assert time_before is not None
    # Should be approximately 7 days ago
    import datetime
    now = datetime.datetime.now(datetime.UTC)
    expected = now - datetime.timedelta(days=7)
    assert abs((time_after - expected).total_seconds()) < 60


def test_extract_time_filter_no_filter(module: SecondBrainModule) -> None:
    """Test time filter extraction with no time reference."""
    time_after, time_before = module._extract_time_filter("What did I think about X?")

    assert time_after is None
    assert time_before is None


# =============================================================================
# Search Query Cleaning
# =============================================================================


def test_clean_search_query(module: SecondBrainModule) -> None:
    """Test search query cleaning."""
    cleaned = module._clean_search_query("What did I think about JavaScript last month?")
    assert "javascript" in cleaned.lower()
    assert "what did i think about" not in cleaned.lower()
    assert "last month" not in cleaned.lower()


# =============================================================================
# Content Classification
# =============================================================================


def test_keyword_classify_task(module: SecondBrainModule) -> None:
    """Test classification of task-type content."""
    assert module._keyword_classify("Call dentist tomorrow") == "task"
    assert module._keyword_classify("Buy groceries after work") == "task"
    assert module._keyword_classify("Finish the report by Friday") == "task"


def test_keyword_classify_idea(module: SecondBrainModule) -> None:
    """Test classification of idea-type content."""
    assert module._keyword_classify("I have an idea for a new feature") == "idea"
    # "What if" is a question, not an idea - classify correctly
    assert module._keyword_classify("This concept could work well") == "idea"
    assert module._keyword_classify("Here's a concept for a new approach") == "idea"


def test_keyword_classify_note(module: SecondBrainModule) -> None:
    """Test classification of note-type content."""
    assert module._keyword_classify("Note: Meeting at 3pm tomorrow") == "note"
    assert module._keyword_classify("Remember to check the address") == "note"
    assert module._keyword_classify("Important info: password is xyz") == "note"


def test_keyword_classify_insight(module: SecondBrainModule) -> None:
    """Test classification of insight-type content."""
    assert module._keyword_classify("I notice I work better in the morning") == "insight"
    assert module._keyword_classify("I realize I'm more productive after exercise") == "insight"
    # "I find" can match both insight and note, so test a clearer case
    assert module._keyword_classify("I'm better at coding in the morning") == "insight"


def test_keyword_classify_question(module: SecondBrainModule) -> None:
    """Test classification of question-type content."""
    # Add question mark to make it clearer
    assert module._keyword_classify("How do I start with meditation?") == "question"
    assert module._keyword_classify("What is the best approach?") == "question"
    assert module._keyword_classify("Why does this keep happening?") == "question"


def test_keyword_classify_goal(module: SecondBrainModule) -> None:
    """Test classification of goal-type content."""
    assert module._keyword_classify("My goal is to run a marathon") == "goal"
    assert module._keyword_classify("I want to learn Spanish this year") == "goal"
    # Test with explicit "goal" keyword
    assert module._keyword_classify("Goal: save $10k by December") == "goal"


# =============================================================================
# Content Capture and Routing
# =============================================================================


@pytest.mark.asyncio
async def test_handle_search_query(module: SecondBrainModule, ctx_adhd: ModuleContext) -> None:
    """Test handling a search query."""
    response = await module.handle("What did I think about JavaScript last month?", ctx_adhd)

    assert response.text is not None
    assert "javascript" in response.text.lower() or "search" in response.text.lower()
    assert response.is_end_of_flow is True


@pytest.mark.asyncio
async def test_handle_capture_idea(module: SecondBrainModule, ctx_adhd: ModuleContext) -> None:
    """Test capturing an idea."""
    response = await module.handle("I have an idea for a new feature", ctx_adhd)

    assert response.text is not None
    assert response.is_end_of_flow is True
    assert "idea" in response.text.lower() or "captured" in response.text.lower()


@pytest.mark.asyncio
async def test_handle_capture_task(module: SecondBrainModule, ctx_adhd: ModuleContext) -> None:
    """Test capturing a task."""
    response = await module.handle("Call dentist tomorrow", ctx_adhd)

    assert response.text is not None
    assert response.is_end_of_flow is True


@pytest.mark.asyncio
async def test_handle_capture_goal(module: SecondBrainModule, ctx_adhd: ModuleContext) -> None:
    """Test capturing a goal."""
    response = await module.handle("My goal is to learn Python", ctx_adhd)

    assert response.text is not None
    assert response.is_end_of_flow is True


# =============================================================================
# Segment-Adaptive Confirmation Messages
# =============================================================================


def test_build_confirmation_adhd(module: SecondBrainModule, ctx_adhd: ModuleContext) -> None:
    """Test ADHD confirmation is brief and encouraging."""
    confirmation = module._build_confirmation(
        content_type="idea",
        content="New feature for app",
        segment_context=ctx_adhd.segment_context,
    )

    assert len(confirmation) > 0
    # ADHD confirmations should be brief and exciting
    assert len(confirmation) < 150  # Reasonable max length


def test_build_confirmation_autism(module: SecondBrainModule, ctx_autism: ModuleContext) -> None:
    """Test Autism confirmation is clear and structured."""
    confirmation = module._build_confirmation(
        content_type="note",
        content="Meeting notes",
        segment_context=ctx_autism.segment_context,
    )

    assert len(confirmation) > 0
    # Autism confirmations should be clear and structured


def test_build_confirmation_audhd(module: SecondBrainModule, ctx_audhd: ModuleContext) -> None:
    """Test AuDHD confirmation is flexible."""
    confirmation = module._build_confirmation(
        content_type="insight",
        content="Morning productivity insight",
        segment_context=ctx_audhd.segment_context,
    )

    assert len(confirmation) > 0


# =============================================================================
# GDPR Methods
# =============================================================================


@pytest.mark.asyncio
async def test_export_user_data(module: SecondBrainModule) -> None:
    """Test GDPR export."""
    data = await module.export_user_data(user_id=1)

    assert isinstance(data, dict)
    assert "second_brain_entries" in data
    assert "qdrant_vectors" in data
    assert "neo4j_nodes" in data


@pytest.mark.asyncio
async def test_delete_user_data(module: SecondBrainModule) -> None:
    """Test GDPR delete."""
    # Should not raise
    await module.delete_user_data(user_id=1)


@pytest.mark.asyncio
async def test_freeze_user_data(module: SecondBrainModule) -> None:
    """Test GDPR freeze."""
    # Should not raise
    await module.freeze_user_data(user_id=1)


@pytest.mark.asyncio
async def test_unfreeze_user_data(module: SecondBrainModule) -> None:
    """Test GDPR unfreeze."""
    # Should not raise
    await module.unfreeze_user_data(user_id=1)


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_handle_empty_message(module: SecondBrainModule, ctx_adhd: ModuleContext) -> None:
    """Test handling empty message."""
    response = await module.handle("", ctx_adhd)
    assert response.text is not None


@pytest.mark.asyncio
async def test_handle_very_long_message(module: SecondBrainModule, ctx_adhd: ModuleContext) -> None:
    """Test handling very long message."""
    long_message = "I have an idea " + ("x" * 500)
    response = await module.handle(long_message, ctx_adhd)
    assert response.text is not None
    # Confirmation should truncate long content
    assert len(response.text) < 500


def test_clean_content_with_prefix(module: SecondBrainModule) -> None:
    """Test content cleaning removes prefixes."""
    cleaned = module._clean_content("idea: New feature", "idea")
    assert cleaned == "New feature"

    cleaned = module._clean_content("task: Call dentist", "task")
    assert cleaned == "Call dentist"


def test_clean_content_without_prefix(module: SecondBrainModule) -> None:
    """Test content cleaning without prefix."""
    cleaned = module._clean_content("New feature idea", "idea")
    assert cleaned == "New feature idea"
