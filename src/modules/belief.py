"""
Limiting Beliefs Module for Aurora Sun V1.

This module handles the surfacing, challenging, and reframing of limiting beliefs.
Uses Socratic questioning adapted per neurotype segment.

Key features:
- Natural language surfacing of beliefs
- Auto-detection from patterns (user avoids same goal)
- Socratic questioning (segment-adapted via SegmentContext)
- Evidence collection (supporting and contradicting)
- ContradictionIndex tracking
- Planning integration hooks

State machine: SURFACE -> IDENTIFY -> EVIDENCE_FOR -> EVIDENCE_AGAINST -> CHALLENGE -> REFRAME -> TRACK -> DONE

Reference:
- ARCHITECTURE.md Section 2 (Module System)
- ROADMAP.md 3.5: Limiting Beliefs Module
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.gdpr_mixin import GDPRModuleMixin
from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse
from src.lib.encrypted_field import EncryptedFieldDescriptor
from src.lib.encryption import DataClassification
from src.models.base import Base

if TYPE_CHECKING:
    pass


# =============================================================================
# Belief States
# =============================================================================

class BeliefState:
    """State machine states for the Limiting Beliefs Module."""

    SURFACE = "SURFACE"
    IDENTIFY = "IDENTIFY"
    EVIDENCE_FOR = "EVIDENCE_FOR"
    EVIDENCE_AGAINST = "EVIDENCE_AGAINST"
    CHALLENGE = "CHALLENGE"
    REFRAME = "REFRAME"
    TRACK = "TRACK"
    DONE = "DONE"

    ALL: list[str] = [
        SURFACE,
        IDENTIFY,
        EVIDENCE_FOR,
        EVIDENCE_AGAINST,
        CHALLENGE,
        REFRAME,
        TRACK,
        DONE,
    ]


# =============================================================================
# SQLAlchemy Models
# =============================================================================

class Belief(Base):
    """
    Belief model for tracking user beliefs.

    Data Classification: ART_9_SPECIAL (mental health data)
    - belief_text: Encrypted with AES-256-GCM + field-level salt
      (GDPR Art. 9 special category: mental health beliefs)

    The ContradictionIndex tracks the ratio of contradicting to total evidence.
    Higher values indicate the belief is being successfully challenged.
    """

    __tablename__ = "beliefs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    _belief_text_plaintext = Column("belief_text", Text, nullable=False)
    belief_type = Column(String(20), nullable=False, default="limiting")  # limiting | empowering
    is_active = Column(Integer, default=1)  # 1 = active, 0 = resolved/inactive
    contradiction_index = Column(Float, default=0.0)  # 0.0-1.0
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Encrypted field (fail-hard, no plaintext fallback)
    belief_text = EncryptedFieldDescriptor(
        plaintext_attr="_belief_text_plaintext",
        field_name="belief_text",
        classification=DataClassification.ART_9_SPECIAL,
    )

    # Relationships
    evidence_items = relationship("BeliefEvidence", back_populates="belief", lazy="select")


class BeliefEvidence(Base):
    """
    Evidence for or against a belief.

    Data Classification: ART_9_SPECIAL (mental health data)
    - evidence_text: Encrypted with AES-256-GCM + field-level salt

    Evidence type is either 'supporting' (confirms the belief) or
    'contradicting' (challenges the belief). The ContradictionIndex
    is recalculated when new evidence is added.
    """

    __tablename__ = "belief_evidence"

    id = Column(Integer, primary_key=True)
    belief_id = Column(Integer, ForeignKey("beliefs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    _evidence_text_plaintext = Column("evidence_text", Text, nullable=False)
    evidence_type = Column(String(20), nullable=False)  # supporting | contradicting
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Encrypted field (fail-hard, no plaintext fallback)
    evidence_text = EncryptedFieldDescriptor(
        plaintext_attr="_evidence_text_plaintext",
        field_name="evidence_text",
        classification=DataClassification.ART_9_SPECIAL,
    )

    # Relationships
    belief = relationship("Belief", back_populates="evidence_items")


# =============================================================================
# Session Data
# =============================================================================

@dataclass
class BeliefSession:
    """Session data for the belief exploration flow."""

    belief_text: str = ""
    belief_type: str = "limiting"
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    challenge_response: str = ""
    reframe: str = ""


# =============================================================================
# Belief Module
# =============================================================================

class BeliefModule(GDPRModuleMixin):
    """
    Limiting Beliefs Module for Aurora Sun V1.

    Uses Socratic questioning to surface, challenge, and reframe limiting beliefs.

    Segment-adaptive behavior via SegmentContext fields:
    - routine_anchoring (AU): Structured, step-by-step questioning. Clear evidence
      categories. Predictable flow.
    - channel_dominance_enabled (AH): Channel-aware pacing. Integrity trigger
      check. Spoon-drawer integration for energy management.
    - icnu_enabled (AD/AH): Brief, engaging questions. Quick wins.
      Dopamine-positive reframing.
    - Default (NT): Standard Socratic method.

    ContradictionIndex: ratio of contradicting evidence to total evidence.
    Used to track progress in challenging a belief over time.
    """

    name: str = "belief"
    intents: list[str] = [
        "belief.surface",
        "belief.explore",
        "belief.challenge",
        "belief.list",
        "belief.reframe",
    ]
    pillar: str = "second_brain"

    def __init__(self) -> None:
        """Initialize the Belief Module."""
        self._sessions: dict[int, BeliefSession] = {}

    # =========================================================================
    # Module Protocol Implementation
    # =========================================================================

    async def on_enter(self, ctx: ModuleContext) -> ModuleResponse:
        """
        Start the belief exploration flow.

        Segment-specific entry:
        - routine_anchoring: Structured, predictable intro
        - channel_dominance_enabled: Flexible, channel-aware
        - icnu_enabled: Engaging, brief
        - Default: Standard
        """
        features = ctx.segment_context.features

        if features.routine_anchoring:
            text = (
                "Let's explore a belief that might be holding you back. "
                "I'll guide you through a structured process: identify the belief, "
                "examine evidence, challenge it, and create a new perspective. "
                "What belief would you like to examine?"
            )
        elif features.channel_dominance_enabled:
            text = (
                "Let's work through a limiting belief together. "
                "We'll go at your pace - I'll check in on your energy "
                "as we go. What belief is on your mind?"
            )
        elif features.icnu_enabled:
            text = (
                "Time to challenge a belief! This is powerful work. "
                "What's a thought or belief that keeps showing up "
                "and holding you back?"
            )
        else:
            text = (
                "Let's explore a belief that might be limiting you. "
                "What thought or assumption keeps coming up?"
            )

        self._sessions[ctx.user_id] = BeliefSession()

        return ModuleResponse(
            text=text,
            next_state=BeliefState.SURFACE,
        )

    async def handle(
        self,
        message: str,
        ctx: ModuleContext,
    ) -> ModuleResponse:
        """
        Handle user message based on current state.

        Routes to the appropriate state handler.
        """
        session = self._sessions.get(ctx.user_id)
        if session is None:
            return await self.on_enter(ctx)

        _HandlerType = Callable[
            [str, ModuleContext, BeliefSession],
            Awaitable[ModuleResponse],
        ]
        state_handlers: dict[str, _HandlerType] = {
            BeliefState.SURFACE: self._handle_surface,
            BeliefState.IDENTIFY: self._handle_identify,
            BeliefState.EVIDENCE_FOR: self._handle_evidence_for,
            BeliefState.EVIDENCE_AGAINST: self._handle_evidence_against,
            BeliefState.CHALLENGE: self._handle_challenge,
            BeliefState.REFRAME: self._handle_reframe,
            BeliefState.TRACK: self._handle_track,
        }

        handler = state_handlers.get(ctx.state)
        if handler is not None:
            return await handler(message, ctx, session)

        return await self.on_enter(ctx)

    async def on_exit(self, ctx: ModuleContext) -> None:
        """Clean up session data when leaving the belief module."""
        self._sessions.pop(ctx.user_id, None)

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        """
        Return hooks for the daily workflow.

        planning_enrichment: Surface blocking beliefs before planning.
        """
        return DailyWorkflowHooks(
            planning_enrichment=self._surface_blocking_beliefs,
            hook_name="belief",
            priority=30,
        )

    def _gdpr_data_categories(self) -> dict[str, list[str]]:
        """Declare belief data categories for GDPR (ART_9_SPECIAL)."""
        return {
            "beliefs": ["belief_text", "belief_type", "contradiction_index"],
            "belief_evidence": ["evidence_text", "evidence_type"],
        }

    # =========================================================================
    # State Handlers
    # =========================================================================

    async def _handle_surface(
        self,
        message: str,
        ctx: ModuleContext,
        session: BeliefSession,
    ) -> ModuleResponse:
        """Handle SURFACE state - capture the raw belief expression."""
        session.belief_text = message.strip()

        # Detect if this is a limiting or empowering belief
        session.belief_type = self._classify_belief(session.belief_text)

        features = ctx.segment_context.features

        if session.belief_type == "empowering":
            text = (
                f"That sounds like a positive belief: '{session.belief_text}'\n\n"
                f"Would you like to explore a limiting belief instead, "
                f"or strengthen this empowering one?"
            )
            return ModuleResponse(
                text=text,
                next_state=BeliefState.IDENTIFY,
            )

        # Limiting belief - proceed with Socratic questioning
        if features.routine_anchoring:
            text = (
                f"You've identified: '{session.belief_text}'\n\n"
                f"Let me confirm: Is this a belief you want to examine and "
                f"potentially change? I'll walk through the evidence step by step."
            )
        elif features.icnu_enabled:
            text = (
                f"Got it: '{session.belief_text}'\n\n"
                f"Let's dig into this. Is this something you've believed "
                f"for a long time? Let's understand where it comes from."
            )
        else:
            text = (
                f"I hear you: '{session.belief_text}'\n\n"
                f"Let's examine this belief together. "
                f"Would you like to explore the evidence for and against it?"
            )

        return ModuleResponse(
            text=text,
            next_state=BeliefState.IDENTIFY,
        )

    async def _handle_identify(
        self,
        message: str,
        ctx: ModuleContext,
        session: BeliefSession,
    ) -> ModuleResponse:
        """Handle IDENTIFY state - confirm the belief and move to evidence collection."""
        import re

        message_lower = message.lower().strip()

        yes_pattern = re.compile(r"\b(yes|y|ja|sure|ok|okay|explore|examine|change|limiting)\b")

        if yes_pattern.search(message_lower):
            text = (
                f"Let's start with evidence that supports this belief.\n\n"
                f"Belief: '{session.belief_text}'\n\n"
                f"What experiences or facts make you think this is true? "
                f"Share as many as come to mind."
            )
            return ModuleResponse(
                text=text,
                next_state=BeliefState.EVIDENCE_FOR,
            )

        # User wants to explore something else
        return ModuleResponse(
            text="What belief would you like to explore instead?",
            next_state=BeliefState.SURFACE,
        )

    async def _handle_evidence_for(
        self,
        message: str,
        ctx: ModuleContext,
        session: BeliefSession,
    ) -> ModuleResponse:
        """Handle EVIDENCE_FOR state - collect supporting evidence."""
        # Parse evidence items (split by newlines or "and")
        evidence_items = self._parse_evidence(message)
        session.evidence_for.extend(evidence_items)

        count = len(session.evidence_for)

        features = ctx.segment_context.features

        if features.routine_anchoring:
            text = (
                f"Noted {count} piece(s) of supporting evidence.\n\n"
                f"Now, let's look at the other side. What experiences or facts "
                f"contradict this belief? When has the opposite been true?"
            )
        elif features.icnu_enabled:
            text = (
                f"Okay, {count} reason(s) supporting this belief.\n\n"
                f"Now for the interesting part - can you think of times "
                f"when this belief was wrong? When did the opposite happen?"
            )
        else:
            text = (
                f"I've noted {count} piece(s) of supporting evidence.\n\n"
                f"Now let's examine the other side. What evidence contradicts "
                f"this belief? When has it not been true?"
            )

        return ModuleResponse(
            text=text,
            next_state=BeliefState.EVIDENCE_AGAINST,
        )

    async def _handle_evidence_against(
        self,
        message: str,
        ctx: ModuleContext,
        session: BeliefSession,
    ) -> ModuleResponse:
        """Handle EVIDENCE_AGAINST state - collect contradicting evidence."""
        evidence_items = self._parse_evidence(message)
        session.evidence_against.extend(evidence_items)

        # Calculate ContradictionIndex
        contradiction_index = self.calculate_contradiction_index(
            supporting_count=len(session.evidence_for),
            contradicting_count=len(session.evidence_against),
        )

        features = ctx.segment_context.features

        if features.icnu_enabled:
            text = (
                f"Interesting! You found {len(session.evidence_against)} "
                f"piece(s) of contradicting evidence.\n\n"
                f"Contradiction Index: {contradiction_index:.0%}\n\n"
                f"Looking at both sides, what stands out to you? "
                f"Is this belief as solid as it seemed?"
            )
        elif features.routine_anchoring:
            text = (
                f"Evidence summary:\n"
                f"- Supporting: {len(session.evidence_for)} item(s)\n"
                f"- Contradicting: {len(session.evidence_against)} item(s)\n"
                f"- Contradiction Index: {contradiction_index:.0%}\n\n"
                f"Based on this evidence, what conclusion do you draw about "
                f"this belief?"
            )
        else:
            text = (
                f"Evidence summary:\n"
                f"- For: {len(session.evidence_for)}\n"
                f"- Against: {len(session.evidence_against)}\n"
                f"- Contradiction Index: {contradiction_index:.0%}\n\n"
                f"What do you notice when you see both sides?"
            )

        return ModuleResponse(
            text=text,
            next_state=BeliefState.CHALLENGE,
            metadata={"contradiction_index": contradiction_index},
        )

    async def _handle_challenge(
        self,
        message: str,
        ctx: ModuleContext,
        session: BeliefSession,
    ) -> ModuleResponse:
        """Handle CHALLENGE state - process the user's reflection and guide reframing."""
        session.challenge_response = message.strip()

        features = ctx.segment_context.features

        if features.routine_anchoring:
            text = (
                "Thank you for that reflection.\n\n"
                "Now let's create a new, more balanced belief. "
                "Based on the evidence, what would be a fairer way to "
                "think about this?\n\n"
                "Try starting with: 'I can...' or 'Sometimes I...' or "
                "'Even though..., I...'"
            )
        elif features.icnu_enabled:
            text = (
                "Great insight!\n\n"
                "Now for the reframe - what's a more empowering way to "
                "think about this? Make it something that excites you!\n\n"
                "Try: 'I am someone who...' or 'I can...'"
            )
        else:
            text = (
                "Good reflection.\n\n"
                "Let's create a reframe - a more balanced and accurate belief "
                "to replace the limiting one. What would that be?"
            )

        return ModuleResponse(
            text=text,
            next_state=BeliefState.REFRAME,
        )

    async def _handle_reframe(
        self,
        message: str,
        ctx: ModuleContext,
        session: BeliefSession,
    ) -> ModuleResponse:
        """Handle REFRAME state - capture reframe and show summary."""
        session.reframe = message.strip()

        contradiction_index = self.calculate_contradiction_index(
            supporting_count=len(session.evidence_for),
            contradicting_count=len(session.evidence_against),
        )

        text = (
            f"Summary:\n\n"
            f"Original belief: '{session.belief_text}'\n"
            f"New perspective: '{session.reframe}'\n\n"
            f"Evidence for: {len(session.evidence_for)} item(s)\n"
            f"Evidence against: {len(session.evidence_against)} item(s)\n"
            f"Contradiction Index: {contradiction_index:.0%}\n\n"
            f"Shall I save this and track the belief over time? (yes/no)"
        )

        return ModuleResponse(
            text=text,
            next_state=BeliefState.TRACK,
            metadata={"contradiction_index": contradiction_index},
        )

    async def _handle_track(
        self,
        message: str,
        ctx: ModuleContext,
        session: BeliefSession,
    ) -> ModuleResponse:
        """Handle TRACK state - save or discard the belief work."""
        import re

        message_lower = message.lower().strip()
        yes_pattern = re.compile(r"\b(yes|y|ja|si|da|yeah|yep|sure|ok|okay|save)\b")
        no_pattern = re.compile(r"\b(no|n|nein|nao|nope|cancel|discard)\b")

        if yes_pattern.search(message_lower):
            from src.core.side_effects import SideEffect, SideEffectType

            contradiction_index = self.calculate_contradiction_index(
                supporting_count=len(session.evidence_for),
                contradicting_count=len(session.evidence_against),
            )

            self._sessions.pop(ctx.user_id, None)

            return ModuleResponse(
                text=(
                    "Belief saved and tracking started. "
                    "I'll periodically check in on this belief and "
                    "help you collect more evidence over time."
                ),
                is_end_of_flow=True,
                next_state=BeliefState.DONE,
                side_effects=[
                    SideEffect(
                        effect_type=SideEffectType.SAVE_BELIEF,
                        payload={
                            "belief_text": session.belief_text,
                            "belief_type": session.belief_type,
                            "evidence_for": session.evidence_for,
                            "evidence_against": session.evidence_against,
                            "reframe": session.reframe,
                            "contradiction_index": contradiction_index,
                        },
                    )
                ],
            )

        elif no_pattern.search(message_lower):
            self._sessions.pop(ctx.user_id, None)
            return ModuleResponse(
                text="No problem. The work you did today is still valuable. Come back anytime.",
                is_end_of_flow=True,
                next_state=BeliefState.DONE,
            )

        else:
            return ModuleResponse(
                text="Would you like to save this belief work? (yes/no)",
                next_state=BeliefState.TRACK,
            )

    # =========================================================================
    # Daily Workflow Hooks
    # =========================================================================

    async def _surface_blocking_beliefs(
        self,
        ctx: ModuleContext,
    ) -> str | None:
        """
        Surface beliefs that might block current goals.

        Called during planning_enrichment to flag limiting beliefs
        that are relevant to today's planned work.
        """
        # TODO: Query database for active limiting beliefs
        # TODO: Match against today's planned goals/tasks
        return None

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _classify_belief(self, belief_text: str) -> str:
        """
        Classify a belief as limiting or empowering.

        Uses keyword analysis. In production, this would be enhanced
        with LLM classification.

        Args:
            belief_text: The raw belief text

        Returns:
            "limiting" or "empowering"
        """
        limiting_keywords = [
            "can't", "cannot", "never", "won't", "unable",
            "impossible", "too", "not enough", "don't deserve",
            "not good enough", "always fail", "never succeed",
            "not smart", "not capable", "hopeless", "useless",
            "stuck", "broken", "damaged",
        ]

        empowering_keywords = [
            "i can", "i am able", "i deserve", "i'm capable",
            "i'm strong", "i believe", "i trust", "i'm growing",
            "i'm learning", "i will", "possible", "capable",
        ]

        text_lower = belief_text.lower()

        limiting_score = sum(1 for kw in limiting_keywords if kw in text_lower)
        empowering_score = sum(1 for kw in empowering_keywords if kw in text_lower)

        if empowering_score > limiting_score:
            return "empowering"
        return "limiting"

    def _parse_evidence(self, message: str) -> list[str]:
        """
        Parse evidence items from user message.

        Splits by newlines, numbered lists, or bullet points.

        Args:
            message: Raw user message

        Returns:
            List of evidence strings
        """
        lines = message.strip().split("\n")
        evidence: list[str] = []

        for line in lines:
            line = line.strip()
            # Remove numbering/bullets
            if line and (line[0].isdigit() or line.startswith("-") or line.startswith("*")):
                line = line.lstrip("0123456789.-* ").strip()
            if line and len(line) > 2:
                evidence.append(line)

        # If no line breaks, treat entire message as one evidence item
        if not evidence and message.strip():
            evidence.append(message.strip())

        return evidence

    @staticmethod
    def calculate_contradiction_index(
        supporting_count: int,
        contradicting_count: int,
    ) -> float:
        """
        Calculate the ContradictionIndex.

        ContradictionIndex = contradicting / (supporting + contradicting)

        A higher index means more contradicting evidence has been found,
        suggesting the belief is being successfully challenged.

        Args:
            supporting_count: Number of supporting evidence items
            contradicting_count: Number of contradicting evidence items

        Returns:
            ContradictionIndex as 0.0-1.0
        """
        total = supporting_count + contradicting_count
        if total == 0:
            return 0.0
        return contradicting_count / total


# =============================================================================
# Module Export
# =============================================================================

__all__ = [
    "BeliefModule",
    "BeliefState",
    "BeliefSession",
    "Belief",
    "BeliefEvidence",
]
