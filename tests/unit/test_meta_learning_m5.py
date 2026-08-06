"""
M5 Meta-Learning Engineering Tests

Covers:
- M5.1: ExperienceStore SQLite persistence
- M5.2: LearningRateScheduler ReduceLROnPlateau
- M5.3: StrategyComparator A/B validation
- M5.4: Adversarial distribution drift resilience
- M5.5: Reward function calibration
"""

from __future__ import annotations

import statistics
import tempfile
from pathlib import Path

from maref.learning import (
    ABDecision,
    ABWinner,
    ExperienceStore,
    LearningRateScheduler,
    MetricSnapshot,
    StrategyComparator,
)
from maref.learning.replay import DecisionOutcome
from maref_lite.meta_learning import MetaLearner
from maref_lite.state_machine import GovernanceState


class TestExperienceStore:
    """M5.1: SQLite-backed experience replay buffer."""

    def test_insert_and_count(self) -> None:
        store = ExperienceStore()
        assert store.count() == 0

        outcome = DecisionOutcome(
            timestamp=1000.0,
            decision_type="test",
            state_before="OBSERVE",
            state_after="ANALYZE",
            entropy_before=1,
            entropy_after=2,
            reward=0.5,
        )
        store.insert(outcome)
        assert store.count() == 1

    def test_insert_batch(self) -> None:
        store = ExperienceStore()
        outcomes = [
            DecisionOutcome(
                timestamp=float(i),
                decision_type="test",
                state_before="OBSERVE",
                state_after="ANALYZE",
                entropy_before=1,
                entropy_after=2,
                reward=float(i % 3 - 1),
            )
            for i in range(10)
        ]
        store.insert_batch(outcomes)
        assert store.count() == 10

    def test_get_recent(self) -> None:
        store = ExperienceStore()
        for i in range(100):
            store.insert(
                DecisionOutcome(
                    timestamp=float(i),
                    decision_type="test",
                    state_before="OBSERVE",
                    state_after="ANALYZE",
                    entropy_before=1,
                    entropy_after=2,
                    reward=0.1,
                )
            )

        recent = store.get_recent(20)
        assert len(recent) == 20
        assert recent[0].timestamp > recent[-1].timestamp

    def test_sample_stratified(self) -> None:
        store = ExperienceStore()
        for i in range(50):
            store.insert(
                DecisionOutcome(
                    timestamp=float(i),
                    decision_type="test",
                    state_before="OBSERVE",
                    state_after="STABILIZE",
                    entropy_before=3,
                    entropy_after=1,
                    reward=1.0,
                )
            )
        for i in range(50):
            store.insert(
                DecisionOutcome(
                    timestamp=float(100 + i),
                    decision_type="test",
                    state_before="ANALYZE",
                    state_after="HALT",
                    entropy_before=2,
                    entropy_after=0,
                    reward=-5.0,
                )
            )

        sample = store.sample(batch_size=40, stratified=True)
        assert len(sample) == 40
        pos = sum(1 for s in sample if s.reward > 0)
        neg = sum(1 for s in sample if s.reward <= 0)
        assert pos > 0
        assert neg > 0

    def test_avg_reward(self) -> None:
        store = ExperienceStore()
        for i in range(100):
            store.insert(
                DecisionOutcome(
                    timestamp=float(i),
                    decision_type="test",
                    state_before="OBSERVE",
                    state_after="ANALYZE",
                    entropy_before=1,
                    entropy_after=2,
                    reward=0.5,
                )
            )

        avg = store.avg_reward()
        assert 0.4 < avg < 0.6

    def test_persistence_across_instances(self) -> None:
        db_path = tempfile.mktemp(suffix=".db")

        store1 = ExperienceStore(db_path=db_path)
        store1.insert(
            DecisionOutcome(
                timestamp=1000.0,
                decision_type="test",
                state_before="OBSERVE",
                state_after="ANALYZE",
                entropy_before=1,
                entropy_after=2,
                reward=0.7,
            )
        )
        assert store1.count() == 1
        store1.close()

        store2 = ExperienceStore(db_path=db_path)
        assert store2.count() == 1
        samples = store2.get_recent(1)
        assert samples[0].reward == 0.7
        store2.close()

        Path(db_path).unlink(missing_ok=True)

    def test_trim_oldest(self) -> None:
        store = ExperienceStore(max_size=100)
        for i in range(150):
            store.insert(
                DecisionOutcome(
                    timestamp=float(i),
                    decision_type="test",
                    state_before="OBSERVE",
                    state_after="ANALYZE",
                    entropy_before=1,
                    entropy_after=2,
                    reward=0.1,
                )
            )

        assert store.count() <= 100

    def test_get_stats(self) -> None:
        store = ExperienceStore()
        for i in range(50):
            store.insert(
                DecisionOutcome(
                    timestamp=float(i),
                    decision_type="test",
                    state_before="OBSERVE",
                    state_after="ANALYZE",
                    entropy_before=2,
                    entropy_after=1,
                    reward=0.5,
                )
            )

        stats = store.get_stats()
        assert stats["total_samples"] == 50
        assert stats["avg_reward"] > 0
        assert "buffer_utilization" in stats
        assert stats["positive_count"] == 50

    def test_clear(self) -> None:
        store = ExperienceStore()
        store.insert(
            DecisionOutcome(
                timestamp=1000.0,
                decision_type="test",
                state_before="OBSERVE",
                state_after="ANALYZE",
                entropy_before=1,
                entropy_after=2,
                reward=0.5,
            )
        )
        assert store.count() == 1
        store.clear()
        assert store.count() == 0


class TestLearningRateScheduler:
    """M5.2: ReduceLROnPlateau adaptive scheduling."""

    def test_initial_lr(self) -> None:
        scheduler = LearningRateScheduler(initial_lr=0.01)
        assert scheduler.learning_rate == 0.01

    def test_no_reduction_with_improvement(self) -> None:
        scheduler = LearningRateScheduler(initial_lr=0.01)
        for i in range(10):
            lr = scheduler.step(float(i) * 0.2)
        assert lr == 0.01

    def test_reduction_on_plateau(self) -> None:
        scheduler = LearningRateScheduler(initial_lr=0.01)
        for _ in range(20):
            lr = scheduler.step(0.0)
        assert lr <= 0.005

    def test_min_lr_floor(self) -> None:
        scheduler = LearningRateScheduler(initial_lr=0.001)
        for _ in range(50):
            lr = scheduler.step(0.0)
        assert lr >= 0.0001

    def test_cooldown_after_reduction(self) -> None:
        scheduler = LearningRateScheduler(initial_lr=0.01)
        for _ in range(5):
            scheduler.step(0.0)

        reduced = scheduler.learning_rate
        assert reduced < 0.01

        for _ in range(2):
            lr = scheduler.step(0.0)
        assert lr == reduced

    def test_should_reduce(self) -> None:
        scheduler = LearningRateScheduler(initial_lr=0.01)
        assert scheduler.learning_rate == 0.01

        for _ in range(5):
            scheduler.step(0.0)

        assert scheduler.learning_rate < 0.01

    def test_get_stats(self) -> None:
        scheduler = LearningRateScheduler(initial_lr=0.01)
        stats = scheduler.get_stats()
        assert stats["current_lr"] == 0.01
        assert stats["epoch_count"] == 0
        assert "config" in stats


class TestStrategyComparator:
    """M5.3: A/B strategy comparison pipeline."""

    def test_insufficient_data(self) -> None:
        comp = StrategyComparator()
        result = comp.compare()
        assert result.winner == ABWinner.NONE
        assert result.confidence == 0.0

    def test_b_clearly_better(self) -> None:
        comp = StrategyComparator()
        for _ in range(10):
            comp.record_a(MetricSnapshot(fnr=0.6, fpr=0.3, avg_reward=0.2, stability_rate=0.3))
            comp.record_b(MetricSnapshot(fnr=0.1, fpr=0.05, avg_reward=0.9, stability_rate=0.9))

        result = comp.compare()
        assert result.winner == ABWinner.STRATEGY_B
        assert result.confidence > 0.5

    def test_a_clearly_better(self) -> None:
        comp = StrategyComparator()
        for _ in range(10):
            comp.record_a(MetricSnapshot(fnr=0.05, fpr=0.02, avg_reward=0.95, stability_rate=0.95))
            comp.record_b(MetricSnapshot(fnr=0.7, fpr=0.4, avg_reward=0.1, stability_rate=0.2))

        result = comp.compare()
        assert result.winner == ABWinner.STRATEGY_A
        assert result.confidence > 0.5

    def test_hold_when_close(self) -> None:
        comp = StrategyComparator()
        for _ in range(10):
            comp.record_a(MetricSnapshot(fnr=0.5, fpr=0.1, avg_reward=0.5, stability_rate=0.5))
            comp.record_b(MetricSnapshot(fnr=0.5, fpr=0.1, avg_reward=0.5, stability_rate=0.5))

        result = comp.compare()
        assert result.winner == ABWinner.NONE

    def test_mixed_metrics_hold(self) -> None:
        comp = StrategyComparator()
        comp.record_a(MetricSnapshot(fnr=0.01, fpr=0.8, avg_reward=0.4, stability_rate=0.3))
        comp.record_b(MetricSnapshot(fnr=0.9, fpr=0.02, avg_reward=0.5, stability_rate=0.6))

        result = comp.compare()
        f_prom = sum(1 for d in result.decisions.values() if d == ABDecision.PROMOTE)
        f_roll = sum(1 for d in result.decisions.values() if d == ABDecision.ROLLBACK)
        assert f_prom < 3 or f_roll < 3

    def test_oscillation_improvement(self) -> None:
        comp = StrategyComparator()
        comp.record_a(MetricSnapshot(oscillation_count=20))
        comp.record_b(MetricSnapshot(oscillation_count=5))

        result = comp.compare()
        assert result.metric_deltas["oscillation_count"] == 15

    def test_to_dict(self) -> None:
        comp = StrategyComparator()
        comp.record_a(MetricSnapshot(fnr=0.2, fpr=0.1))
        comp.record_b(MetricSnapshot(fnr=0.1, fpr=0.05))

        result = comp.compare()
        d = result.to_dict()
        assert "winner" in d
        assert "confidence" in d
        assert "decisions" in d
        assert "metric_deltas" in d


class TestAdversarialDriftResilience:
    """M5.4: Adversarial distribution drift - verifies meta-learner
    does not collapse or diverge under extreme/unseen scenarios."""

    def test_extreme_reward_distribution(self) -> None:
        learner = MetaLearner(experience_db_path=":memory:")
        for i in range(200):
            reward = 500.0 if i % 10 == 0 else -300.0
            outcome = DecisionOutcome(
                timestamp=float(i),
                decision_type="adversarial",
                state_before="OBSERVE",
                state_after="ANALYZE",
                entropy_before=4,
                entropy_after=0,
                reward=reward,
            )
            learner.record_decision(outcome)

        for _ in range(5):
            policy = learner.optimize_policy()
            if policy:
                assert 0.0 < policy.kl_warning < 10.0
                assert 0.0 < policy.kl_critical < 20.0

    def test_entropy_spike_does_not_diverge(self) -> None:
        learner = MetaLearner(experience_db_path=":memory:")
        for i in range(200):
            entropy_before = 4 if i < 100 else 0
            entropy_after = 0 if i < 100 else 4
            outcome = DecisionOutcome(
                timestamp=float(i),
                decision_type="adversarial",
                state_before="OBSERVE",
                state_after="STABILIZE",
                entropy_before=entropy_before,
                entropy_after=entropy_after,
                reward=1.0 if entropy_before > entropy_after else -1.0,
            )
            learner.record_decision(outcome)

        policy = learner.optimize_policy()
        assert policy is not None

        for weight in learner._state.policy_weights.values():
            assert abs(weight) <= learner._max_weight_magnitude

    def test_all_negative_rewards_no_collapse(self) -> None:
        learner = MetaLearner(experience_db_path=":memory:")
        for i in range(200):
            outcome = DecisionOutcome(
                timestamp=float(i),
                decision_type="adversarial",
                state_before="OBSERVE",
                state_after="STABILIZE",
                entropy_before=3,
                entropy_after=4,
                reward=-2.0,
            )
            learner.record_decision(outcome)

        policy = learner.optimize_policy()
        assert policy is not None
        for weight in learner._state.policy_weights.values():
            assert abs(weight) <= learner._max_weight_magnitude

    def test_rapid_oscillation_scenario(self) -> None:
        learner = MetaLearner(experience_db_path=":memory:")
        states = ["OBSERVE", "ANALYZE", "DECIDE", "ACT", "STABILIZE"]
        for i in range(200):
            outcome = DecisionOutcome(
                timestamp=float(i),
                decision_type="adversarial",
                state_before=states[i % len(states)],
                state_after=states[(i + 1) % len(states)],
                entropy_before=(i % 5),
                entropy_after=((i + 1) % 5),
                reward=0.5 if (i % 5) > ((i + 1) % 5) else -0.3,
            )
            learner.record_decision(outcome)

        policies = []
        for _ in range(10):
            policy = learner.optimize_policy()
            if policy:
                policies.append(policy.kl_warning)

        if len(policies) > 1:
            std_dev = statistics.stdev(policies)
            assert std_dev < 0.5, f"Policy diverged under oscillation: std={std_dev}"

    def test_zero_reward_stability(self) -> None:
        learner = MetaLearner(experience_db_path=":memory:")
        for i in range(200):
            outcome = DecisionOutcome(
                timestamp=float(i),
                decision_type="adversarial",
                state_before="OBSERVE",
                state_after="OBSERVE",
                entropy_before=2,
                entropy_after=2,
                reward=0.0,
            )
            learner.record_decision(outcome)

        policy = learner.optimize_policy()
        assert policy is not None

    def test_cross_session_persistence(self) -> None:
        db_path = tempfile.mktemp(suffix=".db")
        learner1 = MetaLearner(experience_db_path=db_path)
        for i in range(100):
            learner1.record_decision(
                DecisionOutcome(
                    timestamp=float(i),
                    decision_type="test",
                    state_before="OBSERVE",
                    state_after="ANALYZE",
                    entropy_before=3,
                    entropy_after=1,
                    reward=1.0,
                )
            )
        assert learner1._store.count() >= 100
        learner1._store.close()

        learner2 = MetaLearner(experience_db_path=db_path)
        assert learner2._store.count() >= 100
        policy = learner2.optimize_policy()
        assert policy is not None
        learner2._store.close()
        Path(db_path).unlink(missing_ok=True)


class TestRewardCalibration:
    """M5.5: Reward function calibration — verify consistency
    between expected and computed rewards across state transitions."""

    def test_entropy_reduction_positive(self) -> None:
        learner = MetaLearner()
        reward = learner.compute_reward(
            state_before=GovernanceState.ANALYZE,
            state_after=GovernanceState.OBSERVE,
            entropy_before=3,
            entropy_after=1,
            anomaly_resolved=False,
            time_in_state=10.0,
        )
        assert reward > 0

    def test_entropy_increase_negative(self) -> None:
        learner = MetaLearner()
        reward = learner.compute_reward(
            state_before=GovernanceState.OBSERVE,
            state_after=GovernanceState.ANALYZE,
            entropy_before=1,
            entropy_after=3,
            anomaly_resolved=False,
            time_in_state=1.0,
        )
        assert reward < 0

    def test_anomaly_resolution_strong_positive(self) -> None:
        learner = MetaLearner()
        reward = learner.compute_reward(
            state_before=GovernanceState.ACT,
            state_after=GovernanceState.VERIFY,
            entropy_before=4,
            entropy_after=3,
            anomaly_resolved=True,
            time_in_state=3.0,
        )
        assert reward > 2.0

    def test_halt_always_penalized(self) -> None:
        learner = MetaLearner()
        reward = learner.compute_reward(
            state_before=GovernanceState.STABILIZE,
            state_after=GovernanceState.HALT,
            entropy_before=1,
            entropy_after=0,
            anomaly_resolved=False,
            time_in_state=2.0,
        )
        assert reward < 0

    def test_stabilize_bonus(self) -> None:
        learner = MetaLearner()
        reward_stab = learner.compute_reward(
            state_before=GovernanceState.DECIDE,
            state_after=GovernanceState.STABILIZE,
            entropy_before=3,
            entropy_after=1,
            anomaly_resolved=False,
            time_in_state=10.0,
        )
        reward_other = learner.compute_reward(
            state_before=GovernanceState.DECIDE,
            state_after=GovernanceState.REPORT,
            entropy_before=3,
            entropy_after=1,
            anomaly_resolved=False,
            time_in_state=10.0,
        )
        assert reward_stab > reward_other

    def test_rapid_transition_penalty(self) -> None:
        learner = MetaLearner()
        reward_slow = learner.compute_reward(
            state_before=GovernanceState.OBSERVE,
            state_after=GovernanceState.ANALYZE,
            entropy_before=1,
            entropy_after=2,
            anomaly_resolved=False,
            time_in_state=10.0,
        )
        reward_fast = learner.compute_reward(
            state_before=GovernanceState.OBSERVE,
            state_after=GovernanceState.ANALYZE,
            entropy_before=1,
            entropy_after=2,
            anomaly_resolved=False,
            time_in_state=0.5,
        )
        assert reward_slow > reward_fast

    def test_calibration_consistency_over_noise(self) -> None:
        learner = MetaLearner()
        rewards = []
        for _ in range(100):
            r = learner.compute_reward(
                state_before=GovernanceState.OBSERVE,
                state_after=GovernanceState.STABILIZE,
                entropy_before=2,
                entropy_after=1,
                anomaly_resolved=False,
                time_in_state=6.0,
            )
            rewards.append(r)
        variance = statistics.variance(rewards) if len(rewards) > 1 else 0
        assert variance == 0.0

    def test_entropy_monotonic(self) -> None:
        learner = MetaLearner()
        rewards = []
        for entropy_before in range(5):
            r = learner.compute_reward(
                state_before=GovernanceState.OBSERVE,
                state_after=GovernanceState.STABILIZE,
                entropy_before=entropy_before,
                entropy_after=0,
                anomaly_resolved=False,
                time_in_state=6.0,
            )
            rewards.append(r)
        for i in range(len(rewards) - 1):
            assert rewards[i] <= rewards[i + 1], (
                f"Entropy monotonicity violated: reward({i})={rewards[i]} "
                f"> reward({i+1})={rewards[i+1]}"
            )

    def test_reward_bounded_by_limits(self) -> None:
        learner = MetaLearner()
        for state in GovernanceState:
            r = learner.compute_reward(
                state_before=GovernanceState.OBSERVE,
                state_after=state,
                entropy_before=4,
                entropy_after=0,
                anomaly_resolved=True,
                time_in_state=100.0,
            )
            assert -20.0 < r < 20.0, f"Reward r={r} out of bounds for state {state.name}"
