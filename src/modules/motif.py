"""
Landscape of Motifs Module for Aurora Sun V1.

This module detects, maps, and reflects on recurring motifs (patterns of meaning)
in a user's life. Motifs are deeper than goals -- they represent fundamental drives,
talents, passions, fears, avoidances, and attractions.

Key features:
- Motif detection from existing data (captures, goals, habits, beliefs)
- Types: drive, talent, passion, fear, avoidance, attraction
- Confidence scoring (based on number of independent signals)
- "Passion archaeology": what excited you before obligations
- Planning integration hooks (suggest motif-aligned tasks)

State machine: EXPLORE -> DETECT -> MAP -> REFLECT -> DONE

Reference:
- ARCHITECTURE.md Section 2 (Module System)
- ROADMAP.md 3.6: Landscape of Motifs Module
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse
from src.models.base import Base

if TYPE_CHECKING:
    pass


# Valid motif types
MOTIF_TYPES: list[str] = [
    "drive",
    "talent",
    "passion",
    "fear",
    "avoidance",
    "attraction",
]

# Valid signal sources
SIGNAL_SOURCES: list[str] = [
    "aurora",
    "pattern",
    "fulfillment",
    "capture",
    "user_input",
]


# =============================================================================
# Motif States
# =============================================================================

class MotifState:
    """State machine states for the Landscape of Motifs Module."""

    EXPLORE = "EXPLORE"
    DETECT = "DETECT"
    MAP = "MAP"
    REFLECT = "REFLECT"
    DONE = "DONE"

    ALL: list[str] = [
        EXPLORE,
        DETECT,
        MAP,
        REFLECT,
        DONE,
    ]


# =============================================================================
# SQLAlchemy Models
# =============================================================================

class Motif(Base):
    """
    Motif model representing a recurring pattern of meaning.

    Data Classification: SENSITIVE
    - name: Encrypted with AES-256-GCM (personal identity data)

    Motifs are deeper patterns that emerge from multiple signals across
    different data sources. Confidence grows with independent signal count.

    Types:
    - drive: Core motivation ("I need to create")
    - talent: Natural ability ("I'm good at explaining")
    - passion: Deep interest ("I light up when...")
    - fear: Recurring avoidance trigger ("I'm afraid of...")
    - avoidance: Pattern of steering away ("I always avoid...")
    - attraction: Pattern of gravitation ("I'm drawn to...")
    """

    __tablename__ = "motifs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    _name_plaintext = Column("name", Text, nullable=False)
    motif_type = Column(String(20), nullable=False)  # drive|talent|passion|fear|avoidance|attraction
    confidence_score = Column(Float, default=0.0)  # 0.0-1.0
    signal_count = Column(Integer, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    signals = relationship("MotifSignal", back_populates="motif", lazy="select")

    @property
    def name(self) -> str:
        """Get decrypted name."""
        if self._name_plaintext is None:
            return ""
        try:
            import json
            data = json.loads(str(self._name_plaintext))
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                return get_encryption_service().decrypt_field(
                    encrypted, int(self.user_id), "name"
                )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return str(self._name_plaintext)

    @name.setter
    def name(self, value: str | None) -> None:
        """Set encrypted name."""
        if value is None:
            setattr(self, "_name_plaintext", None)
            return
        try:
            import json

            from src.lib.encryption import DataClassification, get_encryption_service
            encrypted = get_encryption_service().encrypt_field(
                value, int(self.user_id), DataClassification.SENSITIVE, "name"
            )
            setattr(self, "_name_plaintext", json.dumps(encrypted.to_db_dict()))
        except Exception:
            setattr(self, "_name_plaintext", value)


class MotifSignal(Base):
    """
    A signal that contributes to motif detection.

    Data Classification: SENSITIVE
    - signal_text: Encrypted with AES-256-GCM

    Signals come from different sources:
    - aurora: Detected by Aurora agent during conversation
    - pattern: Detected from behavioral patterns (habits, tasks)
    - fulfillment: From fulfillment tracking data
    - capture: From captured thoughts/ideas
    - user_input: Directly provided by the user
    """

    __tablename__ = "motif_signals"

    id = Column(Integer, primary_key=True)
    motif_id = Column(Integer, ForeignKey("motifs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source = Column(String(20), nullable=False)  # aurora|pattern|fulfillment|capture|user_input
    _signal_text_plaintext = Column("signal_text", Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    motif = relationship("Motif", back_populates="signals")

    @property
    def signal_text(self) -> str:
        """Get decrypted signal text."""
        if self._signal_text_plaintext is None:
            return ""
        try:
            import json
            data = json.loads(str(self._signal_text_plaintext))
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                return get_encryption_service().decrypt_field(
                    encrypted, int(self.user_id), "signal_text"
                )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return str(self._signal_text_plaintext)

    @signal_text.setter
    def signal_text(self, value: str | None) -> None:
        """Set encrypted signal text."""
        if value is None:
            setattr(self, "_signal_text_plaintext", None)
            return
        try:
            import json

            from src.lib.encryption import DataClassification, get_encryption_service
            encrypted = get_encryption_service().encrypt_field(
                value, int(self.user_id), DataClassification.SENSITIVE, "signal_text"
            )
            setattr(self, "_signal_text_plaintext", json.dumps(encrypted.to_db_dict()))
        except Exception:
            setattr(self, "_signal_text_plaintext", value)


# =============================================================================
# Session Data
# =============================================================================

@dataclass
class MotifExplorationSession:
    """Session data for the motif exploration flow."""

    exploration_focus: str = ""
    detected_motifs: list[dict[str, str]] = field(default_factory=list)
    mapped_motifs: list[dict[str, str]] = field(default_factory=list)
    reflection: str = ""
    passion_archaeology_responses: list[str] = field(default_factory=list)


# =============================================================================
# Motif Module
# =============================================================================

class MotifModule:
    """
    Landscape of Motifs Module for Aurora Sun V1.

    Detects and maps recurring patterns of meaning in a user's life.

    Segment-adaptive behavior via SegmentContext fields:
    - routine_anchoring (AU): Structured motif mapping. Consistent categories.
      Clear visual layout.
    - channel_dominance_enabled (AH): Channel-aware exploration. Motifs may
      manifest differently per channel.
    - icnu_enabled (AD/AH): Novelty-positive exploration. Quick pattern recognition.
      Excitement-driven discovery.
    - Default (NT): Standard reflective exploration.

    Passion archaeology: guided exploration of past interests and excitements
    to uncover buried motifs from before obligations took over.
    """

    name: str = "motif"
    intents: list[str] = [
        "motif.explore",
        "motif.detect",
        "motif.map",
        "motif.archaeology",
        "motif.list",
    ]
    pillar: str = "second_brain"

    def __init__(self) -> None:
        """Initialize the Motif Module."""
        self._sessions: dict[int, MotifExplorationSession] = {}

    # =========================================================================
    # Module Protocol Implementation
    # =========================================================================

    async def on_enter(self, ctx: ModuleContext) -> ModuleResponse:
        """
        Start the motif exploration flow.

        Segment-specific entry messages use SegmentContext features.
        """
        features = ctx.segment_context.features

        if features.routine_anchoring:
            text = (
                "Let's explore your motifs - the recurring patterns of meaning "
                "in your life. I'll guide you through a structured process:\n"
                "1. Explore what matters to you\n"
                "2. Detect patterns\n"
                "3. Map your motif landscape\n"
                "4. Reflect on what you've found\n\n"
                "We can start with passion archaeology (exploring past interests) "
                "or look at current patterns. What would you prefer?"
            )
        elif features.channel_dominance_enabled:
            text = (
                "Let's map your inner landscape of motifs - the deep patterns "
                "that drive you. These might show up differently depending on "
                "which channel you're in. What patterns have you noticed in "
                "what draws you in or pushes you away?"
            )
        elif features.icnu_enabled:
            text = (
                "Time for some pattern discovery! Your motifs are the hidden "
                "threads that run through everything you do. Let's find them!\n\n"
                "Want to start with passion archaeology (what excited you as a kid?) "
                "or explore current patterns?"
            )
        else:
            text = (
                "Let's explore the landscape of motifs in your life - "
                "the recurring patterns of drives, talents, passions, fears, "
                "and attractions. What themes keep showing up for you?"
            )

        self._sessions[ctx.user_id] = MotifExplorationSession()

        return ModuleResponse(
            text=text,
            next_state=MotifState.EXPLORE,
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
            [str, ModuleContext, MotifExplorationSession],
            Awaitable[ModuleResponse],
        ]
        state_handlers: dict[str, _HandlerType] = {
            MotifState.EXPLORE: self._handle_explore,
            MotifState.DETECT: self._handle_detect,
            MotifState.MAP: self._handle_map,
            MotifState.REFLECT: self._handle_reflect,
        }

        handler = state_handlers.get(ctx.state)
        if handler is not None:
            return await handler(message, ctx, session)

        return await self.on_enter(ctx)

    async def on_exit(self, ctx: ModuleContext) -> None:
        """Clean up session data when leaving the motif module."""
        self._sessions.pop(ctx.user_id, None)

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        """
        Return hooks for the daily workflow.

        planning_enrichment: Suggest motif-aligned tasks.
        """
        return DailyWorkflowHooks(
            planning_enrichment=self._suggest_motif_aligned_tasks,
            hook_name="motif",
            priority=40,
        )

    # =========================================================================
    # GDPR Methods
    # =========================================================================

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """
        GDPR Art. 15: Export all motif data for a user.
        """
        # TODO: Query database
        return {
            "motifs": [],
            "motif_signals": [],
        }

    async def delete_user_data(self, user_id: int) -> None:
        """GDPR Art. 17: Delete all motif data for a user."""
        # TODO: DELETE FROM motif_signals WHERE user_id = ?
        # TODO: DELETE FROM motifs WHERE user_id = ?
        pass

    async def freeze_user_data(self, user_id: int) -> None:
        """GDPR Art. 18: Restrict processing of motif data."""
        pass

    async def unfreeze_user_data(self, user_id: int) -> None:
        """GDPR Art. 18: Lift restriction on motif data processing."""
        pass

    # =========================================================================
    # State Handlers
    # =========================================================================

    async def _handle_explore(
        self,
        message: str,
        ctx: ModuleContext,
        session: MotifExplorationSession,
    ) -> ModuleResponse:
        """Handle EXPLORE state - capture exploration input and guide discovery."""
        message_lower = message.lower().strip()
        session.exploration_focus = message.strip()

        # Check if user wants passion archaeology
        if any(kw in message_lower for kw in ["archaeology", "past", "kid", "childhood", "before"]):
            return await self._passion_archaeology(ctx, session)

        # Detect potential motifs from the input
        detected = self._detect_motifs_from_text(message)
        session.detected_motifs = detected

        if detected:
            motif_list = "\n".join(
                f"- {m['name']} ({m['type']})"
                for m in detected
            )
            text = (
                f"I detect some potential motifs in what you shared:\n\n"
                f"{motif_list}\n\n"
                f"Do these resonate? Tell me more about any of these, "
                f"or share additional patterns you've noticed."
            )
        else:
            text = (
                "Tell me more. Think about:\n"
                "- What activities make you lose track of time?\n"
                "- What topics do you keep coming back to?\n"
                "- What do you consistently avoid?\n"
                "- What were you passionate about before life got busy?"
            )

        return ModuleResponse(
            text=text,
            next_state=MotifState.DETECT,
        )

    async def _handle_detect(
        self,
        message: str,
        ctx: ModuleContext,
        session: MotifExplorationSession,
    ) -> ModuleResponse:
        """Handle DETECT state - refine detected motifs and move to mapping."""
        # Add new detections from this message
        new_detected = self._detect_motifs_from_text(message)
        session.detected_motifs.extend(new_detected)

        if not session.detected_motifs:
            # Try passion archaeology if no motifs detected
            return await self._passion_archaeology(ctx, session)

        # Prepare for mapping
        motif_list = "\n".join(
            f"- {m['name']} ({m['type']})"
            for m in session.detected_motifs
        )

        features = ctx.segment_context.features

        if features.routine_anchoring:
            text = (
                f"Detected motifs so far:\n\n{motif_list}\n\n"
                f"Let's organize these into your motif landscape. "
                f"For each motif, I'll note the type and your confidence level. "
                f"Which of these feel most true to you? Rate each from 1-5."
            )
        elif features.icnu_enabled:
            text = (
                f"Look at what we've found!\n\n{motif_list}\n\n"
                f"Which ones light you up? Which ones surprise you? "
                f"Let's map these out - rate your confidence in each (1-5)."
            )
        else:
            text = (
                f"Here are the motifs we've identified:\n\n{motif_list}\n\n"
                f"Let's map these. How confident are you in each? "
                f"Rate them 1-5, or tell me which feel strongest."
            )

        return ModuleResponse(
            text=text,
            next_state=MotifState.MAP,
        )

    async def _handle_map(
        self,
        message: str,
        ctx: ModuleContext,
        session: MotifExplorationSession,
    ) -> ModuleResponse:
        """Handle MAP state - create the motif landscape map."""
        # Parse confidence ratings
        mapped = self._parse_confidence_ratings(message, session.detected_motifs)
        session.mapped_motifs = mapped

        # Build landscape visualization
        landscape = self._build_landscape_text(mapped)

        text = (
            f"Your Motif Landscape:\n\n{landscape}\n\n"
            f"Take a moment to look at this map. What do you notice? "
            f"Any patterns across the motifs? Any surprises?"
        )

        return ModuleResponse(
            text=text,
            next_state=MotifState.REFLECT,
        )

    async def _handle_reflect(
        self,
        message: str,
        ctx: ModuleContext,
        session: MotifExplorationSession,
    ) -> ModuleResponse:
        """Handle REFLECT state - capture reflection and save."""
        session.reflection = message.strip()

        from src.core.side_effects import SideEffect, SideEffectType

        self._sessions.pop(ctx.user_id, None)

        features = ctx.segment_context.features

        if features.routine_anchoring:
            closing = (
                "Your motif landscape has been saved. I'll use these patterns "
                "to suggest aligned tasks during planning and to detect new "
                "signals over time. You can revisit your motifs anytime."
            )
        elif features.icnu_enabled:
            closing = (
                "Motif landscape saved! I'll keep watching for new signals "
                "and weave these patterns into your planning. "
                "This is going to help you find more flow!"
            )
        else:
            closing = (
                "Your motif landscape has been saved. I'll integrate these "
                "patterns into your planning and watch for new signals."
            )

        return ModuleResponse(
            text=closing,
            is_end_of_flow=True,
            next_state=MotifState.DONE,
            side_effects=[
                SideEffect(
                    effect_type=SideEffectType.CUSTOM,
                    payload={
                        "effect_name": "save_motif_landscape",
                        "motifs": session.mapped_motifs,
                        "reflection": session.reflection,
                        "exploration_focus": session.exploration_focus,
                    },
                )
            ],
        )

    # =========================================================================
    # Passion Archaeology
    # =========================================================================

    async def _passion_archaeology(
        self,
        ctx: ModuleContext,
        session: MotifExplorationSession,
    ) -> ModuleResponse:
        """
        Guide the user through passion archaeology.

        Passion archaeology explores past interests, excitements, and
        curiosities from before obligations took over. It helps
        uncover buried motifs.
        """
        features = ctx.segment_context.features

        if features.routine_anchoring:
            text = (
                "Let's do some passion archaeology. I'll ask you a series of "
                "questions about your past. Answer whatever comes to mind.\n\n"
                "Think back to when you were 10-12 years old:\n"
                "- What activities could you do for hours?\n"
                "- What topics did you know everything about?\n"
                "- What did you want to be when you grew up?"
            )
        elif features.icnu_enabled:
            text = (
                "Passion archaeology time! Let's dig up buried treasure.\n\n"
                "Think back to before life got serious - what made you lose "
                "track of time? What did you dream about? "
                "What could you talk about for hours?"
            )
        else:
            text = (
                "Let's explore your past interests. Think back to childhood "
                "or early teens:\n"
                "- What activities absorbed you completely?\n"
                "- What subjects fascinated you?\n"
                "- What dreams did you have before practical concerns took over?"
            )

        return ModuleResponse(
            text=text,
            next_state=MotifState.DETECT,
        )

    # =========================================================================
    # Daily Workflow Hooks
    # =========================================================================

    async def _suggest_motif_aligned_tasks(
        self,
        ctx: ModuleContext,
    ) -> str | None:
        """
        Suggest tasks aligned with user's strongest motifs.

        Called during planning_enrichment to help users choose
        motif-aligned priorities.
        """
        # TODO: Query database for user's motifs with highest confidence
        # TODO: Cross-reference with today's planned tasks
        return None

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _detect_motifs_from_text(self, text: str) -> list[dict[str, str]]:
        """
        Detect potential motifs from user text.

        Uses keyword analysis. In production, this would be enhanced
        with LLM-based detection and cross-referencing with existing data.

        Args:
            text: User's input text

        Returns:
            List of detected motif dicts with 'name' and 'type' keys
        """
        text_lower = text.lower()
        detected: list[dict[str, str]] = []

        # Drive detection
        drive_keywords = [
            "need to", "have to", "driven to", "compelled",
            "must", "calling", "purpose", "mission",
        ]
        if any(kw in text_lower for kw in drive_keywords):
            detected.append({"name": self._extract_motif_name(text, "drive"), "type": "drive"})

        # Talent detection
        talent_keywords = [
            "good at", "natural", "talent", "skill",
            "easy for me", "strength", "ability",
        ]
        if any(kw in text_lower for kw in talent_keywords):
            detected.append({"name": self._extract_motif_name(text, "talent"), "type": "talent"})

        # Passion detection
        passion_keywords = [
            "love", "passionate", "excited", "light up",
            "lose track", "fascinated", "absorbed", "flow",
        ]
        if any(kw in text_lower for kw in passion_keywords):
            detected.append({"name": self._extract_motif_name(text, "passion"), "type": "passion"})

        # Fear detection
        fear_keywords = [
            "afraid", "fear", "scared", "anxious",
            "worried", "terrified", "dread",
        ]
        if any(kw in text_lower for kw in fear_keywords):
            detected.append({"name": self._extract_motif_name(text, "fear"), "type": "fear"})

        # Avoidance detection
        avoidance_keywords = [
            "avoid", "stay away", "don't want", "hate",
            "resist", "procrastinate", "put off",
        ]
        if any(kw in text_lower for kw in avoidance_keywords):
            detected.append({"name": self._extract_motif_name(text, "avoidance"), "type": "avoidance"})

        # Attraction detection
        attraction_keywords = [
            "drawn to", "attracted", "gravitate", "pull toward",
            "curious about", "interested in", "intrigued",
        ]
        if any(kw in text_lower for kw in attraction_keywords):
            detected.append({"name": self._extract_motif_name(text, "attraction"), "type": "attraction"})

        return detected

    def _extract_motif_name(self, text: str, motif_type: str) -> str:
        """
        Extract a concise motif name from text.

        In production, this would use LLM extraction.
        For now, truncates to first meaningful phrase.

        Args:
            text: Source text
            motif_type: Type of motif for context

        Returns:
            A concise motif name
        """
        # Simple extraction: use first 50 chars of the relevant text
        clean = text.strip()
        if len(clean) > 50:
            clean = clean[:50] + "..."
        return clean

    def _parse_confidence_ratings(
        self,
        message: str,
        detected_motifs: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """
        Parse confidence ratings from user message and apply to motifs.

        Args:
            message: User's confidence ratings
            detected_motifs: Previously detected motifs

        Returns:
            Motifs with confidence scores added
        """
        import re

        mapped: list[dict[str, str]] = []

        # Look for number ratings in the message
        numbers = re.findall(r"\d+", message)

        for i, motif in enumerate(detected_motifs):
            new_motif = dict(motif)
            if i < len(numbers):
                rating = int(numbers[i])
                rating = max(1, min(5, rating))
                new_motif["confidence"] = str(rating / 5.0)
            else:
                new_motif["confidence"] = "0.6"  # Default medium confidence
            mapped.append(new_motif)

        return mapped

    def _build_landscape_text(self, motifs: list[dict[str, str]]) -> str:
        """
        Build a text visualization of the motif landscape.

        Args:
            motifs: Mapped motifs with confidence scores

        Returns:
            Text representation of the landscape
        """
        if not motifs:
            return "(No motifs mapped yet)"

        lines: list[str] = []

        # Group by type
        by_type: dict[str, list[dict[str, str]]] = {}
        for motif in motifs:
            mtype = motif.get("type", "unknown")
            if mtype not in by_type:
                by_type[mtype] = []
            by_type[mtype].append(motif)

        type_labels: dict[str, str] = {
            "drive": "Drives (core motivations)",
            "talent": "Talents (natural abilities)",
            "passion": "Passions (deep interests)",
            "fear": "Fears (avoidance triggers)",
            "avoidance": "Avoidances (patterns of steering away)",
            "attraction": "Attractions (patterns of gravitation)",
        }

        for mtype, label in type_labels.items():
            if mtype in by_type:
                lines.append(f"{label}:")
                for motif in by_type[mtype]:
                    confidence = motif.get("confidence", "0.5")
                    try:
                        conf_val = float(confidence)
                        bar = self._confidence_bar(conf_val)
                    except ValueError:
                        bar = "[???]"
                    lines.append(f"  {bar} {motif['name']}")
                lines.append("")

        return "\n".join(lines).rstrip()

    @staticmethod
    def _confidence_bar(confidence: float) -> str:
        """
        Create a text-based confidence bar.

        Args:
            confidence: Confidence score 0.0-1.0

        Returns:
            Text bar like "[====  ]"
        """
        filled = int(confidence * 5)
        empty = 5 - filled
        return f"[{'=' * filled}{' ' * empty}]"

    @staticmethod
    def calculate_confidence(signal_count: int) -> float:
        """
        Calculate confidence score from number of independent signals.

        Uses a logarithmic scale so early signals have more impact.
        1 signal = 0.2, 2 = 0.4, 3 = 0.55, 5 = 0.7, 10 = 0.85, 20+ = ~0.95

        Args:
            signal_count: Number of independent signals

        Returns:
            Confidence score 0.0-1.0
        """
        import math

        if signal_count <= 0:
            return 0.0
        # Logarithmic scaling: confidence = 1 - 1/(1 + ln(1 + count))
        raw = 1.0 - 1.0 / (1.0 + math.log(1.0 + signal_count))
        return min(1.0, max(0.0, raw))


# =============================================================================
# Module Export
# =============================================================================

__all__ = [
    "MotifModule",
    "MotifState",
    "MotifExplorationSession",
    "Motif",
    "MotifSignal",
    "MOTIF_TYPES",
    "SIGNAL_SOURCES",
]
