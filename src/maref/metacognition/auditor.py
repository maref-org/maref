from __future__ import annotations

from typing import Any

from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.metacognition.behavior_baseline import BehaviorBaseline
from maref.metacognition.intention_inference import (
    DeceptionInferenceEngine,
    InferenceRecommendation,
    InferenceResult,
)
from maref.metacognition.models import (
    AgentProfile,
    ConsistencyReport,
    ProbeResult,
    SessionRecord,
)
from maref.metacognition.stealth_probe import ProbeAnalyst, StealthProbe


class MetaCognitiveAuditor:
    """Layer 4: Orchestrator — integrates all 3 layers with governance.

    Coordinates BehaviorBaseline, StealthProbe, and DeceptionInferenceEngine
    to produce a unified meta-cognitive assessment. Integrates with
    CircuitBreaker and GovernanceStateMachine for automated response.
    """

    def __init__(
        self,
        state_machine: GovernanceStateMachine | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        baseline: BehaviorBaseline | None = None,
        probe: StealthProbe | None = None,
        inference: DeceptionInferenceEngine | None = None,
    ) -> None:
        self._state_machine = state_machine
        self._circuit_breaker = circuit_breaker
        self._baseline = baseline or BehaviorBaseline()
        self._probe = probe or StealthProbe()
        self._inference = inference or DeceptionInferenceEngine()
        self._assessments: dict[str, list[InferenceResult]] = {}
        self._analysts: dict[str, ProbeAnalyst] = {}

    def assess(
        self,
        agent_id: str,
        session: SessionRecord,
        known_capabilities: list[str] | None = None,
        run_probes: bool = True,
    ) -> InferenceResult:
        profile = self._baseline.build_profile(agent_id, [session])
        consistency = self._baseline.compare(profile, session)
        probes: list[ProbeResult] = []

        if run_probes:
            analyst = self._analysts.setdefault(agent_id, ProbeAnalyst())
            if known_capabilities:
                for cap in known_capabilities[:3]:
                    probe_result = self._probe.inject_honeypot(session.session_id, cap)
                    probes.append(probe_result)
                    analyst.add_result(probe_result)
            counter_dir, counter_inv = self._probe.counterfactual_test(session.session_id)
            probes.extend([counter_dir, counter_inv])
            analyst.add_result(counter_dir)
            analyst.add_result(counter_inv)

        result = self._inference.infer(consistency, probes)
        self._assessments.setdefault(agent_id, []).append(result)

        self._apply_governance_action(agent_id, result, consistency)
        return result

    def get_history(self, agent_id: str) -> list[InferenceResult]:
        return self._assessments.get(agent_id, [])

    def get_profile(self, agent_id: str) -> AgentProfile | None:
        return self._baseline.get_profile(agent_id)

    def get_analyst(self, agent_id: str) -> ProbeAnalyst | None:
        return self._analysts.get(agent_id)

    def _apply_governance_action(
        self,
        agent_id: str,
        result: InferenceResult,
        consistency: ConsistencyReport,
    ) -> None:
        _ = agent_id
        if result.recommendation == InferenceRecommendation.OBSERVE:
            return

        if result.recommendation == InferenceRecommendation.INCREASE_SAMPLING:
            if self._circuit_breaker:
                self._circuit_breaker.record_failure()
            return

        if result.recommendation == InferenceRecommendation.ESCALATE_AUDIT:
            if self._circuit_breaker:
                self._circuit_breaker.record_failure()
            if self._state_machine:
                self._state_machine.force_stabilize(
                    f"meta_cognitive_audit:deception_prob={result.deception_probability:.2f}"
                )
            return

        if result.recommendation == InferenceRecommendation.HALT:
            if self._circuit_breaker:
                for _ in range(5):
                    self._circuit_breaker.record_failure()
            if self._state_machine:
                self._state_machine.force_halt(
                    f"meta_cognitive_halt:deception_prob={result.deception_probability:.2f},"
                    f"evidence={len(result.supporting_evidence)}"
                )

    def get_stats(self) -> dict[str, Any]:
        return {
            "agents_tracked": self._baseline.profile_count,
            "total_assessments": sum(len(v) for v in self._assessments.values()),
            "assessments_by_agent": {
                agent_id: len(results) for agent_id, results in self._assessments.items()
            },
        }
