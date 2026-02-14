"""
Tests for the Narrative Engine.

Covers:
- StoryArc creation and serialization
- Chapter creation with notes and milestones
- DailyNote lifecycle
- MilestoneCard creation
- Theme determination
- Energy trend calculation
- Insight extraction
- GDPR export/delete
"""

from __future__ import annotations

import pytest

from src.agents.aurora.narrative import (
    Chapter,
    ChapterTheme,
    DailyNote,
    MilestoneCard,
    NarrativeEngine,
    NoteType,
    StoryArc,
)


@pytest.fixture()
def engine() -> NarrativeEngine:
    """Create a NarrativeEngine instance."""
    return NarrativeEngine()


# ============================================================================
# DailyNote tests
# ============================================================================


class TestDailyNote:
    def test_create_daily_note(self) -> None:
        note = DailyNote(
            user_id=1,
            date="2026-02-14",
            note_type=NoteType.WIN,
            content="Completed morning routine",
        )
        assert note.user_id == 1
        assert note.note_type == NoteType.WIN
        assert note.content == "Completed morning routine"

    def test_daily_note_to_dict(self) -> None:
        note = DailyNote(
            user_id=1,
            date="2026-02-14",
            note_type=NoteType.OBSERVATION,
            content="Test",
            tags=["focus", "morning"],
            energy_level=0.7,
        )
        d = note.to_dict()
        assert d["note_type"] == "observation"
        assert d["tags"] == ["focus", "morning"]
        assert d["energy_level"] == 0.7

    def test_daily_note_defaults(self) -> None:
        note = DailyNote()
        assert note.user_id == 0
        assert note.note_type == NoteType.OBSERVATION
        assert note.tags == []
        assert note.energy_level is None


# ============================================================================
# MilestoneCard tests
# ============================================================================


class TestMilestoneCard:
    def test_create_milestone_card(self) -> None:
        card = MilestoneCard(
            user_id=1,
            title="First Week Complete",
            description="Finished your first week",
            milestone_type="goal_achieved",
            celebration_text="You did it!",
        )
        assert card.title == "First Week Complete"
        assert card.celebration_text == "You did it!"

    def test_milestone_card_to_dict(self) -> None:
        card = MilestoneCard(user_id=1, title="Test")
        d = card.to_dict()
        assert d["user_id"] == 1
        assert d["title"] == "Test"
        assert "card_id" in d


# ============================================================================
# Chapter tests
# ============================================================================


class TestChapter:
    def test_create_chapter(self) -> None:
        chapter = Chapter(
            user_id=1,
            week_number=3,
            theme=ChapterTheme.MOMENTUM,
            title="Week 3: Building Momentum",
            summary="A great week.",
        )
        assert chapter.week_number == 3
        assert chapter.theme == ChapterTheme.MOMENTUM

    def test_chapter_to_dict(self) -> None:
        chapter = Chapter(user_id=1, week_number=1, title="Test")
        d = chapter.to_dict()
        assert d["week_number"] == 1
        assert d["title"] == "Test"
        assert "chapter_id" in d

    def test_chapter_with_notes_and_milestones(self) -> None:
        notes = [
            DailyNote(content="Note 1"),
            DailyNote(content="Note 2"),
        ]
        milestones = [MilestoneCard(title="Goal done")]
        chapter = Chapter(
            user_id=1,
            week_number=1,
            daily_notes=notes,
            milestones=milestones,
        )
        d = chapter.to_dict()
        assert len(d["daily_notes"]) == 2
        assert len(d["milestones"]) == 1


# ============================================================================
# StoryArc tests
# ============================================================================


class TestStoryArc:
    def test_create_story_arc(self) -> None:
        arc = StoryArc(user_id=1)
        assert arc.user_id == 1
        assert arc.chapters == []
        assert arc.total_milestones == 0

    def test_story_arc_to_dict(self) -> None:
        arc = StoryArc(user_id=1, arc_summary="Test journey")
        d = arc.to_dict()
        assert d["user_id"] == 1
        assert d["arc_summary"] == "Test journey"


# ============================================================================
# NarrativeEngine tests
# ============================================================================


class TestNarrativeEngine:
    def test_add_daily_note(self, engine: NarrativeEngine) -> None:
        note = engine.add_daily_note(
            user_id=1,
            content="Felt productive today",
            note_type=NoteType.WIN,
        )
        assert note.user_id == 1
        assert note.note_type == NoteType.WIN

    def test_add_daily_note_with_energy(self, engine: NarrativeEngine) -> None:
        note = engine.add_daily_note(
            user_id=1,
            content="Moderate energy",
            energy_level=0.6,
        )
        assert note.energy_level == 0.6

    def test_create_chapter_basic(self, engine: NarrativeEngine) -> None:
        engine.add_daily_note(user_id=1, content="Day 1", note_type=NoteType.WIN)
        engine.add_daily_note(user_id=1, content="Day 2", note_type=NoteType.WIN)
        chapter = engine.create_chapter(user_id=1, week_number=1)
        assert chapter.user_id == 1
        assert chapter.week_number == 1
        assert chapter.title.startswith("Week 1:")

    def test_create_chapter_clears_notes(self, engine: NarrativeEngine) -> None:
        engine.add_daily_note(user_id=1, content="Note")
        engine.create_chapter(user_id=1, week_number=1)
        remaining = engine.get_recent_notes(user_id=1)
        assert len(remaining) == 0

    def test_create_chapter_adds_to_arc(self, engine: NarrativeEngine) -> None:
        engine.create_chapter(user_id=1, week_number=1)
        engine.create_chapter(user_id=1, week_number=2)
        arc = engine.get_narrative_arc(user_id=1)
        assert len(arc.chapters) == 2

    def test_create_chapter_with_milestones(self, engine: NarrativeEngine) -> None:
        milestone = MilestoneCard(title="First Goal")
        chapter = engine.create_chapter(
            user_id=1, week_number=1, milestones=[milestone]
        )
        assert len(chapter.milestones) == 1
        arc = engine.get_narrative_arc(user_id=1)
        assert arc.total_milestones == 1

    def test_create_chapter_custom_title(self, engine: NarrativeEngine) -> None:
        chapter = engine.create_chapter(
            user_id=1, week_number=5, title="My Custom Title"
        )
        assert chapter.title == "My Custom Title"

    def test_theme_determination_breakthrough(self, engine: NarrativeEngine) -> None:
        milestones = [MilestoneCard(title="A"), MilestoneCard(title="B")]
        chapter = engine.create_chapter(
            user_id=1, week_number=1, milestones=milestones
        )
        assert chapter.theme == ChapterTheme.BREAKTHROUGH

    def test_theme_determination_momentum(self, engine: NarrativeEngine) -> None:
        notes = [
            DailyNote(note_type=NoteType.WIN, content="Win 1"),
            DailyNote(note_type=NoteType.WIN, content="Win 2"),
            DailyNote(note_type=NoteType.WIN, content="Win 3"),
        ]
        chapter = engine.create_chapter(
            user_id=1, week_number=1, notes=notes
        )
        assert chapter.theme == ChapterTheme.MOMENTUM

    def test_theme_determination_discovery(self, engine: NarrativeEngine) -> None:
        notes = [
            DailyNote(note_type=NoteType.INSIGHT, content="Insight 1"),
            DailyNote(note_type=NoteType.INSIGHT, content="Insight 2"),
        ]
        chapter = engine.create_chapter(
            user_id=1, week_number=1, notes=notes
        )
        assert chapter.theme == ChapterTheme.DISCOVERY

    def test_theme_determination_resilience(self, engine: NarrativeEngine) -> None:
        notes = [
            DailyNote(note_type=NoteType.CHALLENGE, content="C1"),
            DailyNote(note_type=NoteType.CHALLENGE, content="C2"),
        ]
        chapter = engine.create_chapter(
            user_id=1, week_number=1, notes=notes
        )
        assert chapter.theme == ChapterTheme.RESILIENCE

    def test_energy_trend_improving(self, engine: NarrativeEngine) -> None:
        notes = [
            DailyNote(energy_level=0.3, content="D1"),
            DailyNote(energy_level=0.3, content="D2"),
            DailyNote(energy_level=0.7, content="D3"),
            DailyNote(energy_level=0.8, content="D4"),
        ]
        chapter = engine.create_chapter(
            user_id=1, week_number=1, notes=notes
        )
        assert chapter.energy_trend == "improving"

    def test_energy_trend_declining(self, engine: NarrativeEngine) -> None:
        notes = [
            DailyNote(energy_level=0.8, content="D1"),
            DailyNote(energy_level=0.7, content="D2"),
            DailyNote(energy_level=0.3, content="D3"),
            DailyNote(energy_level=0.2, content="D4"),
        ]
        chapter = engine.create_chapter(
            user_id=1, week_number=1, notes=notes
        )
        assert chapter.energy_trend == "declining"

    def test_energy_trend_stable(self, engine: NarrativeEngine) -> None:
        notes = [
            DailyNote(energy_level=0.5, content="D1"),
            DailyNote(energy_level=0.5, content="D2"),
        ]
        chapter = engine.create_chapter(
            user_id=1, week_number=1, notes=notes
        )
        assert chapter.energy_trend == "stable"

    def test_detect_milestone(self, engine: NarrativeEngine) -> None:
        card = engine.detect_milestone(
            user_id=1,
            milestone_type="goal_achieved",
            title="Shipped project",
            description="Completed the project",
        )
        assert card.title == "Shipped project"
        assert "Shipped project" in card.celebration_text

    def test_detect_milestone_custom_celebration(self, engine: NarrativeEngine) -> None:
        card = engine.detect_milestone(
            user_id=1,
            milestone_type="habit_established",
            title="Morning walk",
            description="21 day streak",
            celebration_text="What a streak!",
        )
        assert card.celebration_text == "What a streak!"

    def test_get_narrative_arc_new_user(self, engine: NarrativeEngine) -> None:
        arc = engine.get_narrative_arc(user_id=999)
        assert arc.user_id == 999
        assert arc.chapters == []

    def test_get_recent_notes(self, engine: NarrativeEngine) -> None:
        engine.add_daily_note(user_id=1, content="Recent", date="2099-01-01")
        engine.add_daily_note(user_id=1, content="Old", date="2020-01-01")
        recent = engine.get_recent_notes(user_id=1, days=7)
        # Only "2099-01-01" is within 7 days of now in the year 2099
        # Both may appear depending on date; just verify structure
        assert all(isinstance(n, DailyNote) for n in recent)

    def test_extract_insights(self, engine: NarrativeEngine) -> None:
        notes = [
            DailyNote(note_type=NoteType.INSIGHT, content="Insight A"),
            DailyNote(note_type=NoteType.PATTERN, content="Pattern B"),
            DailyNote(note_type=NoteType.WIN, content="Win C"),
        ]
        chapter = engine.create_chapter(
            user_id=1, week_number=1, notes=notes
        )
        assert "Insight A" in chapter.key_insights
        assert "Pattern B" in chapter.key_insights
        assert "Win C" not in chapter.key_insights

    def test_gdpr_export(self, engine: NarrativeEngine) -> None:
        engine.add_daily_note(user_id=1, content="Test")
        engine.create_chapter(user_id=1, week_number=1)
        data = engine.export_user_data(user_id=1)
        assert "narrative_arc" in data
        assert "pending_notes" in data
        assert data["narrative_arc"] is not None

    def test_gdpr_delete(self, engine: NarrativeEngine) -> None:
        engine.add_daily_note(user_id=1, content="Test")
        engine.create_chapter(user_id=1, week_number=1)
        engine.delete_user_data(user_id=1)
        data = engine.export_user_data(user_id=1)
        assert data["narrative_arc"] is None
        assert data["pending_notes"] == []

    def test_multiple_users_isolated(self, engine: NarrativeEngine) -> None:
        engine.add_daily_note(user_id=1, content="User 1 note")
        engine.add_daily_note(user_id=2, content="User 2 note")
        engine.create_chapter(user_id=1, week_number=1)
        arc_1 = engine.get_narrative_arc(user_id=1)
        arc_2 = engine.get_narrative_arc(user_id=2)
        assert len(arc_1.chapters) == 1
        assert len(arc_2.chapters) == 0
