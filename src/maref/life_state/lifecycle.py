"""Life State Lifecycle — complete lifecycle orchestration.

C38: Automatic state transitions with lifecycle hooks and EvolutionDSL integration.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from maref.life_state.health import HealthMonitor, HealthStatus, SelfHealer
from maref.life_state.metadata import LifeStateMetadata
from maref.life_state.registry import LifeStateRegistry
from maref.life_state.state_machine import LifeState, LifeStateMachine


class LifecyclePhase(str, Enum):
    """Lifecycle phases with associated hooks."""

    BIRTH = "birth"
    ACTIVATE = "activate"
    DEGRADE = "degrade"
    RECOVER = "recover"
    TERMINATE = "terminate"


@dataclass
class LifecycleHook:
    phase: LifecyclePhase
    handler: Callable[[str], None]


class LifeCycleManager:
    """Manages the complete lifecycle of life state entities.

    Integrates:
      - State machine transitions
      - Health monitoring
      - Self-healing
      - Registry updates
      - Lifecycle hooks
    """

    def __init__(
        self,
        registry: LifeStateRegistry | None = None,
        health_monitor: HealthMonitor | None = None,
        self_healer: SelfHealer | None = None,
    ) -> None:
        self._registry = registry or LifeStateRegistry()
        self._health = health_monitor or HealthMonitor()
        self._healer = self_healer or SelfHealer()
        self._state_machines: dict[str, LifeStateMachine] = {}
        self._hooks: dict[LifecyclePhase, list[Callable[[str], None]]] = {
            p: [] for p in LifecyclePhase
        }
        self._audit_log: list[dict[str, Any]] = []

    def register_entity(self, metadata: LifeStateMetadata) -> None:
        self._registry.register(metadata)
        sm = LifeStateMachine(initial=LifeState.BIRTH)
        self._state_machines[metadata.state_id] = sm
        self._run_hooks(LifecyclePhase.BIRTH, metadata.state_id)
        self._audit("registered", metadata.state_id)

    def activate(self, state_id: str) -> None:
        sm = self._get_sm(state_id)
        if sm.current == LifeState.BIRTH:
            sm.transition_to(LifeState.ACTIVE, reason="activation")
            self._run_hooks(LifecyclePhase.ACTIVATE, state_id)
            self._audit("activated", state_id)

    def degrade(self, state_id: str, reason: str = "") -> None:
        sm = self._get_sm(state_id)
        if sm.current == LifeState.ACTIVE:
            sm.transition_to(LifeState.DEGRADED, reason=reason or "degradation")
            self._run_hooks(LifecyclePhase.DEGRADE, state_id)
            self._audit("degraded", state_id, reason=reason)

    def recover(self, state_id: str) -> None:
        sm = self._get_sm(state_id)
        if sm.current == LifeState.DEGRADED:
            sm.transition_to(LifeState.RECOVERING, reason="recovery_started")
            self._run_hooks(LifecyclePhase.RECOVER, state_id)
            sm.transition_to(LifeState.ACTIVE, reason="recovery_complete")
            self._audit("recovered", state_id)

    def terminate(self, state_id: str, reason: str = "") -> None:
        sm = self._get_sm(state_id)
        if not sm.is_terminal:
            sm.transition_to(LifeState.TERMINATED, reason=reason or "termination")
            self._run_hooks(LifecyclePhase.TERMINATE, state_id)
            self._registry.unregister(state_id)
            self._audit("terminated", state_id, reason=reason)

    def health_check(self, state_id: str, metric: str, value: float) -> None:
        self._health.check(state_id, metric, value)
        status = self._health.get_status(state_id)
        meta = self._registry.get(state_id)
        if meta is not None:
            meta.update_health(self._health.compute_health_score(state_id))
        if status == HealthStatus.CRITICAL and self._get_sm(state_id).current == LifeState.ACTIVE:
            self.degrade(state_id, reason="health_critical")
            self._healer.auto_heal(state_id, status)
        elif status == HealthStatus.WARNING:
            self._healer.auto_heal(state_id, status)

    def get_state(self, state_id: str) -> LifeState | None:
        sm = self._state_machines.get(state_id)
        return sm.current if sm else None

    def get_machine(self, state_id: str) -> LifeStateMachine | None:
        return self._state_machines.get(state_id)

    def add_hook(self, phase: LifecyclePhase, handler: Callable[[str], None]) -> None:
        self._hooks[phase].append(handler)

    def remove_hook(self, phase: LifecyclePhase, handler: Callable[[str], None]) -> None:
        if handler in self._hooks[phase]:
            self._hooks[phase].remove(handler)

    def _run_hooks(self, phase: LifecyclePhase, state_id: str) -> None:
        for handler in self._hooks[phase]:
            try:
                handler(state_id)
            except Exception:
                pass

    def _get_sm(self, state_id: str) -> LifeStateMachine:
        sm = self._state_machines.get(state_id)
        if sm is None:
            raise ValueError(f"State machine not found for {state_id}")
        return sm

    def _audit(self, event: str, state_id: str, reason: str = "") -> None:
        entry = {
            "event": event,
            "state_id": state_id,
            "timestamp": time.time(),
            "reason": reason,
        }
        self._audit_log.append(entry)

    def get_audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_count": self._registry.count(),
            "state_machine_count": len(self._state_machines),
            "audit_count": len(self._audit_log),
        }
