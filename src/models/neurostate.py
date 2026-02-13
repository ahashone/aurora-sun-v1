"""
Neurostate Models for Aurora Sun V1.

Data Classification: ART_9_SPECIAL (all neurostate data is Art. 9 health-related)

References:
- ARCHITECTURE.md Section 3 (Neurotype Segmentation)
- ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
- ARCHITECTURE.md Section 14 (Data Models)
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Index, ForeignKey, JSON
from sqlalchemy.orm import relationship

from src.models.base import Base
from src.lib.encryption import DataClassification, EncryptedField, get_encryption_service


# =============================================================================
# Enums
# =============================================================================

class InertiaType(str, Enum):
    """Types of inertia as defined in ARCHITECTURE.md Section 3."""
    AUTISTIC_INERTIA = "autistic_inertia"      # Monotropism: cannot switch attention
    ACTIVATION_DEFICIT = "activation_deficit"   # ADHD: motivation/activation failure
    DOUBLE_BLOCK = "double_block"              # AuDHD: both types combined


class BurnoutType(str, Enum):
    """Burnout types as defined in ARCHITECTURE.md Section 3."""
    AD_BOOM_BUST = "ad_boom_bust"               # ADHD: hyperfocus -> collapse cycle
    AU_OVERLOAD = "au_overload"                 # Autism: sensory/cognitive overload -> shutdown
    AH_TRIPLE = "ah_triple"                     # AuDHD: all three types combined


class ChannelType(str, Enum):
    """Channel types for AuDHD channel dominance."""
    FOCUS = "focus"
    CREATIVE = "creative"
    SOCIAL = "social"
    PHYSICAL = "physical"
    LEARNING = "learning"


class EnergyLevel(str, Enum):
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
        default=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # User segment (for tracking which profile applies to which segment)
    segment_code = Column(String(2), nullable=True)  # AU or AH

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # Table indices
    __table_args__ = (
        Index("idx_sensory_user_segment", "user_id", "segment_code"),
        Index("idx_sensory_last_assessed", "last_assessed"),
    )

    @property
    def modality_loads(self) -> dict:
        """
        Get decrypted modality loads.

        Data Classification: ART_9_SPECIAL (encrypted)
        """
        if self._modality_loads_plaintext is None:
            return {}
        try:
            # TODO: Integrate EncryptionService.decrypt_field() when available
            # For now, return parsed JSON (will be fixed in next iteration)
            import json
            return json.loads(self._modality_loads_plaintext)
        except Exception:
            return {}

    @modality_loads.setter
    def modality_loads(self, value: dict) -> None:
        """
        Set encrypted modality loads.

        Data Classification: ART_9_SPECIAL (encrypted)
        """
        import json
        # TODO: Integrate EncryptionService.encrypt_field() when available
        # For now, store JSON (will be fixed in next iteration)
        self._modality_loads_plaintext = json.dumps(value)

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
        default=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
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
        # TODO: Integrate EncryptionService.decrypt_field() when available
        return self._notes_plaintext

    @notes.setter
    def notes(self, value: str | None) -> None:
        """Set encrypted notes."""
        # TODO: Integrate EncryptionService.encrypt_field() when available
        self._notes_plaintext = value

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

    # Supporting indicators (JSON)
    indicators = Column(JSON, nullable=True)

    # Assessment notes (encrypted)
    _notes_plaintext = Column("notes", Text, nullable=True)

    # Assessment timestamp
    assessed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # Resolution timestamp (when burnout was addressed)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # Table indices
    __table_args__ = (
        Index("idx_burnout_user_type", "user_id", "burnout_type"),
        Index("idx_burnout_assessed_at", "assessed_at"),
        Index("idx_burnout_resolved", "resolved_at"),
    )

    @property
    def energy_trajectory(self) -> list:
        """Get decrypted energy trajectory."""
        if self._energy_trajectory_plaintext is None:
            return []
        try:
            import json
            return json.loads(self._energy_trajectory_plaintext)
        except Exception:
            return []

    @energy_trajectory.setter
    def energy_trajectory(self, value: list) -> None:
        """Set encrypted energy trajectory."""
        import json
        self._energy_trajectory_plaintext = json.dumps(value)

    @property
    def notes(self) -> str | None:
        """Get decrypted notes."""
        if self._notes_plaintext is None:
            return None
        return self._notes_plaintext

    @notes.setter
    def notes(self, value: str | None) -> None:
        """Set encrypted notes."""
        self._notes_plaintext = value

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

    # Channel scores (0-100 for each channel)
    channel_scores = Column(JSON, nullable=False)

    # Confidence in dominance detection (0-1)
    confidence = Column(Float, default=0.0, nullable=False)

    # Supporting signals (JSON)
    supporting_signals = Column(JSON, nullable=True)

    # Period start
    period_start = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # Period end
    period_end = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # Table indices
    __table_args__ = (
        Index("idx_channel_user_period", "user_id", "period_start"),
        Index("idx_channel_dominant", "dominant_channel"),
    )

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

    # Attempted interventions (JSON array)
    attempted_interventions = Column(JSON, nullable=True)

    # Outcome ("resolved", "ongoing", "escalated")
    outcome = Column(String(20), nullable=True)

    # Duration in minutes (if resolved)
    duration_minutes = Column(Integer, nullable=True)

    # Notes (encrypted)
    _notes_plaintext = Column("notes", Text, nullable=True)

    # Event timestamps
    detected_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # Table indices
    __table_args__ = (
        Index("idx_inertia_user_type", "user_id", "inertia_type"),
        Index("idx_inertia_detected_at", "detected_at"),
        Index("idx_inertia_resolved", "resolved_at"),
    )

    @property
    def notes(self) -> str | None:
        """Get decrypted notes."""
        if self._notes_plaintext is None:
            return None
        return self._notes_plaintext

    @notes.setter
    def notes(self, value: str | None) -> None:
        """Set encrypted notes."""
        self._notes_plaintext = value

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

    # Behavioral proxies used (JSON)
    behavioral_proxies = Column(JSON, nullable=True)

    # Session ID (if applicable)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True, index=True)

    # Prediction timestamp
    predicted_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # Table indices
    __table_args__ = (
        Index("idx_energy_user_predicted", "user_id", "predicted_at"),
        Index("idx_energy_level", "energy_level"),
    )

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
