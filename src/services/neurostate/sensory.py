"""
Sensory State Assessment Service for Aurora Sun V1.

For Autism/AuDHD: cumulative sensory load tracking, no habituation.
Each modality is tracked separately as per ARCHITECTURE.md Section 3.

References:
- ARCHITECTURE.md Section 3 (Neurotype Segmentation)
- ARCHITECTURE.md Section 3.2 (Sensory State - AU/AH)
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.models.neurostate import SensoryProfile

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SensoryState:
    """Represents the current sensory state for a user."""

    user_id: int
    modality_loads: dict[str, float]  # Per-modality loads (0-100)
    overall_load: float                 # Overall load (0-100)
    last_assessed: datetime
    segment_code: str                   # AU or AH
    is_overloaded: bool                 # True if any modality > 80%
    is_critical: bool                   # True if any modality > 95%


@dataclass
class ModalityInput:
    """Input for updating a single modality load."""

    modality: str
    load_delta: float                   # Change in load (-100 to +100)
    context: str                        # What caused the change


# =============================================================================
# Service
# =============================================================================

class SensoryStateAssessment:
    """
    Tracks sensory state for Autism/AuDHD users.

    Key Principles:
    - Sensory load is CUMULATIVE for AU/AH (no habituation)
    - Each modality tracked separately: visual, auditory, tactile, olfactory, proprioceptive
    - Recovery requires REDUCTION of load, not time alone
    - AU: High sensory sensitivity, slower recovery
    - AH: Variable sensitivity based on channel dominance

    Usage:
        service = SensoryStateAssessment(db)
        state = await service.assess(user_id=123, current_load={...})
    """

    MODALITIES = ["visual", "auditory", "tactile", "olfactory", "proprioceptive"]

    # Thresholds
    OVERLOAD_THRESHOLD = 80.0
    CRITICAL_THRESHOLD = 95.0

    def __init__(self, db: Session):
        """
        Initialize the sensory state assessment service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    async def assess(
        self,
        user_id: int,
        current_load: dict[str, float] | None = None,
    ) -> SensoryState:
        """
        Assess the current sensory state for a user.

        Args:
            user_id: The user's ID
            current_load: Optional current load dict {modality: load}

        Returns:
            SensoryState with per-modality loads and overall assessment
        """
        # Get or create sensory profile
        profile = self._get_or_create_profile(user_id)

        # Use provided load or stored load
        if current_load:
            modality_loads = current_load
        else:
            modality_loads = profile.modality_loads

        # Calculate overall load (max of all modalities, not average)
        # This is because any single modality can trigger overwhelm
        overall_load = max(modality_loads.values()) if modality_loads else 0.0

        # Determine thresholds
        is_overloaded = any(v > self.OVERLOAD_THRESHOLD for v in modality_loads.values())
        is_critical = any(v > self.CRITICAL_THRESHOLD for v in modality_loads.values())

        return SensoryState(
            user_id=user_id,
            modality_loads=modality_loads,
            overall_load=overall_load,
            last_assessed=profile.last_assessed if isinstance(profile.last_assessed, datetime) else datetime.now(UTC),
            segment_code=profile.segment_code if isinstance(profile.segment_code, str) else "AU",
            is_overloaded=is_overloaded,
            is_critical=is_critical,
        )

    async def update_modality(
        self,
        user_id: int,
        modality: str,
        load_delta: float,
        context: str,
    ) -> SensoryState:
        """
        Update a single modality's sensory load.

        CRITICAL: Loads are CUMULATIVE. Positive delta increases load,
        negative delta decreases load. No automatic recovery.

        Args:
            user_id: The user's ID
            modality: The modality to update (visual, auditory, etc.)
            load_delta: Change in load (-100 to +100)
            context: Description of what caused the change

        Returns:
            Updated SensoryState

        Raises:
            ValueError: If modality is not valid
        """
        if modality not in self.MODALITIES:
            raise ValueError(
                f"Invalid modality: {modality}. Must be one of: {self.MODALITIES}"
            )

        # Get or create profile
        profile = self._get_or_create_profile(user_id)

        # Get current loads
        modality_loads = profile.modality_loads.copy()
        current_load = modality_loads.get(modality, 0.0)

        # Apply delta (cumulative, no bounds initially)
        new_load = max(0.0, min(100.0, current_load + load_delta))
        modality_loads[modality] = new_load

        # Save profile
        profile.modality_loads = modality_loads
        profile.overall_load = max(modality_loads.values())
        profile.last_assessed = datetime.now(UTC)  # type: ignore[assignment]
        self.db.commit()

        # Return updated state
        return await self.assess(user_id)

    async def reset_modality(
        self,
        user_id: int,
        modality: str,
    ) -> SensoryState:
        """
        Reset a single modality's load to zero.

        Args:
            user_id: The user's ID
            modality: The modality to reset

        Returns:
            Updated SensoryState
        """
        return await self.update_modality(user_id, modality, -100.0, "manual_reset")

    async def get_recovery_recommendations(
        self,
        user_id: int,
    ) -> list[str]:
        """
        Get sensory recovery recommendations based on current state.

        Args:
            user_id: The user's ID

        Returns:
            List of recommendations
        """
        state = await self.assess(user_id)
        recommendations = []

        # High modalities
        high_modalities = [
            mod for mod, load in state.modality_loads.items()
            if load > self.OVERLOAD_THRESHOLD
        ]

        if "visual" in high_modalities:
            recommendations.append("Reduce visual stimulation: dim lights, close eyes, find quiet space")
        if "auditory" in high_modalities:
            recommendations.append("Reduce auditory input: earplugs, white noise, quiet room")
        if "tactile" in high_modalities:
            recommendations.append("Reduce tactile input: remove tight clothing, find soft textures")
        if "olfactory" in high_modalities:
            recommendations.append("Reduce olfactory input: go outside, find unscented environment")
        if "proprioceptive" in high_modalities:
            recommendations.append("Ground yourself: weighted blanket, compression, firm surface")

        if not recommendations:
            recommendations.append("Current sensory load is manageable. Maintain awareness.")

        return recommendations

    def _get_or_create_profile(self, user_id: int) -> SensoryProfile:
        """Get existing profile or create new one."""
        profile = (
            self.db.query(SensoryProfile)
            .filter(SensoryProfile.user_id == user_id)
            .first()
        )

        if not profile:
            profile = SensoryProfile(
                user_id=user_id,
                modality_loads={mod: 0.0 for mod in self.MODALITIES},
                overall_load=0.0,
                segment_code="AU",  # Default, can be updated
            )
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)

        return profile


__all__ = ["SensoryStateAssessment", "SensoryState", "ModalityInput"]
