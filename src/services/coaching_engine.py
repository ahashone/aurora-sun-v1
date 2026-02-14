"""
Coaching Engine for Aurora Sun V1.

Inline coaching: activated during any module when user says "I'm stuck" / "I can't start".
No module exit required - coaching happens within current state.

Segment-specific protocols:
- ADHD → PINCH activation (Passion, Interest, Novelty, Competition, Hurry)
- Autism → Inertia protocol (transition bridges, NOT "just start")
- AuDHD → Channel check first (SW-19), then route to ADHD or Autism protocol
- Neurotypical → Standard motivation coaching

Reference: ARCHITECTURE.md Section 3 (Inline Coaching) and Section 4 (Coaching Engine)
Reference: SW-3 (Inline Coaching Trigger), SW-11 (Crisis Override), SW-12 (Burnout Redirect)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse

from .tension_engine import (
    Quadrant,
    TensionEngine,
    get_tension_engine,
)

# Type aliases
ChannelDominance = Literal["ADHD", "AUTISM", "BALANCED"]


@dataclass
class CoachingResponse:
    """Response from the coaching engine.

    Contains the coaching message and any additional actions to take.
    """

    text: str
    should_continue_module: bool = True  # If False, module should pause/suspend
    is_crisis_response: bool = False     # True if this is a crisis protocol response
    is_burnout_redirect: bool = False    # True if this redirects to burnout recovery
    recommended_action: str | None = None  # e.g., "pause_module", "suspend_daily_workflow"
    metadata: dict = None  # Additional coaching metadata

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_module_response(self) -> ModuleResponse:
        """Convert to ModuleResponse for return to module system."""
        return ModuleResponse(
            text=self.text,
            metadata=self.metadata,
        )


class CoachingEngine:
    """Inline coaching engine for Aurora Sun V1.

    Activated during any module when the user expresses being stuck or unable to start.
    No module exit required - coaching happens within the current state.

    The coaching flow:
        1. Detect "I'm stuck" / drift signals
        2. Check Tension Engine quadrant
        3. Check burnout gate (if burnout trajectory → recovery, not activation)
        4. Route to segment-specific protocol
        5. Return coaching response

    Usage:
        engine = CoachingEngine()
        is_stuck = await engine.detect_stuck(message, ctx)
        if is_stuck:
            response = await engine.handle_stuck(message, ctx, active_module, active_state)
    """

    # Stuck detection patterns (NLI-based in production, heuristics for now)
    STUCK_PATTERNS = [
        "i'm stuck",
        "i cant start",
        "i can't start",
        "i don't know where to start",
        "i don't know how to start",
        "i don't know what to do",
        "i'm overwhelmed",
        "i can't get started",
        "i'm frozen",
        "i'm not able to start",
        "i don't know how to begin",
        "i have no idea where to start",
        "i'm blocked",
        "i can't begin",
    ]

    # Drift signals (softer than explicit "stuck")
    DRIFT_PATTERNS = [
        "maybe later",
        "not now",
        "i'll do it tomorrow",
        "i forgot what i was doing",
        "i lost focus",
        "i got distracted",
        "i was doing something else",
    ]

    def __init__(self, tension_engine: TensionEngine | None = None):
        """Initialize the coaching engine.

        Args:
            tension_engine: Optional TensionEngine instance (uses singleton if not provided)
        """
        self.tension_engine = tension_engine or get_tension_engine()

        # Channel dominance cache for AuDHD users (SW-19)
        # In production, this would be backed by Redis
        self._channel_dominance_cache: dict[int, ChannelDominance] = {}

    async def detect_stuck(self, message: str, ctx: ModuleContext) -> bool:
        """Detect if the user is expressing being stuck.

        Uses NLI classification in production. For now, uses pattern matching
        on known stuck/drift phrases.

        Args:
            message: The user's message
            ctx: The current module context

        Returns:
            True if stuck signal detected, False otherwise
        """
        message_lower = message.lower().strip()

        # Check for explicit stuck patterns
        for pattern in self.STUCK_PATTERNS:
            if pattern in message_lower:
                return True

        # Check for drift patterns (softer signals)
        # These only trigger if user is in AVOIDANCE quadrant
        for pattern in self.DRIFT_PATTERNS:
            if pattern in message_lower:
                # Check tension state to determine if this is concerning
                state = await self.tension_engine.get_state(ctx.user_id)
                if state.quadrant == Quadrant.AVOIDANCE:
                    return True

        return False

    async def handle_stuck(
        self,
        message: str,
        ctx: ModuleContext,
        active_module: str,
        active_state: str,
    ) -> CoachingResponse:
        """Handle a stuck situation with segment-specific coaching.

        This is the main entry point for inline coaching. It:
        1. Checks the Tension Engine quadrant
        2. Checks burnout gate (if burnout trajectory → recovery, not activation)
        3. Routes to segment-specific protocol

        Args:
            message: The user's stuck message
            ctx: The current module context
            active_module: Name of the currently active module
            active_state: Current state within the module

        Returns:
            CoachingResponse with appropriate coaching message
        """
        # Get tension state
        state = await self.tension_engine.get_state(ctx.user_id)

        # Step 1: Check Tension Engine quadrant
        quadrant = state.quadrant

        # Quadrant-based routing
        if quadrant == Quadrant.SWEET_SPOT:
            # Already in good state - reinforce, no coaching needed
            return await self._reinforce_sweet_spot(ctx)

        elif quadrant == Quadrant.CRISIS:
            # Crisis state - trigger crisis protocol (SW-11)
            return await self._handle_crisis(ctx)

        elif quadrant == Quadrant.BURNOUT:
            # Burnout trajectory - redirect to recovery (SW-12)
            return await self._handle_burnout(ctx)

        # AVOIDANCE quadrant or default: continue with segment-specific protocol

        # Step 2: Check burnout gate (even for AVOIDANCE)
        burnout_gate = await self.burnout_gate(ctx)
        if burnout_gate:
            return await self._handle_burnout(ctx)

        # Step 3: Route to segment-specific protocol
        # FIX: Use SegmentContext fields instead of string comparison
        # This follows the ARCHITECTURE.md rule: "Never if segment == 'AD' in code"
        features = ctx.segment_context.features

        # Route based on segment features, not string comparison
        # AuDHD has special handling via channel dominance check
        if features.channel_dominance_enabled:
            # AH: Channel dominance check first (SW-19)
            return await self._handle_audhd(ctx)
        elif features.icnu_enabled:
            # AD: ICNU-based activation
            return await self.pinch_activation(ctx)
        elif features.routine_anchoring:
            # AU: Inertia protocol for routine-based users
            return await self.inertia_protocol(ctx)
        else:
            # NT or CU: Standard motivation
            return await self.standard_motivation(ctx)

    async def pinch_activation(self, ctx: ModuleContext) -> CoachingResponse:
        """PINCH activation protocol for ADHD users.

        PINCH:
        - P: Passion - "What would you love to do?"
        - I: Interest - "What's intriguing about this?"
        - N: Novelty - "Let's try something new"
        - C: Competition - "Beat your yesterday's record"
        - H: Hurry - "5-minute sprint challenge"

        Args:
            ctx: The current module context

        Returns:
            CoachingResponse with PINCH activation
        """
        # In production, this would use DSPy-optimized prompts
        # and pull from Neo4j/Qdrant knowledge base

        responses = [
            "What's one thing about this that genuinely interests you?",
            "Let's make this a bit more exciting. What's a novel angle we could try?",
            "I dare you to beat what you did yesterday. Just 5 minutes to start?",
            "Quick challenge: can you do just 5 minutes? That's all. Start a timer.",
        ]

        # Pick response based on time/patterns (random in production)
        import random
        text = random.choice(responses)

        return CoachingResponse(
            text=text,
            should_continue_module=True,
            metadata={"protocol": "pinch_activation", "segment": "AD"},
        )

    async def inertia_protocol(self, ctx: ModuleContext) -> CoachingResponse:
        """Inertia protocol for Autism users.

        IMPORTANT: NOT "just start" - this will backfire!

        The Autism inertia protocol:
        - Transition bridges: small pre-tasks to ease into the main task
        - Reduce friction: remove decision points
        - External structure: "First, I'll tell you what to do"

        Reference: ARCHITECTURE.md Section 3 - "Inertia != laziness != activation deficit"

        Args:
            ctx: The current module context

        Returns:
            CoachingResponse with inertia protocol
        """
        # In production: use DSPy-optimized prompts for Autistic Inertia

        responses = [
            "Let's break this into tiny steps. First, just tell me one thing you see nearby.",
            "No need to do everything at once. What's the smallest possible first move?",
            "I'll tell you exactly what to do: First, [specific instruction]. That's it for now.",
            "You don't need to figure this out. I'm here to guide you step by step. What's step one?",
        ]

        import random
        text = random.choice(responses)

        return CoachingResponse(
            text=text,
            should_continue_module=True,
            metadata={"protocol": "inertia_protocol", "segment": "AU"},
        )

    async def check_channel_dominance(self, user_id: int) -> ChannelDominance:
        """Check channel dominance for AuDHD users (SW-19).

        Determines if today is an ADHD-day or Autism-day for the user.
        Wrong-channel interventions fail or backfire.

        Args:
            user_id: The user's unique identifier

        Returns:
            Channel dominance: "ADHD", "AUTISM", or "BALANCED"
        """
        # Check cache first
        if user_id in self._channel_dominance_cache:
            return self._channel_dominance_cache[user_id]

        # In production: query NeurostateService for channel dominance
        # For now, return a default based on time or random
        # This would integrate with the actual NeurostateService

        # Default to balanced (conservative)
        dominant = "BALANCED"

        # Cache for session
        self._channel_dominance_cache[user_id] = dominant

        return dominant

    async def _handle_audhd(self, ctx: ModuleContext) -> CoachingResponse:
        """Handle AuDHD users: channel dominance check first (SW-19).

        Args:
            ctx: The current module context

        Returns:
            CoachingResponse based on channel dominance
        """
        channel = await self.check_channel_dominance(ctx.user_id)

        if channel == "ADHD":
            # ADHD-day: use PINCH activation
            return await self.pinch_activation(ctx)

        elif channel == "AUTISM":
            # Autism-day: use inertia protocol
            return await self.inertia_protocol(ctx)

        else:
            # BALANCED: default to hybrid approach or ask
            # For now, use a gentle hybrid
            text = "I notice you're having a hard time getting started. Would you like a gentle nudge or step-by-step guidance?"
            return CoachingResponse(
                text=text,
                should_continue_module=True,
                metadata={"protocol": "audhd_balanced", "segment": "AH"},
            )

    async def standard_motivation(self, ctx: ModuleContext) -> CoachingResponse:
        """Standard motivation coaching for Neurotypical users.

        Args:
            ctx: The current module context

        Returns:
            CoachingResponse with standard motivation
        """
        responses = [
            "What's the next small step you could take?",
            "Let's break this down into actionable pieces. What feels manageable?",
            "What's standing in the way? We can tackle it together.",
        ]

        import random
        text = random.choice(responses)

        return CoachingResponse(
            text=text,
            should_continue_module=True,
            metadata={"protocol": "standard_motivation", "segment": "NT"},
        )

    async def burnout_gate(self, ctx: ModuleContext) -> bool:
        """Check if burnout trajectory detected.

        If burnout is emerging or active, coaching should shift from
        activation to recovery. Behavioral Activation during Autistic
        Burnout actively harms (SW-12).

        Args:
            ctx: The current module context

        Returns:
            True if burnout trajectory detected, False otherwise
        """
        # In production: query NeurostateService for burnout severity
        # For now, check tension state

        state = await self.tension_engine.get_state(ctx.user_id)

        # If in burnout quadrant, definitely gate
        if state.quadrant == Quadrant.BURNOUT:
            return True

        # If crisis quadrant, also gate (more severe)
        if state.quadrant == Quadrant.CRISIS:
            return True

        # Additional checks in production:
        # - NeurostateService.burnout_severity > 0.3
        # - PatternDetectionService.detected("boom_bust") for AD
        # - PatternDetectionService.detected("overload_shutdown") for AU

        return False

    async def _handle_crisis(self, ctx: ModuleContext) -> CoachingResponse:
        """Handle crisis state (SW-11).

        Crisis protocol:
        - Empathetic acknowledgment (segment-adapted)
        - NO task-focused prompts
        - NO "just breathe" / "just start" platitudes
        - Provide appropriate resources

        Args:
            ctx: The current module context

        Returns:
            CoachingResponse with crisis protocol
        """
        segment = ctx.segment_context.core.code

        # Crisis responses (segment-adapted but always empathetic)
        crisis_texts = {
            "AD": "I hear you. This feels overwhelming right now. You don't have to do anything - I'm here.",
            "AU": "I can see you're struggling. There's no pressure to do anything. I'm here with you.",
            "AH": "This is hard. You don't have to push through - let's just be here for a moment.",
            "NT": "I'm here with you. You don't have to be okay right now. Let's take it slow.",
        }

        text = crisis_texts.get(segment, crisis_texts["NT"])

        return CoachingResponse(
            text=text,
            should_continue_module=False,  # Pause the module
            is_crisis_response=True,
            recommended_action="pause_module",
            metadata={
                "protocol": "crisis_override",
                "workflow": "SW-11",
                "segment": segment,
            },
        )

    async def _handle_burnout(self, ctx: ModuleContext) -> CoachingResponse:
        """Handle burnout state (SW-12).

        Burnout redirect:
        - Shift from activation to recovery
        - ADHD: pacing protocol, energy banking
        - Autism: reduced demands, sensory recovery
        - AuDHD: identify burnout type first, then segment-appropriate recovery

        Args:
            ctx: The current module context

        Returns:
            CoachingResponse with burnout redirect
        """
        segment = ctx.segment_context.core.code

        burnout_texts = {
            "AD": "I notice you're running on empty. Let's focus on recovery today - no big pushes needed.",
            "AU": "This sounds like a lot right now. Let's scale back and give your system a break.",
            "AH": "Your system is signaling overload. Let's switch to recovery mode today.",
            "NT": "You seem exhausted. Let's make today about gentle recovery rather than productivity.",
        }

        text = burnout_texts.get(segment, burnout_texts["NT"])

        return CoachingResponse(
            text=text,
            should_continue_module=True,  # Can continue but with reduced demands
            is_burnout_redirect=True,
            recommended_action="gentle_redirect",
            metadata={
                "protocol": "burnout_redirect",
                "workflow": "SW-12",
                "segment": segment,
            },
        )

    async def _reinforce_sweet_spot(self, ctx: ModuleContext) -> CoachingResponse:
        """Reinforce when user is in sweet spot quadrant.

        When user is already in SWEET_SPOT (HIGH sonne + HIGH erde),
        no coaching is needed - just reinforce the good state.

        Args:
            ctx: The current module context

        Returns:
            CoachingResponse with reinforcement
        """
        text = "You're doing great! Keep this energy going."

        return CoachingResponse(
            text=text,
            should_continue_module=True,
            metadata={"protocol": "sweet_spot_reinforce"},
        )

    async def effectiveness_track(
        self,
        user_id: int,
        intervention_type: str,
        response: CoachingResponse,
    ) -> None:
        """Track intervention effectiveness (for RIA service).

        This would be called by the module system after the coaching
        response is delivered, to feed back to the EffectivenessService.

        Args:
            user_id: The user's unique identifier
            intervention_type: Type of intervention (e.g., "inline_coaching")
            response: The coaching response that was delivered
        """
        # In production: call EffectivenessService.track_intervention()
        # This is a placeholder for the integration

        # Would track:
        # - intervention_type
        # - user_id
        # - segment
        # - protocol_used
        # - timestamp
        # - (later) whether it worked
        pass


# Module-level singleton for easy access
_coaching_engine: CoachingEngine | None = None


def get_coaching_engine() -> CoachingEngine:
    """Get the singleton CoachingEngine instance.

    Returns:
        The global CoachingEngine instance
    """
    global _coaching_engine
    if _coaching_engine is None:
        _coaching_engine = CoachingEngine()
    return _coaching_engine
