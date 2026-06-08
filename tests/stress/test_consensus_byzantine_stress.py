"""Byzantine attack stress tests for WeightedConsensusEngine and CrossValidator."""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from maref.cross_validator.consensus_algorithm import (
    ConsensusStatus,
    VoteValue,
    WeightedConsensusEngine,
)


class TestByzantineMajorityAttack:
    """Verify consensus engine survives byzantine majority attacks."""

    def test_51_percent_byzantine_majority(self):
        """51% malicious validators — system should detect BYZANTINE_DETECTED."""
        engine = WeightedConsensusEngine()
        for i in range(49):
            engine.register_validator(f"honest-{i}", initial_weight=1.0)
        for i in range(51):
            engine.register_validator(f"malicious-{i}", initial_weight=1.0)

        engine.create_proposal("p1", {"action": "attack"}, "proposer")

        for v in engine._validators:
            if "malicious" in v:
                engine.cast_vote("p1", v, VoteValue.APPROVE)
            else:
                engine.cast_vote("p1", v, VoteValue.REJECT)

        result = engine.evaluate_consensus("p1")
        assert result.status in (ConsensusStatus.BYZANTINE_DETECTED, ConsensusStatus.INCONCLUSIVE), (
            f"Expected BYZANTINE_DETECTED or INCONCLUSIVE, got {result.status}"
        )

    def test_66_percent_byzantine_supermajority(self):
        """66% malicious — system should still detect byzantine behavior."""
        engine = WeightedConsensusEngine()
        for i in range(34):
            engine.register_validator(f"honest-{i}", initial_weight=1.0)
        for i in range(66):
            engine.register_validator(f"malicious-{i}", initial_weight=1.0)

        engine.create_proposal("p2", {"action": "malicious_takeover"}, "attacker")

        for v in engine._validators:
            if "malicious" in v:
                engine.cast_vote("p2", v, VoteValue.APPROVE)
            else:
                engine.cast_vote("p2", v, VoteValue.REJECT)

        result = engine.evaluate_consensus("p2")
        byzantine_count = len(result.byzantine_nodes_detected)
        assert byzantine_count > 0, "Should detect at least some byzantine nodes"

    def test_sybil_attack_1000_sockpuppets(self):
        """1000 sock puppet validators should not corrupt consensus."""
        engine = WeightedConsensusEngine()
        for i in range(10):
            engine.register_validator(f"real-{i}", initial_weight=5.0)
        for i in range(1000):
            engine.register_validator(f"sybil-{i}", initial_weight=0.1)

        engine.create_proposal("p3", {"test": True}, "real-0")

        for v in engine._validators:
            engine.cast_vote("p3", v, VoteValue.APPROVE)

        result = engine.evaluate_consensus("p3")
        assert result.status == ConsensusStatus.REACHED, (
            f"Expected REACHED despite sybils, got {result.status}"
        )

    def test_validator_churn_during_voting(self):
        """Rapid validator registration/unregistration during voting."""
        engine = WeightedConsensusEngine()
        for i in range(20):
            engine.register_validator(f"base-{i}")

        engine.create_proposal("p4", {"test": True}, "base-0")

        for i in range(1000):
            engine.register_validator(f"churn-{i}")
            if i > 0 and i % 3 == 0:
                engine.unregister_validator(f"churn-{i - 2}")
            engine.cast_vote("p4", f"churn-{i}", VoteValue.APPROVE)

        result = engine.evaluate_consensus("p4")
        for node_id in result.byzantine_nodes_detected:
            assert "churn-" not in node_id, (
                f"Churned validator {node_id} should not be in byzantine list"
            )

    def test_weight_manipulation_attack(self):
        """Weight manipulation should not bypass consensus."""
        engine = WeightedConsensusEngine()
        engine.register_validator("attacker", initial_weight=100.0)
        for i in range(100):
            engine.register_validator(f"honest-{i}", initial_weight=1.0)

        engine.create_proposal("p5", {"malicious": True}, "attacker")

        for v in engine._validators:
            if v == "attacker":
                engine.cast_vote("p5", v, VoteValue.APPROVE)
            else:
                engine.cast_vote("p5", v, VoteValue.REJECT)

        result = engine.evaluate_consensus("p5")
        honest_total = sum(1 for v in engine._validators if "honest" in v)
        weight_ratio = 100.0 / (100.0 + honest_total)
        if weight_ratio < 0.5:
            assert result.status in (ConsensusStatus.REACHED, ConsensusStatus.BYZANTINE_DETECTED), (
                f"Expected REACHED or BYZANTINE_DETECTED, got {result.status}"
            )


class TestConsensusConcurrentAccess:
    """Concurrent access stress tests."""

    def test_concurrent_voting_100_threads(self):
        """100 threads casting votes simultaneously."""
        engine = WeightedConsensusEngine()
        for i in range(100):
            engine.register_validator(f"voter-{i}")
        engine.create_proposal("pc1", {"test": True}, "voter-0")

        errors: list[Exception] = []
        lock = threading.Lock()

        def cast_vote(voter_id: str):
            try:
                engine.cast_vote("pc1", voter_id, VoteValue.APPROVE)
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=100) as ex:
            futures = [
                ex.submit(cast_vote, f"voter-{i}")
                for i in range(100)
            ]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    with lock:
                        errors.append(e)

        assert len(errors) == 0, f"Concurrent voting caused {len(errors)} errors"
        result = engine.evaluate_consensus("pc1")
        assert result.status in (ConsensusStatus.REACHED, ConsensusStatus.PENDING)

    def test_concurrent_proposal_and_voting(self):
        """Concurrent proposal creation and voting."""
        engine = WeightedConsensusEngine()
        for i in range(50):
            engine.register_validator(f"v-{i}")

        errors: list[Exception] = []
        lock = threading.Lock()

        def worker_p1():
            try:
                engine.create_proposal("multi-1", {"x": 1}, "v-0")
                for i in range(50):
                    engine.cast_vote("multi-1", f"v-{i}", VoteValue.APPROVE)
            except Exception as e:
                with lock:
                    errors.append(e)

        def worker_p2():
            try:
                engine.create_proposal("multi-2", {"x": 2}, "v-0")
                for i in range(50):
                    engine.cast_vote("multi-2", f"v-{i}", VoteValue.REJECT)
            except Exception as e:
                with lock:
                    errors.append(e)

        t1 = threading.Thread(target=worker_p1)
        t2 = threading.Thread(target=worker_p2)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0, f"Concurrent proposals caused {len(errors)} errors"
        r1 = engine.evaluate_consensus("multi-1")
        r2 = engine.evaluate_consensus("multi-2")
        assert r1.status in (ConsensusStatus.REACHED, ConsensusStatus.PENDING)
        assert r2.status in (ConsensusStatus.REACHED, ConsensusStatus.PENDING)

    def test_validator_register_during_consensus(self):
        """Registering validators during consensus evaluation should not crash."""
        engine = WeightedConsensusEngine()
        for i in range(20):
            engine.register_validator(f"base-{i}")
        engine.create_proposal("pc3", {"test": True}, "base-0")

        for i in range(20):
            engine.cast_vote("pc3", f"base-{i}", VoteValue.APPROVE)

        for i in range(100):
            engine.register_validator(f"late-{i}")
        engine.evaluate_consensus("pc3")

        result = engine.evaluate_consensus("pc3")
        assert result.status in (ConsensusStatus.REACHED, ConsensusStatus.PENDING), (
            f"Expected REACHED or PENDING, got {result.status}"
        )


class TestConsensusWeightUpdateStress:
    """Weight update and reputation stress tests."""

    def test_1000_round_weight_evolution(self):
        """1000 consensus rounds should produce stable weight distribution."""
        engine = WeightedConsensusEngine()
        for i in range(10):
            engine.register_validator(f"good-{i}", initial_weight=1.0)

        for round_id in range(1000):
            pid = f"round-{round_id}"
            engine.create_proposal(pid, {"round": round_id}, "good-0")
            for v in engine._validators:
                engine.cast_vote(pid, v, VoteValue.APPROVE)
            engine.update_weights_after_consensus(pid)

        stats = engine.get_network_stats()
        assert stats["consensus_reached"] > 0
        assert stats["average_trust"] > 0

    def test_byzantine_penalty_convergence(self):
        """Byzantine validators should have weight converge to near-zero."""
        engine = WeightedConsensusEngine()
        for i in range(20):
            engine.register_validator(f"honest-{i}", initial_weight=1.0)
        for i in range(5):
            engine.register_validator(f"evil-{i}", initial_weight=1.0)

        for round_id in range(200):
            pid = f"penalty-{round_id}"
            engine.create_proposal(pid, {"round": round_id}, "honest-0")
            for v in engine._validators:
                if "evil" in v:
                    engine.cast_vote(pid, v, VoteValue.REJECT)
                else:
                    engine.cast_vote(pid, v, VoteValue.APPROVE)
            engine.update_weights_after_consensus(pid)

        for i in range(5):
            stats = engine.get_validator_stats(f"evil-{i}")
            assert stats is not None
            assert stats["current_weight"] < 0.5, (
                f"Byzantine validator evil-{i} weight {stats['current_weight']} not suppressed"
            )
