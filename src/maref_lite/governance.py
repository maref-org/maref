"""
MAREF-Lite Governance Overlay

Integrates the four core components:
1. State Machine (10-state Gray code)
2. Observation system (probes + dual-threshold detection)
3. Audit logging (append-only, immutable)
4. Oscillation fix closed loop

Phase 10 (M4): Event-driven architecture with audit trail,
oscillation resolution loop, and circuit breaker integration.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from drift_guard.types import DriftSeverity, ModelSignature

if TYPE_CHECKING:
    from drift_guard.pipeline import DriftDetectionPipeline
from sidecar.collector import ObservationCollector
from sidecar.monitor import AnomalyEvent, CompositeMonitor

from maref.governance import (
    AuditLogger,
    GovernanceState,
    GovernanceStateMachine,
    OscillationFixLoop,
)
from maref.observation.detector import DualThresholdConfig, DualThresholdDetector
from maref.observation.probes import (
    AnomalyProbe,
    EntropyProbe,
    KGProbe,
    LatencyProbe,
    OscillationProbe,
)
from maref.observation.registry import ProbeRegistry
from maref.observation.store import ObservationStore


@dataclass
class GovernanceDecision:
    """A decision made by the governance overlay."""

    action: str
    reason: str
    from_state: GovernanceState
    to_state: GovernanceState
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SelfObservation:
    """Self-observation record for recursive governance (backward compat)."""

    timestamp: float
    state: str
    entropy: int
    decision_count: int
    anomaly_count: int
    critical_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


class GovernanceOverlay:
    """
    MAREF-Lite governance overlay (M4 enhanced).

    M4 enhancements:
    - AuditLogger: every decision logged to append-only trail
    - OscillationFixLoop: detect→stabilize→cooldown→verify→adjust
    - Event-driven: asyncio.Queue replaces sleep polling
    - Circuit breaker integration point (used by recursive layer)
    """

    def __init__(
        self,
        state_machine: GovernanceStateMachine | None = None,
        collector: ObservationCollector | None = None,
        monitor: CompositeMonitor | None = None,
        drift_pipeline: DriftDetectionPipeline | None = None,
        enable_self_observation: bool = True,
        observation_db_path: str = "governance_observations.db",
        detector_config: DualThresholdConfig | None = None,
        audit_log_path: str = "governance_audit.jsonl",
        oscillation_cooldown: float = 30.0,
        max_decisions: int = 1000,
        max_self_observations: int = 500,
    ) -> None:
        self._state_machine = state_machine or GovernanceStateMachine()
        self._collector = collector
        self._monitor = monitor or CompositeMonitor()
        self._drift = drift_pipeline
        self._decisions: list[GovernanceDecision] = []
        self._max_decisions = max_decisions
        self._max_self_observations = max_self_observations
        self._running = False
        self._enable_self_observation = enable_self_observation

        # M2: Probe system
        self._probe_registry = ProbeRegistry()
        self._setup_probes()
        self._detector = DualThresholdDetector(config=detector_config)
        self._store = ObservationStore(db_path=observation_db_path)

        # M4: Audit logger
        self._audit = AuditLogger(log_path=audit_log_path)

        # M4: Oscillation fix loop
        self._oscillation_loop = OscillationFixLoop(
            stabilize_fn=self.force_stabilize,
            get_state_fn=self.get_status,
            cooldown_seconds=oscillation_cooldown,
            max_rate=10.0,
        )

        # M4: Event bus (replaces sleep polling)
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        # Legacy self-observation
        self._self_observations: list[SelfObservation] = []
        self._self_observation_callbacks: list[Callable[[SelfObservation], None]] = []

        if self._collector:
            self._collector.add_callback(self._on_observation)
        if self._enable_self_observation:
            self._state_machine.add_callback(self._on_state_transition)

    def _setup_probes(self) -> None:
        self._probe_registry.register(EntropyProbe(primary_threshold=4.0, shadow_threshold=2.0))
        self._probe_registry.register(AnomalyProbe(primary_threshold=10.0, shadow_threshold=3.0))
        self._probe_registry.register(LatencyProbe(primary_threshold=5.0, shadow_threshold=1.0))
        self._probe_registry.register(KGProbe(primary_threshold=0.95))
        self._probe_registry.register(OscillationProbe(
            primary_threshold=10.0, shadow_threshold=4.0, window_seconds=60.0,
        ))

    # --- Event Bus ---

    async def emit_event(self, event_type: str, **data: Any) -> None:
        await self._event_queue.put({"type": event_type, "data": data, "timestamp": time.time()})

    async def _process_events(self) -> None:
        while self._running:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.5)
                await self._handle_event(event)
            except asyncio.TimeoutError:
                self._read_probes()

    async def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = event["type"]
        data = event["data"]

        if event_type == "oscillation_detected":
            await self._oscillation_loop.detect_and_fix(
                rate=float(data.get("rate", 0)),
                entropy=self._state_machine.current_entropy,
                current_state=self._state_machine.current_state.name,
            )

    # --- Decision Logging ---

    def _record_decision(
        self,
        action: str,
        reason: str,
        from_state: GovernanceState,
        to_state: GovernanceState,
        **extra: Any,
    ) -> GovernanceDecision:
        decision = GovernanceDecision(
            action=action,
            reason=reason,
            from_state=from_state,
            to_state=to_state,
            metadata=extra,
        )
        self._decisions.append(decision)
        if len(self._decisions) > self._max_decisions:
            self._decisions = self._decisions[-self._max_decisions:]

        # Audit log
        self._audit.log_decision(
            actor="GovernanceOverlay",
            action=action,
            reason=reason,
            from_state=from_state.name,
            to_state=to_state.name,
            **extra,
        )
        return decision

    # --- Legacy self-observation ---

    def _on_state_transition(self, transition: Any) -> None:
        if not self._enable_self_observation:
            return

        obs = SelfObservation(
            timestamp=time.time(),
            state=self._state_machine.current_state.name,
            entropy=self._state_machine.current_entropy,
            decision_count=len(self._decisions),
            anomaly_count=self._monitor.get_anomaly_count(),
            critical_count=self._monitor.get_critical_count(),
            metadata={
                "from_state": transition.from_state.name,
                "to_state": transition.to_state.name,
                "reason": transition.reason,
            },
        )
        self._self_observations.append(obs)
        if len(self._self_observations) > self._max_self_observations:
            self._self_observations = self._self_observations[-self._max_self_observations:]
        for cb in self._self_observation_callbacks:
            with contextlib.suppress(Exception):
                cb(obs)

        osc_probe = self._probe_registry.get("oscillation")
        if isinstance(osc_probe, OscillationProbe):
            osc_probe.record_change()

        self._read_probes()

    def add_self_observation_callback(
        self, callback: Callable[[SelfObservation], None]
    ) -> None:
        self._self_observation_callbacks.append(callback)

    def get_self_observations(self, n: int = 100) -> list[SelfObservation]:
        return self._self_observations[-n:]

    # --- Probe system ---

    def _read_probes(self) -> None:
        status = self.get_status()
        context = {
            "entropy": self._state_machine.current_entropy,
            "anomaly_count": self._monitor.get_anomaly_count(),
            "critical_count": self._monitor.get_critical_count(),
            "total_nodes": 0,
            "orphaned_nodes": 0,
            "latency_ms": 0.0,
            "decision_count": len(self._decisions),
            "state": self._state_machine.current_state.name,
            "entropy_mean": status.get("entropy_trend", {}).get("mean", 0),
            "entropy_max": status.get("entropy_trend", {}).get("max", 0),
        }
        readings = self._probe_registry.read_all(**context)

        result = self._detector.evaluate(
            value=float(self._state_machine.current_entropy),
            ground_truth_is_anomaly=None,
        )

        if result["primary_triggered"]:
            self._state_machine.force_stabilize(reason="dual_threshold_primary")
            self._record_decision(
                action="force_stabilize",
                reason="dual_threshold_primary",
                from_state=self._state_machine.current_state,
                to_state=GovernanceState.STABILIZE,
            )

        if readings:
            self._store.insert_batch(readings)

    def get_probe_stats(self) -> dict[str, Any]:
        return {
            "probe_counts": self._probe_registry.get_counts_by_probe(),
            "severity_counts": self._probe_registry.get_counts_by_severity(),
            "total_readings": self._probe_registry.get_reading_count(),
            "detector_stats": self._detector.get_stats(),
            "db_counts": self._store.get_counts(),
            "oscillation_stats": self._oscillation_loop.get_stats(),
        }

    def log_fnr_fpr_batch(self, batch_id: str, snapshot: Any) -> None:
        stats = self._detector.get_stats()["fnr_fpr"]
        self._store.log_fnr_fpr(
            batch_id=batch_id,
            fnr=stats["fnr"],
            fpr=stats["fpr"],
            tp=stats["true_positives"],
            fp=stats["false_positives"],
            tn=stats["true_negatives"],
            fn_count=stats["false_negatives"],
        )

    # --- Anomaly handling ---

    def _on_observation(self, observation: Any) -> None:
        anomalies = self._monitor.process(observation)
        for anomaly in anomalies:
            self._audit.log_anomaly(
                actor="CompositeMonitor",
                anomaly_type=getattr(anomaly, "anomaly_type", "unknown"),
                severity=getattr(anomaly, "severity", "normal"),
                description=getattr(anomaly, "description", ""),
            )
            self._handle_anomaly(anomaly)

    def _handle_anomaly(self, anomaly: AnomalyEvent) -> None:
        if anomaly.severity == "critical" and self._state_machine.current_entropy >= 3:
            prev_state = self._state_machine.current_state
            self._state_machine.force_stabilize(
                reason=f"critical_anomaly:{anomaly.anomaly_type}"
            )
            self._record_decision(
                action="force_stabilize",
                reason=anomaly.description,
                from_state=prev_state,
                to_state=GovernanceState.STABILIZE,
                anomaly_type=anomaly.anomaly_type,
            )
        if self._collector:
            self._collector.notify_anomaly()

    async def check_drift(
        self,
        baseline_weights: Any,
        current_weights: Any,
        model: ModelSignature,
        baseline: ModelSignature,
    ) -> None:
        if not self._drift:
            return

        event = await self._drift.check_drift(
            baseline_weights, current_weights, model, baseline
        )
        if event and event.reading.severity in (
            DriftSeverity.HIGH,
            DriftSeverity.CRITICAL,
        ):
            if self._state_machine.can_transition(GovernanceState.VERIFY):
                self._state_machine.transition(
                    GovernanceState.VERIFY,
                    reason=f"drift_detected:{event.reading.severity.name}",
                )
            else:
                self._state_machine.force_stabilize(
                    reason=f"drift_detected:{event.reading.severity.name}"
                )

    # --- Status & Control ---

    def get_decisions(self, caller_id: str = "anonymous") -> list[GovernanceDecision]:
        self._audit.log_decision(
            event_type="access",
            actor=caller_id,
            action="get_decisions",
        )
        return list(self._decisions)

    def get_status(self) -> dict[str, Any]:
        return {
            "state": self._state_machine.current_state.name,
            "entropy": self._state_machine.current_entropy,
            "entropy_trend": self._state_machine.get_entropy_trend(),
            "anomaly_count": self._monitor.get_anomaly_count(),
            "critical_count": self._monitor.get_critical_count(),
            "decision_count": len(self._decisions),
            "is_terminal": self._state_machine.is_terminal(),
        }

    def get_audit_log(self, caller_id: str = "anonymous") -> list[dict[str, Any]]:
        self._audit.log_decision(
            event_type="access",
            actor=caller_id,
            action="get_audit_log",
        )
        return [e.to_dict() for e in self._audit.read_all()[-20:]]

    async def run(self) -> None:
        self._running = True
        if self._collector:
            asyncio.create_task(self._collector.run())
        try:
            await self._process_events()
        finally:
            self._running = False
            if self._collector:
                self._collector.stop()

    def stop(self) -> None:
        self._running = False

    def transition_state(self, target: GovernanceState, reason: str = "", caller_id: str = "anonymous") -> bool:
        self._audit.log_decision(
            event_type="state_transition",
            actor=caller_id,
            action="transition_state",
            details=f"{self._state_machine.current_state.name}→{target.name}:{reason}" if reason else f"{self._state_machine.current_state.name}→{target.name}",
        )
        return self._state_machine.transition(target, reason)

    def force_stabilize(self, reason: str = "", caller_id: str = "anonymous") -> bool:
        self._audit.log_decision(
            event_type="state_transition",
            actor=caller_id,
            action="force_stabilize",
            details=reason,
        )
        return self._state_machine.force_stabilize(reason)

    async def _governance_cycle(self) -> None:
        state = self._state_machine.current_state
        if state == GovernanceState.INIT:
            self._state_machine.transition(GovernanceState.OBSERVE, reason="auto_init")
            self._record_decision(
                action="auto_transition",
                reason="Initial governance cycle",
                from_state=state,
                to_state=GovernanceState.OBSERVE,
            )
