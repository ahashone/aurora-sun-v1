"""
Energy System for Aurora Sun V1.

Unified energy management across segments:
- ADHD: IBNS/PINCH (Interest-Based Need State)
- AuDHD: ICNU + Integrity Trigger + Spoon-Drawer
- Autism: Sensory + Cognitive load
- Neurotypical: Simple RED/YELLOW/GREEN

Data Classification: SENSITIVE (energy states contain personal data)

Reference: ARCHITECTURE.md Section 3 (Neurotype Segmentation)
Reference: ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from enum import StrEnum
from typing import Any, Literal

from src.core.segment_context import SegmentContext
from src.models.task import Task

# Energy state levels for simple RED/YELLOW/GREEN model
EnergyLevel = Literal["RED", "YELLOW", "GREEN"]


class EnergyStateEnum(StrEnum):
    """Simple energy state levels."""

    RED = "RED"      # Low energy - rest needed
    YELLOW = "YELLOW"  # Moderate energy - careful pacing
    GREEN = "GREEN"    # High energy - ready for action


@dataclass
class EnergyState:
    """
    Simple energy state (RED/YELLOW/GREEN) for ADHD/Neurotypical users.

    This is the baseline energy model. More complex models (IBNS, ICNU,
    Spoon-Drawer, Sensory-Cognitive) are calculated on top of this.
    """

    level: EnergyStateEnum
    score: float  # 0.0 to 1.0 (1 = full energy)
    user_id: int

    @property
    def is_low_energy(self) -> bool:
        """Check if energy is too low for non-essential tasks."""
        return self.level == EnergyStateEnum.RED

    @property
    def can_attempt_demanding_task(self) -> bool:
        """Check if user has enough energy for demanding tasks."""
        return self.level == EnergyStateEnum.GREEN

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "user_id": self.user_id,
            "level": self.level.value,
            "score": self.score,
        }


@dataclass
class IBNSResult:
    """
    Interest-Based Need State (IBNS) result for ADHD users.

    IBNS = Interest + Challenge + Novelty + Urgency
    Higher scores indicate higher task match for ADHD brain.
    """

    total_score: float  # 0.0 to 1.0 composite score
    interest: float     # Interest component (0-1)
    challenge: float    # Challenge component (0-1)
    novelty: float     # Novelty component (0-1)
    urgency: float      # Urgency component (0-1)
    recommendation: str  # "highly_recommended" | "recommended" | "neutral" | "discouraged"


@dataclass
class ICNUResult:
    """
    Interest, Challenge, Novelty, Urgency (ICNU) result for AuDHD users.

    Unlike ADHD's IBNS, this separates the components for finer control
    and includes Integrity Trigger detection.
    """

    interest: float          # Interest component (0-1)
    challenge: float         # Challenge component (0-1)
    novelty: float           # Novelty component (0-1)
    urgency: float           # Urgency component (0-1)
    total_score: float       # Composite score (0-1)
    integrity_trigger: bool  # Whether integrity is at risk
    recommendation: str     # "highly_recommended" | "recommended" | "neutral" | "discouraged"


@dataclass
class SpoonDrawer:
    """
    Spoon-Drawer model for AuDHD users.

    Tracks 6 resource pools. Each starts at 10 spoons (max).
    spoons represent available mental/physical resources.

    For AuDHD, masking is exponential (not linear) - each spoon
    used costs more than the last due to cumulative masking effort.
    """

    social: int      # 0-10 spoons: Social interaction capacity
    sensory: int    # 0-10 spoons: Sensory processing capacity
    ef: int         # 0-10 spoons: Executive function capacity
    emotional: int  # 0-10 spoons: Emotional regulation capacity
    physical: int   # 0-10 spoons: Physical energy capacity
    masking: int    # 0-10 spoons: Masking effort capacity (exponential cost for AuDHD)

    @property
    def total_spoons(self) -> int:
        """Total spoons across all pools."""
        return self.social + self.sensory + self.ef + self.emotional + self.physical + self.masking

    @property
    def is_depleted(self) -> bool:
        """Check if any pool is critically low."""
        return min(self.social, self.sensory, self.ef, self.emotional, self.physical, self.masking) <= 2

    @property
    def masking_cost_multiplier(self) -> float:
        """
        Calculate the exponential cost of masking for AuDHD.

        Returns a multiplier (1.0 to 3.0) representing how much
        more effort masking requires compared to baseline.
        """
        # Exponential curve: more masking used = exponentially harder
        if self.masking <= 0:
            return 1.0
        # Formula: 1.0 + (masking_spoons / 10) ^ 1.5 * 2.0
        return float(1.0 + pow(self.masking / 10, 1.5) * 2.0)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "social": self.social,
            "sensory": self.sensory,
            "ef": self.ef,
            "emotional": self.emotional,
            "physical": self.physical,
            "masking": self.masking,
            "total_spoons": self.total_spoons,
            "is_depleted": self.is_depleted,
            "masking_cost_multiplier": self.masking_cost_multiplier,
        }


@dataclass
class SensoryCognitiveLoad:
    """
    Sensory and Cognitive load for Autism users.

    Tracks sensory overwhelm and cognitive load separately.
    Unlike ADHD, sensory load ACCUMULATES (does not habituate).
    """

    sensory_load: float      # 0-10: Current sensory overwhelm level
    cognitive_load: float    # 0-10: Current cognitive processing load
    sensory_accumulated: float  # 0-10: Accumulated sensory load over time
    overload_risk: float     # 0-1: Risk of shutdown/burnout

    @property
    def is_overloaded(self) -> bool:
        """Check if user is at risk of sensory/cognitive overload."""
        return self.sensory_load >= 7 or self.cognitive_load >= 7

    @property
    def needs_break(self) -> bool:
        """Check if user needs immediate break."""
        return self.sensory_load >= 8 or self.cognitive_load >= 8

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "sensory_load": self.sensory_load,
            "cognitive_load": self.cognitive_load,
            "sensory_accumulated": self.sensory_accumulated,
            "overload_risk": self.overload_risk,
            "is_overloaded": self.is_overloaded,
            "needs_break": self.needs_break,
        }


class EnergySystem:
    """
    Unified energy management across segments.

    This service provides segment-specific energy calculations:
    - AD: IBNS/PINCH for task matching
    - AH: ICNU + Spoon-Drawer + Integrity Trigger
    - AU: Sensory + Cognitive load tracking
    - NT: Simple RED/YELLOW/GREEN

    Usage:
        energy_system = EnergySystem()

        # Get simple energy state (AD/NT)
        state = await energy_system.get_energy_state(user_id=123)

        # Get IBNS score (AD)
        ibns = await energy_system.calculate_ibns(user_id=123, task=my_task)

        # Get ICNU score (AH)
        icnu = await energy_system.calculate_icnu(user_id=123, task=my_task)

        # Get Spoon-Drawer (AH)
        spoons = await energy_system.calculate_spoon_drawer(user_id=123)

        # Get Sensory/Cognitive load (AU)
        load = await energy_system.get_sensory_cognitive_load(user_id=123)

        # Energy gating
        can_proceed = await energy_system.can_attempt_task(user_id=123, task=my_task)
    """

    def __init__(self) -> None:
        """Initialize the Energy System."""
        # In-memory storage for energy states (in production, backed by Redis)
        self._energy_states: dict[int, EnergyState] = {}
        self._spoon_drawers: dict[int, SpoonDrawer] = {}
        self._sensory_cognitive: dict[int, SensoryCognitiveLoad] = {}


    async def get_energy_state(self, user_id: int) -> EnergyState:
        """
        Get simple energy state (RED/YELLOW/GREEN) for ADHD/Neurotypical users.

        This is the baseline energy model. More complex models (IBNS, ICNU,
        Spoon-Drawer) build on top of this.

        Args:
            user_id: The user's unique identifier

        Returns:
            EnergyState with level and score
        """
        if user_id not in self._energy_states:
            # Default to YELLOW (moderate energy)
            # In production, load from database or prompt user
            self._energy_states[user_id] = EnergyState(
                level=EnergyStateEnum.YELLOW,
                score=0.5,
                user_id=user_id,
            )
        return self._energy_states[user_id]

    async def update_energy_state(
        self,
        user_id: int,
        level: EnergyStateEnum | None = None,
        score: float | None = None,
    ) -> EnergyState:
        """
        Update the user's energy state.

        Args:
            user_id: The user's unique identifier
            level: New energy level (None = no change)
            score: New energy score 0.0-1.0 (None = no change)

        Returns:
            Updated EnergyState
        """
        current = await self.get_energy_state(user_id)

        new_level = level if level is not None else current.level
        new_score = score if score is not None else current.score

        # Ensure score is in valid range
        new_score = max(0.0, min(1.0, new_score))

        # Auto-determine level from score if not explicitly provided
        if level is None:
            if new_score >= 0.7:
                new_level = EnergyStateEnum.GREEN
            elif new_score >= 0.3:
                new_level = EnergyStateEnum.YELLOW
            else:
                new_level = EnergyStateEnum.RED

        self._energy_states[user_id] = EnergyState(
            level=new_level,
            score=new_score,
            user_id=user_id,
        )

        # In production: persist to database/Redis here
        return self._energy_states[user_id]

    async def calculate_ibns(
        self,
        user_id: int,
        task: Task,
    ) -> IBNSResult:
        """
        Calculate Interest-Based Need State (IBNS) score for ADHD users.

        IBNS = Interest + Challenge + Novelty + Urgency
        Higher scores indicate better task match for ADHD brain.

        The ADHD brain is motivated by:
        - Interest (novelty, passion)
        - Challenge (not too easy, not too hard - flow state)
        - Novelty (new experiences, changes)
        - Urgency (deadlines, time pressure)

        Args:
            user_id: The user's unique identifier
            task: The task to evaluate

        Returns:
            IBNSResult with component scores and recommendation
        """
        # Get task attributes for scoring
        # Cast Column types to plain Python types for mypy
        task_title = str(task.title) if task.title is not None else ""
        task_priority = int(task.priority) if task.priority is not None else 3

        # Calculate components (simplified - in production, use LLM for nuanced scoring)

        # Interest: Based on task title keywords and user history
        # Higher priority tasks may indicate higher interest
        interest = self._calculate_interest_score(task_title, task_priority)

        # Challenge: Inverse of priority (lower priority = more challenging)
        # 1 = highest priority (easy/small), 5 = lowest (hard/big)
        challenge = self._calculate_challenge_score(task_priority)

        # Novelty: Based on task creation recency and title keywords
        novelty = self._calculate_novelty_score(task)

        # Urgency: Based on committed date
        urgency = self._calculate_urgency_score(task)

        # Calculate total score (weighted average)
        # Weights: Interest (0.35), Challenge (0.2), Novelty (0.25), Urgency (0.2)
        total_score = (
            interest * 0.35 +
            challenge * 0.2 +
            novelty * 0.25 +
            urgency * 0.2
        )

        # Determine recommendation
        if total_score >= 0.75:
            recommendation = "highly_recommended"
        elif total_score >= 0.5:
            recommendation = "recommended"
        elif total_score >= 0.25:
            recommendation = "neutral"
        else:
            recommendation = "discouraged"

        return IBNSResult(
            total_score=total_score,
            interest=interest,
            challenge=challenge,
            novelty=novelty,
            urgency=urgency,
            recommendation=recommendation,
        )

    def _calculate_interest_score(self, title: str, priority: int) -> float:
        """
        Calculate interest score based on task title and priority.

        Higher priority (1-2) often indicates higher interest.
        """
        # Base score from priority
        base = 1.0 - ((priority - 1) / 4)  # 1 -> 1.0, 5 -> 0.0

        # Boost for interest keywords
        interest_keywords = ["learn", "create", "explore", "design", "build", "new", "fun", "exciting"]
        title_lower = title.lower()
        keyword_boost = sum(0.1 for kw in interest_keywords if kw in title_lower)

        return min(1.0, base + keyword_boost)

    def _calculate_challenge_score(self, priority: int) -> float:
        """
        Calculate challenge score.

        Flow state: challenge should match skill level.
        Here we approximate: medium priority (3) = optimal challenge.
        """
        # Priority 3 = optimal challenge (0.8)
        # Priority 1-2 = too easy (lower)
        # Priority 4-5 = too hard (lower)
        distance_from_optimal = abs(priority - 3)
        return 1.0 - (distance_from_optimal * 0.25)

    def _calculate_novelty_score(self, task: Task) -> float:
        """
        Calculate novelty score based on task creation recency.
        """
        from datetime import datetime, timedelta

        if not task.created_at:
            return 0.5  # Default if no creation date

        # Tasks created in last 24 hours are most novel
        age = datetime.now(UTC) - task.created_at
        if age < timedelta(hours=24):
            return 1.0
        elif age < timedelta(days=7):
            return 0.7
        elif age < timedelta(days=30):
            return 0.4
        else:
            return 0.2

    def _calculate_urgency_score(self, task: Task) -> float:
        """
        Calculate urgency score based on committed date.
        """
        from datetime import date

        if not task.committed_date:
            return 0.3  # Default if no commitment

        today = date.today()
        days_until = (task.committed_date - today).days

        if days_until < 0:
            # Overdue - highest urgency
            return 1.0
        elif days_until == 0:
            # Due today
            return 0.9
        elif days_until == 1:
            return 0.7
        elif days_until <= 3:
            return 0.5
        elif days_until <= 7:
            return 0.3
        else:
            return 0.1

    async def calculate_icnu(
        self,
        user_id: int,
        task: Task,
    ) -> ICNUResult:
        """
        Calculate ICNU (Interest, Challenge, Novelty, Urgency) for AuDHD users.

        Unlike ADHD's IBNS, this separates the components for finer control
        and includes Integrity Trigger detection.

        The Integrity Trigger detects when a task connects to the user's
        core values/identity - these tasks get a boost regardless of energy.

        Args:
            user_id: The user's unique identifier
            task: The task to evaluate

        Returns:
            ICNUResult with component scores and integrity trigger flag
        """
        # Calculate components (same as IBNS but kept separate)
        # Cast Column types to plain Python types for mypy
        task_title = str(task.title) if task.title is not None else ""
        task_priority = int(task.priority) if task.priority is not None else 3

        interest = self._calculate_interest_score(task_title, task_priority)
        challenge = self._calculate_challenge_score(task_priority)
        novelty = self._calculate_novelty_score(task)
        urgency = self._calculate_urgency_score(task)

        # Calculate total score
        total_score = (
            interest * 0.3 +
            challenge * 0.2 +
            novelty * 0.25 +
            urgency * 0.25
        )

        # Check for integrity trigger
        # Tasks with identity/values keywords get integrity boost
        integrity_keywords = ["values", "purpose", "meaning", "identity", "core", "belief", "mission", "vision"]
        title_lower = task_title.lower()
        integrity_trigger = any(kw in title_lower for kw in integrity_keywords)

        # If integrity trigger, boost total score
        if integrity_trigger:
            total_score = min(1.0, total_score + 0.2)

        # Determine recommendation
        if total_score >= 0.75:
            recommendation = "highly_recommended"
        elif total_score >= 0.5:
            recommendation = "recommended"
        elif total_score >= 0.25:
            recommendation = "neutral"
        else:
            recommendation = "discouraged"

        return ICNUResult(
            interest=interest,
            challenge=challenge,
            novelty=novelty,
            urgency=urgency,
            total_score=total_score,
            integrity_trigger=integrity_trigger,
            recommendation=recommendation,
        )

    async def calculate_spoon_drawer(self, user_id: int) -> SpoonDrawer:
        """
        Calculate Spoon-Drawer for AuDHD users.

        Tracks 6 resource pools: Social, Sensory, EF, Emotional, Physical, Masking.
        Each starts at 10 spoons. Depleted pools block related activities.

        For AuDHD, masking is exponential - each spoon costs more than the last.

        Args:
            user_id: The user's unique identifier

        Returns:
            SpoonDrawer with all 6 pool values
        """
        if user_id not in self._spoon_drawers:
            # Initialize with full spoons
            # In production, load from database or prompt user
            self._spoon_drawers[user_id] = SpoonDrawer(
                social=10,
                sensory=10,
                ef=10,
                emotional=10,
                physical=10,
                masking=10,
            )
        return self._spoon_drawers[user_id]

    async def update_spoon_drawer(
        self,
        user_id: int,
        social: int | None = None,
        sensory: int | None = None,
        ef: int | None = None,
        emotional: int | None = None,
        physical: int | None = None,
        masking: int | None = None,
    ) -> SpoonDrawer:
        """
        Update specific spoon pools.

        Args:
            user_id: The user's unique identifier
            social: New social spoon count (None = no change)
            sensory: New sensory spoon count (None = no change)
            ef: New executive function spoon count (None = no change)
            emotional: New emotional spoon count (None = no change)
            physical: New physical spoon count (None = no change)
            masking: New masking spoon count (None = no change)

        Returns:
            Updated SpoonDrawer
        """
        current = await self.calculate_spoon_drawer(user_id)

        self._spoon_drawers[user_id] = SpoonDrawer(
            social=max(0, min(10, social if social is not None else current.social)),
            sensory=max(0, min(10, sensory if sensory is not None else current.sensory)),
            ef=max(0, min(10, ef if ef is not None else current.ef)),
            emotional=max(0, min(10, emotional if emotional is not None else current.emotional)),
            physical=max(0, min(10, physical if physical is not None else current.physical)),
            masking=max(0, min(10, masking if masking is not None else current.masking)),
        )

        # In production: persist to database/Redis here
        return self._spoon_drawers[user_id]

    async def spend_spoons(
        self,
        user_id: int,
        task: Task,
    ) -> SpoonDrawer:
        """
        Spend spoons for a task.

        Different task types cost different spoon pools:
        - Social tasks: -social, -masking (exponential)
        - Sensory-heavy tasks: -sensory
        - Complex/EF tasks: -ef
        - Emotional tasks: -emotional
        - Physical tasks: -physical
        - Masking-heavy (social): -masking (exponential)

        Args:
            user_id: The user's unique identifier
            task: The task to spend spoons on

        Returns:
            Updated SpoonDrawer after spending
        """
        current = await self.calculate_spoon_drawer(user_id)

        # Determine task type and cost
        # In production, use LLM or task metadata
        task_title = (task.title or "").lower()

        # Calculate costs
        social_cost = 2 if any(w in task_title for w in ["talk", "meet", "call", "social", "friend"]) else 0
        sensory_cost = 3 if any(w in task_title for w in ["noise", "bright", "crowd", "sensory"]) else 0
        ef_cost = 3 if any(w in task_title for w in ["plan", "organize", "decide", "focus", "complex"]) else 0
        emotional_cost = 2 if any(w in task_title for w in ["emotional", "difficult", "hard", "stress"]) else 0
        physical_cost = 2 if any(w in task_title for w in ["exercise", "walk", "run", "physical"]) else 0
        masking_cost = 2 if any(w in task_title for w in ["present", "interview", "social", "public"]) else 0

        # Apply exponential masking cost for AuDHD
        if masking_cost > 0:
            masking_cost = int(masking_cost * current.masking_cost_multiplier)

        # Update spoons
        return await self.update_spoon_drawer(
            user_id,
            social=current.social - social_cost,
            sensory=current.sensory - sensory_cost,
            ef=current.ef - ef_cost,
            emotional=current.emotional - emotional_cost,
            physical=current.physical - physical_cost,
            masking=current.masking - masking_cost,
        )

    async def get_sensory_cognitive_load(self, user_id: int) -> SensoryCognitiveLoad:
        """
        Get Sensory and Cognitive load for Autism users.

        Unlike ADHD, sensory load ACCUMULATES over time (does not habituate).
        This tracks both current load and accumulated load.

        Args:
            user_id: The user's unique identifier

        Returns:
            SensoryCognitiveLoad with current and accumulated values
        """
        if user_id not in self._sensory_cognitive:
            # Initialize with zero load
            # In production, load from database or prompt user
            self._sensory_cognitive[user_id] = SensoryCognitiveLoad(
                sensory_load=0.0,
                cognitive_load=0.0,
                sensory_accumulated=0.0,
                overload_risk=0.0,
            )
        return self._sensory_cognitive[user_id]

    async def update_sensory_cognitive_load(
        self,
        user_id: int,
        sensory: float | None = None,
        cognitive: float | None = None,
    ) -> SensoryCognitiveLoad:
        """
        Update sensory and cognitive load.

        Note: sensory_load ACCUMULATES (additive), doesn't reset.
        This reflects the autism reality that sensory overwhelm doesn't habituate.

        Args:
            user_id: The user's unique identifier
            sensory: Additional sensory load to add (None = no change)
            cognitive: New cognitive load (None = no change)

        Returns:
            Updated SensoryCognitiveLoad
        """
        current = await self.get_sensory_cognitive_load(user_id)

        # Sensory accumulates (doesn't reset)
        new_sensory = current.sensory_load
        if sensory is not None:
            new_sensory = min(10.0, current.sensory_load + sensory)
            # Accumulated also increases
            accumulated = min(10.0, current.sensory_accumulated + sensory)

        # Cognitive is replaced (not cumulative in the same way)
        new_cognitive = cognitive if cognitive is not None else current.cognitive_load

        # Calculate overload risk
        overload_risk = max(
            new_sensory / 10.0,
            new_cognitive / 10.0,
            (current.sensory_accumulated / 10.0) * 0.5  # Accumulated contributes to risk
        )

        self._sensory_cognitive[user_id] = SensoryCognitiveLoad(
            sensory_load=new_sensory,
            cognitive_load=new_cognitive,
            sensory_accumulated=current.sensory_accumulated if sensory is None else accumulated,
            overload_risk=overload_risk,
        )

        # In production: persist to database/Redis here
        return self._sensory_cognitive[user_id]

    async def can_attempt_task(
        self,
        user_id: int,
        task: Task,
        segment_context: SegmentContext,
    ) -> bool:
        """
        Determine if user has enough energy to attempt a task.

        RED blocks non-essential tasks.
        Essential tasks (high integrity/urgency) can override.

        Energy gating rules:
        - RED: Only essential tasks
        - YELLOW: Non-demanding tasks OK
        - GREEN: All tasks OK

        For AuDHD with Spoon-Drawer: checks pool availability.
        For Autism with Sensory-Cognitive: checks overload risk.

        Args:
            user_id: The user's unique identifier
            task: The task to evaluate
            segment_context: The user's segment context

        Returns:
            True if user can attempt the task, False if blocked
        """
        # Check simple energy state first
        energy_state = await self.get_energy_state(user_id)

        # Get basic energy check
        if energy_state.level == EnergyStateEnum.RED:
            # RED blocks non-essential tasks
            # Check if task is essential (high priority or high integrity)
            # Cast Column type to int for comparison
            task_priority_val = int(task.priority) if task.priority is not None else 3
            is_essential = task_priority_val <= 2

            # For segments with integrity trigger enabled, also check integrity
            if segment_context.features.integrity_trigger_enabled:
                task_title = (task.title or "").lower()
                integrity_keywords = ["values", "purpose", "meaning", "identity", "core"]
                has_integrity = any(kw in task_title for kw in integrity_keywords)
                is_essential = is_essential or has_integrity

            if not is_essential:
                return False

        # Segment-specific checks

        # Check Spoon-Drawer availability (AuDHD)
        if segment_context.features.spoon_drawer_enabled:
            spoons = await self.calculate_spoon_drawer(user_id)
            if spoons.is_depleted:
                # Check if task requires depleted pool
                task_title = (task.title or "").lower()

                if any(w in task_title for w in ["social", "talk", "meet"]) and spoons.social <= 2:
                    return False
                if any(w in task_title for w in ["noise", "sensory"]) and spoons.sensory <= 2:
                    return False
                if any(w in task_title for w in ["plan", "focus", "complex"]) and spoons.ef <= 2:
                    return False
                if any(w in task_title for w in ["emotional", "stress"]) and spoons.emotional <= 2:
                    return False

        # Check Sensory/Cognitive load (Autism/AuDHD)
        if segment_context.features.sensory_check_required:
            load = await self.get_sensory_cognitive_load(user_id)
            if load.is_overloaded:
                return False

        # Default: allow
        return True

    async def get_energy_recommendation(
        self,
        user_id: int,
        segment_context: SegmentContext,
        task: Task | None = None,
    ) -> dict[str, Any]:
        """
        Get comprehensive energy recommendation for a user.

        Returns segment-appropriate energy information:
        - AD: IBNS score + simple energy state
        - AH: ICNU + Spoon-Drawer + simple energy state
        - AU: Sensory-Cognitive load
        - NT: Simple energy state

        Args:
            user_id: The user's unique identifier
            segment_context: The user's segment context
            task: Optional task for IBNS/ICNU calculation

        Returns:
            Dictionary with segment-appropriate energy data
        """
        # Base response
        response: dict[str, Any] = {
            "segment": segment_context.core.code,  # Use 'code' instead of 'working_style_code'
            "user_id": user_id,
        }

        # Always include simple energy state
        energy_state = await self.get_energy_state(user_id)
        response["energy_state"] = energy_state.to_dict()

        # Segment-specific additions based on energy_check_type and features

        # ADHD path: energy_check_type == "simple" + ICNU enabled
        if segment_context.ux.energy_check_type == "simple" and segment_context.features.icnu_enabled and task:
            # ADHD: Add IBNS
            ibns = await self.calculate_ibns(user_id, task)
            response["ibns"] = {
                "total_score": ibns.total_score,
                "interest": ibns.interest,
                "challenge": ibns.challenge,
                "novelty": ibns.novelty,
                "urgency": ibns.urgency,
                "recommendation": ibns.recommendation,
            }

        # AuDHD path: energy_check_type == "spoon_drawer"
        elif segment_context.ux.energy_check_type == "spoon_drawer":
            # AuDHD: Add ICNU and Spoon-Drawer
            response["icnu_enabled"] = True
            response["spoon_drawer"] = (await self.calculate_spoon_drawer(user_id)).to_dict()

            if task:
                icnu = await self.calculate_icnu(user_id, task)
                response["icnu"] = {
                    "total_score": icnu.total_score,
                    "interest": icnu.interest,
                    "challenge": icnu.challenge,
                    "novelty": icnu.novelty,
                    "urgency": icnu.urgency,
                    "integrity_trigger": icnu.integrity_trigger,
                    "recommendation": icnu.recommendation,
                }

        # Autism path: energy_check_type == "sensory_cognitive"
        elif segment_context.ux.energy_check_type == "sensory_cognitive":
            # Autism: Add Sensory-Cognitive load
            load = await self.get_sensory_cognitive_load(user_id)
            response["sensory_cognitive"] = load.to_dict()

        # Add gating decision if task provided
        if task:
            response["can_attempt"] = await self.can_attempt_task(user_id, task, segment_context)

        return response


# Module-level singleton for easy access
_energy_system: EnergySystem | None = None


def get_energy_system() -> EnergySystem:
    """
    Get the singleton EnergySystem instance.

    Returns:
        The global EnergySystem instance
    """
    global _energy_system
    if _energy_system is None:
        _energy_system = EnergySystem()
    return _energy_system


async def get_user_energy_state(user_id: int) -> EnergyState:
    """
    Convenience function to get a user's simple energy state.

    Args:
        user_id: The user's unique identifier

    Returns:
        The user's current EnergyState
    """
    system = get_energy_system()
    return await system.get_energy_state(user_id)


async def can_user_attempt_task(user_id: int, task: Task, segment_context: SegmentContext) -> bool:
    """
    Convenience function to check if user can attempt a task.

    Args:
        user_id: The user's unique identifier
        task: The task to evaluate
        segment_context: The user's segment context

    Returns:
        True if user can attempt the task
    """
    system = get_energy_system()
    return await system.can_attempt_task(user_id, task, segment_context)
