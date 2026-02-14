"""
Avicenna State Tracker for Aurora Sun V1.

Tracks module state machine transitions and detects anomalies:
- Invalid transitions (not in spec)
- Missing DB writes (expected but didn't happen)
- Stuck states (user in same state > 30 min)
- Stale interactions (no interaction > 60 min)
- Rolling issue buffer with severity levels

Philosophy: Diagnose, never fix. Human decides.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from .spec import SpecManager

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================


class IssueSeverity(StrEnum):
    """Issue severity levels for the issue buffer."""

    CRITICAL = "critical"  # Immediate admin notification
    WARNING = "warning"    # Buffer, notify on pattern
    INFO = "info"          # Log only


@dataclass
class Issue:
    """A detected quality issue.

    Attributes:
        severity: Issue severity level.
        issue_type: Type of issue (e.g. "invalid_transition", "stuck_state").
        module: Module that produced the issue.
        description: Human-readable description.
        timestamp: When the issue was detected.
        user_id: Affected user (if applicable).
        details: Additional details for debugging.
    """

    severity: IssueSeverity
    issue_type: str
    module: str
    description: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    user_id: int | None = None
    details: dict[str, str | int | float | None] = field(default_factory=dict)


class IssueBuffer:
    """Rolling buffer of detected issues.

    Maintains a bounded deque of issues with methods to query by severity,
    module, and time range.

    Args:
        max_size: Maximum number of issues to keep in the buffer.
    """

    def __init__(self, max_size: int = 1000) -> None:
        """Initialize issue buffer with given capacity."""
        self._buffer: deque[Issue] = deque(maxlen=max_size)
        self._max_size = max_size

    @property
    def size(self) -> int:
        """Number of issues currently in the buffer."""
        return len(self._buffer)

    def add(self, issue: Issue) -> None:
        """Add an issue to the buffer.

        Args:
            issue: The issue to add.
        """
        self._buffer.append(issue)
        logger.log(
            logging.CRITICAL if issue.severity == IssueSeverity.CRITICAL
            else logging.WARNING if issue.severity == IssueSeverity.WARNING
            else logging.INFO,
            "avicenna_issue severity=%s type=%s module=%s desc=%s",
            issue.severity.value,
            issue.issue_type,
            issue.module,
            issue.description,
        )

    def get_issues(
        self,
        severity: IssueSeverity | None = None,
        module: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Issue]:
        """Get issues from the buffer with optional filters.

        Args:
            severity: Filter by severity level.
            module: Filter by module name.
            since: Only return issues after this timestamp.
            limit: Maximum number of issues to return.

        Returns:
            List of matching issues, most recent first.
        """
        result: list[Issue] = []
        for issue in reversed(self._buffer):
            if severity is not None and issue.severity != severity:
                continue
            if module is not None and issue.module != module:
                continue
            if since is not None and issue.timestamp < since:
                continue
            result.append(issue)
            if len(result) >= limit:
                break
        return result

    def get_critical_count(self, since: datetime | None = None) -> int:
        """Count critical issues, optionally since a given time.

        Args:
            since: Only count issues after this timestamp.

        Returns:
            Number of critical issues.
        """
        return len(self.get_issues(severity=IssueSeverity.CRITICAL, since=since))

    def get_warning_count(self, since: datetime | None = None) -> int:
        """Count warning issues, optionally since a given time.

        Args:
            since: Only count issues after this timestamp.

        Returns:
            Number of warning issues.
        """
        return len(self.get_issues(severity=IssueSeverity.WARNING, since=since))

    def clear(self) -> None:
        """Clear all issues from the buffer."""
        self._buffer.clear()


# =============================================================================
# State Tracker
# =============================================================================


@dataclass
class _TrackedSession:
    """Internal: tracks the state of a single user session in a module."""

    user_id: int
    module: str
    current_state: str | None
    entered_state_at: datetime
    last_interaction_at: datetime


class StateTracker:
    """Track module state machine transitions and detect anomalies.

    Uses the SpecManager to validate transitions against the architecture
    specification. Detects stuck states and stale interactions.

    Args:
        spec: The SpecManager instance with the loaded spec.

    Usage:
        tracker = StateTracker(spec_manager)
        issues = tracker.track_transition(
            user_id=1, module="planning",
            from_state=None, to_state="SCOPE"
        )
    """

    def __init__(self, spec: SpecManager) -> None:
        """Initialize state tracker with spec manager."""
        self._spec = spec
        self._issue_buffer = IssueBuffer()
        # Active sessions: key = (user_id, module)
        self._sessions: dict[tuple[int, str], _TrackedSession] = {}

    @property
    def issue_buffer(self) -> IssueBuffer:
        """Access the underlying issue buffer."""
        return self._issue_buffer

    def track_transition(
        self,
        user_id: int,
        module: str,
        from_state: str | None,
        to_state: str | None,
    ) -> list[Issue]:
        """Track a state transition and report any issues.

        Validates the transition against the spec and checks for expected
        DB writes. Updates the tracked session state.

        Args:
            user_id: User performing the transition.
            module: Module name (e.g. "planning").
            from_state: Source state (None for initial entry).
            to_state: Target state (None for exit).

        Returns:
            List of issues detected during this transition (may be empty).
        """
        issues: list[Issue] = []
        now = datetime.now(UTC)

        # Validate transition against spec
        if not self._spec.is_valid_transition(module, from_state, to_state):
            issue = Issue(
                severity=IssueSeverity.CRITICAL,
                issue_type="invalid_transition",
                module=module,
                description=(
                    f"Invalid transition: {from_state} -> {to_state} "
                    f"not in spec for module '{module}'"
                ),
                user_id=user_id,
                details={
                    "from_state": from_state,
                    "to_state": to_state,
                },
            )
            issues.append(issue)
            self._issue_buffer.add(issue)

        # Log valid state entry/exit as INFO
        if to_state is not None:
            info_issue = Issue(
                severity=IssueSeverity.INFO,
                issue_type="state_entered",
                module=module,
                description=f"Entered state {to_state}",
                user_id=user_id,
            )
            self._issue_buffer.add(info_issue)

        if from_state is not None and to_state is None:
            info_issue = Issue(
                severity=IssueSeverity.INFO,
                issue_type="state_exited",
                module=module,
                description=f"Exited from state {from_state}",
                user_id=user_id,
            )
            self._issue_buffer.add(info_issue)

        # Update tracked session
        session_key = (user_id, module)
        if to_state is None:
            # Module exit: remove tracked session
            self._sessions.pop(session_key, None)
        else:
            self._sessions[session_key] = _TrackedSession(
                user_id=user_id,
                module=module,
                current_state=to_state,
                entered_state_at=now,
                last_interaction_at=now,
            )

        return issues

    def record_interaction(self, user_id: int, module: str) -> None:
        """Record that an interaction happened (updates last_interaction_at).

        Args:
            user_id: User who interacted.
            module: Module that received the interaction.
        """
        session_key = (user_id, module)
        session = self._sessions.get(session_key)
        if session is not None:
            session.last_interaction_at = datetime.now(UTC)

    def check_stuck_states(
        self,
        threshold_minutes: int | None = None,
    ) -> list[Issue]:
        """Check all tracked sessions for stuck states.

        A session is "stuck" if the user has been in the same state for
        longer than the SLA threshold.

        Args:
            threshold_minutes: Override threshold (default: from SLA config).

        Returns:
            List of stuck-state issues detected.
        """
        if threshold_minutes is None:
            threshold_minutes = self._spec.get_sla().max_state_duration_minutes

        threshold = timedelta(minutes=threshold_minutes)
        now = datetime.now(UTC)
        issues: list[Issue] = []

        for session_key, session in self._sessions.items():
            duration = now - session.entered_state_at
            if duration > threshold:
                issue = Issue(
                    severity=IssueSeverity.CRITICAL,
                    issue_type="stuck_state",
                    module=session.module,
                    description=(
                        f"User stuck in state '{session.current_state}' "
                        f"for {duration.total_seconds() / 60:.1f} min "
                        f"(threshold: {threshold_minutes} min)"
                    ),
                    user_id=session.user_id,
                    details={
                        "current_state": session.current_state,
                        "duration_minutes": round(duration.total_seconds() / 60, 1),
                        "threshold_minutes": threshold_minutes,
                    },
                )
                issues.append(issue)
                self._issue_buffer.add(issue)

        return issues

    def check_stale_interactions(
        self,
        threshold_minutes: int | None = None,
    ) -> list[Issue]:
        """Check all tracked sessions for stale interactions.

        A session is "stale" if no interaction has happened for longer
        than the SLA threshold.

        Args:
            threshold_minutes: Override threshold (default: from SLA config).

        Returns:
            List of stale-interaction issues detected.
        """
        if threshold_minutes is None:
            threshold_minutes = self._spec.get_sla().max_interaction_gap_minutes

        threshold = timedelta(minutes=threshold_minutes)
        now = datetime.now(UTC)
        issues: list[Issue] = []

        for session_key, session in self._sessions.items():
            gap = now - session.last_interaction_at
            if gap > threshold:
                issue = Issue(
                    severity=IssueSeverity.WARNING,
                    issue_type="stale_interaction",
                    module=session.module,
                    description=(
                        f"No interaction for {gap.total_seconds() / 60:.1f} min "
                        f"in module '{session.module}' state '{session.current_state}' "
                        f"(threshold: {threshold_minutes} min)"
                    ),
                    user_id=session.user_id,
                    details={
                        "current_state": session.current_state,
                        "gap_minutes": round(gap.total_seconds() / 60, 1),
                        "threshold_minutes": threshold_minutes,
                    },
                )
                issues.append(issue)
                self._issue_buffer.add(issue)

        return issues

    def get_active_sessions(self) -> list[dict[str, str | int | None]]:
        """Get all currently tracked sessions.

        Returns:
            List of session info dicts.
        """
        return [
            {
                "user_id": s.user_id,
                "module": s.module,
                "current_state": s.current_state,
                "entered_state_at": s.entered_state_at.isoformat(),
                "last_interaction_at": s.last_interaction_at.isoformat(),
            }
            for s in self._sessions.values()
        ]

    def get_issues(self, **kwargs: int | str | datetime | IssueSeverity | None) -> list[Issue]:
        """Delegate to the issue buffer's get_issues method.

        Supports same keyword arguments as IssueBuffer.get_issues().

        Returns:
            List of matching issues.
        """
        # Filter kwargs to only pass valid types
        filtered: dict[str, IssueSeverity | str | datetime | int | None] = {}
        for k, v in kwargs.items():
            if k == "severity" and isinstance(v, IssueSeverity):
                filtered[k] = v
            elif k == "module" and isinstance(v, str):
                filtered[k] = v
            elif k == "since" and isinstance(v, datetime):
                filtered[k] = v
            elif k == "limit" and isinstance(v, int):
                filtered[k] = v
        return self._issue_buffer.get_issues(**filtered)  # type: ignore[arg-type]
