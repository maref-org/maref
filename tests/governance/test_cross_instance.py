"""Tests for CrossInstanceGovernor, SyncPolicy, and FederatedAudit."""

from __future__ import annotations

from typing import Any

from maref.governance.cross_instance import (
    CrossInstanceGovernor,
    InstanceStatus,
    SyncResult,
    WeightPoisonDetector,
    WeightSnapshot,
)
from maref.governance.federated_audit import AuditEventType, FederatedAuditLog
from maref.governance.sync_policy import (
    ConflictStrategy,
    SyncDataType,
    SyncDirection,
    SyncPolicy,
    SyncPolicyRegistry,
)

# ── SyncPolicy Tests ─────────────────────────────────────────────────────────

class TestSyncPolicyRegistry:
    def test_default_policies_exist(self) -> None:
        registry = SyncPolicyRegistry()
        assert len(registry.list_policies()) == 8

    def test_get_policy(self) -> None:
        registry = SyncPolicyRegistry()
        policy = registry.get_policy(SyncDataType.TRUST_SCORES)
        assert policy is not None
        assert policy.data_type == SyncDataType.TRUST_SCORES
        assert policy.requires_consensus

    def test_set_custom_policy(self) -> None:
        registry = SyncPolicyRegistry()
        custom = SyncPolicy(
            data_type=SyncDataType.TRUST_SCORES,
            direction=SyncDirection.PULL_ONLY,
            conflict_strategy=ConflictStrategy.BLOCK,
            requires_consensus=True,
            min_confirmations=5,
        )
        registry.set_policy(custom)
        policy = registry.get_policy(SyncDataType.TRUST_SCORES)
        assert policy is not None
        assert policy.direction == SyncDirection.PULL_ONLY
        assert policy.min_confirmations == 5

    def test_allow_sync(self) -> None:
        registry = SyncPolicyRegistry()
        assert registry.allow_sync(SyncDataType.AUDIT_LOGS)

    def test_allow_sync_disabled(self) -> None:
        registry = SyncPolicyRegistry()
        custom = SyncPolicy(
            data_type=SyncDataType.AUDIT_LOGS, enabled=False,
        )
        registry.set_policy(custom)
        assert not registry.allow_sync(SyncDataType.AUDIT_LOGS)

    def test_reset_to_defaults(self) -> None:
        registry = SyncPolicyRegistry()
        custom = SyncPolicy(
            data_type=SyncDataType.AUDIT_LOGS, enabled=False,
        )
        registry.set_policy(custom)
        registry.reset_to_defaults()
        assert registry.allow_sync(SyncDataType.AUDIT_LOGS)

    def test_policy_to_dict(self) -> None:
        policy = SyncPolicy(
            data_type=SyncDataType.ENTROPY,
            direction=SyncDirection.PUSH_ONLY,
        )
        d = policy.to_dict()
        assert d["data_type"] == "entropy"
        assert d["direction"] == "push_only"

    def test_nonexistent_policy(self) -> None:
        registry = SyncPolicyRegistry()
        assert registry.allow_sync(SyncDataType.ENTROPY)


# ── FederatedAudit Tests ─────────────────────────────────────────────────────

class TestFederatedAudit:
    def test_record_entry(self) -> None:
        log = FederatedAuditLog()
        entry = log.record(
            AuditEventType.SYNC_STARTED, "i1", "i2", "trust_scores",
            details="test sync",
        )
        assert entry.event_type == AuditEventType.SYNC_STARTED
        assert entry.source_instance == "i1"
        assert entry.target_instance == "i2"
        assert entry.hmac_signature != ""

    def test_hmac_verify_valid(self) -> None:
        log = FederatedAuditLog()
        entry = log.record(
            AuditEventType.CONSENSUS_REACHED, "i1", "i2", "config",
        )
        assert entry.verify()

    def test_hmac_verify_tampered(self) -> None:
        log = FederatedAuditLog()
        entry = log.record(
            AuditEventType.SYNC_COMPLETED, "i1", "i2", "audit_logs",
        )
        entry.details = "tampered"
        assert not entry.verify()

    def test_query_by_type(self) -> None:
        log = FederatedAuditLog()
        log.record(AuditEventType.SYNC_STARTED, "i1", "i2", "a")
        log.record(AuditEventType.SYNC_COMPLETED, "i1", "i2", "b")
        log.record(AuditEventType.CONSENSUS_FAILED, "i1", "i2", "c")
        results = log.query(event_type=AuditEventType.SYNC_STARTED)
        assert len(results) == 1

    def test_query_by_source(self) -> None:
        log = FederatedAuditLog()
        log.record(AuditEventType.SYNC_STARTED, "i1", "i2", "a")
        log.record(AuditEventType.SYNC_STARTED, "i2", "i1", "b")
        results = log.query(source="i1")
        assert len(results) == 1

    def test_query_by_severity(self) -> None:
        log = FederatedAuditLog()
        log.record(AuditEventType.SYNC_STARTED, "i1", "i2", "a", severity="info")
        log.record(AuditEventType.SYNC_FAILED, "i1", "i2", "b", severity="warning")
        results = log.query(severity="warning")
        assert len(results) == 1

    def test_verify_all_tamper_detection(self) -> None:
        log = FederatedAuditLog()
        log.record(AuditEventType.SYNC_STARTED, "i1", "i2", "a")
        entry = log.record(AuditEventType.SYNC_COMPLETED, "i1", "i2", "b")
        entry.details = "modified"
        tampered = log.verify_all()
        assert len(tampered) == 1

    def test_entry_to_dict(self) -> None:
        log = FederatedAuditLog()
        entry = log.record(
            AuditEventType.WEIGHT_POISON_DETECTED, "i1", "i2", "weights",
            severity="critical",
        )
        d = entry.to_dict()
        assert d["event_type"] == "weight_poison_detected"
        assert d["severity"] == "critical"

    def test_entry_count(self) -> None:
        log = FederatedAuditLog()
        assert log.entry_count == 0
        log.record(AuditEventType.SYNC_STARTED, "i1", "i2", "a")
        assert log.entry_count == 1


# ── CrossInstanceGovernor Tests ──────────────────────────────────────────────

class TestCrossInstanceGovernor:
    def test_register_instance(self) -> None:
        gov = CrossInstanceGovernor("local")
        info = gov.register_instance("remote1", "10.0.0.1", 9000)
        assert info.instance_id == "remote1"
        assert info.status == InstanceStatus.ACTIVE

    def test_remove_instance(self) -> None:
        gov = CrossInstanceGovernor("local")
        gov.register_instance("remote1", "10.0.0.1", 9000)
        assert gov.remove_instance("remote1")
        assert not gov.remove_instance("nonexistent")

    def test_get_instances(self) -> None:
        gov = CrossInstanceGovernor("local")
        gov.register_instance("r1", "10.0.0.1", 9000)
        gov.register_instance("r2", "10.0.0.2", 9001)
        assert len(gov.get_instances()) == 2

    def test_get_instances_by_status(self) -> None:
        gov = CrossInstanceGovernor("local")
        gov.register_instance("r1", "10.0.0.1", 9000)
        gov.register_instance("r2", "10.0.0.2", 9001)
        gov.set_instance_status("r2", InstanceStatus.SUSPENDED)
        active = gov.get_instances(status=InstanceStatus.ACTIVE)
        assert len(active) == 1
        assert active[0].instance_id == "r1"

    def test_request_sync_blocked_by_policy(self) -> None:
        gov = CrossInstanceGovernor("local")
        gov.register_instance("r1", "10.0.0.1", 9000)
        custom = SyncPolicy(
            data_type=SyncDataType.TRUST_SCORES,
            enabled=False,
        )
        gov.policy_registry.set_policy(custom)
        result = gov.request_sync(SyncDataType.TRUST_SCORES, "r1")
        assert result == SyncResult.BLOCKED_BY_POLICY

    def test_request_sync_pull_only_blocked(self) -> None:
        gov = CrossInstanceGovernor("local")
        gov.register_instance("r1", "10.0.0.1", 9000)
        custom = SyncPolicy(
            data_type=SyncDataType.TRUST_SCORES,
            direction=SyncDirection.PULL_ONLY,
        )
        gov.policy_registry.set_policy(custom)
        result = gov.request_sync(SyncDataType.TRUST_SCORES, "r1")
        assert result == SyncResult.BLOCKED_BY_POLICY

    def test_request_sync_unreachable(self) -> None:
        gov = CrossInstanceGovernor("local")
        result = gov.request_sync(SyncDataType.AUDIT_LOGS, "unknown")
        assert result == SyncResult.INSTANCE_UNREACHABLE

    def test_request_sync_success(self) -> None:
        gov = CrossInstanceGovernor("local")
        gov.register_instance("r1", "10.0.0.1", 9000)
        result = gov.request_sync(SyncDataType.AUDIT_LOGS, "r1")
        assert result == SyncResult.SUCCESS

    def test_receive_weights_normal(self) -> None:
        gov = CrossInstanceGovernor("local")
        snapshot = gov.receive_weights("r1", {"trust": 0.5, "vote": 1.0})
        assert isinstance(snapshot, WeightSnapshot)
        assert snapshot.instance_id == "r1"

    def test_receive_weights_poison_detected(self) -> None:
        gov = CrossInstanceGovernor("local")
        gov.receive_weights("r1", {"trust": 0.5, "vote": 1.0})
        gov.receive_weights("r2", {"trust": 0.6, "vote": 1.1})
        poisoned = gov.receive_weights("r3", {"trust": 10.0, "vote": 20.0})
        assert poisoned.instance_id == "r3"

    def test_weight_snapshots_stored(self) -> None:
        gov = CrossInstanceGovernor("local")
        gov.receive_weights("r1", {"trust": 0.5})
        gov.receive_weights("r1", {"trust": 0.6})
        snapshots = gov.get_weight_snapshots("r1")
        assert len(snapshots) == 2

    def test_set_instance_status(self) -> None:
        gov = CrossInstanceGovernor("local")
        gov.register_instance("r1", "10.0.0.1", 9000)
        assert gov.set_instance_status("r1", InstanceStatus.SUSPENDED)

    def test_local_instance_id(self) -> None:
        gov = CrossInstanceGovernor("local-abc")
        assert gov.local_instance_id == "local-abc"

    def test_instance_info_to_dict(self) -> None:
        gov = CrossInstanceGovernor("local")
        info = gov.register_instance("r1", "10.0.0.1", 9000)
        d = info.to_dict()
        assert d["instance_id"] == "r1"
        assert d["status"] == "active"
        assert d["host"] == "10.0.0.1"

    def test_weight_snapshot_to_dict(self) -> None:
        gov = CrossInstanceGovernor("local")
        snapshot = gov.receive_weights("r1", {"trust": 0.5})
        d = snapshot.to_dict()
        assert d["instance_id"] == "r1"
        assert d["weights"]["trust"] == 0.5

    def test_set_status_unknown_instance(self) -> None:
        gov = CrossInstanceGovernor("local")
        assert not gov.set_instance_status("nonexistent", InstanceStatus.SUSPENDED)

    def test_audit_log_property(self) -> None:
        gov = CrossInstanceGovernor("local")
        assert gov.audit_log is not None
        assert gov.audit_log.entry_count == 0

    def test_consensus_validator(self) -> None:
        gov = CrossInstanceGovernor("local")
        gov.register_instance("r1", "10.0.0.1", 9000)

        def always_pass(_s: str, _t: str, _d: Any) -> bool:
            return True

        gov.register_consensus_validator(always_pass)
        result = gov.request_sync(SyncDataType.VERIFIER_STATE, "r1")
        assert result == SyncResult.SUCCESS

    def test_consensus_validator_block(self) -> None:
        gov = CrossInstanceGovernor("local")
        gov.register_instance("r1", "10.0.0.1", 9000)

        def always_fail(_s: str, _t: str, _d: Any) -> bool:
            return False

        gov.register_consensus_validator(always_fail)
        result = gov.request_sync(SyncDataType.VERIFIER_STATE, "r1")
        assert result == SyncResult.CONSENSUS_FAILED


class TestWeightPoisonDetector:
    def test_no_poison_with_normal_weights(self) -> None:
        detector = WeightPoisonDetector()
        weights = {
            "i1": {"trust": 0.5, "vote": 1.0},
            "i2": {"trust": 0.6, "vote": 1.1},
            "i3": {"trust": 0.55, "vote": 0.9},
        }
        poisoned = detector.detect_poisoning(weights)
        assert len(poisoned) == 0

    def test_detects_outlier(self) -> None:
        detector = WeightPoisonDetector()
        weights = {
            "i1": {"trust": 0.5},
            "i2": {"trust": 0.6},
            "i3": {"trust": 10.0},
        }
        poisoned = detector.detect_poisoning(weights)
        assert len(poisoned) == 1
        assert poisoned[0]["instance_id"] == "i3"

    def test_not_enough_instances_no_detection(self) -> None:
        detector = WeightPoisonDetector()
        weights = {
            "i1": {"trust": 0.5},
            "i2": {"trust": 10.0},
        }
        poisoned = detector.detect_poisoning(weights)
        assert len(poisoned) == 0

    def test_multiple_poisoned_keys(self) -> None:
        detector = WeightPoisonDetector()
        weights = {
            "i1": {"trust": 0.5, "vote": 1.0},
            "i2": {"trust": 0.6, "vote": 1.1},
            "i3": {"trust": 8.0, "vote": 9.0},
        }
        poisoned = detector.detect_poisoning(weights)
        assert len(poisoned) == 2

    def test_empty_weights_no_detection(self) -> None:
        detector = WeightPoisonDetector()
        assert detector.detect_poisoning({}) == []
