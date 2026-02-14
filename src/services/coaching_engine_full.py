"""
Full Coaching Engine for Aurora Sun V1.

Advanced coaching engine with LangGraph workflow and 4-tier fallback:
    Router -> Enrich Context -> Knowledge -> Coaching -> Memory -> Summary -> END

4-tier fallback for coaching response generation:
1. Optimized Artifact (pre-built templates per segment)
2. DSPy signature (prompt optimization)
3. PydanticAI (structured LLM output)
4. Placeholder (deterministic fallback)

Segment-specific coaching signatures ensure that coaching responses
are appropriate for the user's neurotype. This is NOT optional.

Reference: ARCHITECTURE.md Section 4 (Full Coaching Engine)
Reference: ARCHITECTURE.md Section 3 (Neurotype Segmentation)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.core.segment_context import SegmentContext


class CoachingStep(StrEnum):
    """Steps in the coaching workflow."""

    ROUTER = "router"
    ENRICH_CONTEXT = "enrich_context"
    KNOWLEDGE = "knowledge"
    COACHING = "coaching"
    MEMORY = "memory"
    SUMMARY = "summary"
    END = "end"
    ERROR = "error"


class CoachingTier(StrEnum):
    """Coaching response generation tiers (fallback chain)."""

    OPTIMIZED_ARTIFACT = "optimized_artifact"  # Pre-built templates
    DSPY = "dspy"                               # DSPy-optimized prompt
    PYDANTIC_AI = "pydantic_ai"                # PydanticAI structured output
    PLACEHOLDER = "placeholder"                 # Deterministic fallback


class CoachingIntent(StrEnum):
    """Intents that the coaching engine can handle."""

    STUCK = "stuck"                 # User is stuck
    PLANNING = "planning"           # Planning assistance
    REFLECTION = "reflection"       # Reflection/review
    MOTIVATION = "motivation"       # Motivation boost
    ACCOUNTABILITY = "accountability"  # Accountability check
    ENERGY_CHECK = "energy_check"   # Energy assessment
    GENERAL = "general"             # General coaching


@dataclass
class CoachingContext:
    """Enriched context for coaching response generation.

    Contains all the information needed to generate a
    segment-appropriate coaching response.
    """

    user_id: int = 0
    session_id: str = field(
        default_factory=lambda: uuid.uuid4().hex[:12]
    )
    intent: CoachingIntent = CoachingIntent.GENERAL
    message: str = ""
    segment_ctx: SegmentContext | None = None
    energy_level: float | None = None
    recent_patterns: list[str] = field(default_factory=list)
    active_goals: list[str] = field(default_factory=list)
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "intent": self.intent.value,
            "message": self.message,
            "segment_code": (
                self.segment_ctx.core.code
                if self.segment_ctx
                else None
            ),
            "energy_level": self.energy_level,
            "recent_patterns": self.recent_patterns,
            "active_goals": self.active_goals,
            "metadata": self.metadata,
        }


@dataclass
class CoachingResult:
    """Result from the full coaching engine.

    Contains the coaching response, which tier generated it,
    and metadata about the generation process.
    """

    text: str = ""
    tier_used: CoachingTier = CoachingTier.PLACEHOLDER
    intent: CoachingIntent = CoachingIntent.GENERAL
    step_completed: CoachingStep = CoachingStep.END
    context_enriched: bool = False
    knowledge_applied: bool = False
    memory_stored: bool = False
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "text": self.text,
            "tier_used": self.tier_used.value,
            "intent": self.intent.value,
            "step_completed": self.step_completed.value,
            "context_enriched": self.context_enriched,
            "knowledge_applied": self.knowledge_applied,
            "memory_stored": self.memory_stored,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "errors": self.errors,
            "generated_at": self.generated_at,
        }


# ============================================================================
# Segment-Specific Coaching Signatures
# ============================================================================

# These are the coaching "signatures" - segment-specific templates
# that guide the tone, approach, and content of coaching responses.
# In production, these feed into DSPy for prompt optimization.

COACHING_SIGNATURES: dict[str, dict[str, str]] = {
    "AD": {
        "stuck": (
            "You sound stuck. Let's find a spark. "
            "What's one thing about this that could be interesting or novel? "
            "We could try a 5-minute sprint - just to see what happens."
        ),
        "planning": (
            "Let's keep this simple. Two priorities max for today. "
            "What's the one thing that would make today feel like a win?"
        ),
        "reflection": (
            "Quick check-in: What went well? What surprised you? "
            "No need for a long review - just the highlights."
        ),
        "motivation": (
            "You've got momentum to build on. "
            "What's one small thing you could knock out right now?"
        ),
        "accountability": (
            "Let's see where things stand. "
            "No judgment - just a quick status check."
        ),
        "energy_check": (
            "How's your energy right now? "
            "Quick gut check - RED, YELLOW, or GREEN?"
        ),
        "general": (
            "What's on your mind? "
            "I'm here to help you figure out the next move."
        ),
    },
    "AU": {
        "stuck": (
            "I can see you are having a hard time getting started. "
            "Let me break this down for you step by step. "
            "First, let's identify exactly what needs to happen."
        ),
        "planning": (
            "Let's create a clear structure for today. "
            "I'll walk you through each step. "
            "What's already on your schedule?"
        ),
        "reflection": (
            "Let's review how things went today. "
            "Take your time - there's no rush. "
            "What felt manageable? What felt like too much?"
        ),
        "motivation": (
            "You've been consistent. That matters. "
            "Your system is working. Let's keep building on it."
        ),
        "accountability": (
            "Let's check in on your progress. "
            "Which items from your plan are done? "
            "Which ones need adjustment?"
        ),
        "energy_check": (
            "How's your sensory and cognitive load right now? "
            "Let's check both channels separately."
        ),
        "general": (
            "What would be helpful right now? "
            "I can provide structure, break things down, or just listen."
        ),
    },
    "AH": {
        "stuck": (
            "Let me check in with you. "
            "Is this feeling more like 'I can't start' or 'everything is too much'? "
            "That'll help me figure out the best way to support you right now."
        ),
        "planning": (
            "Let's plan in a way that works for today. "
            "How are you feeling - more structured or more flexible? "
            "We'll adapt the approach to match."
        ),
        "reflection": (
            "How did today go? "
            "Let's look at what worked and what didn't, "
            "without getting caught in a spiral about it."
        ),
        "motivation": (
            "You're doing more than you think. "
            "Let's acknowledge that before we move forward."
        ),
        "accountability": (
            "Quick check-in, adapted to your current channel. "
            "What's done? What shifted? What needs to move?"
        ),
        "energy_check": (
            "Let's check your spoon drawer. "
            "How many spoons do you feel like you have right now? "
            "And which channel feels dominant today?"
        ),
        "general": (
            "I'm here. What would help most right now? "
            "Structure, a gentle nudge, or just space to think?"
        ),
    },
    "NT": {
        "stuck": (
            "Sounds like you're stuck. "
            "What's the main blocker? "
            "Let's figure out a way around it."
        ),
        "planning": (
            "Let's plan your day. "
            "What are your top three priorities?"
        ),
        "reflection": (
            "How did today go? "
            "What worked? What would you do differently?"
        ),
        "motivation": (
            "You're making progress. "
            "What's the next step you want to tackle?"
        ),
        "accountability": (
            "Let's check your progress. "
            "What's done and what's still pending?"
        ),
        "energy_check": (
            "How's your energy level? "
            "Are you feeling ready for a challenge or need something lighter?"
        ),
        "general": (
            "What can I help you with? "
            "I'm here to support your goals."
        ),
    },
    "CU": {
        "stuck": (
            "I notice you're having difficulty. "
            "What kind of support would be most helpful right now?"
        ),
        "planning": (
            "Let's plan your day. "
            "What approach works best for you?"
        ),
        "reflection": (
            "Let's reflect on your day. "
            "What stands out to you?"
        ),
        "motivation": (
            "You're moving forward. "
            "What would help you keep this momentum?"
        ),
        "accountability": (
            "Let's review where things stand. "
            "What's your current status?"
        ),
        "energy_check": (
            "How are you feeling energy-wise? "
            "Let's calibrate the rest of the day."
        ),
        "general": (
            "How can I help? "
            "I'll adapt my approach to what works for you."
        ),
    },
}


class FullCoachingEngine:
    """Full Coaching Engine with LangGraph workflow and 4-tier fallback.

    Provides advanced coaching with:
    - Intent routing
    - Context enrichment
    - Knowledge retrieval (future: Qdrant/Neo4j)
    - Segment-specific coaching signatures
    - Memory storage (future: Letta)
    - Response summarization

    Usage:
        engine = FullCoachingEngine()
        result = await engine.coach(
            user_id=1,
            message="I'm stuck on my project",
            segment_ctx=ctx,
        )
    """

    def __init__(self) -> None:
        """Initialize the full coaching engine."""
        self._memory: dict[int, list[dict[str, Any]]] = {}

    async def coach(
        self,
        user_id: int,
        message: str,
        segment_ctx: SegmentContext,
        energy_level: float | None = None,
        recent_patterns: list[str] | None = None,
        active_goals: list[str] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> CoachingResult:
        """Run the full coaching workflow.

        Router -> Enrich Context -> Knowledge -> Coaching -> Memory -> Summary -> END

        Args:
            user_id: The user's unique identifier
            message: The user's message
            segment_ctx: The user's segment context
            energy_level: Current energy level (0.0-1.0)
            recent_patterns: Recently detected patterns
            active_goals: Currently active goals
            conversation_history: Recent conversation history

        Returns:
            CoachingResult with the coaching response
        """
        # Build context
        context = CoachingContext(
            user_id=user_id,
            message=message,
            segment_ctx=segment_ctx,
            energy_level=energy_level,
            recent_patterns=recent_patterns or [],
            active_goals=active_goals or [],
            conversation_history=conversation_history or [],
        )

        result = CoachingResult()

        # Step 1: ROUTER - determine intent
        context = self.route_context(context)
        result.intent = context.intent

        # Step 2: ENRICH CONTEXT
        context = self.enrich_context(context)
        result.context_enriched = True

        # Step 3: KNOWLEDGE (future: Qdrant/Neo4j retrieval)
        context = await self._apply_knowledge(context)
        result.knowledge_applied = True

        # Step 4: COACHING - generate response with 4-tier fallback
        result = await self.generate_coaching_response(context, result)

        # Step 5: MEMORY - store interaction
        await self._store_memory(context, result)
        result.memory_stored = True

        # Step 6: SUMMARY
        result.step_completed = CoachingStep.END

        return result

    def route_context(self, context: CoachingContext) -> CoachingContext:
        """Route the message to the appropriate coaching intent.

        Uses pattern matching (production: NLI classifier).

        Args:
            context: The coaching context

        Returns:
            Updated context with intent set
        """
        message_lower = context.message.lower().strip()

        # Intent detection via heuristic patterns
        # Production: replace with NLI classifier
        stuck_patterns = [
            "stuck", "can't start", "cant start", "frozen",
            "overwhelmed", "blocked", "don't know where",
            "don't know how", "unable to",
        ]
        planning_patterns = [
            "plan", "priority", "priorities", "today",
            "schedule", "organize", "what should",
        ]
        reflection_patterns = [
            "review", "reflect", "how did", "went well",
            "went wrong", "learned", "noticed",
        ]
        motivation_patterns = [
            "motivation", "motivate", "inspire",
            "struggling", "hard time", "difficult",
        ]
        accountability_patterns = [
            "progress", "status", "check in",
            "accountability", "done", "completed",
        ]
        energy_patterns = [
            "energy", "tired", "exhausted", "spoons",
            "capacity", "how am i", "feeling",
        ]

        if any(p in message_lower for p in stuck_patterns):
            context.intent = CoachingIntent.STUCK
        elif any(p in message_lower for p in planning_patterns):
            context.intent = CoachingIntent.PLANNING
        elif any(p in message_lower for p in reflection_patterns):
            context.intent = CoachingIntent.REFLECTION
        elif any(p in message_lower for p in motivation_patterns):
            context.intent = CoachingIntent.MOTIVATION
        elif any(p in message_lower for p in accountability_patterns):
            context.intent = CoachingIntent.ACCOUNTABILITY
        elif any(p in message_lower for p in energy_patterns):
            context.intent = CoachingIntent.ENERGY_CHECK
        else:
            context.intent = CoachingIntent.GENERAL

        return context

    def enrich_context(self, context: CoachingContext) -> CoachingContext:
        """Enrich the coaching context with additional data.

        In production, this pulls from:
        - PatternDetectionService
        - EnergySystem
        - NeurostateService
        - GoalService

        For now, uses provided data directly.

        Args:
            context: The coaching context

        Returns:
            Enriched context
        """
        # Add segment-specific metadata
        if context.segment_ctx:
            context.metadata["burnout_model"] = (
                context.segment_ctx.neuro.burnout_model
            )
            context.metadata["inertia_type"] = (
                context.segment_ctx.neuro.inertia_type
            )
            context.metadata["energy_assessment"] = (
                context.segment_ctx.neuro.energy_assessment
            )
            context.metadata["sensory_accumulation"] = (
                context.segment_ctx.neuro.sensory_accumulation
            )

        return context

    async def generate_coaching_response(
        self,
        context: CoachingContext,
        result: CoachingResult,
    ) -> CoachingResult:
        """Generate coaching response with 4-tier fallback.

        Tier 1: Optimized Artifact (pre-built templates)
        Tier 2: DSPy (prompt optimization) -- future
        Tier 3: PydanticAI (structured LLM) -- future
        Tier 4: Placeholder (deterministic fallback)

        Args:
            context: The enriched coaching context
            result: The coaching result to populate

        Returns:
            Updated CoachingResult with response text
        """
        # Tier 1: Optimized Artifact
        text = self._try_optimized_artifact(context)
        if text:
            result.text = text
            result.tier_used = CoachingTier.OPTIMIZED_ARTIFACT
            result.confidence = 0.85
            return result

        # Tier 2: DSPy (future implementation)
        text = await self._try_dspy(context)
        if text:
            result.text = text
            result.tier_used = CoachingTier.DSPY
            result.confidence = 0.90
            return result

        # Tier 3: PydanticAI (future implementation)
        text = await self._try_pydantic_ai(context)
        if text:
            result.text = text
            result.tier_used = CoachingTier.PYDANTIC_AI
            result.confidence = 0.88
            return result

        # Tier 4: Placeholder (always available)
        result.text = self._placeholder_response(context)
        result.tier_used = CoachingTier.PLACEHOLDER
        result.confidence = 0.60
        return result

    def _try_optimized_artifact(
        self, context: CoachingContext
    ) -> str | None:
        """Try to get a response from optimized artifacts (Tier 1).

        Uses segment-specific coaching signatures.

        Args:
            context: The coaching context

        Returns:
            Response text or None if not available
        """
        if not context.segment_ctx:
            return None

        segment_code = context.segment_ctx.core.code
        intent = context.intent.value

        signatures = COACHING_SIGNATURES.get(segment_code)
        if not signatures:
            return None

        text = signatures.get(intent)
        return text

    async def _try_dspy(
        self, context: CoachingContext
    ) -> str | None:
        """Try to get a response from DSPy (Tier 2).

        Future implementation: DSPy-optimized prompts.

        Args:
            context: The coaching context

        Returns:
            Response text or None if not available
        """
        # Future: DSPy integration
        # from dspy import Predict
        # signature = self._get_dspy_signature(context)
        # result = await Predict(signature)(context=context)
        return None

    async def _try_pydantic_ai(
        self, context: CoachingContext
    ) -> str | None:
        """Try to get a response from PydanticAI (Tier 3).

        Future implementation: PydanticAI structured output.

        Args:
            context: The coaching context

        Returns:
            Response text or None if not available
        """
        # Future: PydanticAI integration
        # from pydantic_ai import Agent
        # agent = Agent("anthropic:claude-3-5-sonnet", ...)
        # result = await agent.run(context.message)
        return None

    def _placeholder_response(
        self, context: CoachingContext
    ) -> str:
        """Deterministic placeholder response (Tier 4).

        Always available as a fallback.

        Args:
            context: The coaching context

        Returns:
            Response text
        """
        responses: dict[CoachingIntent, str] = {
            CoachingIntent.STUCK: (
                "I hear that you're stuck. "
                "Let's take it one small step at a time."
            ),
            CoachingIntent.PLANNING: (
                "Let's figure out what's most important today."
            ),
            CoachingIntent.REFLECTION: (
                "Take a moment to notice what went well today."
            ),
            CoachingIntent.MOTIVATION: (
                "You've made progress. Let's build on it."
            ),
            CoachingIntent.ACCOUNTABILITY: (
                "Let's check in on where things stand."
            ),
            CoachingIntent.ENERGY_CHECK: (
                "How's your energy right now?"
            ),
            CoachingIntent.GENERAL: (
                "I'm here to help. What would be most useful?"
            ),
        }
        return responses.get(context.intent, responses[CoachingIntent.GENERAL])

    async def _apply_knowledge(
        self, context: CoachingContext
    ) -> CoachingContext:
        """Apply knowledge retrieval to context.

        Future: Qdrant vector search + Neo4j graph queries.

        Args:
            context: The coaching context

        Returns:
            Context enriched with knowledge
        """
        # Future: Knowledge retrieval
        # relevant_findings = await qdrant.search(context.message, segment=...)
        # context.metadata["knowledge"] = relevant_findings
        return context

    async def _store_memory(
        self,
        context: CoachingContext,
        result: CoachingResult,
    ) -> None:
        """Store the interaction in memory.

        Future: Letta memory service.
        For now: in-memory storage.

        Args:
            context: The coaching context
            result: The coaching result
        """
        if context.user_id not in self._memory:
            self._memory[context.user_id] = []

        self._memory[context.user_id].append({
            "message": context.message,
            "intent": context.intent.value,
            "response": result.text,
            "tier": result.tier_used.value,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        # Keep only last 100 interactions per user
        if len(self._memory[context.user_id]) > 100:
            self._memory[context.user_id] = (
                self._memory[context.user_id][-100:]
            )

    def export_user_data(self, user_id: int) -> dict[str, Any]:
        """GDPR export for coaching data.

        Args:
            user_id: The user's unique identifier

        Returns:
            All coaching data for the user
        """
        memory = self._memory.get(user_id, [])
        return {
            "coaching_interactions": memory,
        }

    def delete_user_data(self, user_id: int) -> None:
        """GDPR delete for coaching data.

        Args:
            user_id: The user's unique identifier
        """
        self._memory.pop(user_id, None)
