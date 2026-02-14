"""
Comprehensive tests for the EnergySystem (segment-specific energy management).

Tests cover:
- EnergyState (RED/YELLOW/GREEN levels, properties)
- IBNSResult (ADHD: Interest-Based Need State)
- ICNUResult (AuDHD: Interest, Challenge, Novelty, Urgency)
- SpoonDrawer (AuDHD: 6 resource pools, exponential masking cost)
- SensoryCognitiveLoad (Autism: sensory accumulation, overload detection)
- EnergySystem.get_energy_state (simple energy state)
- EnergySystem.update_energy_state (level and score updates)
- EnergySystem.calculate_ibns (ADHD task matching)
- EnergySystem.calculate_icnu (AuDHD task matching with integrity trigger)
- EnergySystem.calculate_spoon_drawer (AuDHD resource tracking)
- EnergySystem.update_spoon_drawer (pool updates, bounds checking)
- EnergySystem.spend_spoons (task-specific spoon costs, exponential masking)
- EnergySystem.get_sensory_cognitive_load (Autism sensory/cognitive tracking)
- EnergySystem.update_sensory_cognitive_load (accumulation, overload risk)
- EnergySystem.can_attempt_task (energy gating by segment)
- EnergySystem.get_energy_recommendation (segment-appropriate energy data)
- Singleton access (get_energy_system, get_user_energy_state, can_user_attempt_task)
- Segment-specific logic (IBNS for AD, ICNU+Spoons for AH, Sensory for AU, simple for NT)

Data Classification: SENSITIVE (energy states contain personal data)

Reference: ARCHITECTURE.md Section 3 (Neurotype Segmentation)
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.core.segment_context import SegmentContext
from src.models.task import Task
from src.services.energy_system import (
    EnergyState,
    EnergyStateEnum,
    EnergySystem,
    IBNSResult,
    ICNUResult,
    SensoryCognitiveLoad,
    SpoonDrawer,
    can_user_attempt_task,
    get_energy_system,
    get_user_energy_state,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def energy_system():
    """Create a fresh EnergySystem instance."""
    return EnergySystem()


@pytest.fixture
def adhd_context():
    """ADHD segment context."""
    return SegmentContext.from_code("AD")


@pytest.fixture
def autism_context():
    """Autism segment context."""
    return SegmentContext.from_code("AU")


@pytest.fixture
def audhd_context():
    """AuDHD segment context."""
    return SegmentContext.from_code("AH")


@pytest.fixture
def nt_context():
    """Neurotypical segment context."""
    return SegmentContext.from_code("NT")


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    task = MagicMock(spec=Task)
    task.title = "Write documentation"
    task.priority = 3
    task.created_at = datetime.now(UTC)
    task.committed_date = date.today() + timedelta(days=3)
    return task


@pytest.fixture
def urgent_task():
    """Create an urgent task (high priority, due soon)."""
    task = MagicMock(spec=Task)
    task.title = "Fix critical bug"
    task.priority = 1
    task.created_at = datetime.now(UTC) - timedelta(hours=1)
    task.committed_date = date.today()
    return task


@pytest.fixture
def integrity_task():
    """Create a task with integrity trigger keywords."""
    task = MagicMock(spec=Task)
    task.title = "Align with core values and purpose"
    task.priority = 3
    task.created_at = datetime.now(UTC)
    task.committed_date = date.today() + timedelta(days=7)
    return task


@pytest.fixture
def social_task():
    """Create a social task for spoon testing."""
    task = MagicMock(spec=Task)
    task.title = "Call friend for social meet"
    task.priority = 3
    task.created_at = datetime.now(UTC)
    task.committed_date = date.today() + timedelta(days=2)
    return task


# =============================================================================
# EnergyState Tests
# =============================================================================


def test_energy_state_properties():
    """Test EnergyState property calculations."""
    red_state = EnergyState(level=EnergyStateEnum.RED, score=0.2, user_id=1)
    assert red_state.is_low_energy is True
    assert red_state.can_attempt_demanding_task is False

    yellow_state = EnergyState(level=EnergyStateEnum.YELLOW, score=0.5, user_id=1)
    assert yellow_state.is_low_energy is False
    assert yellow_state.can_attempt_demanding_task is False

    green_state = EnergyState(level=EnergyStateEnum.GREEN, score=0.9, user_id=1)
    assert green_state.is_low_energy is False
    assert green_state.can_attempt_demanding_task is True


def test_energy_state_to_dict():
    """Test EnergyState serialization."""
    state = EnergyState(level=EnergyStateEnum.GREEN, score=0.8, user_id=42)
    result = state.to_dict()

    assert result["user_id"] == 42
    assert result["level"] == "GREEN"
    assert result["score"] == 0.8


# =============================================================================
# SpoonDrawer Tests
# =============================================================================


def test_spoon_drawer_total_spoons():
    """Test SpoonDrawer total spoon calculation."""
    drawer = SpoonDrawer(social=10, sensory=8, ef=6, emotional=9, physical=7, masking=5)
    assert drawer.total_spoons == 45


def test_spoon_drawer_is_depleted():
    """Test SpoonDrawer depletion detection."""
    full = SpoonDrawer(social=10, sensory=10, ef=10, emotional=10, physical=10, masking=10)
    assert full.is_depleted is False

    depleted = SpoonDrawer(social=10, sensory=2, ef=10, emotional=10, physical=10, masking=10)
    assert depleted.is_depleted is True


def test_spoon_drawer_masking_cost_multiplier():
    """Test SpoonDrawer exponential masking cost for AuDHD."""
    low_masking = SpoonDrawer(social=10, sensory=10, ef=10, emotional=10, physical=10, masking=2)
    high_masking = SpoonDrawer(social=10, sensory=10, ef=10, emotional=10, physical=10, masking=8)

    # Higher masking spoons = higher cost multiplier (exponential)
    assert low_masking.masking_cost_multiplier < high_masking.masking_cost_multiplier
    assert high_masking.masking_cost_multiplier > 2.0


def test_spoon_drawer_to_dict():
    """Test SpoonDrawer serialization."""
    drawer = SpoonDrawer(social=10, sensory=8, ef=6, emotional=9, physical=7, masking=5)
    result = drawer.to_dict()

    assert result["social"] == 10
    assert result["sensory"] == 8
    assert result["ef"] == 6
    assert result["emotional"] == 9
    assert result["physical"] == 7
    assert result["masking"] == 5
    assert result["total_spoons"] == 45
    assert "is_depleted" in result
    assert "masking_cost_multiplier" in result


# =============================================================================
# SensoryCognitiveLoad Tests
# =============================================================================


def test_sensory_cognitive_load_is_overloaded():
    """Test SensoryCognitiveLoad overload detection."""
    low_load = SensoryCognitiveLoad(sensory_load=3.0, cognitive_load=4.0, sensory_accumulated=2.0, overload_risk=0.3)
    assert low_load.is_overloaded is False

    high_sensory = SensoryCognitiveLoad(sensory_load=8.0, cognitive_load=4.0, sensory_accumulated=6.0, overload_risk=0.7)
    assert high_sensory.is_overloaded is True

    high_cognitive = SensoryCognitiveLoad(sensory_load=4.0, cognitive_load=9.0, sensory_accumulated=3.0, overload_risk=0.8)
    assert high_cognitive.is_overloaded is True


def test_sensory_cognitive_load_needs_break():
    """Test SensoryCognitiveLoad break detection."""
    moderate = SensoryCognitiveLoad(sensory_load=6.0, cognitive_load=5.0, sensory_accumulated=4.0, overload_risk=0.5)
    assert moderate.needs_break is False

    critical = SensoryCognitiveLoad(sensory_load=9.0, cognitive_load=7.0, sensory_accumulated=8.0, overload_risk=0.9)
    assert critical.needs_break is True


def test_sensory_cognitive_load_to_dict():
    """Test SensoryCognitiveLoad serialization."""
    load = SensoryCognitiveLoad(sensory_load=7.0, cognitive_load=5.0, sensory_accumulated=6.0, overload_risk=0.7)
    result = load.to_dict()

    assert result["sensory_load"] == 7.0
    assert result["cognitive_load"] == 5.0
    assert result["sensory_accumulated"] == 6.0
    assert result["overload_risk"] == 0.7
    assert "is_overloaded" in result
    assert "needs_break" in result


# =============================================================================
# EnergySystem - Basic Energy State Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_energy_state_default(energy_system):
    """Test getting default energy state for new user."""
    state = await energy_system.get_energy_state(user_id=1)

    assert state.level == EnergyStateEnum.YELLOW
    assert state.score == 0.5
    assert state.user_id == 1


@pytest.mark.asyncio
async def test_update_energy_state_explicit_level(energy_system):
    """Test updating energy state with explicit level."""
    state = await energy_system.update_energy_state(user_id=1, level=EnergyStateEnum.GREEN, score=0.8)

    assert state.level == EnergyStateEnum.GREEN
    assert state.score == 0.8


@pytest.mark.asyncio
async def test_update_energy_state_auto_level_from_score(energy_system):
    """Test auto-determining level from score."""
    # High score → GREEN
    state1 = await energy_system.update_energy_state(user_id=1, score=0.9)
    assert state1.level == EnergyStateEnum.GREEN

    # Medium score → YELLOW
    state2 = await energy_system.update_energy_state(user_id=2, score=0.5)
    assert state2.level == EnergyStateEnum.YELLOW

    # Low score → RED
    state3 = await energy_system.update_energy_state(user_id=3, score=0.1)
    assert state3.level == EnergyStateEnum.RED


@pytest.mark.asyncio
async def test_update_energy_state_bounds_clamping(energy_system):
    """Test score clamping to [0.0, 1.0]."""
    # Above 1.0
    state1 = await energy_system.update_energy_state(user_id=1, score=1.5)
    assert state1.score == 1.0

    # Below 0.0
    state2 = await energy_system.update_energy_state(user_id=2, score=-0.5)
    assert state2.score == 0.0


# =============================================================================
# IBNS Tests (ADHD)
# =============================================================================


@pytest.mark.asyncio
async def test_calculate_ibns_high_interest_task(energy_system, urgent_task):
    """Test IBNS calculation for high-interest task."""
    result = await energy_system.calculate_ibns(user_id=1, task=urgent_task)

    assert isinstance(result, IBNSResult)
    assert 0.0 <= result.total_score <= 1.0
    assert result.interest > 0.5  # High priority = high interest
    assert result.urgency > 0.5   # Due today = high urgency
    assert result.recommendation in ["highly_recommended", "recommended", "neutral", "discouraged"]


@pytest.mark.asyncio
async def test_calculate_ibns_recommendation_thresholds(energy_system, sample_task):
    """Test IBNS recommendation thresholds."""
    result = await energy_system.calculate_ibns(user_id=1, task=sample_task)

    # Check that recommendation matches score thresholds
    if result.total_score >= 0.75:
        assert result.recommendation == "highly_recommended"
    elif result.total_score >= 0.5:
        assert result.recommendation == "recommended"
    elif result.total_score >= 0.25:
        assert result.recommendation == "neutral"
    else:
        assert result.recommendation == "discouraged"


@pytest.mark.asyncio
async def test_calculate_ibns_interest_score(energy_system):
    """Test IBNS interest score calculation."""
    # High priority = high interest
    task_high = MagicMock(spec=Task)
    task_high.title = "learn new exciting framework"
    task_high.priority = 1
    task_high.created_at = datetime.now(UTC)
    task_high.committed_date = date.today() + timedelta(days=3)

    result = await energy_system.calculate_ibns(user_id=1, task=task_high)
    assert result.interest > 0.8  # High priority + interest keywords


@pytest.mark.asyncio
async def test_calculate_ibns_novelty_score(energy_system):
    """Test IBNS novelty score based on task age."""
    # New task = high novelty
    new_task = MagicMock(spec=Task)
    new_task.title = "New task"
    new_task.priority = 3
    new_task.created_at = datetime.now(UTC)
    new_task.committed_date = date.today() + timedelta(days=3)

    result_new = await energy_system.calculate_ibns(user_id=1, task=new_task)
    assert result_new.novelty >= 0.7

    # Old task = low novelty
    old_task = MagicMock(spec=Task)
    old_task.title = "Old task"
    old_task.priority = 3
    old_task.created_at = datetime.now(UTC) - timedelta(days=60)
    old_task.committed_date = date.today() + timedelta(days=3)

    result_old = await energy_system.calculate_ibns(user_id=1, task=old_task)
    assert result_old.novelty < 0.5


@pytest.mark.asyncio
async def test_calculate_ibns_urgency_score(energy_system):
    """Test IBNS urgency score based on committed date."""
    # Overdue = max urgency
    overdue_task = MagicMock(spec=Task)
    overdue_task.title = "Overdue task"
    overdue_task.priority = 3
    overdue_task.created_at = datetime.now(UTC)
    overdue_task.committed_date = date.today() - timedelta(days=1)

    result_overdue = await energy_system.calculate_ibns(user_id=1, task=overdue_task)
    assert result_overdue.urgency >= 0.9

    # Far future = low urgency
    future_task = MagicMock(spec=Task)
    future_task.title = "Future task"
    future_task.priority = 3
    future_task.created_at = datetime.now(UTC)
    future_task.committed_date = date.today() + timedelta(days=30)

    result_future = await energy_system.calculate_ibns(user_id=1, task=future_task)
    assert result_future.urgency < 0.3


# =============================================================================
# ICNU Tests (AuDHD)
# =============================================================================


@pytest.mark.asyncio
async def test_calculate_icnu_basic(energy_system, sample_task):
    """Test ICNU calculation for AuDHD."""
    result = await energy_system.calculate_icnu(user_id=1, task=sample_task)

    assert isinstance(result, ICNUResult)
    assert 0.0 <= result.total_score <= 1.0
    assert hasattr(result, "integrity_trigger")
    assert result.recommendation in ["highly_recommended", "recommended", "neutral", "discouraged"]


@pytest.mark.asyncio
async def test_calculate_icnu_integrity_trigger(energy_system, integrity_task):
    """Test ICNU integrity trigger detection."""
    result = await energy_system.calculate_icnu(user_id=1, task=integrity_task)

    # Task with "values", "purpose" keywords should trigger integrity
    assert result.integrity_trigger is True
    # Integrity trigger boosts total score
    assert result.total_score >= 0.2


@pytest.mark.asyncio
async def test_calculate_icnu_no_integrity_trigger(energy_system, sample_task):
    """Test ICNU without integrity trigger."""
    result = await energy_system.calculate_icnu(user_id=1, task=sample_task)

    # Normal task should not trigger integrity
    assert result.integrity_trigger is False


# =============================================================================
# SpoonDrawer Tests (AuDHD)
# =============================================================================


@pytest.mark.asyncio
async def test_calculate_spoon_drawer_default(energy_system):
    """Test default spoon drawer initialization."""
    drawer = await energy_system.calculate_spoon_drawer(user_id=1)

    assert drawer.social == 10
    assert drawer.sensory == 10
    assert drawer.ef == 10
    assert drawer.emotional == 10
    assert drawer.physical == 10
    assert drawer.masking == 10


@pytest.mark.asyncio
async def test_update_spoon_drawer_single_pool(energy_system):
    """Test updating a single spoon pool."""
    drawer = await energy_system.update_spoon_drawer(user_id=1, social=5)

    assert drawer.social == 5
    assert drawer.sensory == 10  # Unchanged
    assert drawer.ef == 10        # Unchanged


@pytest.mark.asyncio
async def test_update_spoon_drawer_bounds_clamping(energy_system):
    """Test spoon drawer bounds clamping [0, 10]."""
    # Above 10
    drawer1 = await energy_system.update_spoon_drawer(user_id=1, social=15)
    assert drawer1.social == 10

    # Below 0
    drawer2 = await energy_system.update_spoon_drawer(user_id=2, ef=-5)
    assert drawer2.ef == 0


@pytest.mark.asyncio
async def test_spend_spoons_social_task(energy_system, social_task):
    """Test spending spoons on a social task."""
    # Initialize with full spoons
    await energy_system.update_spoon_drawer(user_id=1, social=10, masking=10)

    # Spend spoons on social task
    result = await energy_system.spend_spoons(user_id=1, task=social_task)

    # Social tasks cost social and masking spoons
    assert result.social < 10
    assert result.masking < 10


@pytest.mark.asyncio
async def test_spend_spoons_exponential_masking_cost(energy_system, social_task):
    """Test exponential masking cost for AuDHD."""
    # High masking spoons → higher masking cost multiplier
    await energy_system.update_spoon_drawer(user_id=1, masking=8)
    result_high = await energy_system.spend_spoons(user_id=1, task=social_task)
    masking_spent_high = 8 - result_high.masking

    # Low masking spoons → lower masking cost multiplier
    await energy_system.update_spoon_drawer(user_id=2, masking=2)
    result_low = await energy_system.spend_spoons(user_id=2, task=social_task)
    masking_spent_low = 2 - result_low.masking

    # Exponential cost means high-masking users spend MORE per task
    assert masking_spent_high >= masking_spent_low


# =============================================================================
# Sensory/Cognitive Load Tests (Autism)
# =============================================================================


@pytest.mark.asyncio
async def test_get_sensory_cognitive_load_default(energy_system):
    """Test default sensory/cognitive load initialization."""
    load = await energy_system.get_sensory_cognitive_load(user_id=1)

    assert load.sensory_load == 0.0
    assert load.cognitive_load == 0.0
    assert load.sensory_accumulated == 0.0
    assert load.overload_risk == 0.0


@pytest.mark.asyncio
async def test_update_sensory_cognitive_load_accumulation(energy_system):
    """Test sensory load ACCUMULATION (does not habituate)."""
    # Add sensory load
    load1 = await energy_system.update_sensory_cognitive_load(user_id=1, sensory=3.0)
    assert load1.sensory_load == 3.0

    # Add more sensory load (accumulates)
    load2 = await energy_system.update_sensory_cognitive_load(user_id=1, sensory=4.0)
    assert load2.sensory_load == 7.0  # 3.0 + 4.0


@pytest.mark.asyncio
async def test_update_sensory_cognitive_load_cognitive_replacement(energy_system):
    """Test cognitive load REPLACEMENT (not cumulative like sensory)."""
    # Set cognitive load
    load1 = await energy_system.update_sensory_cognitive_load(user_id=1, cognitive=5.0)
    assert load1.cognitive_load == 5.0

    # Update cognitive load (replaces, not adds)
    load2 = await energy_system.update_sensory_cognitive_load(user_id=1, cognitive=7.0)
    assert load2.cognitive_load == 7.0  # Replaced, not 5.0 + 7.0


@pytest.mark.asyncio
async def test_update_sensory_cognitive_load_overload_risk(energy_system):
    """Test overload risk calculation."""
    # High sensory load
    load = await energy_system.update_sensory_cognitive_load(user_id=1, sensory=8.0, cognitive=3.0)
    assert load.overload_risk > 0.5


# =============================================================================
# Energy Gating Tests (can_attempt_task)
# =============================================================================


@pytest.mark.asyncio
async def test_can_attempt_task_green_state_allows_all(energy_system, sample_task, adhd_context):
    """Test GREEN state allows all tasks."""
    await energy_system.update_energy_state(user_id=1, level=EnergyStateEnum.GREEN)

    can_proceed = await energy_system.can_attempt_task(user_id=1, task=sample_task, segment_context=adhd_context)
    assert can_proceed is True


@pytest.mark.asyncio
async def test_can_attempt_task_red_state_blocks_non_essential(energy_system, sample_task, adhd_context):
    """Test RED state blocks non-essential tasks."""
    await energy_system.update_energy_state(user_id=1, level=EnergyStateEnum.RED)

    # Non-essential task (priority 3) should be blocked
    can_proceed = await energy_system.can_attempt_task(user_id=1, task=sample_task, segment_context=adhd_context)
    assert can_proceed is False


@pytest.mark.asyncio
async def test_can_attempt_task_red_state_allows_essential(energy_system, urgent_task, adhd_context):
    """Test RED state allows essential tasks (high priority)."""
    await energy_system.update_energy_state(user_id=1, level=EnergyStateEnum.RED)

    # Essential task (priority 1) should be allowed
    can_proceed = await energy_system.can_attempt_task(user_id=1, task=urgent_task, segment_context=adhd_context)
    assert can_proceed is True


@pytest.mark.asyncio
async def test_can_attempt_task_integrity_override(energy_system, integrity_task, audhd_context):
    """Test integrity trigger overrides RED state for AuDHD."""
    await energy_system.update_energy_state(user_id=1, level=EnergyStateEnum.RED)

    # Integrity task should override RED state
    can_proceed = await energy_system.can_attempt_task(user_id=1, task=integrity_task, segment_context=audhd_context)
    assert can_proceed is True


@pytest.mark.asyncio
async def test_can_attempt_task_spoon_depletion_blocks(energy_system, social_task, audhd_context):
    """Test depleted spoon pool blocks related tasks."""
    await energy_system.update_energy_state(user_id=1, level=EnergyStateEnum.GREEN)
    await energy_system.update_spoon_drawer(user_id=1, social=1, sensory=10, ef=10, emotional=10, physical=10, masking=10)

    # Social task should be blocked due to low social spoons
    can_proceed = await energy_system.can_attempt_task(user_id=1, task=social_task, segment_context=audhd_context)
    assert can_proceed is False


@pytest.mark.asyncio
async def test_can_attempt_task_sensory_overload_blocks(energy_system, sample_task, autism_context):
    """Test sensory overload blocks tasks for Autism."""
    await energy_system.update_energy_state(user_id=1, level=EnergyStateEnum.GREEN)
    await energy_system.update_sensory_cognitive_load(user_id=1, sensory=9.0, cognitive=3.0)

    # Task should be blocked due to sensory overload
    can_proceed = await energy_system.can_attempt_task(user_id=1, task=sample_task, segment_context=autism_context)
    assert can_proceed is False


# =============================================================================
# Energy Recommendation Tests (segment-specific)
# =============================================================================


@pytest.mark.asyncio
async def test_get_energy_recommendation_adhd_includes_ibns(energy_system, adhd_context, sample_task):
    """Test ADHD recommendation includes IBNS."""
    rec = await energy_system.get_energy_recommendation(user_id=1, segment_context=adhd_context, task=sample_task)

    assert rec["segment"] == "AD"
    assert "energy_state" in rec
    assert "ibns" in rec
    assert rec["ibns"]["total_score"] >= 0.0


@pytest.mark.asyncio
async def test_get_energy_recommendation_audhd_includes_icnu_and_spoons(energy_system, audhd_context, sample_task):
    """Test AuDHD recommendation includes ICNU and Spoon-Drawer."""
    rec = await energy_system.get_energy_recommendation(user_id=1, segment_context=audhd_context, task=sample_task)

    assert rec["segment"] == "AH"
    assert "energy_state" in rec
    assert "icnu" in rec
    assert "spoon_drawer" in rec
    assert rec["icnu"]["integrity_trigger"] in [True, False]


@pytest.mark.asyncio
async def test_get_energy_recommendation_autism_includes_sensory(energy_system, autism_context):
    """Test Autism recommendation includes Sensory-Cognitive load."""
    rec = await energy_system.get_energy_recommendation(user_id=1, segment_context=autism_context)

    assert rec["segment"] == "AU"
    assert "energy_state" in rec
    assert "sensory_cognitive" in rec


@pytest.mark.asyncio
async def test_get_energy_recommendation_includes_gating(energy_system, adhd_context, sample_task):
    """Test recommendation includes gating decision when task provided."""
    rec = await energy_system.get_energy_recommendation(user_id=1, segment_context=adhd_context, task=sample_task)

    assert "can_attempt" in rec
    assert isinstance(rec["can_attempt"], bool)


# =============================================================================
# Singleton Access Tests
# =============================================================================


def test_get_energy_system_singleton():
    """Test get_energy_system returns singleton instance."""
    system1 = get_energy_system()
    system2 = get_energy_system()
    assert system1 is system2


@pytest.mark.asyncio
async def test_get_user_energy_state_convenience():
    """Test get_user_energy_state convenience function."""
    state = await get_user_energy_state(user_id=1)
    assert isinstance(state, EnergyState)


@pytest.mark.asyncio
async def test_can_user_attempt_task_convenience(sample_task, adhd_context):
    """Test can_user_attempt_task convenience function."""
    result = await can_user_attempt_task(user_id=1, task=sample_task, segment_context=adhd_context)
    assert isinstance(result, bool)
