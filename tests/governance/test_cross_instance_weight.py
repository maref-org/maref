"""Tests for CrossInstanceGovernor weight management and WeightPoisonDetector.

RL-005 enforcement: weight poisoning detection, weight snapshot integrity.
"""

from __future__ import annotations

from maref.governance.cross_instance import (
    CrossInstanceGovernor,
    InstanceStatus,
    WeightPoisonDetector,
    WeightSnapshot,
)


class TestWeightPoisonDetector:
    def test_no_poisoning_with_few_instances(self):
        detector = WeightPoisonDetector()
        weights = {"inst1": {"trust": 0.5}, "inst2": {"trust": 0.6}}
        poisoned = detector.detect_poisoning(weights)
        assert poisoned == []

    def test_detects_outlier_weight(self):
        detector = WeightPoisonDetector()
        weights = {
            "inst1": {"trust": 0.5},
            "inst2": {"trust": 0.5},
            "inst3": {"trust": 0.5},
            "inst4": {"trust": 10.0},
        }
        poisoned = detector.detect_poisoning(weights)
        assert len(poisoned) >= 1
        assert poisoned[0]["instance_id"] == "inst4"

    def test_no_false_positive_for_uniform_weights(self):
        detector = WeightPoisonDetector()
        weights = {
            "inst1": {"trust": 0.5},
            "inst2": {"trust": 0.6},
            "inst3": {"trust": 0.55},
            "inst4": {"trust": 0.52},
        }
        poisoned = detector.detect_poisoning(weights)
        assert poisoned == []

    def test_multi_key_poisoning(self):
        detector = WeightPoisonDetector()
        weights = {
            "inst1": {"trust": 0.5, "reputation": 0.5},
            "inst2": {"trust": 0.5, "reputation": 0.5},
            "inst3": {"trust": 0.5, "reputation": 0.5},
            "inst4": {"trust": 10.0, "reputation": 0.5},
        }
        poisoned = detector.detect_poisoning(weights)
        keys_found = {p["key"] for p in poisoned}
        assert "trust" in keys_found


class TestCrossInstanceWeight:
    def test_receive_weights_creates_snapshot(self):
        gov = CrossInstanceGovernor("local")
        snap = gov.receive_weights("remote1", {"trust": 0.5})
        assert isinstance(snap, WeightSnapshot)
        assert snap.instance_id == "remote1"
        assert snap.weights == {"trust": 0.5}

    def test_get_weight_snapshots_returns_recent(self):
        gov = CrossInstanceGovernor("local")
        gov.receive_weights("remote1", {"trust": 0.5})
        gov.receive_weights("remote1", {"trust": 0.6})
        snaps = gov.get_weight_snapshots("remote1", limit=1)
        assert len(snaps) == 1
        assert snaps[0].weights["trust"] == 0.6

    def test_register_instance_fires_audit(self):
        gov = CrossInstanceGovernor("local")
        initial = len(gov.audit_log.query())
        gov.register_instance("remote1", "10.0.0.1", 8080)
        assert len(gov.audit_log.query()) == initial + 1

    def test_set_instance_status(self):
        gov = CrossInstanceGovernor("local")
        gov.register_instance("remote1", "10.0.0.1", 8080)
        gov.set_instance_status("remote1", InstanceStatus.SUSPENDED)
        instances = gov.get_instances(status=InstanceStatus.SUSPENDED)
        assert len(instances) == 1
        assert instances[0].instance_id == "remote1"

    def test_remove_instance_removes_and_audits(self):
        gov = CrossInstanceGovernor("local")
        gov.register_instance("remote1", "10.0.0.1", 8080)
        assert gov.remove_instance("remote1") is True
        assert gov.remove_instance("nonexistent") is False
