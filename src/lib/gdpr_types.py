"""
GDPR types, enums, dataclasses, and protocols.

Extracted from src/lib/gdpr.py for maintainability.
Contains all type definitions used across GDPR sub-modules.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol

from src.lib.encryption import DataClassification

logger = logging.getLogger(__name__)

# Named constant for indefinite retention.
# -1 means the data has no retention limit and is kept indefinitely
# (e.g., anonymized analytics or public data that does not contain PII).
RETENTION_INDEFINITE: int = -1


class ProcessingRestriction(Enum):
    """
    GDPR Art. 18: Restriction of processing.
    User data can be frozen (restricted) when consent is withdrawn
    but data must be retained for legal obligations.
    """
    ACTIVE = "active"           # Normal processing
    RESTRICTED = "restricted"   # No processing, data retained for legal obligation


@dataclass
class RecordsToDelete:
    """Record identified for deletion due to retention policy expiration."""
    table_name: str
    record_id: int
    classification: DataClassification
    created_at: datetime
    days_since_creation: int
    reason: str


@dataclass
class RetentionPolicyConfig:
    """
    Retention policy configuration per data classification.
    Per ARCHITECTURE.md Section 10.6.

    Default retention:
    - SENSITIVE: 0 days (deleted while account active, immediate cascade on delete)
    - ART_9_SPECIAL: 0 days (deleted while account active, immediate cascade on delete)
    - FINANCIAL: 0 days (deleted while account active, immediate cascade on delete)
    - Consent records: 1825 days (5 years after withdrawal - legal obligation)
    - INTERNAL: No retention limit (anonymized analytics)
    - PUBLIC: No retention limit
    """
    retention_days: dict[DataClassification, int] = field(default_factory=lambda: {
        DataClassification.PUBLIC: RETENTION_INDEFINITE,       # No retention needed
        DataClassification.INTERNAL: RETENTION_INDEFINITE,     # Anonymized
        DataClassification.SENSITIVE: 0,                       # Delete while active
        DataClassification.ART_9_SPECIAL: 0,                   # Delete while active
        DataClassification.FINANCIAL: 0,                       # Delete while active
    })

    # Consent records have special retention: 5 years after withdrawal
    CONSENT_RETENTION_DAYS: int = 1825  # 5 years

    def get_retention_days(self, classification: DataClassification) -> int:
        """Get retention days for a classification. RETENTION_INDEFINITE (-1) means indefinite."""
        return self.retention_days.get(classification, 0)

    def is_expired(self, classification: DataClassification, created_at: datetime) -> bool:
        """Check if a record has exceeded its retention period."""
        retention = self.get_retention_days(classification)
        if retention == RETENTION_INDEFINITE:
            return False  # Indefinite retention
        if retention == 0:
            return True  # Delete while active (not stored)

        days_since = (datetime.now(UTC) - created_at).days
        return days_since > retention


class GDPRModuleInterface(Protocol):
    """
    Protocol for GDPR-compliant modules.
    Every module must implement these methods to comply with GDPR.

    Per ARCHITECTURE.md Section 10.5: Module Protocol (Extended)
    """

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """
        GDPR Art. 15 & 20: Export all user data in machine-readable format.
        Called by SW-15 workflow when user requests data export.

        Returns:
            dict: Module-specific user data as JSON-serializable dict
        """
        ...

    async def delete_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 17: Delete all user data (right to be forgotten).
        Called by SW-15 workflow when user requests deletion.

        Must:
        - Delete all records in primary database
        - Delete all vectors in vector store
        - Delete all memories in memory store
        - Delete all Redis keys
        - Mark encryption keys for destruction
        """
        ...

    async def freeze_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 18: Restrict processing of user data.
        Called when user withdraws consent but data must be retained
        for legal obligations (e.g., financial records).

        Must:
        - Set processing_restriction = RESTRICTED
        - Stop all active processing
        - Retain data for legal compliance period
        """
        ...

    async def unfreeze_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 18: Lift restriction on processing.
        Called when user re-consents or restriction reason expires.

        Must:
        - Set processing_restriction = ACTIVE
        - Resume normal processing
        """
        ...


@dataclass
class GDPRExportRecord:
    """Single module's data export for aggregation."""
    module_name: str
    exported_at: datetime
    data: dict[str, Any]
