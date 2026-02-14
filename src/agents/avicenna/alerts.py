"""
Avicenna Alert System for Aurora Sun V1.

Manages notifications to admin when quality issues are detected:
- Telegram DM to admin for critical/warning issues
- Rate limiting (cooldown between alerts)
- Pending alert queue

Philosophy: Diagnose, never fix. Human decides.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================


class AlertSeverity(StrEnum):
    """Alert severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"


@dataclass
class PendingAlert:
    """An alert waiting to be sent.

    Attributes:
        severity: Alert severity.
        title: Short alert title.
        message: Full alert message.
        module: Module that produced the alert.
        created_at: When the alert was created.
        sent: Whether the alert has been sent.
        sent_at: When the alert was sent (if sent).
    """

    severity: AlertSeverity
    title: str
    message: str
    module: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    sent: bool = False
    sent_at: datetime | None = None


# =============================================================================
# Alert System
# =============================================================================


class AlertSystem:
    """Manage quality alerts with rate limiting.

    Sends Telegram DMs to admin when critical or warning issues are detected.
    Applies cooldown to prevent alert flooding.

    Args:
        cooldown_seconds: Minimum seconds between alerts of the same type.
        admin_chat_id: Telegram chat ID for admin notifications (stub).

    Usage:
        alerts = AlertSystem(cooldown_seconds=60)
        alert = alerts.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Invalid Transition",
            message="planning: SCOPE -> DONE not in spec",
            module="planning",
        )
        if alerts.should_alert(alert):
            await alerts.send_alert(alert)
    """

    def __init__(
        self,
        cooldown_seconds: int = 60,
        admin_chat_id: int | None = None,
    ) -> None:
        """Initialize alert system with cooldown and optional admin chat ID."""
        self._cooldown_seconds = cooldown_seconds
        self._admin_chat_id = admin_chat_id
        self._pending: list[PendingAlert] = []
        self._sent_history: list[PendingAlert] = []
        # Last alert time by (severity, module) key for cooldown tracking
        self._last_alert_time: dict[tuple[str, str], datetime] = {}

    @property
    def cooldown_seconds(self) -> int:
        """Current cooldown setting in seconds."""
        return self._cooldown_seconds

    def create_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        module: str,
    ) -> PendingAlert:
        """Create a new pending alert.

        Args:
            severity: Alert severity level.
            title: Short alert title.
            message: Full alert message body.
            module: Module that produced the alert.

        Returns:
            The created PendingAlert.
        """
        alert = PendingAlert(
            severity=severity,
            title=title,
            message=message,
            module=module,
        )
        self._pending.append(alert)
        return alert

    def should_alert(self, alert: PendingAlert) -> bool:
        """Check if an alert should be sent (respects cooldown).

        Args:
            alert: The alert to check.

        Returns:
            True if the alert should be sent (cooldown has elapsed).
        """
        cooldown_key = (alert.severity.value, alert.module)
        last_sent = self._last_alert_time.get(cooldown_key)

        if last_sent is None:
            return True

        elapsed = (datetime.now(UTC) - last_sent).total_seconds()
        return elapsed >= self._cooldown_seconds

    async def send_alert(self, alert: PendingAlert) -> bool:
        """Send an alert to admin via Telegram DM.

        In the current implementation, this is a stub that logs the alert
        and marks it as sent. Full Telegram integration will be added
        when the bot infrastructure is connected.

        Args:
            alert: The alert to send.

        Returns:
            True if the alert was sent (or logged) successfully.
        """
        if not self.should_alert(alert):
            logger.debug(
                "avicenna_alert_cooldown severity=%s module=%s",
                alert.severity.value,
                alert.module,
            )
            return False

        # Mark as sent
        alert.sent = True
        alert.sent_at = datetime.now(UTC)

        # Update cooldown tracking
        cooldown_key = (alert.severity.value, alert.module)
        self._last_alert_time[cooldown_key] = alert.sent_at

        # Move from pending to sent history
        if alert in self._pending:
            self._pending.remove(alert)
        self._sent_history.append(alert)

        # Stub: Log instead of sending Telegram DM
        # In production, this would call the Telegram Bot API
        log_level = (
            logging.CRITICAL if alert.severity == AlertSeverity.CRITICAL
            else logging.WARNING
        )
        logger.log(
            log_level,
            "avicenna_alert_sent severity=%s module=%s title=%s",
            alert.severity.value,
            alert.module,
            alert.title,
        )

        return True

    def get_pending_alerts(self) -> list[PendingAlert]:
        """Get all unsent pending alerts.

        Returns:
            List of pending alerts that have not been sent yet.
        """
        return [a for a in self._pending if not a.sent]

    def get_sent_alerts(
        self,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[PendingAlert]:
        """Get sent alert history.

        Args:
            since: Only return alerts sent after this timestamp.
            limit: Maximum number of alerts to return.

        Returns:
            List of sent alerts, most recent first.
        """
        result: list[PendingAlert] = []
        for alert in reversed(self._sent_history):
            if since is not None and alert.sent_at is not None and alert.sent_at < since:
                continue
            result.append(alert)
            if len(result) >= limit:
                break
        return result

    def clear_pending(self) -> int:
        """Clear all pending alerts.

        Returns:
            Number of alerts cleared.
        """
        count = len(self._pending)
        self._pending.clear()
        return count
