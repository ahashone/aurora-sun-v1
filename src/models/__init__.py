"""
Models package for Aurora Sun V1.

This package exports all SQLAlchemy models.

Usage:
    from src.models import User, Vision, Goal, Task, DailyPlan, Session
    from src.models import SensoryProfile, MaskingLog, BurnoutAssessment
    from src.models import ChannelState, InertiaEvent, EnergyLevelRecord
"""

from src.models.base import Base
from src.models.user import User
from src.models.vision import Vision
from src.models.goal import Goal
from src.models.task import Task
from src.models.daily_plan import DailyPlan
from src.models.session import Session
from src.models.neurostate import (
    SensoryProfile,
    MaskingLog,
    BurnoutAssessment,
    ChannelState,
    InertiaEvent,
    EnergyLevelRecord,
    InertiaType,
    BurnoutType,
    ChannelType,
    EnergyLevel,
)

__all__ = [
    # Base
    "Base",
    # Core Models
    "User",
    "Vision",
    "Goal",
    "Task",
    "DailyPlan",
    "Session",
    # Neurostate Models
    "SensoryProfile",
    "MaskingLog",
    "BurnoutAssessment",
    "ChannelState",
    "InertiaEvent",
    "EnergyLevelRecord",
    # Neurostate Enums
    "InertiaType",
    "BurnoutType",
    "ChannelType",
    "EnergyLevel",
]
