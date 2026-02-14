"""
Avicenna Agent for Aurora Sun V1.

Quality Observer: Diagnose, never fix. Human decides.

Avicenna validates runtime behavior against the architecture spec:
- State machine transitions (valid/invalid)
- Expected DB writes per transition
- Stuck state detection (30 min threshold)
- Stale interaction detection (60 min threshold)
- Rolling issue buffer with severity levels (CRITICAL/WARNING/INFO)
- Health report generation for admin

Reference: ARCHITECTURE.md Section 6 (Avicenna Agent)
Reference: src/agents/avicenna_spec.yaml (architecture specification)
"""

from __future__ import annotations

from .agent import AvicennaAgent
from .alerts import AlertSeverity, AlertSystem, PendingAlert
from .spec import ExpectedWrite, SLAConfig, SpecManager, ValidTransition
from .tracker import Issue, IssueBuffer, IssueSeverity, StateTracker

__all__ = [
    # Agent
    "AvicennaAgent",
    # Spec
    "SpecManager",
    "ValidTransition",
    "ExpectedWrite",
    "SLAConfig",
    # Tracker
    "StateTracker",
    "IssueBuffer",
    "Issue",
    "IssueSeverity",
    # Alerts
    "AlertSystem",
    "PendingAlert",
    "AlertSeverity",
]
