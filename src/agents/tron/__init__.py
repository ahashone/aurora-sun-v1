"""
TRON Agent for Aurora Sun V1.

Security Automation: Observe by default. Every action -> DM to admin.
Crisis override: Mental Health > Security (defer to CrisisService).

Modes:
- Observe (dev): Monitor only, log everything, alert admin
- Suggest+Auto-Low (beta): Auto-handle low threats, suggest for medium+
- Auto-High (production): Auto-handle up to high, alert for critical

Reference: ARCHITECTURE.md Section 7 (TRON Agent)
"""

from __future__ import annotations

from .agent import TRONAgent, TRONMode
from .compliance import ComplianceAuditor, ComplianceReport, ComplianceStatus
from .incident import Incident, IncidentGraph, IncidentSeverity, IncidentStatus
from .threat_monitor import ActiveThreat, ThreatLevel, ThreatMonitor, ThreatScore

__all__ = [
    # Agent
    "TRONAgent",
    "TRONMode",
    # Threat Monitor
    "ThreatMonitor",
    "ThreatLevel",
    "ThreatScore",
    "ActiveThreat",
    # Compliance
    "ComplianceAuditor",
    "ComplianceReport",
    "ComplianceStatus",
    # Incident
    "IncidentGraph",
    "Incident",
    "IncidentSeverity",
    "IncidentStatus",
]
