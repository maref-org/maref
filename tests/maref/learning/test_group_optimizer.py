from __future__ import annotations

from maref.learning.group_optimizer import (
    EntropyRegularizer,
    OptimizerConfig,
    OptimizerState,
    PolicyUpdateResult,
)


class TestOptimizerConfig:
    def test_defaults(self) -> None:
        cfg = OptimizerConfig()
        assert cfg.clip_epsilon == 0.2
        assert cfg.value_loss_coeff == 0.5
        assert cfg.entropy_coeff == 0.01
        assert cfg.max_grad_norm == 1.0
        assert cfg.gae_lambda == 0.95
        assert cfg.discount_factor == 0.99
        assert cfg.min_learning_rate == 0.0001
        assert cfg.scheduler_patience == 3

    def test_custom(self) -> None:
        cfg = OptimizerConfig(
            clip_epsilon=0.1, entropy_coeff=0.05, discount_factor=0.95
        )
        assert cfg.clip_epsilon == 0.1
        assert cfg.entropy_coeff == 0.05
        assert cfg.discount_factor == 0.95

    def test_to_dict(self) -> None:
        cfg = OptimizerConfig()
        d = cfg.to_dict()
        assert d["clip_epsilon"] == 0.2
        assert d["entropy_coeff"] == 0.01


class TestOptimizerState:
    def test_defaults(self) -> None:
        state = OptimizerState()
        assert state.total_updates == 0
        assert state.total_clipped == 0
        assert state.reward_history == []
        assert state.clip_fraction == 0.0

    def test_clip_fraction(self) -> None:
        state = OptimizerState(total_updates=10, total_clipped=3)
        state_dict = state.to_dict()
        assert state_dict["clip_fraction"] == 0.3

    def test_clip_fraction_zero(self) -> None:
        state = OptimizerState()
        assert state.to_dict()["clip_fraction"] == 0.0

    def test_with_history(self) -> None:
        state = OptimizerState(
            reward_history=[1.0, 2.0],
            loss_history=[0.5, 0.3],
            entropy_history=[0.1, 0.2],
        )
        d = state.to_dict()
        assert d["recent_rewards"] == [1.0, 2.0]
        assert d["recent_losses"] == [0.5, 0.3]
        assert d["recent_entropy"] == [0.1, 0.2]


class TestPolicyUpdateResult:
    def test_fields(self) -> None:
        result = PolicyUpdateResult(
            agent_updates={"agent1": {"weight": 0.5}},
            loss=0.25,
            clipped_count=2,
            entropy=0.1,
            gradient_norm=1.5,
        )
        assert result.agent_updates == {"agent1": {"weight": 0.5}}
        assert result.loss == 0.25
        assert result.clipped_count == 2
        assert result.entropy == 0.1
        assert result.gradient_norm == 1.5


class TestEntropyRegularizer:
    def test_compute_entropy_uniform(self) -> None:
        entropy = EntropyRegularizer.compute_entropy({"a": 1.0, "b": 1.0})
        assert entropy > 0

    def test_compute_entropy_deterministic(self) -> None:
        entropy = EntropyRegularizer.compute_entropy({"a": 100.0, "b": 0.0})
        assert entropy < 0.01

    def test_compute_entropy_empty(self) -> None:
        assert EntropyRegularizer.compute_entropy({}) == 0.0

    def test_entropy_bonus(self) -> None:
        bonus = EntropyRegularizer.entropy_bonus(
            {"a": 0.5, "b": 0.5}, coeff=0.1
        )
        expected = 0.1 * EntropyRegularizer.compute_entropy({"a": 0.5, "b": 0.5})
        assert abs(bonus - expected) < 1e-10

    def test_entropy_gradient_empty(self) -> None:
        assert EntropyRegularizer.entropy_gradient({}) == {}

    def test_entropy_gradient_nonempty(self) -> None:
        grad = EntropyRegularizer.entropy_gradient({"a": 0.5, "b": 0.5})
        assert "a" in grad
        assert "b" in grad
