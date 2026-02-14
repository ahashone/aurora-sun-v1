"""
Neurostate Models for Aurora Sun V1.

Data Classification: ART_9_SPECIAL (all neurostate data is Art. 9 health-related)

References:
- ARCHITECTURE.md Section 3 (Neurotype Segmentation)
- ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
- ARCHITECTURE.md Section 14 (Data Models)
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text

from src.models.base import Base

# =============================================================================
# Enums
# =============================================================================

class InertiaType(StrEnum):
    """Types of inertia as defined in ARCHITECTURE.md Section 3."""
    AUTISTIC_INERTIA = "autistic_inertia"      # Monotropism: cannot switch attention
    ACTIVATION_DEFICIT = "activation_deficit"   # ADHD: motivation/activation failure
    DOUBLE_BLOCK = "double_block"              # AuDHD: both types combined


class BurnoutType(StrEnum):
    """Burnout types as defined in ARCHITECTURE.md Section 3."""
    AD_BOOM_BUST = "ad_boom_bust"               # ADHD: hyperfocus -> collapse cycle
    AU_OVERLOAD = "au_overload"                 # Autism: sensory/cognitive overload -> shutdown
    AH_TRIPLE = "ah_triple"                     # AuDHD: all three types combined


class ChannelType(StrEnum):
    """Channel types for AuDHD channel dominance."""
    FOCUS = "focus"
    CREATIVE = "creative"
    SOCIAL = "social"
    PHYSICAL = "physical"
    LEARNING = "learning"


class EnergyLevel(StrEnum):
    """Energy levels derived from behavioral proxies."""
    CRITICAL = "critical"        # Near shutdown
    LOW = "low"                 # Below baseline
    BASELINE = "baseline"       # Normal functioning
    ELEVATED = "elevated"       # Above baseline
    HYPERFOCUS = "hyperfocus"   # Peak engagement


# =============================================================================
# Sensory Profile Model
# =============================================================================

class SensoryProfile(Base):
    """
    Tracks sensory state for Autism/AuDHD users.

    CRITICAL: Sensory load is CUMULATIVE for AU/AH - no habituation.
    Each modality is tracked separately as per ARCHITECTURE.md.

    Data Classification: ART_9_SPECIAL
    - All sensory data is health-related and encrypted
    - Per-user encryption key + field-level salt
    """

    __tablename__ = "sensory_profiles"

    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Sensory load per modality (0-100 scale)
    # Stored as encrypted JSON for ART.9 classification
    _modality_loads_plaintext = Column(
        "modality_loads",
        Text,
        nullable=True,
    )

    # Current overall sensory state (0-100)
    overall_load = Column(Float, default=0.0, nullable=False)

    # Last assessment timestamp
    last_assessed = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # User segment (for tracking which profile applies to which segment)
    segment_code = Column(String(2), nullable=True)  # AU or AH

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Table indices
    __table_args__ = (
        Index("idx_sensory_user_segment", "user_id", "segment_code"),
        Index("idx_sensory_last_assessed", "last_assessed"),
    )

    @property
    def modality_loads(self) -> dict[str, Any]:
        """Get decrypted modality loads. Data Classification: ART_9_SPECIAL"""
        if self._modality_loads_plaintext is None:
            return {}
        try:
            import json
            plaintext = str(self._modality_loads_plaintext)
            data = json.loads(plaintext)
            # Try to decrypt if it's an encrypted envelope
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                decrypted = get_encryption_service().decrypt_field(encrypted, int(self.user_id), "modality_loads")
                result: dict[str, Any] = json.loads(decrypted)
                return result
            # Plaintext JSON fallback (legacy/unencrypted data)
            if isinstance(data, dict):
                return data
            return {}
        except (json.JSONDecodeError, KeyError, ValueError):
            return {}

    @modality_loads.setter
    def modality_loads(self, value: dict[str, Any]) -> None:
        """Set encrypted modality loads. Data Classification: ART_9_SPECIAL"""
        import json
        import logging
        try:
            from src.lib.encryption import DataClassification, get_encryption_service
            plaintext_json = json.dumps(value)
            encrypted = get_encryption_service().encrypt_field(
                plaintext_json, int(self.user_id), DataClassification.ART_9_SPECIAL, "modality_loads"
            )
            self._modality_loads_plaintext = json.dumps(encrypted.to_db_dict())  # type: ignore[assignment]
        except Exception as e:
            logging.getLogger(__name__).error(
                "Encryption failed for field 'modality_loads', refusing to store plaintext",
                extra={"error": type(e).__name__},
            )
            raise ValueError("Cannot store data: encryption service unavailable") from e

    def __repr__(self) -> str:
        return f"<SensoryProfile(user_id={self.user_id}, overall_load={self.overall_load:.1f})>"


# =============================================================================
# Masking Log Model
# =============================================================================

class MaskingLog(Base):
    """
    Tracks masking behavior and load for AuDHD users.

    CRITICAL: AuDHD has EXPONENTIAL double-masking cost per ARCHITECTURE.md.
    Masking in different contexts accumulates with compounding cost.

    Data Classification: ART_9_SPECIAL
    - All masking data is health-related and encrypted
    """

    __tablename__ = "masking_logs"

    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Context where masking occurred (e.g., "work", "social", "family")
    context = Column(String(50), nullable=False)

    # Type of masking behavior
    masking_type = Column(String(100), nullable=False)

    # Masking load score (0-100)
    # For AuDHD: exponential accumulation per context
    load_score = Column(Float, default=0.0, nullable=False)

    # Duration in minutes
    duration_minutes = Column(Integer, nullable=True)

    # Notes (encrypted)
    _notes_plaintext = Column("notes", Text, nullable=True)

    # Timestamp
    logged_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Table indices
    __table_args__ = (
        Index("idx_masking_user_context", "user_id", "context"),
        Index("idx_masking_logged_at", "logged_at"),
    )

    @property
    def notes(self) -> str | None:
        """Get decrypted notes."""
        if self._notes_plaintext is None:
            return None
        try:
            import json
            data = json.loads(str(self._notes_plaintext))
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                return get_encryption_service().decrypt_field(encrypted, int(self.user_id), "notes")
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return str(self._notes_plaintext)

    @notes.setter
    def notes(self, value: str | None) -> None:
        """Set encrypted notes."""
        if value is None:
            self._notes_plaintext = None  # type: ignore[assignment]
            return
        try:
            import json

            from src.lib.encryption import DataClassification, get_encryption_service
            encrypted = get_encryption_service().encrypt_field(
                value, int(self.user_id), DataClassification.ART_9_SPECIAL, "notes"
            )
            self._notes_plaintext = json.dumps(encrypted.to_db_dict())  # type: ignore[assignment]
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                "Encryption failed for field 'notes', refusing to store plaintext",
                extra={"error": type(e).__name__},
            )
            raise ValueError("Cannot store data: encryption service unavailable") from e

    def __repr__(self) -> str:
        return f"<MaskingLog(user_id={self.user_id}, context={self.context}, load={self.load_score:.1f})>"


# =============================================================================
# Burnout Assessment Model
# =============================================================================

class BurnoutAssessment(Base):
    """
    Tracks burnout type and severity for all neurodivergent users.

    CRITICAL: Three distinct burnout types by segment:
    - AD: Boom-Bust cycle (hyperfocus -> crash)
    - AU: Overload -> Shutdown (sensory/cognitive)
    - AH: All three combined

    Data Classification: ART_9_SPECIAL
    - All burnout data is health-related and encrypted
    """

    __tablename__ = "burnout_assessments"

    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Burnout type classification
    burnout_type = Column(String(50), nullable=False)  # InertiaType enum values

    # Severity score (0-100)
    severity_score = Column(Float, default=0.0, nullable=False)

    # Energy trajectory (JSON array of daily energy levels)
    # Encrypted for ART.9 classification
    _energy_trajectory_plaintext = Column(
        "energy_trajectory",
        Text,
        nullable=True,
    )

    # Supporting indicators (encrypted JSON) - FINDING-022: ART_9 data must be encrypted
    _indicators_plaintext = Column("indicators", Text, nullable=True)

    # Assessment notes (encrypted)
    _notes_plaintext = Column("notes", Text, nullable=True)

    # Assessment timestamp
    assessed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Resolution timestamp (when burnout was addressed)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Table indices
    __table_args__ = (
        Index("idx_burnout_user_type", "user_id", "burnout_type"),
        Index("idx_burnout_assessed_at", "assessed_at"),
        Index("idx_burnout_resolved", "resolved_at"),
    )

    @property
    def indicators(self) -> dict[str, Any] | None:
        """Get decrypted indicators. Data Classification: ART_9_SPECIAL"""
        if self._indicators_plaintext is None:
            return None
        try:
            import json
            plaintext = str(self._indicators_plaintext)
            data = json.loads(plaintext)
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                decrypted = get_encryption_service().decrypt_field(encrypted, int(self.user_id), "indicators")
                result: dict[str, Any] = json.loads(decrypted)
                return result
            if isinstance(data, (dict, list)):
                return data  # type: ignore[return-value]
            return None
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    @indicators.setter
    def indicators(self, value: dict[str, Any] | list[Any] | None) -> None:
        """Set encrypted indicators. Data Classification: ART_9_SPECIAL"""
        if value is None:
            self._indicators_plaintext = None  # type: ignore[assignment]
            return
        import json
        import logging
        try:
            from src.lib.encryption import DataClassification, get_encryption_service
            plaintext_json = json.dumps(value)
            encrypted = get_encryption_service().encrypt_field(
                plaintext_json, int(self.user_id), DataClassification.ART_9_SPECIAL, "indicators"
            )
            self._indicators_plaintext = json.dumps(encrypted.to_db_dict())  # type: ignore[assignment]
        except Exception as e:
            logging.getLogger(__name__).error(
                "Encryption failed for field 'indicators', refusing to store plaintext",
                extra={"error": type(e).__name__},
            )
            raise ValueError("Cannot store data: encryption service unavailable") from e

    @property
    def energy_trajectory(self) -> list[Any]:
        """Get decrypted energy trajectory."""
        if self._energy_trajectory_plaintext is None:
            return []
        try:
            import json
            plaintext = str(self._energy_trajectory_plaintext)
            data = json.loads(plaintext)
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                decrypted = get_encryption_service().decrypt_field(encrypted, int(self.user_id), "energy_trajectory")
                result: list[Any] = json.loads(decrypted)
                return result
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, KeyError, ValueError):
            return []

    @energy_trajectory.setter
    def energy_trajectory(self, value: list[Any]) -> None:
        """Set encrypted energy trajectory."""
        import json
        import logging
        try:
            from src.lib.encryption import DataClassification, get_encryption_service
            plaintext_json = json.dumps(value)
            encrypted = get_encryption_service().encrypt_field(
                plaintext_json, int(self.user_id), DataClassification.ART_9_SPECIAL, "energy_trajectory"
            )
            self._energy_trajectory_plaintext = json.dumps(encrypted.to_db_dict())  # type: ignore[assignment]
        except Exception as e:
            logging.getLogger(__name__).error(
                "Encryption failed for field 'energy_trajectory', refusing to store plaintext",
                extra={"error": type(e).__name__},
            )
            raise ValueError("Cannot store data: encryption service unavailable") from e

    @property
    def notes(self) -> str | None:
        """Get decrypted notes."""
        if self._notes_plaintext is None:
            return None
        try:
            import json
            data = json.loads(str(self._notes_plaintext))
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                return get_encryption_service().decrypt_field(encrypted, int(self.user_id), "notes")
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return str(self._notes_plaintext)

    @notes.setter
    def notes(self, value: str | None) -> None:
        """Set encrypted notes."""
        if value is None:
            self._notes_plaintext = None  # type: ignore[assignment]
            return
        try:
            import json

            from src.lib.encryption import DataClassification, get_encryption_service
            encrypted = get_encryption_service().encrypt_field(
                value, int(self.user_id), DataClassification.ART_9_SPECIAL, "notes"
            )
            self._notes_plaintext = json.dumps(encrypted.to_db_dict())  # type: ignore[assignment]
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                "Encryption failed for field 'notes', refusing to store plaintext",
                extra={"error": type(e).__name__},
            )
            raise ValueError("Cannot store data: encryption service unavailable") from e

    def __repr__(self) -> str:
        return f"<BurnoutAssessment(user_id={self.user_id}, type={self.burnout_type}, severity={self.severity_score:.1f})>"


# =============================================================================
# Channel State Model
# =============================================================================

class ChannelState(Base):
    """
    Tracks channel dominance for AuDHD users.

    CRITICAL: AuDHD has variable channel dominance - ADHD-day vs Autism-day.
    Detected via behavioral signals in conversation.

    Data Classification: ART_9_SPECIAL
    """

    __tablename__ = "channel_states"

    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Dominant channel for this period
    dominant_channel = Column(String(20), nullable=False)  # ChannelType enum values

    # Channel scores (0-100 for each channel) - FINDING-022: ART_9 data must be encrypted
    _channel_scores_plaintext = Column("channel_scores", Text, nullable=False)

    # Confidence in dominance detection (0-1)
    confidence = Column(Float, default=0.0, nullable=False)

    # Supporting signals - FINDING-022: ART_9 data must be encrypted
    _supporting_signals_plaintext = Column("supporting_signals", Text, nullable=True)

    # Period start
    period_start = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Period end
    period_end = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Table indices
    __table_args__ = (
        Index("idx_channel_user_period", "user_id", "period_start"),
        Index("idx_channel_dominant", "dominant_channel"),
    )

    @property
    def channel_scores(self) -> dict[str, Any]:
        """Get decrypted channel scores. Data Classification: ART_9_SPECIAL"""
        if self._channel_scores_plaintext is None:
            return {}
        try:
            import json
            plaintext = str(self._channel_scores_plaintext)
            data = json.loads(plaintext)
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                decrypted = get_encryption_service().decrypt_field(encrypted, int(self.user_id), "channel_scores")
                result: dict[str, Any] = json.loads(decrypted)
                return result
            if isinstance(data, dict):
                return data
            return {}
        except (json.JSONDecodeError, KeyError, ValueError):
            return {}

    @channel_scores.setter
    def channel_scores(self, value: dict[str, Any]) -> None:
        """Set encrypted channel scores. Data Classification: ART_9_SPECIAL"""
        import json
        import logging
        try:
            from src.lib.encryption import DataClassification, get_encryption_service
            plaintext_json = json.dumps(value)
            encrypted = get_encryption_service().encrypt_field(
                plaintext_json, int(self.user_id), DataClassification.ART_9_SPECIAL, "channel_scores"
            )
            self._channel_scores_plaintext = json.dumps(encrypted.to_db_dict())  # type: ignore[assignment]
        except Exception as e:
            logging.getLogger(__name__).error(
                "Encryption failed for field 'channel_scores', refusing to store plaintext",
                extra={"error": type(e).__name__},
            )
            raise ValueError("Cannot store data: encryption service unavailable") from e

    @property
    def supporting_signals(self) -> dict[str, Any] | None:
        """Get decrypted supporting signals. Data Classification: ART_9_SPECIAL"""
        if self._supporting_signals_plaintext is None:
            return None
        try:
            import json
            plaintext = str(self._supporting_signals_plaintext)
            data = json.loads(plaintext)
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                decrypted = get_encryption_service().decrypt_field(encrypted, int(self.user_id), "supporting_signals")
                result: dict[str, Any] = json.loads(decrypted)
                return result
            if isinstance(data, (dict, list)):
                return data  # type: ignore[return-value]
            return None
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    @supporting_signals.setter
    def supporting_signals(self, value: dict[str, Any] | list[Any] | None) -> None:
        """Set encrypted supporting signals. Data Classification: ART_9_SPECIAL"""
        if value is None:
            self._supporting_signals_plaintext = None  # type: ignore[assignment]
            return
        import json
        import logging
        try:
            from src.lib.encryption import DataClassification, get_encryption_service
            plaintext_json = json.dumps(value)
            encrypted = get_encryption_service().encrypt_field(
                plaintext_json, int(self.user_id), DataClassification.ART_9_SPECIAL, "supporting_signals"
            )
            self._supporting_signals_plaintext = json.dumps(encrypted.to_db_dict())  # type: ignore[assignment]
        except Exception as e:
            logging.getLogger(__name__).error(
                "Encryption failed for field 'supporting_signals', refusing to store plaintext",
                extra={"error": type(e).__name__},
            )
            raise ValueError("Cannot store data: encryption service unavailable") from e

    def __repr__(self) -> str:
        return f"<ChannelState(user_id={self.user_id}, dominant={self.dominant_channel}, confidence={self.confidence:.2f})>"


# =============================================================================
# Inertia Event Model
# =============================================================================

class InertiaEvent(Base):
    """
    Tracks inertia events for all neurodivergent users.

    CRITICAL: Three types of inertia:
    - Autistic Inertia: Cannot initiate (monotropism)
    - Activation Deficit: Cannot motivate (ADHD)
    - Double Block: Both combined (AuDHD)

    Data Classification: ART_9_SPECIAL
    """

    __tablename__ = "inertia_events"

    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Inertia type
    inertia_type = Column(String(50), nullable=False)  # InertiaType enum values

    # Severity (0-100)
    severity = Column(Float, default=0.0, nullable=False)

    # Trigger (what caused the inertia)
    trigger = Column(String(100), nullable=True)

    # Attempted interventions - FINDING-022: ART_9 data must be encrypted
    _attempted_interventions_plaintext = Column("attempted_interventions", Text, nullable=True)

    # Outcome ("resolved", "ongoing", "escalated")
    outcome = Column(String(20), nullable=True)

    # Duration in minutes (if resolved)
    duration_minutes = Column(Integer, nullable=True)

    # Notes (encrypted)
    _notes_plaintext = Column("notes", Text, nullable=True)

    # Event timestamps
    detected_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Table indices
    __table_args__ = (
        Index("idx_inertia_user_type", "user_id", "inertia_type"),
        Index("idx_inertia_detected_at", "detected_at"),
        Index("idx_inertia_resolved", "resolved_at"),
    )

    @property
    def attempted_interventions(self) -> list[Any] | None:
        """Get decrypted attempted interventions. Data Classification: ART_9_SPECIAL"""
        if self._attempted_interventions_plaintext is None:
            return None
        try:
            import json
            plaintext = str(self._attempted_interventions_plaintext)
            data = json.loads(plaintext)
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                decrypted = get_encryption_service().decrypt_field(encrypted, int(self.user_id), "attempted_interventions")
                result: list[Any] = json.loads(decrypted)
                return result
            if isinstance(data, list):
                return data
            return None
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    @attempted_interventions.setter
    def attempted_interventions(self, value: list[Any] | None) -> None:
        """Set encrypted attempted interventions. Data Classification: ART_9_SPECIAL"""
        if value is None:
            self._attempted_interventions_plaintext = None  # type: ignore[assignment]
            return
        import json
        import logging
        try:
            from src.lib.encryption import DataClassification, get_encryption_service
            plaintext_json = json.dumps(value)
            encrypted = get_encryption_service().encrypt_field(
                plaintext_json, int(self.user_id), DataClassification.ART_9_SPECIAL, "attempted_interventions"
            )
            self._attempted_interventions_plaintext = json.dumps(encrypted.to_db_dict())  # type: ignore[assignment]
        except Exception as e:
            logging.getLogger(__name__).error(
                "Encryption failed for field 'attempted_interventions', refusing to store plaintext",
                extra={"error": type(e).__name__},
            )
            raise ValueError("Cannot store data: encryption service unavailable") from e

    @property
    def notes(self) -> str | None:
        """Get decrypted notes."""
        if self._notes_plaintext is None:
            return None
        try:
            import json
            data = json.loads(str(self._notes_plaintext))
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                return get_encryption_service().decrypt_field(encrypted, int(self.user_id), "notes")
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return str(self._notes_plaintext)

    @notes.setter
    def notes(self, value: str | None) -> None:
        """Set encrypted notes."""
        if value is None:
            self._notes_plaintext = None  # type: ignore[assignment]
            return
        try:
            import json

            from src.lib.encryption import DataClassification, get_encryption_service
            encrypted = get_encryption_service().encrypt_field(
                value, int(self.user_id), DataClassification.ART_9_SPECIAL, "notes"
            )
            self._notes_plaintext = json.dumps(encrypted.to_db_dict())  # type: ignore[assignment]
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                "Encryption failed for field 'notes', refusing to store plaintext",
                extra={"error": type(e).__name__},
            )
            raise ValueError("Cannot store data: encryption service unavailable") from e

    def __repr__(self) -> str:
        return f"<InertiaEvent(user_id={self.user_id}, type={self.inertia_type}, severity={self.severity:.1f})>"


# =============================================================================
# Energy Level Model (for behavioral proxy tracking)
# =============================================================================

class EnergyLevelRecord(Base):
    """
    Records energy levels derived from behavioral proxies.

    CRITICAL: Behavioral proxies for energy:
    - Response latency
    - Message length
    - Vocabulary complexity
    - Time-of-day patterns

    Data Classification: ART_9_SPECIAL
    """

    __tablename__ = "energy_level_records"

    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Energy level
    energy_level = Column(String(20), nullable=False)  # EnergyLevel enum values

    # Numeric score (0-100)
    energy_score = Column(Float, default=50.0, nullable=False)

    # Behavioral proxies used - FINDING-022: ART_9 data must be encrypted
    _behavioral_proxies_plaintext = Column("behavioral_proxies", Text, nullable=True)

    # Session ID (if applicable)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True, index=True)

    # Prediction timestamp
    predicted_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Table indices
    __table_args__ = (
        Index("idx_energy_user_predicted", "user_id", "predicted_at"),
        Index("idx_energy_level", "energy_level"),
    )

    @property
    def behavioral_proxies(self) -> dict[str, Any] | None:
        """Get decrypted behavioral proxies. Data Classification: ART_9_SPECIAL"""
        if self._behavioral_proxies_plaintext is None:
            return None
        try:
            import json
            plaintext = str(self._behavioral_proxies_plaintext)
            data = json.loads(plaintext)
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                decrypted = get_encryption_service().decrypt_field(encrypted, int(self.user_id), "behavioral_proxies")
                result: dict[str, Any] = json.loads(decrypted)
                return result
            if isinstance(data, (dict, list)):
                return data  # type: ignore[return-value]
            return None
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    @behavioral_proxies.setter
    def behavioral_proxies(self, value: dict[str, Any] | list[Any] | None) -> None:
        """Set encrypted behavioral proxies. Data Classification: ART_9_SPECIAL"""
        if value is None:
            self._behavioral_proxies_plaintext = None  # type: ignore[assignment]
            return
        import json
        import logging
        try:
            from src.lib.encryption import DataClassification, get_encryption_service
            plaintext_json = json.dumps(value)
            encrypted = get_encryption_service().encrypt_field(
                plaintext_json, int(self.user_id), DataClassification.ART_9_SPECIAL, "behavioral_proxies"
            )
            self._behavioral_proxies_plaintext = json.dumps(encrypted.to_db_dict())  # type: ignore[assignment]
        except Exception as e:
            logging.getLogger(__name__).error(
                "Encryption failed for field 'behavioral_proxies', refusing to store plaintext",
                extra={"error": type(e).__name__},
            )
            raise ValueError("Cannot store data: encryption service unavailable") from e

    def __repr__(self) -> str:
        return f"<EnergyLevelRecord(user_id={self.user_id}, level={self.energy_level}, score={self.energy_score:.1f})>"


__all__ = [
    # Enums
    "InertiaType",
    "BurnoutType",
    "ChannelType",
    "EnergyLevel",
    # Models
    "SensoryProfile",
    "MaskingLog",
    "BurnoutAssessment",
    "ChannelState",
    "InertiaEvent",
    "EnergyLevelRecord",
]
