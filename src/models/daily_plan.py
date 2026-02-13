"""
DailyPlan Model for Aurora Sun V1.

Data Classification: SENSITIVE (reflection_text contains personal data)

References:
- ARCHITECTURE.md Section 14 (Data Models)
- ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
"""

from datetime import datetime, date
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class DailyPlan(Base):
    """
    DailyPlan model representing the daily workflow state for a user.

    Tracks the progress through the daily planning cycle:
    - vision_displayed: Was the vision shown to the user?
    - goals_reviewed: Did the user review their goals?
    - priorities_selected: Did the user select priorities?
    - tasks_committed: Did the user commit to tasks?

    Energy tracking (segment-adaptive):
    - morning_energy: Self-reported energy at start of day (1-5)
    - evening_energy: Self-reported energy at end of day (1-5)

    Attributes:
        id: Primary key
        user_id: Foreign key to users.id
        date: The date this plan is for
        vision_displayed: Vision was shown
        goals_reviewed: Goals were reviewed
        priorities_selected: Priorities were selected
        tasks_committed: Tasks were committed
        morning_energy: Morning energy level (1-5)
        evening_energy: Evening energy level (1-5)
        auto_review_triggered: Was evening review auto-triggered?
        reflection_text: User's reflection (encrypted in production)
        created_at: Creation timestamp
        updated_at: Last update timestamp

    Data Classification: SENSITIVE
    - reflection_text: Encrypted with AES-256-GCM (per-user key)
    """

    __tablename__ = "daily_plans"

    # Relationships
    user = relationship("User", back_populates="daily_plans")

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date = Column(Date, nullable=False, index=True)

    # Daily workflow state flags
    vision_displayed = Column(Boolean, default=False, nullable=False)
    goals_reviewed = Column(Boolean, default=False, nullable=False)
    priorities_selected = Column(Boolean, default=False, nullable=False)
    tasks_committed = Column(Boolean, default=False, nullable=False)

    # Energy tracking (segment-adaptive)
    morning_energy = Column(Integer, nullable=True)  # 1-5
    evening_energy = Column(Integer, nullable=True)  # 1-5

    # Auto-review flag
    auto_review_triggered = Column(Boolean, default=False, nullable=False)

    # Reflection (encrypted in production)
    reflection_text = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # Table indices
    __table_args__ = (
        Index("idx_daily_plan_user_date", "user_id", "date", unique=True),
        Index("idx_daily_plan_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<DailyPlan(id={self.id}, user_id={self.user_id}, date={self.date})>"

    @property
    def completion_percentage(self) -> float:
        """Calculate the percentage of daily workflow completed."""
        total = 4  # vision_displayed, goals_reviewed, priorities_selected, tasks_committed
        completed = sum([
            self.vision_displayed,
            self.goals_reviewed,
            self.priorities_selected,
            self.tasks_committed,
        ])
        return (completed / total) * 100


__all__ = ["DailyPlan"]
