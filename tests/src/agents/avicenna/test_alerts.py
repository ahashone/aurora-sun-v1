"""
Unit tests for Avicenna AlertSystem.

Tests cover:
- Alert creation with severity levels
- Cooldown tracking and enforcement
- Alert sending with rate limiting
- Pending and sent alert retrieval
- Alert queue management
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.agents.avicenna.alerts import AlertSeverity, AlertSystem, PendingAlert

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def alert_system():
    """Create an AlertSystem with 60s cooldown."""
    return AlertSystem(cooldown_seconds=60)


@pytest.fixture
def no_cooldown_system():
    """Create an AlertSystem with no cooldown."""
    return AlertSystem(cooldown_seconds=0)


# =============================================================================
# TestAlertCreation
# =============================================================================

class TestAlertCreation:
    """Test alert creation functionality."""

    def test_create_critical_alert(self, alert_system):
        """Can create a critical alert."""
        alert = alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test Critical",
            message="Critical issue detected",
            module="planning",
        )

        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.title == "Test Critical"
        assert alert.message == "Critical issue detected"
        assert alert.module == "planning"
        assert not alert.sent
        assert alert.sent_at is None

    def test_create_warning_alert(self, alert_system):
        """Can create a warning alert."""
        alert = alert_system.create_alert(
            severity=AlertSeverity.WARNING,
            title="Test Warning",
            message="Warning issue detected",
            module="review",
        )

        assert alert.severity == AlertSeverity.WARNING
        assert alert.title == "Test Warning"
        assert alert.module == "review"

    def test_alert_added_to_pending(self, alert_system):
        """Created alerts are added to pending queue."""
        alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="Test message",
            module="test",
        )

        pending = alert_system.get_pending_alerts()
        assert len(pending) == 1
        assert pending[0].title == "Test"

    def test_multiple_alerts_queued(self, alert_system):
        """Multiple alerts can be queued."""
        for i in range(5):
            alert_system.create_alert(
                severity=AlertSeverity.WARNING,
                title=f"Alert {i}",
                message=f"Message {i}",
                module="test",
            )

        pending = alert_system.get_pending_alerts()
        assert len(pending) == 5

    def test_alert_has_created_timestamp(self, alert_system):
        """Created alerts have a created_at timestamp."""
        before = datetime.now(UTC)
        alert = alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="Test",
            module="test",
        )
        after = datetime.now(UTC)

        assert before <= alert.created_at <= after


# =============================================================================
# TestCooldownTracking
# =============================================================================

class TestCooldownTracking:
    """Test cooldown tracking and enforcement."""

    def test_should_alert_first_time(self, alert_system):
        """First alert of a type should be allowed."""
        alert = alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="Test",
            module="planning",
        )

        assert alert_system.should_alert(alert)

    def test_should_not_alert_during_cooldown(self, alert_system):
        """Alerts of same severity/module blocked during cooldown."""
        # Send first alert
        alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Alert 1",
            message="Message 1",
            module="planning",
        )
        alert_system._last_alert_time[("critical", "planning")] = datetime.now(UTC)

        # Try to send second alert immediately
        alert2 = alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Alert 2",
            message="Message 2",
            module="planning",
        )

        assert not alert_system.should_alert(alert2)

    def test_should_alert_after_cooldown(self, alert_system):
        """Alerts allowed after cooldown expires."""
        alert1 = alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Alert 1",
            message="Message 1",
            module="planning",
        )

        # Set last alert time to 61 seconds ago
        alert_system._last_alert_time[("critical", "planning")] = (
            datetime.now(UTC) - timedelta(seconds=61)
        )

        assert alert_system.should_alert(alert1)

    def test_different_severity_not_blocked(self, alert_system):
        """Different severity levels don't block each other."""
        # Send critical alert
        alert_system._last_alert_time[("critical", "planning")] = datetime.now(UTC)

        # Warning alert should be allowed
        warning = alert_system.create_alert(
            severity=AlertSeverity.WARNING,
            title="Warning",
            message="Warning message",
            module="planning",
        )

        assert alert_system.should_alert(warning)

    def test_different_module_not_blocked(self, alert_system):
        """Different modules don't block each other."""
        # Send alert for planning
        alert_system._last_alert_time[("critical", "planning")] = datetime.now(UTC)

        # Alert for review should be allowed
        review_alert = alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Review Alert",
            message="Review message",
            module="review",
        )

        assert alert_system.should_alert(review_alert)

    def test_cooldown_seconds_property(self, alert_system):
        """Can read cooldown_seconds property."""
        assert alert_system.cooldown_seconds == 60


# =============================================================================
# TestSendAlert
# =============================================================================

class TestSendAlert:
    """Test alert sending functionality."""

    @pytest.mark.asyncio
    async def test_send_alert_success(self, no_cooldown_system):
        """Can send an alert successfully."""
        alert = no_cooldown_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="Test message",
            module="test",
        )

        result = await no_cooldown_system.send_alert(alert)

        assert result is True
        assert alert.sent is True
        assert alert.sent_at is not None

    @pytest.mark.asyncio
    async def test_send_alert_blocked_by_cooldown(self, alert_system):
        """Alert sending blocked during cooldown."""
        # Set cooldown
        alert_system._last_alert_time[("critical", "test")] = datetime.now(UTC)

        alert = alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="Test",
            module="test",
        )

        result = await alert_system.send_alert(alert)

        assert result is False
        assert alert.sent is False

    @pytest.mark.asyncio
    async def test_send_alert_updates_cooldown(self, no_cooldown_system):
        """Sending alert updates cooldown tracking."""
        alert = no_cooldown_system.create_alert(
            severity=AlertSeverity.WARNING,
            title="Test",
            message="Test",
            module="test",
        )

        before = datetime.now(UTC)
        await no_cooldown_system.send_alert(alert)
        after = datetime.now(UTC)

        cooldown_key = ("warning", "test")
        assert cooldown_key in no_cooldown_system._last_alert_time
        last_time = no_cooldown_system._last_alert_time[cooldown_key]
        assert before <= last_time <= after

    @pytest.mark.asyncio
    async def test_send_alert_moves_to_sent_history(self, no_cooldown_system):
        """Sent alerts are moved to sent history."""
        alert = no_cooldown_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="Test",
            module="test",
        )

        await no_cooldown_system.send_alert(alert)

        # Check pending (should be removed)
        pending = no_cooldown_system.get_pending_alerts()
        assert len(pending) == 0

        # Check sent history
        sent = no_cooldown_system.get_sent_alerts()
        assert len(sent) == 1
        assert sent[0].title == "Test"

    @pytest.mark.asyncio
    async def test_send_multiple_alerts(self, no_cooldown_system):
        """Can send multiple alerts."""
        for i in range(3):
            alert = no_cooldown_system.create_alert(
                severity=AlertSeverity.WARNING,
                title=f"Alert {i}",
                message=f"Message {i}",
                module="test",
            )
            await no_cooldown_system.send_alert(alert)

        sent = no_cooldown_system.get_sent_alerts()
        assert len(sent) == 3


# =============================================================================
# TestGetPendingAlerts
# =============================================================================

class TestGetPendingAlerts:
    """Test pending alerts retrieval."""

    def test_get_pending_empty(self, alert_system):
        """Empty system returns empty pending list."""
        assert alert_system.get_pending_alerts() == []

    def test_get_pending_filters_sent(self, alert_system):
        """get_pending_alerts filters out sent alerts."""
        alert1 = alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Alert 1",
            message="Message 1",
            module="test",
        )
        alert_system.create_alert(
            severity=AlertSeverity.WARNING,
            title="Alert 2",
            message="Message 2",
            module="test",
        )

        # Mark first as sent
        alert1.sent = True

        pending = alert_system.get_pending_alerts()
        assert len(pending) == 1
        assert pending[0].title == "Alert 2"

    def test_get_pending_all_unsent(self, alert_system):
        """Returns all unsent alerts."""
        for i in range(5):
            alert_system.create_alert(
                severity=AlertSeverity.WARNING,
                title=f"Alert {i}",
                message=f"Message {i}",
                module="test",
            )

        pending = alert_system.get_pending_alerts()
        assert len(pending) == 5


# =============================================================================
# TestGetSentAlerts
# =============================================================================

class TestGetSentAlerts:
    """Test sent alerts retrieval."""

    @pytest.mark.asyncio
    async def test_get_sent_empty(self, alert_system):
        """Empty system returns empty sent list."""
        assert alert_system.get_sent_alerts() == []

    @pytest.mark.asyncio
    async def test_get_sent_returns_sent_alerts(self, no_cooldown_system):
        """Returns sent alerts."""
        alert = no_cooldown_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="Test",
            module="test",
        )
        await no_cooldown_system.send_alert(alert)

        sent = no_cooldown_system.get_sent_alerts()
        assert len(sent) == 1
        assert sent[0].title == "Test"

    @pytest.mark.asyncio
    async def test_get_sent_with_limit(self, no_cooldown_system):
        """Limit parameter restricts results."""
        for i in range(10):
            alert = no_cooldown_system.create_alert(
                severity=AlertSeverity.WARNING,
                title=f"Alert {i}",
                message=f"Message {i}",
                module="test",
            )
            await no_cooldown_system.send_alert(alert)

        sent = no_cooldown_system.get_sent_alerts(limit=5)
        assert len(sent) == 5

    @pytest.mark.asyncio
    async def test_get_sent_most_recent_first(self, no_cooldown_system):
        """Results are ordered most recent first."""
        for i in range(3):
            alert = no_cooldown_system.create_alert(
                severity=AlertSeverity.WARNING,
                title=f"Alert {i}",
                message=f"Message {i}",
                module="test",
            )
            await no_cooldown_system.send_alert(alert)

        sent = no_cooldown_system.get_sent_alerts()
        # Most recent should be Alert 2
        assert sent[0].title == "Alert 2"
        assert sent[2].title == "Alert 0"

    @pytest.mark.asyncio
    async def test_get_sent_since_filter(self, no_cooldown_system):
        """Since parameter filters by timestamp."""
        # Create alerts with different timestamps
        alert1 = no_cooldown_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Old Alert",
            message="Old",
            module="test",
        )
        await no_cooldown_system.send_alert(alert1)

        cutoff = datetime.now(UTC)

        alert2 = no_cooldown_system.create_alert(
            severity=AlertSeverity.WARNING,
            title="New Alert",
            message="New",
            module="test",
        )
        await no_cooldown_system.send_alert(alert2)

        # Get only alerts since cutoff
        sent = no_cooldown_system.get_sent_alerts(since=cutoff)
        assert len(sent) == 1
        assert sent[0].title == "New Alert"


# =============================================================================
# TestClearPending
# =============================================================================

class TestClearPending:
    """Test clearing pending alerts."""

    def test_clear_pending_empty(self, alert_system):
        """Clearing empty queue returns 0."""
        count = alert_system.clear_pending()
        assert count == 0

    def test_clear_pending_removes_all(self, alert_system):
        """Clearing removes all pending alerts."""
        for i in range(5):
            alert_system.create_alert(
                severity=AlertSeverity.WARNING,
                title=f"Alert {i}",
                message=f"Message {i}",
                module="test",
            )

        count = alert_system.clear_pending()
        assert count == 5
        assert len(alert_system.get_pending_alerts()) == 0

    def test_clear_pending_returns_count(self, alert_system):
        """Returns the number of cleared alerts."""
        alert_system.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test 1",
            message="Test 1",
            module="test",
        )
        alert_system.create_alert(
            severity=AlertSeverity.WARNING,
            title="Test 2",
            message="Test 2",
            module="test",
        )

        count = alert_system.clear_pending()
        assert count == 2


# =============================================================================
# TestAlertSeverityEnum
# =============================================================================

class TestAlertSeverityEnum:
    """Test AlertSeverity enum."""

    def test_critical_value(self):
        """CRITICAL has correct string value."""
        assert AlertSeverity.CRITICAL.value == "critical"

    def test_warning_value(self):
        """WARNING has correct string value."""
        assert AlertSeverity.WARNING.value == "warning"

    def test_two_severity_levels(self):
        """There are exactly two severity levels."""
        assert len(AlertSeverity) == 2


# =============================================================================
# TestPendingAlertDataclass
# =============================================================================

class TestPendingAlertDataclass:
    """Test PendingAlert dataclass."""

    def test_default_sent_false(self):
        """PendingAlert defaults sent to False."""
        alert = PendingAlert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="Test message",
            module="test",
        )
        assert alert.sent is False

    def test_default_sent_at_none(self):
        """PendingAlert defaults sent_at to None."""
        alert = PendingAlert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="Test message",
            module="test",
        )
        assert alert.sent_at is None

    def test_created_at_auto_populated(self):
        """PendingAlert auto-populates created_at."""
        before = datetime.now(UTC)
        alert = PendingAlert(
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="Test message",
            module="test",
        )
        after = datetime.now(UTC)

        assert before <= alert.created_at <= after
