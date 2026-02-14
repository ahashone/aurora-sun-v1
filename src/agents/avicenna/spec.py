"""
Avicenna Spec Manager for Aurora Sun V1.

Loads and parses the avicenna_spec.yaml architecture specification.
Provides structured access to valid transitions, expected writes, and SLA config.

Reference: src/agents/avicenna_spec.yaml
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(frozen=True)
class ExpectedWrite:
    """An expected database write for a state transition.

    Attributes:
        table: Target database table name.
        count: Expected number of writes (int or "1+" for one-or-more).
        description: Human-readable description of the write.
    """

    table: str
    count: str  # "1", "1+", etc. -- kept as str for flexibility
    description: str


@dataclass(frozen=True)
class ValidTransition:
    """A valid state machine transition for a module.

    Attributes:
        from_state: Source state (None for initial entry).
        to_state: Target state (None for exit).
        expected_writes: List of expected DB writes for this transition.
    """

    from_state: str | None
    to_state: str | None
    expected_writes: list[ExpectedWrite] = field(default_factory=list)


@dataclass(frozen=True)
class SLAConfig:
    """SLA thresholds loaded from the spec.

    Attributes:
        max_response_time_seconds: Maximum time for a single module response.
        max_state_duration_minutes: Maximum time in a single state before alerting.
        max_interaction_gap_minutes: Maximum time since last interaction.
        admin_notification_cooldown_seconds: Cooldown between admin notifications.
        max_concurrent_sessions_per_user: Maximum concurrent sessions per user.
    """

    max_response_time_seconds: int = 30
    max_state_duration_minutes: int = 30
    max_interaction_gap_minutes: int = 60
    admin_notification_cooldown_seconds: int = 60
    max_concurrent_sessions_per_user: int = 3


@dataclass
class ModuleSpec:
    """Specification for a single module's state machine.

    Attributes:
        name: Module name (e.g. "planning", "review").
        states: List of valid states for this module.
        transitions: List of valid transitions.
    """

    name: str
    states: list[str] = field(default_factory=list)
    transitions: list[ValidTransition] = field(default_factory=list)


# =============================================================================
# Spec Manager
# =============================================================================


class SpecManager:
    """Load and query the Avicenna architecture specification.

    Parses avicenna_spec.yaml and provides methods to look up valid
    transitions, expected writes, and SLA configuration.

    Usage:
        spec = SpecManager()
        spec.load_spec()  # loads from default path
        transitions = spec.get_valid_transitions("planning")
        sla = spec.get_sla()
    """

    def __init__(self) -> None:
        """Initialize empty SpecManager. Call load_spec() to populate."""
        self._modules: dict[str, ModuleSpec] = {}
        self._sla: SLAConfig = SLAConfig()
        self._severity_rules: dict[str, list[dict[str, str]]] = {}
        self._loaded: bool = False

    @property
    def is_loaded(self) -> bool:
        """Whether the spec has been loaded."""
        return self._loaded

    def load_spec(self, spec_path: str | Path | None = None) -> None:
        """Load and parse the avicenna_spec.yaml file.

        Args:
            spec_path: Path to the YAML spec file. If None, uses the default
                       path relative to the agents package.

        Raises:
            FileNotFoundError: If the spec file does not exist.
            ValueError: If the spec file is malformed.
        """
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            # Fallback: try to load with a minimal YAML parser
            logger.warning("PyYAML not available, attempting fallback load")
            self._load_fallback(spec_path)
            return

        if spec_path is None:
            # Default: src/agents/avicenna_spec.yaml
            spec_path = Path(__file__).parent.parent / "avicenna_spec.yaml"

        spec_path = Path(spec_path)
        if not spec_path.exists():
            raise FileNotFoundError(f"Avicenna spec not found: {spec_path}")

        with open(spec_path) as f:
            data: dict[str, Any] = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("Avicenna spec must be a YAML mapping at the root level")

        self._parse_modules(data.get("modules", {}))
        self._parse_sla(data.get("slas", {}))
        self._parse_severity_rules(data.get("severity_rules", {}))
        self._loaded = True

        logger.info(
            "avicenna_spec_loaded modules=%d",
            len(self._modules),
        )

    def load_from_dict(self, data: dict[str, Any]) -> None:
        """Load spec from a dictionary (useful for testing).

        Args:
            data: Spec data in the same structure as the YAML file.
        """
        self._parse_modules(data.get("modules", {}))
        self._parse_sla(data.get("slas", {}))
        self._parse_severity_rules(data.get("severity_rules", {}))
        self._loaded = True

    def _load_fallback(self, spec_path: str | Path | None) -> None:
        """Fallback loader when PyYAML is not available.

        Loads a minimal spec with defaults only. Not for production use.
        """
        self._modules = {}
        self._sla = SLAConfig()
        self._loaded = True
        logger.warning("avicenna_spec_loaded_fallback no_yaml_parser")

    def _parse_modules(self, modules_data: dict[str, Any]) -> None:
        """Parse modules section of the spec."""
        for module_name, module_data in modules_data.items():
            if not isinstance(module_data, dict):
                continue

            states = module_data.get("states", [])
            transitions_data = module_data.get("transitions", [])

            transitions: list[ValidTransition] = []
            for t in transitions_data:
                if not isinstance(t, dict):
                    continue

                expected_writes: list[ExpectedWrite] = []
                for w in t.get("expected_writes", []):
                    if isinstance(w, dict):
                        expected_writes.append(ExpectedWrite(
                            table=str(w.get("table", "")),
                            count=str(w.get("count", "1")),
                            description=str(w.get("description", "")),
                        ))

                transitions.append(ValidTransition(
                    from_state=t.get("from"),
                    to_state=t.get("to"),
                    expected_writes=expected_writes,
                ))

            self._modules[module_name] = ModuleSpec(
                name=module_name,
                states=states,
                transitions=transitions,
            )

    def _parse_sla(self, sla_data: dict[str, Any]) -> None:
        """Parse SLA section of the spec."""
        if not isinstance(sla_data, dict):
            self._sla = SLAConfig()
            return

        self._sla = SLAConfig(
            max_response_time_seconds=int(
                sla_data.get("max_response_time_seconds", 30)
            ),
            max_state_duration_minutes=int(
                sla_data.get("max_state_duration_minutes", 30)
            ),
            max_interaction_gap_minutes=int(
                sla_data.get("max_interaction_gap_minutes", 60)
            ),
            admin_notification_cooldown_seconds=int(
                sla_data.get("admin_notification_cooldown_seconds", 60)
            ),
            max_concurrent_sessions_per_user=int(
                sla_data.get("max_concurrent_sessions_per_user", 3)
            ),
        )

    def _parse_severity_rules(self, rules_data: dict[str, Any]) -> None:
        """Parse severity rules section of the spec."""
        if not isinstance(rules_data, dict):
            return

        for severity, rules in rules_data.items():
            if isinstance(rules, list):
                self._severity_rules[str(severity)] = [
                    {"type": str(r.get("type", "")), "description": str(r.get("description", ""))}
                    for r in rules
                    if isinstance(r, dict)
                ]

    # -------------------------------------------------------------------------
    # Public Query Methods
    # -------------------------------------------------------------------------

    def get_module_names(self) -> list[str]:
        """Get all module names in the spec.

        Returns:
            List of module names.
        """
        return list(self._modules.keys())

    def get_module_states(self, module_name: str) -> list[str]:
        """Get valid states for a module.

        Args:
            module_name: Name of the module.

        Returns:
            List of valid state names, or empty list if module not found.
        """
        module = self._modules.get(module_name)
        if module is None:
            return []
        return list(module.states)

    def get_valid_transitions(self, module_name: str) -> list[ValidTransition]:
        """Get all valid transitions for a module.

        Args:
            module_name: Name of the module.

        Returns:
            List of valid transitions, or empty list if module not found.
        """
        module = self._modules.get(module_name)
        if module is None:
            return []
        return list(module.transitions)

    def is_valid_transition(
        self,
        module_name: str,
        from_state: str | None,
        to_state: str | None,
    ) -> bool:
        """Check if a specific transition is valid for a module.

        Args:
            module_name: Name of the module.
            from_state: Source state (None for initial entry).
            to_state: Target state (None for exit).

        Returns:
            True if the transition is in the spec.
        """
        transitions = self.get_valid_transitions(module_name)
        return any(
            t.from_state == from_state and t.to_state == to_state
            for t in transitions
        )

    def get_expected_writes(
        self,
        module_name: str,
        from_state: str | None,
        to_state: str | None,
    ) -> list[ExpectedWrite]:
        """Get expected DB writes for a specific transition.

        Args:
            module_name: Name of the module.
            from_state: Source state (None for initial entry).
            to_state: Target state (None for exit).

        Returns:
            List of expected writes, or empty list if transition not found.
        """
        transitions = self.get_valid_transitions(module_name)
        for t in transitions:
            if t.from_state == from_state and t.to_state == to_state:
                return list(t.expected_writes)
        return []

    def get_sla(self) -> SLAConfig:
        """Get the SLA configuration.

        Returns:
            SLAConfig with all thresholds.
        """
        return self._sla

    def get_severity_rules(self, severity: str) -> list[dict[str, str]]:
        """Get issue types for a given severity level.

        Args:
            severity: Severity level ("critical", "warning", "info").

        Returns:
            List of rule dicts with 'type' and 'description' keys.
        """
        return list(self._severity_rules.get(severity, []))
