"""
TRON Threat Monitor for Aurora Sun V1.

Deterministic, rule-based threat detection:
- Anomaly detection (unusual login patterns, rate limit violations, injection attempts)
- Threat scoring (no ML, pure rules)
- Active threat tracking

Reference: ARCHITECTURE.md Section 7 (TRON Agent)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================


class ThreatLevel(StrEnum):
    """Threat severity levels."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ThreatScore:
    """Calculated threat score for a user or system event.

    Attributes:
        score: Numeric score (0-100).
        level: Derived threat level.
        factors: Contributing factors with their individual scores.
        timestamp: When the score was calculated.
    """

    score: int
    level: ThreatLevel
    factors: dict[str, int] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ActiveThreat:
    """An active threat being tracked.

    Attributes:
        threat_id: Unique identifier.
        level: Threat severity.
        threat_type: Type of threat detected.
        description: Human-readable description.
        user_id: Affected user (if applicable).
        detected_at: When the threat was first detected.
        last_seen_at: When the threat was last observed.
        event_count: Number of times this threat has been observed.
        resolved: Whether the threat has been resolved.
    """

    threat_id: str
    level: ThreatLevel
    threat_type: str
    description: str
    user_id: int | None = None
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_count: int = 1
    resolved: bool = False


# =============================================================================
# Anomaly Types
# =============================================================================


class AnomalyType(StrEnum):
    """Types of anomalies that TRON detects."""

    RATE_LIMIT_VIOLATION = "rate_limit_violation"
    INJECTION_ATTEMPT = "injection_attempt"
    UNUSUAL_LOGIN_PATTERN = "unusual_login_pattern"
    BRUTE_FORCE = "brute_force"
    DATA_EXFILTRATION = "data_exfiltration"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    SUSPICIOUS_PAYLOAD = "suspicious_payload"


# =============================================================================
# Threat Monitor
# =============================================================================


class ThreatMonitor:
    """Rule-based threat detection and monitoring.

    Detects anomalies using deterministic rules (no ML). Maintains
    a registry of active threats and calculates threat scores.

    Usage:
        monitor = ThreatMonitor()
        anomalies = monitor.detect_anomalies(user_id=1, event_type="login", details={})
        score = monitor.calculate_threat_score(user_id=1)
        threats = monitor.get_active_threats()
    """

    # Scoring weights per anomaly type
    ANOMALY_SCORES: dict[str, int] = {
        AnomalyType.RATE_LIMIT_VIOLATION: 15,
        AnomalyType.INJECTION_ATTEMPT: 40,
        AnomalyType.UNUSUAL_LOGIN_PATTERN: 10,
        AnomalyType.BRUTE_FORCE: 35,
        AnomalyType.DATA_EXFILTRATION: 50,
        AnomalyType.PRIVILEGE_ESCALATION: 60,
        AnomalyType.SUSPICIOUS_PAYLOAD: 30,
    }

    # Thresholds for threat levels
    LEVEL_THRESHOLDS: list[tuple[int, ThreatLevel]] = [
        (80, ThreatLevel.CRITICAL),
        (60, ThreatLevel.HIGH),
        (40, ThreatLevel.MEDIUM),
        (20, ThreatLevel.LOW),
        (0, ThreatLevel.NONE),
    ]

    # Rate limit violation thresholds
    RATE_LIMIT_WINDOW_SECONDS: int = 300  # 5 minutes
    RATE_LIMIT_MAX_EVENTS: int = 50

    # Brute force detection
    BRUTE_FORCE_WINDOW_SECONDS: int = 60  # 1 minute
    BRUTE_FORCE_MAX_FAILURES: int = 5

    def __init__(self) -> None:
        """Initialize the threat monitor."""
        self._active_threats: dict[str, ActiveThreat] = {}
        self._threat_counter: int = 0
        # Per-user event tracking for rate limiting
        self._user_events: dict[int, list[float]] = defaultdict(list)
        # Per-user failed login tracking
        self._failed_logins: dict[int, list[float]] = defaultdict(list)
        # Per-user anomaly history for scoring
        self._user_anomalies: dict[int, list[tuple[str, datetime]]] = defaultdict(list)

    def detect_anomalies(
        self,
        user_id: int | None = None,
        event_type: str = "",
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> list[ActiveThreat]:
        """Detect anomalies in a user event.

        Runs all detection rules against the event and returns any
        threats detected.

        Args:
            user_id: User who triggered the event.
            event_type: Type of event (e.g. "login", "message", "api_call").
            details: Additional event details.

        Returns:
            List of newly detected threats.
        """
        if details is None:
            details = {}

        detected: list[ActiveThreat] = []
        now = time.monotonic()

        # Rule 1: Rate limit violations
        if user_id is not None:
            self._user_events[user_id].append(now)
            # Clean old events
            cutoff = now - self.RATE_LIMIT_WINDOW_SECONDS
            self._user_events[user_id] = [
                t for t in self._user_events[user_id] if t > cutoff
            ]
            if len(self._user_events[user_id]) > self.RATE_LIMIT_MAX_EVENTS:
                threat = self._create_threat(
                    level=ThreatLevel.MEDIUM,
                    threat_type=AnomalyType.RATE_LIMIT_VIOLATION,
                    description=(
                        f"Rate limit exceeded: {len(self._user_events[user_id])} events "
                        f"in {self.RATE_LIMIT_WINDOW_SECONDS}s window"
                    ),
                    user_id=user_id,
                )
                detected.append(threat)

        # Rule 2: Injection attempts
        payload = str(details.get("payload", ""))
        if self._check_injection(payload):
            threat = self._create_threat(
                level=ThreatLevel.HIGH,
                threat_type=AnomalyType.INJECTION_ATTEMPT,
                description="Injection attempt detected in payload",
                user_id=user_id,
            )
            detected.append(threat)

        # Rule 3: Brute force detection (failed logins)
        if event_type == "login_failure" and user_id is not None:
            self._failed_logins[user_id].append(now)
            cutoff = now - self.BRUTE_FORCE_WINDOW_SECONDS
            self._failed_logins[user_id] = [
                t for t in self._failed_logins[user_id] if t > cutoff
            ]
            if len(self._failed_logins[user_id]) >= self.BRUTE_FORCE_MAX_FAILURES:
                threat = self._create_threat(
                    level=ThreatLevel.HIGH,
                    threat_type=AnomalyType.BRUTE_FORCE,
                    description=(
                        f"Brute force detected: {len(self._failed_logins[user_id])} "
                        f"failed logins in {self.BRUTE_FORCE_WINDOW_SECONDS}s"
                    ),
                    user_id=user_id,
                )
                detected.append(threat)

        # Rule 4: Suspicious payload patterns
        if details.get("suspicious", False):
            threat = self._create_threat(
                level=ThreatLevel.MEDIUM,
                threat_type=AnomalyType.SUSPICIOUS_PAYLOAD,
                description="Suspicious payload flagged by upstream validator",
                user_id=user_id,
            )
            detected.append(threat)

        # Track anomalies for scoring
        if user_id is not None:
            for threat in detected:
                self._user_anomalies[user_id].append(
                    (threat.threat_type, datetime.now(UTC))
                )

        return detected

    def _check_injection(self, payload: str) -> bool:
        """Check payload for common injection patterns.

        Args:
            payload: String to check.

        Returns:
            True if injection patterns detected.
        """
        if not payload:
            return False

        payload_lower = payload.lower()

        # SQL injection patterns
        sql_patterns = [
            "' or '1'='1",
            "'; drop table",
            "union select",
            "' or 1=1",
            "1; delete from",
        ]

        # XSS patterns
        xss_patterns = [
            "<script>",
            "javascript:",
            "onerror=",
            "onload=",
        ]

        # Path traversal
        path_patterns = [
            "../",
            "..\\",
            "/etc/passwd",
        ]

        all_patterns = sql_patterns + xss_patterns + path_patterns
        return any(p in payload_lower for p in all_patterns)

    def _create_threat(
        self,
        level: ThreatLevel,
        threat_type: str,
        description: str,
        user_id: int | None = None,
    ) -> ActiveThreat:
        """Create and register a new active threat.

        Args:
            level: Threat severity.
            threat_type: Type of threat.
            description: Human-readable description.
            user_id: Affected user.

        Returns:
            The created ActiveThreat.
        """
        self._threat_counter += 1
        threat_id = f"TRON-{self._threat_counter:06d}"

        # Check if similar active threat exists (dedup)
        for existing in self._active_threats.values():
            if (
                not existing.resolved
                and existing.threat_type == threat_type
                and existing.user_id == user_id
            ):
                existing.last_seen_at = datetime.now(UTC)
                existing.event_count += 1
                # Escalate if repeated
                if existing.event_count >= 5 and existing.level != ThreatLevel.CRITICAL:
                    existing.level = ThreatLevel(
                        min(
                            ThreatLevel.CRITICAL,
                            self._escalate_level(existing.level),
                        )
                    )
                logger.warning(
                    "tron_threat_updated id=%s type=%s count=%d",
                    existing.threat_id,
                    existing.threat_type,
                    existing.event_count,
                )
                return existing

        threat = ActiveThreat(
            threat_id=threat_id,
            level=level,
            threat_type=threat_type,
            description=description,
            user_id=user_id,
        )
        self._active_threats[threat_id] = threat

        logger.warning(
            "tron_threat_detected id=%s level=%s type=%s",
            threat_id,
            level.value,
            threat_type,
        )

        return threat

    def _escalate_level(self, current: ThreatLevel) -> ThreatLevel:
        """Escalate a threat level by one step.

        Args:
            current: Current threat level.

        Returns:
            Next higher threat level.
        """
        levels = [
            ThreatLevel.NONE,
            ThreatLevel.LOW,
            ThreatLevel.MEDIUM,
            ThreatLevel.HIGH,
            ThreatLevel.CRITICAL,
        ]
        idx = levels.index(current)
        return levels[min(idx + 1, len(levels) - 1)]

    def calculate_threat_score(self, user_id: int) -> ThreatScore:
        """Calculate threat score for a user.

        Based on anomaly history in the last hour. Pure rules, no ML.

        Args:
            user_id: User to score.

        Returns:
            ThreatScore with numeric score and derived level.
        """
        one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
        recent_anomalies = [
            (atype, ts)
            for atype, ts in self._user_anomalies.get(user_id, [])
            if ts > one_hour_ago
        ]

        # Calculate score from anomaly weights
        factors: dict[str, int] = {}
        total_score = 0

        for atype, _ts in recent_anomalies:
            weight = self.ANOMALY_SCORES.get(atype, 10)
            factors[atype] = factors.get(atype, 0) + weight
            total_score += weight

        # Cap at 100
        total_score = min(100, total_score)

        # Determine level
        level = ThreatLevel.NONE
        for threshold, threat_level in self.LEVEL_THRESHOLDS:
            if total_score >= threshold:
                level = threat_level
                break

        return ThreatScore(
            score=total_score,
            level=level,
            factors=factors,
        )

    def get_active_threats(
        self,
        level: ThreatLevel | None = None,
        user_id: int | None = None,
    ) -> list[ActiveThreat]:
        """Get currently active (unresolved) threats.

        Args:
            level: Filter by threat level.
            user_id: Filter by user.

        Returns:
            List of active threats matching the filters.
        """
        result: list[ActiveThreat] = []
        for threat in self._active_threats.values():
            if threat.resolved:
                continue
            if level is not None and threat.level != level:
                continue
            if user_id is not None and threat.user_id != user_id:
                continue
            result.append(threat)
        return result

    def resolve_threat(self, threat_id: str) -> bool:
        """Mark a threat as resolved.

        Args:
            threat_id: Threat identifier to resolve.

        Returns:
            True if the threat was found and resolved.
        """
        threat = self._active_threats.get(threat_id)
        if threat is None:
            return False
        threat.resolved = True
        logger.info("tron_threat_resolved id=%s", threat_id)
        return True
