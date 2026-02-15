"""
Narrative Engine for Aurora Agent.

Transforms raw coaching data into meaningful personal stories:
- StoryArc: The overarching user journey
- Chapter: Weekly narrative summaries
- DailyNote: Individual daily observations
- MilestoneCard: Celebration of significant achievements

The narrative engine creates a sense of progression and continuity,
which is critical for neurodivergent users who may struggle with
long-term perspective and self-perception.

Reference: ARCHITECTURE.md Section 5 (Aurora Agent - Narrative Engine)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from src.lib.security import sanitize_for_storage

logger = logging.getLogger(__name__)


class ChapterTheme(StrEnum):
    """Themes for weekly chapters."""

    MOMENTUM = "momentum"           # Making progress, building speed
    DISCOVERY = "discovery"         # Learning new things about self
    RESILIENCE = "resilience"       # Bouncing back from setbacks
    CONSOLIDATION = "consolidation" # Strengthening existing patterns
    TRANSITION = "transition"       # Shifting focus or approach
    RECOVERY = "recovery"          # Healing from burnout or crisis
    BREAKTHROUGH = "breakthrough"   # Major insight or achievement
    EXPLORATION = "exploration"     # Trying new approaches


class NoteType(StrEnum):
    """Types of daily notes."""

    OBSERVATION = "observation"     # Something noticed about behavior
    INSIGHT = "insight"             # A pattern or connection identified
    WIN = "win"                     # Something went well
    CHALLENGE = "challenge"         # Something was difficult
    ENERGY = "energy"               # Energy-related observation
    PATTERN = "pattern"             # Pattern detection result


@dataclass
class DailyNote:
    """A single daily observation within a chapter.

    Daily notes capture what happened, what was observed, and
    what was learned on a specific day.
    """

    note_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: int = 0
    date: str = ""  # ISO date string (YYYY-MM-DD)
    note_type: NoteType = NoteType.OBSERVATION
    content: str = ""
    tags: list[str] = field(default_factory=list)
    energy_level: float | None = None  # 0.0-1.0 if recorded
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "note_id": self.note_id,
            "user_id": self.user_id,
            "date": self.date,
            "note_type": self.note_type.value,
            "content": self.content,
            "tags": self.tags,
            "energy_level": self.energy_level,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass
class MilestoneCard:
    """A celebration card for significant achievements.

    Milestones are displayed to users as positive reinforcement,
    framed in segment-appropriate language (never shame-inducing).
    """

    card_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: int = 0
    title: str = ""
    description: str = ""
    milestone_type: str = ""  # From MilestoneType enum
    achieved_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    celebration_text: str = ""  # Shame-free, segment-appropriate
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "card_id": self.card_id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "milestone_type": self.milestone_type,
            "achieved_at": self.achieved_at,
            "celebration_text": self.celebration_text,
            "metadata": self.metadata,
        }


@dataclass
class Chapter:
    """A weekly narrative chapter.

    Each chapter summarizes one week of the user's journey,
    including key observations, milestones, and the overall
    narrative theme.
    """

    chapter_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: int = 0
    week_number: int = 0  # Week number in user's journey
    start_date: str = ""  # ISO date string
    end_date: str = ""    # ISO date string
    theme: ChapterTheme = ChapterTheme.EXPLORATION
    title: str = ""
    summary: str = ""
    daily_notes: list[DailyNote] = field(default_factory=list)
    milestones: list[MilestoneCard] = field(default_factory=list)
    key_insights: list[str] = field(default_factory=list)
    energy_trend: str = "stable"  # "improving", "stable", "declining"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "chapter_id": self.chapter_id,
            "user_id": self.user_id,
            "week_number": self.week_number,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "theme": self.theme.value,
            "title": self.title,
            "summary": self.summary,
            "daily_notes": [n.to_dict() for n in self.daily_notes],
            "milestones": [m.to_dict() for m in self.milestones],
            "key_insights": self.key_insights,
            "energy_trend": self.energy_trend,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass
class StoryArc:
    """The overarching user journey narrative.

    A StoryArc spans the entire user journey and contains
    all chapters, providing a coherent long-term narrative.
    """

    arc_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: int = 0
    started_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    chapters: list[Chapter] = field(default_factory=list)
    current_theme: ChapterTheme = ChapterTheme.EXPLORATION
    total_milestones: int = 0
    arc_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "arc_id": self.arc_id,
            "user_id": self.user_id,
            "started_at": self.started_at,
            "chapters": [c.to_dict() for c in self.chapters],
            "current_theme": self.current_theme.value,
            "total_milestones": self.total_milestones,
            "arc_summary": self.arc_summary,
            "metadata": self.metadata,
        }


class NarrativeEngine:
    """Narrative Engine for Aurora Agent.

    Transforms raw coaching data into meaningful personal stories.
    Maintains story arcs per user and generates weekly chapters.

    Usage:
        engine = NarrativeEngine()
        chapter = engine.create_chapter(user_id=1, week_number=3, notes=notes)
        arc = engine.get_narrative_arc(user_id=1)
    """

    def __init__(self) -> None:
        """Initialize the narrative engine."""
        # In-memory storage (production: PostgreSQL + encrypted fields)
        self._arcs: dict[int, StoryArc] = {}
        self._notes: dict[int, list[DailyNote]] = {}

    def get_or_create_arc(self, user_id: int) -> StoryArc:
        """Get or create a story arc for a user.

        Args:
            user_id: The user's unique identifier

        Returns:
            The user's StoryArc
        """
        if user_id not in self._arcs:
            self._arcs[user_id] = StoryArc(user_id=user_id)
        return self._arcs[user_id]

    def add_daily_note(
        self,
        user_id: int,
        content: str,
        note_type: NoteType = NoteType.OBSERVATION,
        tags: list[str] | None = None,
        energy_level: float | None = None,
        date: str | None = None,
    ) -> DailyNote:
        """Add a daily note for a user.

        Args:
            user_id: The user's unique identifier
            content: The note content
            note_type: Type of note
            tags: Optional tags for the note
            energy_level: Optional energy level (0.0-1.0)
            date: Optional date (defaults to today)

        Returns:
            The created DailyNote
        """
        if date is None:
            date = datetime.now(UTC).strftime("%Y-%m-%d")

        # Sanitize narrative content before storing (Cypher/query injection prevention)
        sanitized_content, was_modified = sanitize_for_storage(content, max_length=10000)
        if was_modified:
            logger.info(
                "narrative_content_sanitized user_id=%d note_type=%s",
                user_id,
                note_type.value,
            )

        note = DailyNote(
            user_id=user_id,
            date=date,
            note_type=note_type,
            content=sanitized_content,
            tags=tags or [],
            energy_level=energy_level,
        )

        if user_id not in self._notes:
            self._notes[user_id] = []
        self._notes[user_id].append(note)

        return note

    def create_chapter(
        self,
        user_id: int,
        week_number: int,
        notes: list[DailyNote] | None = None,
        milestones: list[MilestoneCard] | None = None,
        title: str | None = None,
        summary: str | None = None,
    ) -> Chapter:
        """Create a new chapter for a user's story arc.

        Args:
            user_id: The user's unique identifier
            week_number: The week number in the user's journey
            notes: Daily notes for this chapter (uses stored notes if None)
            milestones: Milestones achieved this week
            title: Optional chapter title (auto-generated if None)
            summary: Optional chapter summary (auto-generated if None)

        Returns:
            The created Chapter
        """
        # Get notes for this week if not provided
        if notes is None:
            notes = self._notes.get(user_id, [])

        # Determine theme from notes
        theme = self._determine_theme(notes, milestones or [])

        # Calculate date range
        now = datetime.now(UTC)
        end_date = now.strftime("%Y-%m-%d")
        start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")

        # Auto-generate title if not provided
        if title is None:
            title = self._generate_title(theme, week_number)

        # Auto-generate summary if not provided
        if summary is None:
            summary = self._generate_summary(notes, milestones or [], theme)

        # Determine energy trend
        energy_trend = self._calculate_energy_trend(notes)

        # Extract key insights
        key_insights = self._extract_insights(notes)

        chapter = Chapter(
            user_id=user_id,
            week_number=week_number,
            start_date=start_date,
            end_date=end_date,
            theme=theme,
            title=title,
            summary=summary,
            daily_notes=notes,
            milestones=milestones or [],
            key_insights=key_insights,
            energy_trend=energy_trend,
        )

        # Add to arc
        arc = self.get_or_create_arc(user_id)
        arc.chapters.append(chapter)
        arc.current_theme = theme
        arc.total_milestones += len(milestones or [])

        # Clear processed notes
        self._notes[user_id] = []

        return chapter

    def detect_milestone(
        self,
        user_id: int,
        milestone_type: str,
        title: str,
        description: str,
        celebration_text: str = "",
    ) -> MilestoneCard:
        """Create a milestone card for a user achievement.

        Args:
            user_id: The user's unique identifier
            milestone_type: Type of milestone (from MilestoneType enum)
            title: Milestone title
            description: Milestone description
            celebration_text: Shame-free celebration message

        Returns:
            The created MilestoneCard
        """
        if not celebration_text:
            celebration_text = f"You achieved: {title}. This matters."

        card = MilestoneCard(
            user_id=user_id,
            title=title,
            description=description,
            milestone_type=milestone_type,
            celebration_text=celebration_text,
        )
        return card

    def get_narrative_arc(self, user_id: int) -> StoryArc:
        """Get the complete narrative arc for a user.

        Args:
            user_id: The user's unique identifier

        Returns:
            The user's complete StoryArc
        """
        return self.get_or_create_arc(user_id)

    def get_recent_notes(
        self, user_id: int, days: int = 7
    ) -> list[DailyNote]:
        """Get recent daily notes for a user.

        Args:
            user_id: The user's unique identifier
            days: Number of days to look back

        Returns:
            List of recent DailyNote objects
        """
        cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime(
            "%Y-%m-%d"
        )
        notes = self._notes.get(user_id, [])
        return [n for n in notes if n.date >= cutoff]

    def export_user_data(self, user_id: int) -> dict[str, Any]:
        """GDPR export for narrative data.

        Args:
            user_id: The user's unique identifier

        Returns:
            All narrative data for the user
        """
        arc = self._arcs.get(user_id)
        notes = self._notes.get(user_id, [])
        return {
            "narrative_arc": arc.to_dict() if arc else None,
            "pending_notes": [n.to_dict() for n in notes],
        }

    def delete_user_data(self, user_id: int) -> None:
        """GDPR delete for narrative data.

        Args:
            user_id: The user's unique identifier
        """
        self._arcs.pop(user_id, None)
        self._notes.pop(user_id, None)

    def _determine_theme(
        self,
        notes: list[DailyNote],
        milestones: list[MilestoneCard],
    ) -> ChapterTheme:
        """Determine the chapter theme based on notes and milestones.

        Args:
            notes: Daily notes for the chapter
            milestones: Milestones achieved this chapter

        Returns:
            The determined ChapterTheme
        """
        if not notes and not milestones:
            return ChapterTheme.EXPLORATION

        # Check for breakthrough (milestones present)
        if len(milestones) >= 2:
            return ChapterTheme.BREAKTHROUGH

        # Count note types
        type_counts: dict[NoteType, int] = {}
        for note in notes:
            type_counts[note.note_type] = type_counts.get(
                note.note_type, 0
            ) + 1

        # Determine theme from note distribution
        wins = type_counts.get(NoteType.WIN, 0)
        challenges = type_counts.get(NoteType.CHALLENGE, 0)
        insights = type_counts.get(NoteType.INSIGHT, 0)
        patterns = type_counts.get(NoteType.PATTERN, 0)

        if wins > challenges and wins >= 2:
            return ChapterTheme.MOMENTUM
        if insights >= 2 or patterns >= 2:
            return ChapterTheme.DISCOVERY
        if challenges > wins and challenges >= 2:
            return ChapterTheme.RESILIENCE
        if milestones:
            return ChapterTheme.CONSOLIDATION

        return ChapterTheme.EXPLORATION

    def _generate_title(
        self, theme: ChapterTheme, week_number: int
    ) -> str:
        """Generate a chapter title based on theme.

        Args:
            theme: The chapter theme
            week_number: The week number

        Returns:
            A generated chapter title
        """
        titles: dict[ChapterTheme, str] = {
            ChapterTheme.MOMENTUM: "Building Momentum",
            ChapterTheme.DISCOVERY: "New Discoveries",
            ChapterTheme.RESILIENCE: "Rising Again",
            ChapterTheme.CONSOLIDATION: "Strengthening Foundations",
            ChapterTheme.TRANSITION: "Shifting Gears",
            ChapterTheme.RECOVERY: "Gentle Recovery",
            ChapterTheme.BREAKTHROUGH: "A Breakthrough Week",
            ChapterTheme.EXPLORATION: "Exploring New Ground",
        }
        base_title = titles.get(theme, "A New Chapter")
        return f"Week {week_number}: {base_title}"

    def _generate_summary(
        self,
        notes: list[DailyNote],
        milestones: list[MilestoneCard],
        theme: ChapterTheme,
    ) -> str:
        """Generate a chapter summary.

        In production, this would use an LLM for natural language generation.
        For now, uses template-based generation.

        Args:
            notes: Daily notes for the chapter
            milestones: Milestones achieved
            theme: The chapter theme

        Returns:
            A generated summary string
        """
        parts: list[str] = []

        if notes:
            parts.append(
                f"This week had {len(notes)} recorded observations."
            )

        if milestones:
            milestone_names = [m.title for m in milestones]
            parts.append(
                f"Milestones achieved: {', '.join(milestone_names)}."
            )

        wins = [n for n in notes if n.note_type == NoteType.WIN]
        if wins:
            parts.append(f"Notable wins: {len(wins)}.")

        if not parts:
            parts.append("A week of quiet progress.")

        return " ".join(parts)

    def _calculate_energy_trend(self, notes: list[DailyNote]) -> str:
        """Calculate the energy trend from daily notes.

        Args:
            notes: Daily notes with optional energy levels

        Returns:
            Energy trend: "improving", "stable", or "declining"
        """
        energy_notes = [
            n for n in notes if n.energy_level is not None
        ]
        if len(energy_notes) < 2:
            return "stable"

        # Compare first half to second half
        mid = len(energy_notes) // 2
        first_half = energy_notes[:mid]
        second_half = energy_notes[mid:]

        first_avg = sum(n.energy_level for n in first_half if n.energy_level is not None) / len(first_half)
        second_avg = sum(n.energy_level for n in second_half if n.energy_level is not None) / len(second_half)

        diff = second_avg - first_avg
        if diff > 0.1:
            return "improving"
        elif diff < -0.1:
            return "declining"
        return "stable"

    def _extract_insights(self, notes: list[DailyNote]) -> list[str]:
        """Extract key insights from daily notes.

        Args:
            notes: Daily notes for the chapter

        Returns:
            List of insight strings
        """
        insights: list[str] = []
        for note in notes:
            if note.note_type in (NoteType.INSIGHT, NoteType.PATTERN):
                insights.append(note.content)
        return insights[:5]  # Max 5 key insights per chapter
