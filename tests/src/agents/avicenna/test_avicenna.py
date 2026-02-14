"""
Tests for the Avicenna Agent (Quality Observer).

Tests cover:
- SpecManager: loading, parsing, querying transitions, SLA config
- StateTracker: transition tracking, stuck detection, stale detection, issue buffer
- AlertSystem: alert creation, cooldown, sending, pending alerts
- AvicennaAgent: initialization, health checks, health reports, decorator
- IssueBuffer: add, query, filtering, capacity

Reference: src/agents/avicenna_spec.yaml
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.agents.avicenna.agent import AvicennaAgent, HealthReport
from src.agents.avicenna.alerts import AlertSeverity, AlertSystem, PendingAlert
from src.agents.avicenna.spec import SLAConfig, SpecManager
from src.agents.avicenna.tracker import Issue, IssueBuffer, IssueSeverity, StateTracker

# =============================================================================
# Fixtures
# =============================================================================


MINIMAL_SPEC: dict[str, object] = {
    "modules": {
        "planning": {
            "states": ["SCOPE", "VISION", "DONE"],
            "transitions": [
                {
                    "from": None,
                    "to": "SCOPE",
                    "expected_writes": [
                        {"table": "sessions", "count": "1", "description": "Session started"},
                    ],
                },
                {
                    "from": "SCOPE",
                    "to": "VISION",
                    "expected_writes": [],
                },
                {
                    "from": "VISION",
                    "to": "DONE",
                    "expected_writes": [
                        {"table": "daily_plans", "count": "1", "description": "Plan committed"},
                    ],
                },
                {
                    "from": "DONE",
                    "to": None,
                    "expected_writes": [
                        {"table": "sessions", "count": "1", "description": "Session ended"},
                    ],
                },
            ],
        },
    },
    "slas": {
        "max_response_time_seconds": 30,
        "max_state_duration_minutes": 30,
        "max_interaction_gap_minutes": 60,
        "admin_notification_cooldown_seconds": 60,
        "max_concurrent_sessions_per_user": 3,
    },
    "severity_rules": {
        "critical": [
            {"type": "invalid_transition", "description": "State transition not in spec"},
            {"type": "stuck_state", "description": "User stuck in state"},
        ],
        "warning": [
            {"type": "slow_response", "description": "Response time exceeded SLA"},
        ],
    },
}


@pytest.fixture
def spec_manager() -> SpecManager:
    """SpecManager loaded with minimal test spec."""
    sm = SpecManager()
    sm.load_from_dict(MINIMAL_SPEC)
    return sm


@pytest.fixture
def state_tracker(spec_manager: SpecManager) -> StateTracker:
    """StateTracker with minimal spec."""
    return StateTracker(spec_manager)


@pytest.fixture
def alert_system() -> AlertSystem:
    """AlertSystem with short cooldown for testing."""
    return AlertSystem(cooldown_seconds=1)


@pytest.fixture
def avicenna() -> AvicennaAgent:
    """AvicennaAgent loaded with minimal spec."""
    agent = AvicennaAgent(cooldown_seconds=1)
    agent.load_spec_from_dict(MINIMAL_SPEC)
    return agent


# =============================================================================
# SpecManager Tests
# =============================================================================


class TestSpecManager:
    """Test SpecManager loading and querying."""

    def test_load_from_dict(self, spec_manager: SpecManager) -> None:
        """Spec is loaded successfully from dict."""
        assert spec_manager.is_loaded is True

    def test_get_module_names(self, spec_manager: SpecManager) -> None:
        """All modules from the spec are available."""
        names = spec_manager.get_module_names()
        assert "planning" in names

    def test_get_module_states(self, spec_manager: SpecManager) -> None:
        """Module states match the spec."""
        states = spec_manager.get_module_states("planning")
        assert "SCOPE" in states
        assert "VISION" in states
        assert "DONE" in states

    def test_get_module_states_unknown_module(self, spec_manager: SpecManager) -> None:
        """Unknown module returns empty states list."""
        states = spec_manager.get_module_states("nonexistent")
        assert states == []

    def test_get_valid_transitions(self, spec_manager: SpecManager) -> None:
        """Valid transitions are returned for a module."""
        transitions = spec_manager.get_valid_transitions("planning")
        assert len(transitions) == 4  # null->SCOPE, SCOPE->VISION, VISION->DONE, DONE->null

    def test_is_valid_transition_true(self, spec_manager: SpecManager) -> None:
        """Known transition returns True."""
        assert spec_manager.is_valid_transition("planning", None, "SCOPE") is True
        assert spec_manager.is_valid_transition("planning", "SCOPE", "VISION") is True

    def test_is_valid_transition_false(self, spec_manager: SpecManager) -> None:
        """Invalid transition returns False."""
        assert spec_manager.is_valid_transition("planning", "SCOPE", "DONE") is False
        assert spec_manager.is_valid_transition("planning", None, "DONE") is False

    def test_get_expected_writes(self, spec_manager: SpecManager) -> None:
        """Expected writes are returned for a transition."""
        writes = spec_manager.get_expected_writes("planning", None, "SCOPE")
        assert len(writes) == 1
        assert writes[0].table == "sessions"
        assert writes[0].count == "1"

    def test_get_expected_writes_empty(self, spec_manager: SpecManager) -> None:
        """Transition with no expected writes returns empty list."""
        writes = spec_manager.get_expected_writes("planning", "SCOPE", "VISION")
        assert writes == []

    def test_get_expected_writes_invalid_transition(self, spec_manager: SpecManager) -> None:
        """Invalid transition returns empty expected writes."""
        writes = spec_manager.get_expected_writes("planning", "SCOPE", "DONE")
        assert writes == []

    def test_get_sla(self, spec_manager: SpecManager) -> None:
        """SLA config is loaded correctly."""
        sla = spec_manager.get_sla()
        assert sla.max_response_time_seconds == 30
        assert sla.max_state_duration_minutes == 30
        assert sla.max_interaction_gap_minutes == 60

    def test_get_severity_rules(self, spec_manager: SpecManager) -> None:
        """Severity rules are loaded correctly."""
        critical = spec_manager.get_severity_rules("critical")
        assert len(critical) == 2
        assert any(r["type"] == "invalid_transition" for r in critical)

    def test_default_sla_without_spec(self) -> None:
        """Default SLA values when no spec is loaded."""
        sm = SpecManager()
        sla = sm.get_sla()
        assert isinstance(sla, SLAConfig)
        assert sla.max_response_time_seconds == 30

    def test_not_loaded_initially(self) -> None:
        """SpecManager is not loaded before load_spec is called."""
        sm = SpecManager()
        assert sm.is_loaded is False


# =============================================================================
# IssueBuffer Tests
# =============================================================================


class TestIssueBuffer:
    """Test the IssueBuffer rolling buffer."""

    def test_add_and_size(self) -> None:
        """Issues are added and size tracked."""
        buf = IssueBuffer(max_size=10)
        assert buf.size == 0

        buf.add(Issue(
            severity=IssueSeverity.INFO,
            issue_type="test",
            module="test",
            description="test issue",
        ))
        assert buf.size == 1

    def test_max_size_eviction(self) -> None:
        """Buffer evicts oldest issues when max size is reached."""
        buf = IssueBuffer(max_size=3)
        for i in range(5):
            buf.add(Issue(
                severity=IssueSeverity.INFO,
                issue_type="test",
                module="test",
                description=f"issue {i}",
            ))
        assert buf.size == 3
        issues = buf.get_issues()
        assert issues[0].description == "issue 4"  # Most recent first

    def test_filter_by_severity(self) -> None:
        """Issues can be filtered by severity."""
        buf = IssueBuffer()
        buf.add(Issue(severity=IssueSeverity.CRITICAL, issue_type="a", module="m", description="crit"))
        buf.add(Issue(severity=IssueSeverity.WARNING, issue_type="b", module="m", description="warn"))
        buf.add(Issue(severity=IssueSeverity.INFO, issue_type="c", module="m", description="info"))

        critical = buf.get_issues(severity=IssueSeverity.CRITICAL)
        assert len(critical) == 1
        assert critical[0].description == "crit"

    def test_filter_by_module(self) -> None:
        """Issues can be filtered by module."""
        buf = IssueBuffer()
        buf.add(Issue(severity=IssueSeverity.INFO, issue_type="a", module="planning", description="p"))
        buf.add(Issue(severity=IssueSeverity.INFO, issue_type="b", module="review", description="r"))

        planning = buf.get_issues(module="planning")
        assert len(planning) == 1
        assert planning[0].module == "planning"

    def test_get_critical_count(self) -> None:
        """Critical count is accurate."""
        buf = IssueBuffer()
        buf.add(Issue(severity=IssueSeverity.CRITICAL, issue_type="a", module="m", description="c1"))
        buf.add(Issue(severity=IssueSeverity.CRITICAL, issue_type="b", module="m", description="c2"))
        buf.add(Issue(severity=IssueSeverity.WARNING, issue_type="c", module="m", description="w"))
        assert buf.get_critical_count() == 2

    def test_clear(self) -> None:
        """Clear empties the buffer."""
        buf = IssueBuffer()
        buf.add(Issue(severity=IssueSeverity.INFO, issue_type="a", module="m", description="x"))
        assert buf.size == 1
        buf.clear()
        assert buf.size == 0


# =============================================================================
# StateTracker Tests
# =============================================================================


class TestStateTracker:
    """Test StateTracker transition tracking and anomaly detection."""

    def test_valid_transition_no_issues(self, state_tracker: StateTracker) -> None:
        """Valid transition produces no issues (besides INFO logging)."""
        issues = state_tracker.track_transition(
            user_id=1, module="planning", from_state=None, to_state="SCOPE"
        )
        # Only invalid transitions produce non-INFO issues in the returned list
        assert all(i.severity == IssueSeverity.CRITICAL for i in issues) is True
        assert len(issues) == 0

    def test_invalid_transition_produces_critical_issue(self, state_tracker: StateTracker) -> None:
        """Invalid transition produces a CRITICAL issue."""
        issues = state_tracker.track_transition(
            user_id=1, module="planning", from_state="SCOPE", to_state="DONE"
        )
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.CRITICAL
        assert issues[0].issue_type == "invalid_transition"

    def test_track_multiple_transitions(self, state_tracker: StateTracker) -> None:
        """Multiple valid transitions are tracked."""
        state_tracker.track_transition(1, "planning", None, "SCOPE")
        state_tracker.track_transition(1, "planning", "SCOPE", "VISION")
        sessions = state_tracker.get_active_sessions()
        assert len(sessions) == 1
        assert sessions[0]["current_state"] == "VISION"

    def test_exit_transition_removes_session(self, state_tracker: StateTracker) -> None:
        """Exit transition (to_state=None) removes the tracked session."""
        state_tracker.track_transition(1, "planning", None, "SCOPE")
        assert len(state_tracker.get_active_sessions()) == 1

        state_tracker.track_transition(1, "planning", "DONE", None)
        assert len(state_tracker.get_active_sessions()) == 0

    def test_stuck_state_detection(self, state_tracker: StateTracker) -> None:
        """Stuck state is detected when threshold is exceeded."""
        state_tracker.track_transition(1, "planning", None, "SCOPE")

        # Force the session to appear old by manipulating entered_state_at
        session_key = (1, "planning")
        session = state_tracker._sessions[session_key]
        session.entered_state_at = datetime.now(UTC) - timedelta(minutes=45)

        stuck = state_tracker.check_stuck_states(threshold_minutes=30)
        assert len(stuck) == 1
        assert stuck[0].issue_type == "stuck_state"
        assert stuck[0].user_id == 1

    def test_no_stuck_state_within_threshold(self, state_tracker: StateTracker) -> None:
        """No stuck state when within threshold."""
        state_tracker.track_transition(1, "planning", None, "SCOPE")
        stuck = state_tracker.check_stuck_states(threshold_minutes=30)
        assert len(stuck) == 0

    def test_stale_interaction_detection(self, state_tracker: StateTracker) -> None:
        """Stale interaction is detected when gap exceeds threshold."""
        state_tracker.track_transition(1, "planning", None, "SCOPE")

        # Force the session to appear stale
        session_key = (1, "planning")
        session = state_tracker._sessions[session_key]
        session.last_interaction_at = datetime.now(UTC) - timedelta(minutes=90)

        stale = state_tracker.check_stale_interactions(threshold_minutes=60)
        assert len(stale) == 1
        assert stale[0].issue_type == "stale_interaction"

    def test_record_interaction_updates_timestamp(self, state_tracker: StateTracker) -> None:
        """Recording an interaction updates the last_interaction_at timestamp."""
        state_tracker.track_transition(1, "planning", None, "SCOPE")

        # Force old interaction time
        session_key = (1, "planning")
        old_time = datetime.now(UTC) - timedelta(minutes=90)
        state_tracker._sessions[session_key].last_interaction_at = old_time

        state_tracker.record_interaction(1, "planning")

        # Should now be recent (no stale interactions)
        stale = state_tracker.check_stale_interactions(threshold_minutes=60)
        assert len(stale) == 0


# =============================================================================
# AlertSystem Tests
# =============================================================================


class TestAlertSystem:
    """Test AlertSystem with cooldown and pending queue."""

    def test_create_alert(self, alert_system: AlertSystem) -> None:
        """Alert is created and added to pending."""
        alert = alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test Alert",
            message="Test message",
            module="planning",
        )
        assert isinstance(alert, PendingAlert)
        assert alert.sent is False
        assert len(alert_system.get_pending_alerts()) == 1

    def test_should_alert_first_time(self, alert_system: AlertSystem) -> None:
        """First alert of a type should always be allowed."""
        alert = alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="msg",
            module="planning",
        )
        assert alert_system.should_alert(alert) is True

    @pytest.mark.asyncio
    async def test_send_alert(self, alert_system: AlertSystem) -> None:
        """Sending an alert marks it as sent and removes from pending."""
        alert = alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="msg",
            module="planning",
        )
        result = await alert_system.send_alert(alert)
        assert result is True
        assert alert.sent is True
        assert alert.sent_at is not None
        assert len(alert_system.get_pending_alerts()) == 0

    @pytest.mark.asyncio
    async def test_cooldown_prevents_duplicate(self, alert_system: AlertSystem) -> None:
        """Cooldown prevents sending duplicate alerts too quickly."""
        alert1 = alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="msg1",
            module="planning",
        )
        await alert_system.send_alert(alert1)

        alert2 = alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="msg2",
            module="planning",
        )
        # Same severity + module within cooldown -> should not alert
        assert alert_system.should_alert(alert2) is False
        result = await alert_system.send_alert(alert2)
        assert result is False

    def test_get_sent_alerts(self, alert_system: AlertSystem) -> None:
        """Sent alerts are tracked in history."""
        assert len(alert_system.get_sent_alerts()) == 0

    @pytest.mark.asyncio
    async def test_sent_alert_in_history(self, alert_system: AlertSystem) -> None:
        """After sending, alert appears in sent history."""
        alert = alert_system.create_alert(
            severity=AlertSeverity.WARNING,
            title="Warn",
            message="msg",
            module="review",
        )
        await alert_system.send_alert(alert)
        sent = alert_system.get_sent_alerts()
        assert len(sent) == 1
        assert sent[0].title == "Warn"

    def test_clear_pending(self, alert_system: AlertSystem) -> None:
        """Clear pending removes all unsent alerts."""
        alert_system.create_alert(
            severity=AlertSeverity.WARNING,
            title="A",
            message="m",
            module="x",
        )
        alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="B",
            message="m",
            module="y",
        )
        cleared = alert_system.clear_pending()
        assert cleared == 2
        assert len(alert_system.get_pending_alerts()) == 0


# =============================================================================
# AvicennaAgent Tests
# =============================================================================


class TestAvicennaAgent:
    """Test the main AvicennaAgent orchestrator."""

    def test_initialization(self, avicenna: AvicennaAgent) -> None:
        """Agent initializes and loads spec correctly."""
        assert avicenna.is_initialized is True
        assert avicenna.spec.is_loaded is True

    def test_not_initialized_raises(self) -> None:
        """Accessing tracker before init raises RuntimeError."""
        agent = AvicennaAgent()
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = agent.tracker

    def test_track_valid_transition(self, avicenna: AvicennaAgent) -> None:
        """Valid transition tracked without issues."""
        issues = avicenna.track_transition(
            user_id=1, module="planning", from_state=None, to_state="SCOPE"
        )
        assert len(issues) == 0

    def test_track_invalid_transition_creates_alert(self, avicenna: AvicennaAgent) -> None:
        """Invalid transition creates a CRITICAL alert."""
        issues = avicenna.track_transition(
            user_id=1, module="planning", from_state="SCOPE", to_state="DONE"
        )
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.CRITICAL

        # Alert should be pending
        pending = avicenna.alerts.get_pending_alerts()
        assert len(pending) >= 1

    def test_validate_transition(self, avicenna: AvicennaAgent) -> None:
        """validate_transition checks spec without tracking."""
        assert avicenna.validate_transition("planning", None, "SCOPE") is True
        assert avicenna.validate_transition("planning", "SCOPE", "DONE") is False

    @pytest.mark.asyncio
    async def test_check_health_healthy(self, avicenna: AvicennaAgent) -> None:
        """Health check returns 'healthy' with no issues."""
        status = await avicenna.check_health()
        assert status == "healthy"

    @pytest.mark.asyncio
    async def test_check_health_critical(self, avicenna: AvicennaAgent) -> None:
        """Health check returns 'critical' when critical issues exist."""
        # Force an invalid transition to create a critical issue
        avicenna.track_transition(1, "planning", "SCOPE", "DONE")
        status = await avicenna.check_health()
        assert status == "critical"

    @pytest.mark.asyncio
    async def test_get_health_report(self, avicenna: AvicennaAgent) -> None:
        """Health report contains expected fields."""
        report = await avicenna.get_health_report()
        assert isinstance(report, HealthReport)
        assert report.generated_at is not None
        assert report.status in ("healthy", "degraded", "critical")
        assert isinstance(report.active_sessions, int)
        assert isinstance(report.recent_issues, list)

    @pytest.mark.asyncio
    async def test_health_report_with_issues(self, avicenna: AvicennaAgent) -> None:
        """Health report reflects issues correctly."""
        avicenna.track_transition(1, "planning", "SCOPE", "DONE")
        report = await avicenna.get_health_report()
        assert report.critical_issues >= 1
        assert report.status == "critical"

    def test_detect_stuck_state(self, avicenna: AvicennaAgent) -> None:
        """detect_stuck_state works for specific user/module."""
        avicenna.track_transition(1, "planning", None, "SCOPE")

        # Force old timestamp
        session_key = (1, "planning")
        avicenna.tracker._sessions[session_key].entered_state_at = (
            datetime.now(UTC) - timedelta(minutes=45)
        )

        assert avicenna.detect_stuck_state(1, "planning", threshold_minutes=30) is True
        assert avicenna.detect_stuck_state(2, "planning", threshold_minutes=30) is False

    @pytest.mark.asyncio
    async def test_tracked_decorator(self, avicenna: AvicennaAgent) -> None:
        """@tracked decorator records interactions without modifying handler."""
        # Track a transition first so there is an active session
        avicenna.track_transition(1, "planning", None, "SCOPE")

        @avicenna.tracked("planning")
        async def handle_planning(user_id: int, message: str) -> str:
            return f"handled: {message}"

        result = await handle_planning(user_id=1, message="test")
        assert result == "handled: test"

    @pytest.mark.asyncio
    async def test_tracked_decorator_catches_crash(self, avicenna: AvicennaAgent) -> None:
        """@tracked decorator logs crash and re-raises exception."""
        avicenna.track_transition(1, "planning", None, "SCOPE")

        @avicenna.tracked("planning")
        async def crashing_handler(user_id: int) -> str:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await crashing_handler(user_id=1)

        # Crash should be logged as CRITICAL issue
        issues = avicenna.tracker.issue_buffer.get_issues(severity=IssueSeverity.CRITICAL)
        crash_issues = [i for i in issues if i.issue_type == "module_crash"]
        assert len(crash_issues) >= 1
