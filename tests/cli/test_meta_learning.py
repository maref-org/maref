from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maref.learning.replay import DecisionOutcome
from maref_lite.meta_learning import MetaLearner, MetaLearningState
from maref_lite.state_machine import GovernanceState


class TestMetaLearningState:
    def test_default_values(self) -> None:
        state = MetaLearningState()
        assert state.policy_weights == {}
        assert state.experience_buffer == []
        assert state.total_reward == 0.0
        assert state.episode_count == 0
        assert state.learning_rate == 0.02
        assert state.discount_factor == 0.90

    def test_to_dict(self) -> None:
        state = MetaLearningState(
            policy_weights={"test": 0.5},
            total_reward=10.0,
            episode_count=5,
        )
        d = state.to_dict()
        assert d["policy_weights"] == {"test": 0.5}
        assert d["total_reward"] == 10.0
        assert d["episode_count"] == 5
        assert "buffer_size" in d


class TestMetaLearner:
    def test_init_defaults(self) -> None:
        learner = MetaLearner()
        state = learner._state
        assert "entropy_penalty" in state.policy_weights
        assert state.learning_rate == 0.02
        assert learner._buffer_size == 2000

    def test_record_decision_updates_reward(self) -> None:
        learner = MetaLearner()
        outcome = DecisionOutcome(
            timestamp=100.0,
            decision_type="test",
            state_before="INIT",
            state_after="OBSERVE",
            entropy_before=4,
            entropy_after=2,
            reward=1.5,
        )
        learner.record_decision(outcome)
        assert learner._state.total_reward == 1.5
        assert learner._state.episode_count == 0

    def test_record_decision_buffers(self) -> None:
        learner = MetaLearner(buffer_size=2)
        for i in range(5):
            outcome = DecisionOutcome(
                timestamp=float(i),
                decision_type="test",
                state_before="INIT",
                state_after="OBSERVE",
                entropy_before=4,
                entropy_after=2,
                reward=1.0,
            )
            learner.record_decision(outcome)
        assert len(learner._state.experience_buffer) == 2

    def test_compute_reward_entropy_reduction(self) -> None:
        learner = MetaLearner()
        reward = learner.compute_reward(
            state_before=GovernanceState.ANALYZE,
            state_after=GovernanceState.OBSERVE,
            entropy_before=4,
            entropy_after=2,
            time_in_state=10.0,
        )
        assert reward == pytest.approx(2.0)

    def test_compute_reward_anomaly_resolved(self) -> None:
        learner = MetaLearner()
        reward = learner.compute_reward(
            state_before=GovernanceState.ANALYZE,
            state_after=GovernanceState.OBSERVE,
            entropy_before=4,
            entropy_after=2,
            anomaly_resolved=True,
            time_in_state=10.0,
        )
        assert reward == pytest.approx(4.0)

    def test_compute_reward_halt_penalty(self) -> None:
        learner = MetaLearner()
        reward = learner.compute_reward(
            state_before=GovernanceState.ANALYZE,
            state_after=GovernanceState.HALT,
            entropy_before=4,
            entropy_after=4,
            time_in_state=10.0,
        )
        assert reward == pytest.approx(-8.0)

    def test_compute_reward_stabilize_bonus(self) -> None:
        learner = MetaLearner()
        reward = learner.compute_reward(
            state_before=GovernanceState.ANALYZE,
            state_after=GovernanceState.STABILIZE,
            entropy_before=5,
            entropy_after=1,
            time_in_state=10.0,
        )
        assert reward == pytest.approx(4.0)

    def test_compute_reward_time_penalty(self) -> None:
        learner = MetaLearner()
        reward = learner.compute_reward(
            state_before=GovernanceState.ANALYZE,
            state_after=GovernanceState.ANALYZE,
            entropy_before=3,
            entropy_after=3,
            time_in_state=0.5,
        )
        assert reward == pytest.approx(-0.2)

    def test_optimize_policy_insufficient_data(self) -> None:
        learner = MetaLearner()
        result = learner.optimize_policy()
        assert result is None

    def test_estimate_gradient(self) -> None:
        learner = MetaLearner()
        for i in range(50):
            outcome = DecisionOutcome(
                timestamp=float(i),
                decision_type="test",
                state_before="ANALYZE",
                state_after="OBSERVE",
                entropy_before=4,
                entropy_after=2,
                reward=1.0,
            )
            learner.record_decision(outcome)
        gradient = learner._estimate_gradient()
        assert "entropy_penalty" in gradient
        assert "stability_bonus" in gradient
        assert "transition_efficiency" in gradient

    def test_get_stats(self) -> None:
        learner = MetaLearner()
        stats = learner.get_stats()
        assert "state" in stats
        assert "avg_reward" in stats
        assert "store" in stats
        assert "scheduler" in stats
        assert "persisted_samples" in stats
        assert stats["buffer_utilization"] == 0.0

    def test_save_and_load_state(self, tmp_path: Path) -> None:
        learner = MetaLearner()
        outcome = DecisionOutcome(
            timestamp=1.0,
            decision_type="test",
            state_before="INIT",
            state_after="OBSERVE",
            entropy_before=4,
            entropy_after=2,
            reward=2.0,
        )
        learner.record_decision(outcome)
        path = tmp_path / "meta_state.json"
        learner.save(path)

        learner2 = MetaLearner()
        assert learner2._state.total_reward != 2.0
        learner2.load(path)
        assert learner2._state.total_reward == 2.0
        assert learner2._state.episode_count == 0

    def test_save_creates_file(self, tmp_path: Path) -> None:
        learner = MetaLearner()
        path = tmp_path / "saved.json"
        learner.save(path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert "policy_weights" in data

    def test_load_from_disk(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text(json.dumps({
            "policy_weights": {"entropy_penalty": -0.5},
            "learning_rate": 0.01,
            "total_reward": 5.0,
            "episode_count": 3,
        }))
        learner = MetaLearner()
        learner.load(path)
        assert learner._state.policy_weights["entropy_penalty"] == -0.5
        assert learner._state.learning_rate == 0.01
        assert learner._state.total_reward == 5.0
        assert learner._state.episode_count == 3

    def test_clip_weights(self) -> None:
        learner = MetaLearner()
        learner._state.policy_weights = {"extreme": 10.0}
        learner._clip_weights()
        assert learner._state.policy_weights["extreme"] == 1.0

        learner._state.policy_weights = {"extreme": -10.0}
        learner._clip_weights()
        assert learner._state.policy_weights["extreme"] == -1.0

    def test_generate_policy(self) -> None:
        learner = MetaLearner()
        policy = learner._generate_policy()
        assert hasattr(policy, "kl_warning")
        assert hasattr(policy, "kl_critical")
        assert hasattr(policy, "kl_max")

    def test_decay_learning_rate(self) -> None:
        learner = MetaLearner()
        initial_lr = learner._state.learning_rate
        for _ in range(50):
            outcome = DecisionOutcome(
                timestamp=1.0,
                decision_type="test",
                state_before="A",
                state_after="B",
                entropy_before=4,
                entropy_after=2,
                reward=1.0,
            )
            learner.record_decision(outcome)
        learner._decay_learning_rate()
        assert learner._state.learning_rate >= learner._min_learning_rate

    def test_reward_no_change_in_entropy(self) -> None:
        learner = MetaLearner()
        reward = learner.compute_reward(
            state_before=GovernanceState.OBSERVE,
            state_after=GovernanceState.OBSERVE,
            entropy_before=3,
            entropy_after=3,
            time_in_state=10.0,
        )
        assert reward == 0.0
