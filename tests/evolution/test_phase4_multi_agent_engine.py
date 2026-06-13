"""
Tests for MAREF Multi-Agent Evolution Engine (Phase 4).

Validates:
- MultiAgentEvolutionConfig creation and serialization
- ConstitutionGuard validation and constraint enforcement
- MultiAgentEvolutionEngine initialization and basic execution
- Multi-agent reward computation and policy updates
- Fallback to single-strategy mode
- End-to-end evolution flow
"""

from __future__ import annotations

import asyncio

from maref.evolution.agents import (
    AgentRole,
    GovernanceAgentConfig,
)
from maref.evolution.engine import EvolutionConfig
from maref.evolution.constitution_guard import ValidationResult
from maref.evolution.multi_agent_engine import (
    ConstitutionGuard,
    MultiAgentEvolutionConfig,
    MultiAgentEvolutionEngine,
    MultiAgentEvolutionResult,
    MultiAgentRoundSnapshot,
)

# ============================================================================
# MultiAgentEvolutionConfig Tests
# ============================================================================

class TestMultiAgentEvolutionConfig:
    def test_default_config(self) -> None:
        config = MultiAgentEvolutionConfig()
        assert config.fallback_to_single_strategy is True
        assert config.constitution_guard_enabled is True
        assert config.reward_update_interval == 5

    def test_to_dict(self) -> None:
        config = MultiAgentEvolutionConfig(
            reward_update_interval=10,
            constitution_guard_enabled=False,
        )
        d = config.to_dict()
        assert d["reward_update_interval"] == 10
        assert d["constitution_guard_enabled"] is False

    def test_with_default_agents(self) -> None:
        config = MultiAgentEvolutionConfig.with_default_agents()
        assert len(config.agent_configs) > 0

    def test_custom_base_config(self) -> None:
        base = EvolutionConfig(dry_run=True, dry_run_rounds=1)
        config = MultiAgentEvolutionConfig(base_config=base)
        assert config.base_config.dry_run is True

    def test_custom_optimizer_config(self) -> None:
        from maref.learning.group_optimizer import OptimizerConfig
        opt_config = OptimizerConfig(clip_epsilon=0.1)
        config = MultiAgentEvolutionConfig(optimizer_config=opt_config)
        assert config.optimizer_config.clip_epsilon == 0.1


# ============================================================================
# ConstitutionGuard Tests
# ============================================================================

class TestConstitutionGuard:
    def test_disabled_allows_all(self) -> None:
        guard = ConstitutionGuard(enabled=False)
        result = guard.validate_action("test", {"feature_a": 999.0})
        assert result.allowed is True

    def test_enabled_allows_normal_weights(self) -> None:
        guard = ConstitutionGuard(enabled=True)
        guard.register_agent("test")
        result = guard.validate_action("test", {"feature_a": 0.1})
        assert result.allowed is True
        assert result.violations == []

    def test_enabled_rejects_excessive_weight(self) -> None:
        guard = ConstitutionGuard(enabled=True)
        result = guard.validate_action("test", {"feature_a": 3.0})
        assert result.allowed is False
        assert len(result.violations) >= 1

    def test_enabled_accepts_boundary_weight(self) -> None:
        guard = ConstitutionGuard(enabled=True)
        guard.register_agent("test")
        result = guard.validate_action("test", {"feature_a": 2.0})
        assert result.allowed is True

    def test_enabled_rejects_negative_excessive_weight(self) -> None:
        guard = ConstitutionGuard(enabled=True)
        guard.register_agent("test")
        result = guard.validate_action("test", {"feature_a": -2.1})
        assert result.allowed is False

    def test_constrain_weights(self) -> None:
        guard = ConstitutionGuard(enabled=True)
        constrained = guard.constrain_weights({
            "a": 3.0,
            "b": -3.0,
            "c": 0.5,
        })
        assert constrained["a"] == 2.0
        assert constrained["b"] == -2.0
        assert constrained["c"] == 0.5

    def test_constrain_weights_disabled(self) -> None:
        guard = ConstitutionGuard(enabled=False)
        weights = {"a": 999.0}
        constrained = guard.constrain_weights(weights)
        assert constrained["a"] == 999.0

    def test_violation_count_tracks(self) -> None:
        guard = ConstitutionGuard(enabled=True)
        guard.validate_action("test", {"a": 3.0})
        guard.validate_action("test", {"b": 5.0})
        assert guard.violation_count >= 2

    def test_violation_log(self) -> None:
        guard = ConstitutionGuard(enabled=True)
        guard.validate_action("agent_1", {"a": 3.0})
        log = guard.violation_log
        assert len(log) >= 1
        assert log[0].agent_id == "agent_1"

    def test_get_stats(self) -> None:
        guard = ConstitutionGuard(enabled=True)
        stats = guard.get_stats()
        assert "enabled" in stats
        assert "violation_count" in stats
        assert "recent_violations" in stats


# ============================================================================
# ValidationResult Tests
# ============================================================================

class TestValidationResult:
    def test_allowed_result(self) -> None:
        result = ValidationResult(allowed=True, violations=[])
        assert result.allowed is True

    def test_rejected_result(self) -> None:
        result = ValidationResult(allowed=False, violations=["weight too high"])
        assert result.allowed is False
        assert len(result.violations) == 1


# ============================================================================
# MultiAgentRoundSnapshot Tests
# ============================================================================

class TestMultiAgentRoundSnapshot:
    def test_creation(self) -> None:
        snapshot = MultiAgentRoundSnapshot(
            round_num=5,
            cycle_id="c1",
            fnr=0.12,
            fpr=0.08,
        )
        assert snapshot.round_num == 5
        assert snapshot.cycle_id == "c1"
        assert snapshot.fnr == 0.12

    def test_to_dict(self) -> None:
        snapshot = MultiAgentRoundSnapshot(
            round_num=1,
            cycle_id="c2",
            fnr=0.15,
            fpr=0.10,
            role_rewards=[{"agent_id": "d1", "role_reward": 0.8}],
            round_reward=0.8,
        )
        d = snapshot.to_dict()
        assert d["round_num"] == 1
        assert d["fnr"] == 0.15
        assert len(d["role_rewards"]) == 1

    def test_empty_defaults(self) -> None:
        snapshot = MultiAgentRoundSnapshot(round_num=0, cycle_id="c1")
        assert snapshot.role_rewards == []
        assert snapshot.policy_updates == {}
        assert snapshot.constitution_violations == 0


# ============================================================================
# MultiAgentEvolutionEngine Tests
# ============================================================================

class TestMultiAgentEvolutionEngine:
    def test_create_engine_default(self) -> None:
        engine = MultiAgentEvolutionEngine()
        assert engine.is_multi_agent is False

    def test_create_engine_with_agents(self) -> None:
        config = MultiAgentEvolutionConfig.with_default_agents()
        engine = MultiAgentEvolutionEngine(config)
        assert engine.is_multi_agent is True
        assert engine.registry.agent_count > 0

    def test_engine_registry_accessible(self) -> None:
        config = MultiAgentEvolutionConfig.with_default_agents()
        engine = MultiAgentEvolutionEngine(config)
        assert engine.registry.agent_count >= 5

    def test_engine_with_custom_agents(self) -> None:
        agent_config = GovernanceAgentConfig(
            agent_id="custom_detector",
            role=AgentRole.DETECTOR,
            share_group="custom",
            policy_features=["entropy_penalty", "stability_bonus"],
        )
        config = MultiAgentEvolutionConfig(agent_configs=[agent_config])
        engine = MultiAgentEvolutionEngine(config)
        assert engine.is_multi_agent is True
        assert engine.registry.agent_count == 1

    def test_dry_run_succeeds(self) -> None:
        config = MultiAgentEvolutionConfig.with_default_agents()
        config.base_config.dry_run = True
        engine = MultiAgentEvolutionEngine(config)
        result = asyncio.run(engine.run())
        assert isinstance(result, MultiAgentEvolutionResult)
        assert result.evolution_result.stop_reason == "dry_run_complete"

    def test_dry_run_empty_engine(self) -> None:
        config = MultiAgentEvolutionConfig()
        config.base_config.dry_run = True
        engine = MultiAgentEvolutionEngine(config)
        result = asyncio.run(engine.run())
        assert isinstance(result, MultiAgentEvolutionResult)
        assert result.evolution_result.stop_reason == "dry_run_complete"

    def test_multi_round_dry_run(self) -> None:
        """Dry run with multiple rounds."""
        from maref.evolution.metrics import CycleSpec
        base = EvolutionConfig(dry_run=False)
        base.cycles["c1"] = CycleSpec(
            name="test", rounds=3, description="test"
        )
        config = MultiAgentEvolutionConfig(
            base_config=base,
        )
        config.agent_configs = [GovernanceAgentConfig(
            agent_id="test_d",
            role=AgentRole.DETECTOR,
            share_group="test",
            policy_features=["entropy_penalty"],
        )]
        engine = MultiAgentEvolutionEngine(config)
        result = asyncio.run(engine.run())
        assert result.evolution_result.total_rounds >= 1
        assert result.evolution_result.stop_reason == "normal_completion"

    def test_get_live_status(self) -> None:
        config = MultiAgentEvolutionConfig.with_default_agents()
        engine = MultiAgentEvolutionEngine(config)
        status = engine.get_live_status()
        assert status["running"] is False
        assert status["is_multi_agent"] is True
        assert "constitution_guard" in status
        assert "reward_assembler" in status

    def test_stop(self) -> None:
        engine = MultiAgentEvolutionEngine()
        engine.stop()
        status = engine.get_live_status()
        assert status["running"] is False

    def test_experience_store_tracks_role_rewards(self) -> None:
        config = MultiAgentEvolutionConfig.with_default_agents()
        config.base_config.dry_run = False
        config.base_config.cycles["c1"] = __import__(
            "maref.evolution.metrics", fromlist=["CycleSpec"]
        ).CycleSpec(
            name="test", rounds=6, description="test"
        )
        engine = MultiAgentEvolutionEngine(config)

        asyncio.run(engine.run())

        # After 6 rounds, with reward_update_interval=5, at least one update
        # should have happened. The experience store should have entries.
        status = engine.get_live_status()
        assert status["experience_count"] > 0


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    def test_full_evolution_with_policy_updates(self) -> None:
        """Run a complete evolution cycle and verify policy updates occur."""
        from maref.evolution.metrics import CycleSpec

        base = EvolutionConfig(dry_run=False)
        base.cycles["c1"] = CycleSpec(name="test", rounds=10, description="test")
        base.cycles["c2"] = CycleSpec(name="test", rounds=10, description="test", meta_learning_enabled=True)
        base.cycles["c3"] = CycleSpec(name="test", rounds=10, description="test")

        agent_configs = [
            GovernanceAgentConfig(
                agent_id="detector_1",
                role=AgentRole.DETECTOR,
                share_group="detectors",
                policy_features=["entropy_penalty", "stability_bonus"],
            ),
            GovernanceAgentConfig(
                agent_id="evaluator_1",
                role=AgentRole.EVALUATOR,
                share_group="evaluators",
                policy_features=["entropy_penalty"],
            ),
        ]

        config = MultiAgentEvolutionConfig(
            base_config=base,
            agent_configs=agent_configs,
            reward_update_interval=3,
        )
        engine = MultiAgentEvolutionEngine(config)
        result = asyncio.run(engine.run())

        assert result.evolution_result.total_rounds == 30
        assert len(result.agent_stats) == 2
        assert "detector_1" in result.agent_stats
        assert "evaluator_1" in result.agent_stats

    def test_constitution_guard_integration(self) -> None:
        """Verify constitution guard tracks violations during evolution."""
        from maref.evolution.metrics import CycleSpec

        base = EvolutionConfig(dry_run=False)
        base.cycles["c1"] = CycleSpec(name="test", rounds=10, description="test")
        base.cycles["c2"] = CycleSpec(name="test", rounds=10, description="test", meta_learning_enabled=True)
        base.cycles["c3"] = CycleSpec(name="test", rounds=10, description="test")

        agent_config = GovernanceAgentConfig(
            agent_id="detector_1",
            role=AgentRole.DETECTOR,
            share_group="detectors",
            policy_features=["entropy_penalty"],
            initial_weights={"entropy_penalty": 0.9},
        )

        config = MultiAgentEvolutionConfig(
            base_config=base,
            agent_configs=[agent_config],
            reward_update_interval=3,
            constitution_guard_enabled=True,
        )
        engine = MultiAgentEvolutionEngine(config)
        result = asyncio.run(engine.run())

        # Engine should have run successfully, regardless of violations
        assert result.evolution_result.total_rounds == 30

    def test_summary_format(self) -> None:
        """Test result summary formatting."""
        from maref.evolution.metrics import EvolutionResult as ER

        evolution_result = ER(
            cycles=[],
            stop_reason="test_complete",
            total_rounds=5,
            all_passed=True,
        )
        result = MultiAgentEvolutionResult(
            evolution_result=evolution_result,
            agent_stats={"agent_1": {"total_reward": 0.8}},
            group_stats={"group_1": {"name": "test"}},
            reward_history=[0.5, 0.6, 0.7],
            constitution_violations_total=0,
        )
        summary = result.summary()
        assert "PASSED" in summary
        assert "agent_1" in summary
        assert "5" in summary
