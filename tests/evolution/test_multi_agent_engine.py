from __future__ import annotations

from unittest import mock

import pytest

from maref.evolution.multi_agent_engine import (
    MultiAgentEvolutionConfig,
    MultiAgentEvolutionResult,
    MultiAgentRoundSnapshot,
)


class TestMultiAgentEvolutionConfig:
    def test_default_config(self) -> None:
        config = MultiAgentEvolutionConfig()
        assert config.fallback_to_single_strategy is True
        assert config.constitution_guard_enabled is True
        assert config.reward_update_interval == 5

    def test_to_dict(self) -> None:
        config = MultiAgentEvolutionConfig()
        d = config.to_dict()
        assert "base_config" in d
        assert "agent_configs" in d
        assert "constitution_guard_enabled" in d

    def test_with_default_agents(self) -> None:
        config = MultiAgentEvolutionConfig.with_default_agents()
        assert len(config.agent_configs) == 5


class TestMultiAgentRoundSnapshot:
    def test_to_dict(self) -> None:
        snap = MultiAgentRoundSnapshot(round_num=1, cycle_id="c1")
        d = snap.to_dict()
        assert d["round_num"] == 1
        assert d["cycle_id"] == "c1"
        assert d["constitution_violations"] == 0
        assert d["fnr"] == 0.0


class TestMultiAgentEvolutionResult:
    def test_summary(self) -> None:
        from maref.evolution.metrics import CycleResult, EvolutionMetrics

        em = EvolutionMetrics()
        cr = CycleResult(cycle_id="c1", name="test", rounds_completed=10, rounds_total=50, metrics=em, acceptance={}, passed=True)
        evo_result = mock.Mock()
        evo_result.stop_reason = "normal_completion"
        evo_result.total_rounds = 10
        evo_result.all_passed = True
        result = MultiAgentEvolutionResult(
            evolution_result=evo_result,
            agent_stats={"agent_1": {"total_reward": 0.5}},
            group_stats={},
            reward_history=[0.1, 0.2],
            constitution_violations_total=0,
        )
        s = result.summary()
        assert "PASSED" in s
        assert "Agents: 1" in s
        assert "Constitution violations: 0" in s
