"""
TRON Compliance Auditor for Aurora Sun V1.

Automated compliance checking:
- GDPR retention enforcement
- Consent audit
- Encryption key rotation scheduling
- Vulnerability scanning (dependency check)

Reference: ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================


class ComplianceStatus(StrEnum):
    """Compliance check result status."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"  # Check not applicable


@dataclass
class ComplianceCheck:
    """Result of a single compliance check.

    Attributes:
        check_name: Name of the compliance check.
        status: Check result (pass/warn/fail/skip).
        description: What was checked.
        details: Additional details or findings.
        timestamp: When the check was performed.
    """

    check_name: str
    status: ComplianceStatus
    description: str
    details: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ComplianceReport:
    """Aggregated compliance report.

    Attributes:
        generated_at: When the report was generated.
        overall_status: Worst status across all checks.
        checks: Individual check results.
        total_checks: Number of checks performed.
        passed: Number of passed checks.
        warnings: Number of warning checks.
        failures: Number of failed checks.
        recommendations: Suggested actions.
    """

    generated_at: datetime
    overall_status: ComplianceStatus
    checks: list[ComplianceCheck] = field(default_factory=list)
    total_checks: int = 0
    passed: int = 0
    warnings: int = 0
    failures: int = 0
    recommendations: list[str] = field(default_factory=list)


# =============================================================================
# Compliance Auditor
# =============================================================================


class ComplianceAuditor:
    """Automated compliance checking for GDPR and security policies.

    Runs deterministic checks against the system configuration and data
    to verify compliance with data protection requirements.

    Usage:
        auditor = ComplianceAuditor()
        retention_result = await auditor.check_retention_compliance(user_records)
        consent_result = await auditor.audit_consent(user_consents)
        key_rotation = await auditor.check_key_rotation(last_rotation)
        vulns = await auditor.scan_vulnerabilities()
        report = auditor.generate_report()
    """

    # GDPR retention limits (in days)
    RETENTION_LIMITS: dict[str, int] = {
        "sessions": 365,          # 1 year for session data
        "energy_records": 365,    # 1 year for energy tracking
        "crisis_events": 730,     # 2 years for crisis data (safety review)
        "consent_records": 1825,  # 5 years for consent records (legal req)
        "user_profiles": 365,     # 1 year after account deletion
        "behavioral_data": 180,   # 6 months for behavioral patterns
    }

    # Key rotation schedule (in days)
    KEY_ROTATION_MAX_DAYS: int = 90  # Rotate encryption keys every 90 days

    def __init__(self) -> None:
        """Initialize the compliance auditor."""
        self._checks: list[ComplianceCheck] = []

    async def check_retention_compliance(
        self,
        records: list[dict[str, str | int | datetime | None]] | None = None,
    ) -> ComplianceCheck:
        """Check GDPR data retention compliance.

        Verifies that no data is stored beyond its retention limit.
        In production, this queries the database directly. Currently
        works with provided records or performs a stub check.

        Args:
            records: Optional list of records with 'table', 'oldest_record_at' fields.

        Returns:
            ComplianceCheck result.
        """
        if records is None:
            # Stub: no database access yet
            check = ComplianceCheck(
                check_name="retention_compliance",
                status=ComplianceStatus.SKIP,
                description="GDPR retention compliance check",
                details="No records provided for checking. Stub mode.",
            )
            self._checks.append(check)
            return check

        violations: list[str] = []
        now = datetime.now(UTC)

        for record in records:
            table = str(record.get("table", "unknown"))
            oldest = record.get("oldest_record_at")

            if oldest is None:
                continue

            if isinstance(oldest, str):
                oldest = datetime.fromisoformat(oldest)

            limit_days = self.RETENTION_LIMITS.get(table)
            if limit_days is None:
                continue

            max_age = timedelta(days=limit_days)
            if isinstance(oldest, datetime) and (now - oldest) > max_age:
                violations.append(
                    f"Table '{table}': oldest record is "
                    f"{(now - oldest).days} days old "
                    f"(limit: {limit_days} days)"
                )

        if violations:
            status = ComplianceStatus.FAIL
            details = "; ".join(violations)
        else:
            status = ComplianceStatus.PASS
            details = f"All {len(records)} tables within retention limits"

        check = ComplianceCheck(
            check_name="retention_compliance",
            status=status,
            description="GDPR retention compliance check",
            details=details,
        )
        self._checks.append(check)
        return check

    async def audit_consent(
        self,
        user_consents: list[dict[str, str | int | bool | None]] | None = None,
    ) -> ComplianceCheck:
        """Audit user consent records.

        Verifies that all users have valid, non-expired consent records.
        Checks for: existence, recency, completeness.

        Args:
            user_consents: Optional list of consent records with
                           'user_id', 'has_consent', 'consented_at' fields.

        Returns:
            ComplianceCheck result.
        """
        if user_consents is None:
            check = ComplianceCheck(
                check_name="consent_audit",
                status=ComplianceStatus.SKIP,
                description="User consent audit",
                details="No consent records provided. Stub mode.",
            )
            self._checks.append(check)
            return check

        total_users = len(user_consents)
        missing_consent: list[int] = []
        expired_consent: list[int] = []

        one_year_ago = datetime.now(UTC) - timedelta(days=365)

        for consent in user_consents:
            uid = consent.get("user_id")
            if uid is None:
                continue
            user_id = int(uid)

            has_consent = consent.get("has_consent", False)
            if not has_consent:
                missing_consent.append(user_id)
                continue

            consented_at = consent.get("consented_at")
            if isinstance(consented_at, str):
                consented_at_dt = datetime.fromisoformat(consented_at)
                if consented_at_dt < one_year_ago:
                    expired_consent.append(user_id)

        issues: list[str] = []
        if missing_consent:
            issues.append(f"{len(missing_consent)} users without consent")
        if expired_consent:
            issues.append(f"{len(expired_consent)} users with expired consent (>1 year)")

        if missing_consent:
            status = ComplianceStatus.FAIL
        elif expired_consent:
            status = ComplianceStatus.WARN
        else:
            status = ComplianceStatus.PASS

        details = "; ".join(issues) if issues else f"All {total_users} users have valid consent"

        check = ComplianceCheck(
            check_name="consent_audit",
            status=status,
            description="User consent audit",
            details=details,
        )
        self._checks.append(check)
        return check

    async def check_key_rotation(
        self,
        last_rotation: datetime | None = None,
    ) -> ComplianceCheck:
        """Check encryption key rotation schedule.

        Verifies that encryption keys have been rotated within the
        required timeframe.

        Args:
            last_rotation: Datetime of last key rotation. None if never rotated.

        Returns:
            ComplianceCheck result.
        """
        if last_rotation is None:
            check = ComplianceCheck(
                check_name="key_rotation",
                status=ComplianceStatus.WARN,
                description="Encryption key rotation check",
                details="No rotation history found. Schedule initial rotation.",
            )
            self._checks.append(check)
            return check

        days_since = (datetime.now(UTC) - last_rotation).days

        if days_since > self.KEY_ROTATION_MAX_DAYS:
            status = ComplianceStatus.FAIL
            details = (
                f"Key rotation overdue: {days_since} days since last rotation "
                f"(max: {self.KEY_ROTATION_MAX_DAYS} days)"
            )
        elif days_since > self.KEY_ROTATION_MAX_DAYS - 14:
            status = ComplianceStatus.WARN
            details = (
                f"Key rotation due soon: {days_since} days since last rotation "
                f"({self.KEY_ROTATION_MAX_DAYS - days_since} days remaining)"
            )
        else:
            status = ComplianceStatus.PASS
            details = (
                f"Key rotation on schedule: {days_since} days since last rotation "
                f"({self.KEY_ROTATION_MAX_DAYS - days_since} days remaining)"
            )

        check = ComplianceCheck(
            check_name="key_rotation",
            status=status,
            description="Encryption key rotation check",
            details=details,
        )
        self._checks.append(check)
        return check

    async def scan_vulnerabilities(
        self,
        dependencies: list[dict[str, str]] | None = None,
    ) -> ComplianceCheck:
        """Scan for known vulnerabilities in dependencies.

        In production, this would run against a vulnerability database.
        Currently performs basic version checking against known issues.

        Args:
            dependencies: Optional list of dicts with 'name' and 'version' keys.

        Returns:
            ComplianceCheck result.
        """
        if dependencies is None:
            check = ComplianceCheck(
                check_name="vulnerability_scan",
                status=ComplianceStatus.SKIP,
                description="Dependency vulnerability scan",
                details="No dependency list provided. Run 'pip audit' for full scan.",
            )
            self._checks.append(check)
            return check

        # Known vulnerable version patterns (simplified)
        known_vulns: dict[str, str] = {
            "cryptography": "41.0.0",  # Example: versions below this have known issues
        }

        findings: list[str] = []
        for dep in dependencies:
            name = dep.get("name", "")
            version = dep.get("version", "")

            if name in known_vulns:
                # Simple version comparison (in production, use packaging.version)
                min_version = known_vulns[name]
                if version < min_version:
                    findings.append(
                        f"{name}=={version} has known vulnerabilities "
                        f"(upgrade to >={min_version})"
                    )

        if findings:
            status = ComplianceStatus.FAIL
            details = "; ".join(findings)
        else:
            status = ComplianceStatus.PASS
            details = f"Scanned {len(dependencies)} dependencies, no known vulnerabilities"

        check = ComplianceCheck(
            check_name="vulnerability_scan",
            status=status,
            description="Dependency vulnerability scan",
            details=details,
        )
        self._checks.append(check)
        return check

    def generate_report(self) -> ComplianceReport:
        """Generate an aggregated compliance report from all checks.

        Returns:
            ComplianceReport with overall status and recommendations.
        """
        total = len(self._checks)
        passed = sum(1 for c in self._checks if c.status == ComplianceStatus.PASS)
        warnings = sum(1 for c in self._checks if c.status == ComplianceStatus.WARN)
        failures = sum(1 for c in self._checks if c.status == ComplianceStatus.FAIL)

        # Overall status is the worst status
        if failures > 0:
            overall = ComplianceStatus.FAIL
        elif warnings > 0:
            overall = ComplianceStatus.WARN
        elif total == 0:
            overall = ComplianceStatus.SKIP
        else:
            overall = ComplianceStatus.PASS

        # Generate recommendations
        recommendations: list[str] = []
        for check in self._checks:
            if check.status == ComplianceStatus.FAIL:
                recommendations.append(
                    f"[CRITICAL] Fix {check.check_name}: {check.details}"
                )
            elif check.status == ComplianceStatus.WARN:
                recommendations.append(
                    f"[WARNING] Review {check.check_name}: {check.details}"
                )

        report = ComplianceReport(
            generated_at=datetime.now(UTC),
            overall_status=overall,
            checks=list(self._checks),
            total_checks=total,
            passed=passed,
            warnings=warnings,
            failures=failures,
            recommendations=recommendations,
        )

        logger.info(
            "tron_compliance_report status=%s total=%d pass=%d warn=%d fail=%d",
            overall.value,
            total,
            passed,
            warnings,
            failures,
        )

        return report

    def reset(self) -> None:
        """Clear all check results. Call before a fresh audit run."""
        self._checks.clear()
