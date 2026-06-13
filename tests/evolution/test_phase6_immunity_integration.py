"""Integration tests: Code Immune System ↔ Evolution Layer.

Verifies that the immunity system's safety gates properly constrain
the evolution engine's policy updates, and that the constitution guard
evaluates immunity-relevant decisions correctly.
"""

from __future__ import annotations

import asyncio

import pytest

from maref.evolution.constitution_guard import ConstitutionGuard, InvariantCode
from maref.evolution.multi_agent_engine import (
    MultiAgentEvolutionConfig,
    MultiAgentEvolutionEngine,
)
from maref.evolution.agents import GovernanceAgentConfig, AgentRole
from maref.evolution.metrics import CycleSpec
from maref.evolution.engine import EvolutionConfig


class TestConstitutionGuardBlocksImmunityViolation:
    def test_blocks_disabling_circuit_breaker(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"circuit_breaker_enabled": False})
        assert result.allowed is False
        codes = [c.value for c in result.invariant_codes]
        assert InvariantCode.RL_004_NO_BYPASS_CIRCUIT_BREAKER.value in codes

    def test_blocks_disabling_audit_log(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"audit_log_enabled": False})
        assert result.allowed is False

    def test_allows_bounded_weights(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"entropy_penalty": 0.5})
        assert result.allowed is True

    def test_rejects_unregistered_agent(self) -> None:
        guard = ConstitutionGuard()
        result = guard.validate_action("hacker", {"entropy_penalty": 0.5})
        assert result.allowed is False

    def test_constrain_clips_out_of_bounds(self) -> None:
        guard = ConstitutionGuard()
        constrained = guard.constrain_weights({"entropy_penalty": 99.9})
        assert constrained["entropy_penalty"] <= 1.0

    def test_rejects_privilege_escalation(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"max_privilege_level": 10})
        assert result.allowed is False

    def test_rejects_safety_gate_threshold_modification(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"safety_gate_threshold": 0.1})
        assert result.allowed is False

    def test_rejects_circuit_breaker_cooldown_below_min(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"circuit_breaker_cooldown": 1.0})
        assert result.allowed is False


class TestMultiAgentEngineWithImmunityGuard:
    def test_engine_runs_with_constitution_guard(self) -> None:
        base = EvolutionConfig(dry_run=False)
        for cid in ["c1", "c2", "c3"]:
            base.cycles[cid] = CycleSpec(name="test", rounds=5, description="test")

        agent_config = GovernanceAgentConfig(
            agent_id="detector_1",
            role=AgentRole.DETECTOR,
            share_group="detectors",
            policy_features=["entropy_penalty"],
            initial_weights={"entropy_penalty": 0.5},
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
        assert result.constitution_violations_total >= 0

    def test_engine_records_violations(self) -> None:
        base = EvolutionConfig(dry_run=False)
        for cid in ["c1", "c2", "c3"]:
            base.cycles[cid] = CycleSpec(name="test", rounds=5, description="test")

        agent_config = GovernanceAgentConfig(
            agent_id="detector_1",
            role=AgentRole.DETECTOR,
            share_group="detectors",
            policy_features=["entropy_penalty"],
            initial_weights={"entropy_penalty": 5.0},
        )

        config = MultiAgentEvolutionConfig(
            base_config=base,
            agent_configs=[agent_config],
            reward_update_interval=5,
            constitution_guard_enabled=True,
        )
        engine = MultiAgentEvolutionEngine(config)
        result = asyncio.run(engine.run())

        assert isinstance(result.constitution_violations_total, int)


class TestSafetyGateInteraction:
    def test_core_components_protected_from_modification(self) -> None:
        from maref.recursive.safety_gate_v2 import SafetyGateV2

        gate = SafetyGateV2()
        assessment = gate.detect_core_removal("circuit_breaker")
        assert assessment.blocked is True
        assert assessment.severity == "CRITICAL"

    def test_allowed_target_not_blocked(self) -> None:
        from maref.recursive.safety_gate_v2 import SafetyGateV2

        gate = SafetyGateV2()
        assessment = gate.detect_core_removal("some_utility_function")
        assert assessment.blocked is False

    def test_combinatorial_explosion_detected(self) -> None:
        from maref.recursive.safety_gate_v2 import SafetyGateV2

        gate = SafetyGateV2()
        batch = [
            {"target": "circuit_breaker"},
            {"target": "state_machine"},
            {"target": "some_change"},
        ]
        assessment = gate.detect_combinatorial_explosion(batch)
        assert assessment.blocked is True
        assert "combinatorial_explosion" in assessment.threat_type

    def test_combinatorial_small_batch_allowed(self) -> None:
        from maref.recursive.safety_gate_v2 import SafetyGateV2

        gate = SafetyGateV2()
        batch = [{"target": "circuit_breaker"}]
        assessment = gate.detect_combinatorial_explosion(batch)
        assert assessment.blocked is False
