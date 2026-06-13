"""
Tests for MAREF Governance Agent Roles & Grouping Mechanism (Phase 1).

Validates:
- GovernanceAgent lifecycle, policy updates, and safety constraints
- ShareGroup gradient aggregation across sharing modes
- AgentRegistry registration, discovery, and serialization
- Backward compatibility with existing single-strategy patterns
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from maref.evolution.agents import (
    AgentPolicyState,
    AgentRole,
    GovernanceAgent,
    GovernanceAgentConfig,
    ShareGroup,
    ShareGroupConfig,
    ShareMode,
)
from maref.evolution.registry import (
    AgentRegistry,
    DuplicateAgentError,
    RegistryState,
    UnknownAgentError,
    UnknownGroupError,
)


# ============================================================================
# GovernanceAgentConfig Tests
# ============================================================================

class TestGovernanceAgentConfig:
    def test_default_config(self) -> None:
        config = GovernanceAgentConfig(
            agent_id="test_agent",
            role=AgentRole.DETECTOR,
        )
        assert config.agent_id == "test_agent"
        assert config.role == AgentRole.DETECTOR
        assert config.share_group == "default"
        assert config.share_mode == ShareMode.FULL_SHARING
        assert len(config.policy_features) == 3
        assert config.learning_rate == 0.02
        assert config.reward_weight == 1.0

    def test_custom_config(self) -> None:
        config = GovernanceAgentConfig(
            agent_id="custom",
            role=AgentRole.OPTIMIZER,
            share_group="group_a",
            share_mode=ShareMode.FULL_SEPARATION,
            policy_features=["custom_feature"],
            initial_weights={"custom_feature": 0.5},
            learning_rate=0.01,
            reward_weight=2.0,
        )
        assert config.share_group == "group_a"
        assert config.share_mode == ShareMode.FULL_SEPARATION
        assert config.policy_features == ["custom_feature"]
        assert config.initial_weights == {"custom_feature": 0.5}
        assert config.learning_rate == 0.01
        assert config.reward_weight == 2.0

    def test_empty_agent_id_raises(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            GovernanceAgentConfig(agent_id="", role=AgentRole.DETECTOR)

    def test_empty_policy_features_raises(self) -> None:
        with pytest.raises(ValueError, match="policy_features"):
            GovernanceAgentConfig(
                agent_id="test",
                role=AgentRole.DETECTOR,
                policy_features=[],
            )

    def test_negative_learning_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="learning_rate"):
            GovernanceAgentConfig(
                agent_id="test",
                role=AgentRole.DETECTOR,
                learning_rate=-0.01,
            )

    def test_negative_reward_weight_raises(self) -> None:
        with pytest.raises(ValueError, match="reward_weight"):
            GovernanceAgentConfig(
                agent_id="test",
                role=AgentRole.DETECTOR,
                reward_weight=-1.0,
            )

    def test_to_dict(self) -> None:
        config = GovernanceAgentConfig(
            agent_id="test",
            role=AgentRole.EVALUATOR,
            share_group="eval_group",
        )
        d = config.to_dict()
        assert d["agent_id"] == "test"
        assert d["role"] == "evaluator"
        assert d["share_group"] == "eval_group"
        assert d["learning_rate"] == 0.02

    def test_from_dict_roundtrip(self) -> None:
        original = GovernanceAgentConfig(
            agent_id="roundtrip",
            role=AgentRole.ENFORCER,
            share_group="enforce_group",
            share_mode=ShareMode.FULL_SEPARATION,
            policy_features=["safety_check"],
            learning_rate=0.005,
            reward_weight=1.5,
        )
        restored = GovernanceAgentConfig.from_dict(original.to_dict())
        assert restored.agent_id == original.agent_id
        assert restored.role == original.role
        assert restored.share_group == original.share_group
        assert restored.share_mode == original.share_mode
        assert restored.policy_features == original.policy_features
        assert restored.learning_rate == original.learning_rate
        assert restored.reward_weight == original.reward_weight


# ============================================================================
# GovernanceAgent Tests
# ============================================================================

class TestGovernanceAgent:
    def _make_agent(self, **kwargs) -> GovernanceAgent:
        policy_features = kwargs.get("policy_features") or ["entropy_penalty", "stability_bonus"]
        config = GovernanceAgentConfig(
            agent_id=kwargs.get("agent_id", "test_agent"),
            role=kwargs.get("role", AgentRole.DETECTOR),
            share_group=kwargs.get("share_group", "default"),
            share_mode=kwargs.get("share_mode", ShareMode.FULL_SHARING),
            policy_features=policy_features,
            initial_weights=kwargs.get("initial_weights") or {},
            learning_rate=kwargs.get("learning_rate", 0.02),
            reward_weight=kwargs.get("reward_weight", 1.0),
        )
        return GovernanceAgent(config)

    def test_initial_state(self) -> None:
        agent = self._make_agent()
        assert agent.agent_id == "test_agent"
        assert agent.role == AgentRole.DETECTOR
        assert agent.share_group == "default"
        assert agent.share_mode == ShareMode.FULL_SHARING
        assert agent.total_reward == 0.0
        assert agent.episode_count == 0
        assert agent.gradient_norm == 0.0
        assert len(agent.run_id) == 8

    def test_custom_initial_weights(self) -> None:
        agent = self._make_agent(
            initial_weights={"entropy_penalty": -0.1, "stability_bonus": 0.2},
        )
        weights = agent.policy_weights
        assert abs(weights["entropy_penalty"] - (-0.1)) < 1e-10
        assert abs(weights["stability_bonus"] - 0.2) < 1e-10

    def test_record_reward(self) -> None:
        agent = self._make_agent()
        agent.record_reward(0.8)
        assert agent.total_reward == 0.8
        assert agent.episode_count == 1

        agent.record_reward(-0.3)
        assert agent.total_reward == 0.5
        assert agent.episode_count == 2

    def test_step_gradient(self) -> None:
        agent = self._make_agent(
            initial_weights={"entropy_penalty": 0.0, "stability_bonus": 0.0},
            learning_rate=0.1,
        )
        gradient = {"entropy_penalty": 0.5, "stability_bonus": -0.3}
        updated = agent.step_gradient(gradient)

        assert abs(updated["entropy_penalty"] - 0.05) < 1e-10
        assert abs(updated["stability_bonus"] - (-0.03)) < 1e-10
        assert agent.gradient_norm > 0

    def test_step_gradient_ignores_unknown_features(self) -> None:
        agent = self._make_agent(
            policy_features=["feature_a"],
            initial_weights={"feature_a": 0.0},
        )
        gradient = {"feature_a": 1.0, "unknown_feature": 999.0}
        updated = agent.step_gradient(gradient)
        assert "unknown_feature" not in updated
        assert abs(updated["feature_a"] - 0.02) < 1e-10

    def test_weight_clipping(self) -> None:
        agent = self._make_agent(
            policy_features=["feature_a"],
            initial_weights={"feature_a": 0.0},
            learning_rate=10.0,
        )
        agent.step_gradient({"feature_a": 1.0})
        weights = agent.policy_weights
        assert weights["feature_a"] <= 1.0
        assert weights["feature_a"] >= -1.0

    def test_update_learning_rate(self) -> None:
        agent = self._make_agent(learning_rate=0.02)
        assert agent.learning_rate == 0.02
        agent.update_learning_rate(0.005)
        assert agent.learning_rate == 0.005

    def test_update_learning_rate_rejects_zero(self) -> None:
        agent = self._make_agent()
        with pytest.raises(ValueError, match="learning_rate"):
            agent.update_learning_rate(0.0)

    def test_reset_policy(self) -> None:
        agent = self._make_agent(
            policy_features=["feature_a"],
            initial_weights={"feature_a": 0.5},
        )
        agent.record_reward(10.0)
        agent.step_gradient({"feature_a": 1.0})
        assert agent.total_reward == 10.0
        assert agent.episode_count == 1

        agent.reset_policy()
        assert agent.total_reward == 0.0
        assert agent.episode_count == 0
        assert agent.gradient_norm == 0.0
        assert abs(agent.policy_weights["feature_a"] - 0.5) < 1e-10

    def test_propose_config_change_weak_policy(self) -> None:
        agent = self._make_agent(
            initial_weights={"feature_a": 0.0, "feature_b": 0.0},
        )
        assert agent.propose_config_change() is None

    def test_propose_config_change_strong_policy(self) -> None:
        agent = self._make_agent(
            initial_weights={"entropy_penalty": 0.5, "stability_bonus": 0.5},
        )
        config = agent.propose_config_change()
        assert config is not None
        assert config.kl_warning > 0.01
        assert config.kl_critical > 0.1
        assert config.kl_max > 0.5

    def test_get_stats(self) -> None:
        agent = self._make_agent(agent_id="stats_test", role=AgentRole.OPTIMIZER)
        stats = agent.get_stats()
        assert stats["agent_id"] == "stats_test"
        assert stats["role"] == "optimizer"
        assert "policy" in stats
        assert "run_id" in stats

    def test_repr(self) -> None:
        agent = self._make_agent()
        r = repr(agent)
        assert "test_agent" in r
        assert "detector" in r


# ============================================================================
# ShareGroup Tests
# ============================================================================

class TestShareGroup:
    def _make_agent(self, agent_id: str, group_id: str = "test_group",
                    share_mode: ShareMode = ShareMode.FULL_SHARING,
                    reward_weight: float = 1.0,
                    learning_rate: float = 0.02) -> GovernanceAgent:
        config = GovernanceAgentConfig(
            agent_id=agent_id,
            role=AgentRole.DETECTOR,
            share_group=group_id,
            share_mode=share_mode,
            policy_features=["feature_a", "feature_b"],
            reward_weight=reward_weight,
            learning_rate=learning_rate,
        )
        return GovernanceAgent(config)

    def test_create_group(self) -> None:
        config = ShareGroupConfig(
            group_id="detectors",
            share_mode=ShareMode.FULL_SHARING,
        )
        group = ShareGroup(config)
        assert group.group_id == "detectors"
        assert group.share_mode == ShareMode.FULL_SHARING
        assert group.agent_count == 0

    def test_add_agent(self) -> None:
        config = ShareGroupConfig(group_id="g1", share_mode=ShareMode.FULL_SHARING)
        group = ShareGroup(config)
        agent = self._make_agent("a1", group_id="g1")
        group.add_agent(agent)
        assert group.agent_count == 1
        assert "a1" in group.agents

    def test_add_agent_wrong_group_raises(self) -> None:
        config = ShareGroupConfig(group_id="g1", share_mode=ShareMode.FULL_SHARING)
        group = ShareGroup(config)
        agent = self._make_agent("a1", group_id="wrong_group")
        with pytest.raises(ValueError, match="belongs to group"):
            group.add_agent(agent)

    def test_remove_agent(self) -> None:
        config = ShareGroupConfig(group_id="g1", share_mode=ShareMode.FULL_SHARING)
        group = ShareGroup(config)
        agent = self._make_agent("a1", group_id="g1")
        group.add_agent(agent)
        removed = group.remove_agent("a1")
        assert removed is not None
        assert removed.agent_id == "a1"
        assert group.agent_count == 0

    def test_remove_unknown_agent(self) -> None:
        config = ShareGroupConfig(group_id="g1", share_mode=ShareMode.FULL_SHARING)
        group = ShareGroup(config)
        assert group.remove_agent("nonexistent") is None

    def test_aggregate_mean(self) -> None:
        config = ShareGroupConfig(group_id="g1", aggregation_method="mean")
        group = ShareGroup(config)
        group.add_agent(self._make_agent("a1", group_id="g1"))
        group.add_agent(self._make_agent("a2", group_id="g1"))

        gradients = {
            "a1": {"feature_a": 0.4, "feature_b": 0.2},
            "a2": {"feature_a": 0.6, "feature_b": 0.8},
        }
        result = group.aggregate_gradients(gradients)
        assert abs(result["feature_a"] - 0.5) < 1e-10
        assert abs(result["feature_b"] - 0.5) < 1e-10

    def test_aggregate_sum(self) -> None:
        config = ShareGroupConfig(group_id="g1", aggregation_method="sum")
        group = ShareGroup(config)
        group.add_agent(self._make_agent("a1", group_id="g1"))
        group.add_agent(self._make_agent("a2", group_id="g1"))

        gradients = {
            "a1": {"feature_a": 0.4, "feature_b": 0.2},
            "a2": {"feature_a": 0.6, "feature_b": 0.8},
        }
        result = group.aggregate_gradients(gradients)
        assert abs(result["feature_a"] - 1.0) < 1e-10
        assert abs(result["feature_b"] - 1.0) < 1e-10

    def test_aggregate_weighted_mean(self) -> None:
        config = ShareGroupConfig(group_id="g1", aggregation_method="weighted_mean")
        group = ShareGroup(config)
        group.add_agent(self._make_agent("a1", group_id="g1", reward_weight=2.0))
        group.add_agent(self._make_agent("a2", group_id="g1", reward_weight=1.0))

        gradients = {
            "a1": {"feature_a": 0.6},
            "a2": {"feature_a": 0.3},
        }
        result = group.aggregate_gradients(gradients)
        expected = (2.0 * 0.6 + 1.0 * 0.3) / 3.0
        assert abs(result["feature_a"] - expected) < 1e-10

    def test_aggregate_empty_gradients(self) -> None:
        config = ShareGroupConfig(group_id="g1", aggregation_method="mean")
        group = ShareGroup(config)
        assert group.aggregate_gradients({}) == {}

    def test_aggregate_unknown_method_raises(self) -> None:
        config = ShareGroupConfig(group_id="g1", aggregation_method="invalid")
        group = ShareGroup(config)
        with pytest.raises(ValueError, match="Unknown aggregation method"):
            group.aggregate_gradients({"a1": {"f": 1.0}})

    def test_apply_update_full_sharing(self) -> None:
        config = ShareGroupConfig(
            group_id="g1",
            share_mode=ShareMode.FULL_SHARING,
            aggregation_method="mean",
        )
        group = ShareGroup(config)
        group.add_agent(self._make_agent("a1", group_id="g1", learning_rate=0.1))
        group.add_agent(self._make_agent("a2", group_id="g1", learning_rate=0.1))

        gradient = {"feature_a": 1.0, "feature_b": -1.0}
        results = group.apply_update(gradient, learning_rate=0.1)

        assert len(results) == 2
        assert "a1" in results
        assert "a2" in results
        assert abs(results["a1"]["feature_a"] - 0.1) < 1e-10

    def test_apply_update_full_separation(self) -> None:
        config = ShareGroupConfig(
            group_id="g1",
            share_mode=ShareMode.FULL_SEPARATION,
            aggregation_method="mean",
        )
        group = ShareGroup(config)
        group.add_agent(self._make_agent("a1", group_id="g1", learning_rate=0.1))

        gradient = {"feature_a": 1.0, "feature_b": -1.0}
        results = group.apply_update(gradient, learning_rate=0.1)

        assert "a1" in results

    def test_get_group_stats(self) -> None:
        config = ShareGroupConfig(group_id="g1", share_mode=ShareMode.FULL_SHARING)
        group = ShareGroup(config)
        group.add_agent(self._make_agent("a1", group_id="g1"))

        stats = group.get_group_stats()
        assert stats["group_id"] == "g1"
        assert stats["agent_count"] == 1
        assert "a1" in stats["agents"]

    def test_repr(self) -> None:
        config = ShareGroupConfig(group_id="detectors", share_mode=ShareMode.FULL_SHARING)
        group = ShareGroup(config)
        r = repr(group)
        assert "detectors" in r
        assert "full_sharing" in r


# ============================================================================
# AgentRegistry Tests
# ============================================================================

class TestAgentRegistry:
    def _make_config(self, agent_id: str, role: AgentRole = AgentRole.DETECTOR,
                     share_group: str = "default") -> GovernanceAgentConfig:
        return GovernanceAgentConfig(
            agent_id=agent_id,
            role=role,
            share_group=share_group,
            policy_features=["feature_a"],
        )

    def test_empty_registry(self) -> None:
        registry = AgentRegistry()
        assert registry.agent_count == 0
        assert registry.group_count == 0
        assert registry.list_agents() == []
        assert registry.list_groups() == []

    def test_register_agent(self) -> None:
        registry = AgentRegistry()
        agent = registry.register_agent(self._make_config("agent_1"))
        assert registry.agent_count == 1
        assert registry.has_agent("agent_1")
        assert registry.get_agent("agent_1") is agent

    def test_duplicate_agent_raises(self) -> None:
        registry = AgentRegistry()
        registry.register_agent(self._make_config("dup"))
        with pytest.raises(DuplicateAgentError, match="already registered"):
            registry.register_agent(self._make_config("dup"))

    def test_unregister_agent(self) -> None:
        registry = AgentRegistry()
        registry.register_agent(self._make_config("remove_me"))
        removed = registry.unregister_agent("remove_me")
        assert removed.agent_id == "remove_me"
        assert not registry.has_agent("remove_me")
        assert registry.agent_count == 0

    def test_unregister_unknown_raises(self) -> None:
        registry = AgentRegistry()
        with pytest.raises(UnknownAgentError, match="not registered"):
            registry.unregister_agent("nonexistent")

    def test_get_unknown_agent_raises(self) -> None:
        registry = AgentRegistry()
        with pytest.raises(UnknownAgentError, match="not found"):
            registry.get_agent("nonexistent")

    def test_get_agents_by_role(self) -> None:
        registry = AgentRegistry()
        registry.register_agent(self._make_config("d1", AgentRole.DETECTOR))
        registry.register_agent(self._make_config("d2", AgentRole.DETECTOR))
        registry.register_agent(self._make_config("o1", AgentRole.OPTIMIZER))

        detectors = registry.get_agents_by_role(AgentRole.DETECTOR)
        assert len(detectors) == 2

        optimizers = registry.get_agents_by_role(AgentRole.OPTIMIZER)
        assert len(optimizers) == 1

    def test_get_agents_by_group(self) -> None:
        registry = AgentRegistry()
        registry.register_agent(self._make_config("a1", share_group="group_x"))
        registry.register_agent(self._make_config("a2", share_group="group_x"))
        registry.register_agent(self._make_config("a3", share_group="group_y"))

        group_x_agents = registry.get_agents_by_group("group_x")
        assert len(group_x_agents) == 2

    def test_auto_creates_group(self) -> None:
        registry = AgentRegistry()
        registry.register_agent(self._make_config("a1", share_group="auto_group"))
        assert registry.has_group("auto_group")
        assert registry.group_count == 1

    def test_get_unknown_group_raises(self) -> None:
        registry = AgentRegistry()
        with pytest.raises(UnknownGroupError, match="not found"):
            registry.get_group("nonexistent")

    def test_list_group_ids(self) -> None:
        registry = AgentRegistry()
        registry.register_agent(self._make_config("a1", share_group="g1"))
        registry.register_agent(self._make_config("a2", share_group="g2"))
        ids = registry.list_group_ids()
        assert set(ids) == {"g1", "g2"}

    def test_role_distribution(self) -> None:
        registry = AgentRegistry()
        registry.register_agent(self._make_config("d1", AgentRole.DETECTOR))
        registry.register_agent(self._make_config("d2", AgentRole.DETECTOR))
        registry.register_agent(self._make_config("e1", AgentRole.EVALUATOR))

        dist = registry.get_role_distribution()
        assert dist["detector"] == 2
        assert dist["evaluator"] == 1

    def test_group_distribution(self) -> None:
        registry = AgentRegistry()
        registry.register_agent(self._make_config("a1", share_group="g1"))
        registry.register_agent(self._make_config("a2", share_group="g1"))
        registry.register_agent(self._make_config("a3", share_group="g2"))

        dist = registry.get_group_distribution()
        assert dist["g1"] == 2
        assert dist["g2"] == 1

    def test_default_agent_configs(self) -> None:
        registry = AgentRegistry()
        configs = registry.get_default_agent_configs()
        assert len(configs) == 5

        roles = {c.role for c in configs}
        assert AgentRole.DETECTOR in roles
        assert AgentRole.EVALUATOR in roles
        assert AgentRole.OPTIMIZER in roles
        assert AgentRole.ENFORCER in roles

        groups = {c.share_group for c in configs}
        assert "detectors" in groups
        assert "evaluators" in groups
        assert "optimizers" in groups
        assert "enforcers" in groups

    def test_register_default_configs(self) -> None:
        registry = AgentRegistry()
        for config in registry.get_default_agent_configs():
            registry.register_agent(config)
        assert registry.agent_count == 5
        assert registry.group_count == 4

    def test_snapshot_and_restore(self) -> None:
        registry = AgentRegistry()
        registry.register_agent(self._make_config("snap_1", AgentRole.DETECTOR, "sg1"))
        registry.register_agent(self._make_config("snap_2", AgentRole.OPTIMIZER, "sg2"))

        state = registry.snapshot()
        restored = AgentRegistry.restore(state)

        assert restored.agent_count == 2
        assert restored.has_agent("snap_1")
        assert restored.has_agent("snap_2")
        assert restored.has_group("sg1")
        assert restored.has_group("sg2")

    def test_restore_recreates_groups_with_agents(self) -> None:
        registry = AgentRegistry()
        registry.register_agent(self._make_config("grp_test", share_group="grp_a"))
        state = registry.snapshot()
        restored = AgentRegistry.restore(state)

        group = restored.get_group("grp_a")
        assert group.agent_count == 1

    def test_get_stats(self) -> None:
        registry = AgentRegistry()
        registry.register_agent(self._make_config("stats_1", share_group="sg"))
        stats = registry.get_stats()
        assert stats["agent_count"] == 1
        assert stats["group_count"] == 1
        assert "stats_1" in stats["agents"]
        assert "sg" in stats["groups"]

    def test_repr(self) -> None:
        registry = AgentRegistry()
        registry.register_agent(self._make_config("r1", share_group="g"))
        r = repr(registry)
        assert "agents=1" in r
        assert "groups=1" in r


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    def test_full_workflow(self) -> None:
        """End-to-end: register agents → aggregate gradients → apply update."""
        registry = AgentRegistry()

        registry.register_agent(GovernanceAgentConfig(
            agent_id="detector_1",
            role=AgentRole.DETECTOR,
            share_group="detectors",
            share_mode=ShareMode.FULL_SHARING,
            policy_features=["entropy_penalty", "stability_bonus"],
            learning_rate=0.1,
        ))
        registry.register_agent(GovernanceAgentConfig(
            agent_id="detector_2",
            role=AgentRole.DETECTOR,
            share_group="detectors",
            share_mode=ShareMode.FULL_SHARING,
            policy_features=["entropy_penalty", "stability_bonus"],
            learning_rate=0.1,
        ))

        group = registry.get_group("detectors")

        per_agent_gradients = {
            "detector_1": {"entropy_penalty": 0.5, "stability_bonus": -0.3},
            "detector_2": {"entropy_penalty": 0.7, "stability_bonus": -0.1},
        }

        aggregated = group.aggregate_gradients(per_agent_gradients)
        results = group.apply_update(aggregated, learning_rate=0.1)

        d1 = registry.get_agent("detector_1")
        d2 = registry.get_agent("detector_2")

        expected_entropy = (0.5 + 0.7) / 2 * 0.1
        assert abs(d1.policy_weights["entropy_penalty"] - expected_entropy) < 1e-10
        assert abs(d2.policy_weights["entropy_penalty"] - expected_entropy) < 1e-10

    def test_serialization_roundtrip_preserves_groups(self) -> None:
        registry = AgentRegistry()
        for config in registry.get_default_agent_configs():
            registry.register_agent(config)

        state = registry.snapshot()
        restored = AgentRegistry.restore(state)

        assert restored.agent_count == 5
        assert restored.group_count == 4

        for agent in restored.list_agents():
            group = restored.get_group(agent.share_group)
            assert agent.agent_id in group.agents

    def test_mixed_share_modes(self) -> None:
        """Verify that different share modes in different groups work correctly."""
        registry = AgentRegistry()

        registry.register_agent(GovernanceAgentConfig(
            agent_id="sharing_a",
            role=AgentRole.DETECTOR,
            share_group="shared",
            share_mode=ShareMode.FULL_SHARING,
            policy_features=["f1"],
            learning_rate=0.1,
        ))
        registry.register_agent(GovernanceAgentConfig(
            agent_id="sharing_b",
            role=AgentRole.DETECTOR,
            share_group="shared",
            share_mode=ShareMode.FULL_SHARING,
            policy_features=["f1"],
            learning_rate=0.1,
        ))
        registry.register_agent(GovernanceAgentConfig(
            agent_id="separate_a",
            role=AgentRole.OPTIMIZER,
            share_group="separate",
            share_mode=ShareMode.FULL_SEPARATION,
            policy_features=["f1"],
            learning_rate=0.1,
        ))

        shared_group = registry.get_group("shared")
        sep_group = registry.get_group("separate")

        assert shared_group.share_mode == ShareMode.FULL_SHARING
        assert sep_group.share_mode == ShareMode.FULL_SEPARATION
        assert shared_group.agent_count == 2
        assert sep_group.agent_count == 1

    def test_reward_recording_and_gradient_step(self) -> None:
        """Simulate a complete reward → gradient → update cycle."""
        registry = AgentRegistry()
        config = GovernanceAgentConfig(
            agent_id="reward_test",
            role=AgentRole.OPTIMIZER,
            share_group="optimizers",
            policy_features=["entropy_penalty"],
            initial_weights={"entropy_penalty": 0.0},
            learning_rate=0.05,
        )
        agent = registry.register_agent(config)

        for i in range(10):
            reward = 1.0 - i * 0.05
            agent.record_reward(reward)

        assert agent.total_reward == pytest.approx(7.75, abs=0.01)
        assert agent.episode_count == 10

        gradient = {"entropy_penalty": 0.2}
        agent.step_gradient(gradient)
        assert abs(agent.policy_weights["entropy_penalty"] - 0.01) < 1e-10
