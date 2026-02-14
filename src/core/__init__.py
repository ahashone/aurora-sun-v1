"""
Core Module System for Aurora Sun V1.

This package contains the core interfaces and utilities for the module system.

Reference: ARCHITECTURE.md Section 2 (Module System)

Exports:
    - Module: Protocol that all modules implement
    - ModuleRegistry: Discovers and routes to modules
    - ModuleContext: Context passed to module operations
    - ModuleResponse: Response returned by module operations
    - DailyWorkflowHooks: Module hooks for daily workflow
    - SegmentContext: User segment configuration
    - Button, SideEffect: UI and action elements
"""

from .buttons import Button, ButtonGrid, ButtonRow, ButtonType
from .daily_workflow_hooks import DailyWorkflowHook, DailyWorkflowHooks
from .module_context import ModuleContext
from .module_protocol import Module
from .module_registry import ModuleRegistry, get_registry, set_registry
from .module_response import ModuleResponse
from .segment_context import (
    SEGMENT_DISPLAY_NAMES,
    NeurostateConfig,
    SegmentContext,
    SegmentCore,
    SegmentFeatures,
    SegmentUX,
    WorkingStyleCode,
)
from .side_effects import SideEffect, SideEffectBatch, SideEffectExecutor, SideEffectType

__all__ = [
    # Protocol
    "Module",
    # Registry
    "ModuleRegistry",
    "get_registry",
    "set_registry",
    # Context & Response
    "ModuleContext",
    "ModuleResponse",
    # Daily Workflow
    "DailyWorkflowHooks",
    "DailyWorkflowHook",
    # Segment Context
    "SegmentContext",
    "SegmentCore",
    "SegmentUX",
    "NeurostateConfig",
    "SegmentFeatures",
    "SEGMENT_DISPLAY_NAMES",
    "WorkingStyleCode",
    # UI Elements
    "Button",
    "ButtonRow",
    "ButtonGrid",
    "ButtonType",
    # Side Effects
    "SideEffect",
    "SideEffectType",
    "SideEffectBatch",
    "SideEffectExecutor",
]


# Pillar constants (as defined in ARCHITECTURE.md)
PILLAR_VISION_TO_TASK = "vision_to_task"
PILLAR_SECOND_BRAIN = "second_brain"
PILLAR_MONEY = "money"

__all__.extend([
    "PILLAR_VISION_TO_TASK",
    "PILLAR_SECOND_BRAIN",
    "PILLAR_MONEY",
])
