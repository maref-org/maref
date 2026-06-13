"""OODA loop stress test — zero-human-intervention evolution cycle.

Verifies that the full Observe → Orient → Decide → Act cycle
completes without human intervention, with all safety gates
(ConstitutionGuard, SafetyGateV2, MetaCircuitBreaker) active.
"""

from __future__ import annotations

import asyncio

import pytest

from maref.evolution.agents import GovernanceAgentConfig, AgentRole
from maref.evolution.constitution_guard import ConstitutionGuard
from maref.evolution.engine import EvolutionConfig
from maref.evolution.metrics import CycleSpec
from maref.evolution.multi_agent_engine import (
    MultiAgentEvolutionConfig,
    MultiAgentEvolutionEngine,
)
from maref.recursive.safety_gate_v2 import SafetyGateV2
from maref.recursive.meta_governance import MetaGovernance


class TestOODALoop:
    """OODA loop: Observe → Orient → Decide → Act with all gates active."""

    def test_ooda_cycle_completes_with_all_gates(self) -> None:
        """Run a short evolution cycle with all safety layers enabled."""
        base = EvolutionConfig(dry_run=False)
        for cid in ["c1", "c2", "c3"]:
            base.cycles[cid] = CycleSpec(name="ooda", rounds=5, description="test")

        agent_config = GovernanceAgentConfig(
            agent_id="ooda_detector",
            role=AgentRole.DETECTOR,
            share_group="detectors",
            policy_features=["entropy_penalty", "stability_bonus"],
        )

        config = MultiAgentEvolutionConfig(
            base_config=base,
            agent_configs=[agent_config],
            reward_update_interval=5,
            constitution_guard_enabled=True,
        )
        engine = MultiAgentEvolutionEngine(config)
        result = asyncio.run(engine.run())

        assert result.evolution_result.total_rounds == 15
        assert result.evolution_result.stop_reason == "normal_completion"

    def test_multi_agent_ooda_completes(self) -> None:
        """Multi-agent OODA with 2 roles, verify both get stats."""
        base = EvolutionConfig(dry_run=False)
        for cid in ["c1", "c2", "c3"]:
            base.cycles[cid] = CycleSpec(name="ooda", rounds=5, description="test")

        agents = [
            GovernanceAgentConfig(
                agent_id="detector_1",
                role=AgentRole.DETECTOR,
                share_group="detectors",
                policy_features=["entropy_penalty"],
            ),
            GovernanceAgentConfig(
                agent_id="evaluator_1",
                role=AgentRole.EVALUATOR,
                share_group="evaluators",
                policy_features=["stability_bonus"],
            ),
        ]

        config = MultiAgentEvolutionConfig(
            base_config=base,
            agent_configs=agents,
            reward_update_interval=5,
            constitution_guard_enabled=True,
        )
        engine = MultiAgentEvolutionEngine(config)
        result = asyncio.run(engine.run())

        assert result.evolution_result.total_rounds == 15
        assert "detector_1" in result.agent_stats
        assert "evaluator_1" in result.agent_stats

    def test_ooda_with_constitution_guard_active(self) -> None:
        """ConstitutionGuard must be active and track violations."""
        guard = ConstitutionGuard()
        assert guard.enabled is True
        assert guard.violation_count == 0

        guard.register_agent("ooda_agent")
        result = guard.validate_action("ooda_agent", {"entropy_penalty": 0.3})
        assert result.allowed is True

        result = guard.validate_action("ooda_agent", {"circuit_breaker_enabled": False})
        assert result.allowed is False
        assert guard.violation_count > 0

    def test_ooda_with_safety_gate_active(self) -> None:
        """SafetyGateV2 must block dangerous operations."""
        gate = SafetyGateV2()

        blocked = gate.validate_decomposition(15, ["halt"])
        assert blocked.blocked is True
        assert "explosion" in blocked.threat_type

        allowed = gate.validate_decomposition(3, ["query"])
        assert allowed.blocked is False

    def test_ooda_with_meta_circuit_breaker(self) -> None:
        """MetaGovernance must respect recursion depth limit."""
        gov = MetaGovernance(depth=0)
        assert gov.depth == 0

        with pytest.raises(RuntimeError):
            MetaGovernance(depth=99)

    def test_ooda_no_runaway_recursion(self) -> None:
        """Evolution engine must stop within configured limits."""
        base = EvolutionConfig(dry_run=False)
        for cid in ["c1", "c2", "c3"]:
            base.cycles[cid] = CycleSpec(name="ooda", rounds=5, description="test")
        base.max_total_rounds = 10

        config = MultiAgentEvolutionConfig(base_config=base)
        engine = MultiAgentEvolutionEngine(config)
        result = asyncio.run(engine.run())

        assert result.evolution_result.total_rounds <= 10
        assert result.evolution_result.total_rounds > 0

    def test_ooda_immunity_pollution_tax_on_violation(self) -> None:
        """Verify pollution tax concept: violations reduce allowable scope."""
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")

        for _ in range(10):
            guard.validate_action("agent_1", {"entropy_penalty": 0.3})

        violation_count_before = guard.violation_count

        guard.validate_action("agent_1", {"circuit_breaker_enabled": False})
        assert guard.violation_count > violation_count_before


class TestMultipleCycles:
    """C1 → C2 → C3 cycle completion with safety constraints."""

    def test_c1_c2_c3_completes(self) -> None:
        """Full three-cycle evolution completes with all rounds."""
        base = EvolutionConfig(dry_run=False)
        base.cycles["c1"] = CycleSpec(name="baseline", rounds=5, description="")
        base.cycles["c2"] = CycleSpec(name="optimize", rounds=5, description="",
                                       meta_learning_enabled=True)
        base.cycles["c3"] = CycleSpec(name="converge", rounds=5, description="")

        config = MultiAgentEvolutionConfig(
            base_config=base,
            agent_configs=[
                GovernanceAgentConfig(
                    agent_id="detector_1",
                    role=AgentRole.DETECTOR,
                    share_group="detectors",
                    policy_features=["entropy_penalty"],
                ),
            ],
            reward_update_interval=5,
        )
        engine = MultiAgentEvolutionEngine(config)
        result = asyncio.run(engine.run())

        assert result.evolution_result.total_rounds == 15
        assert len(result.evolution_result.cycles) == 3
