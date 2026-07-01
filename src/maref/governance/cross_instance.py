"""
MAREF Cross-Instance Governor

Governance layer for cross-instance synchronization, federation
consistency, and weight poisoning detection.

Key capabilities:
- CrossInstanceGovernor: coordinates sync, validates consensus,
  enforces sync policies.
- WeightPoisonDetector: detects anomalous trust/vote weight
  distributions using z-score based outlier detection.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.governance.federated_audit import AuditEventType, FederatedAuditLog
from maref.governance.sync_policy import SyncDataType, SyncDirection, SyncPolicyRegistry
from maref.security.decorators import security_critical


class SyncResult(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED_BY_POLICY = "blocked_by_policy"
    CONSENSUS_FAILED = "consensus_failed"
    INSTANCE_UNREACHABLE = "instance_unreachable"


class InstanceStatus(Enum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


@dataclass
class InstanceInfo:
    instance_id: str
    host: str
    port: int
    status: InstanceStatus = InstanceStatus.ACTIVE
    trust_score: float = 0.5
    last_seen: float = field(default_factory=time.time)
    version: str = "0.35.0-beta"
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "host": self.host,
            "port": self.port,
            "status": self.status.value,
            "trust_score": self.trust_score,
            "last_seen": self.last_seen,
            "version": self.version,
            "capabilities": self.capabilities,
        }


@dataclass
class WeightSnapshot:
    instance_id: str
    weights: dict[str, float]
    timestamp: float = field(default_factory=time.time)
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "weights": dict(self.weights),
            "timestamp": self.timestamp,
            "snapshot_id": self.snapshot_id,
        }


class CrossInstanceGovernor:
    def __init__(
        self,
        local_instance_id: str,
        policy_registry: SyncPolicyRegistry | None = None,
        audit_log: FederatedAuditLog | None = None,
    ) -> None:
        self._local_id = local_instance_id
        self._policy_registry = policy_registry or SyncPolicyRegistry()
        self._audit_log = audit_log or FederatedAuditLog()
        self._instances: dict[str, InstanceInfo] = {}
        self._consensus_validators: list[Callable[[str, str, Any], bool]] = []
        self._weight_snapshots: dict[str, list[WeightSnapshot]] = {}
        self._weights: dict[str, dict[str, float]] = {}

    def register_instance(
        self,
        instance_id: str,
        host: str,
        port: int,
        version: str = "0.35.0-beta",
        capabilities: list[str] | None = None,
    ) -> InstanceInfo:
        info = InstanceInfo(
            instance_id=instance_id,
            host=host,
            port=port,
            version=version,
            capabilities=capabilities or [],
        )
        self._instances[instance_id] = info
        self._audit_log.record(
            event_type=AuditEventType.INSTANCE_JOINED,
            source_instance=self._local_id,
            target_instance=instance_id,
            data_type="instance",
            details=f"Instance {instance_id} registered at {host}:{port}",
        )
        return info

    def remove_instance(self, instance_id: str) -> bool:
        instance = self._instances.pop(instance_id, None)
        if instance is None:
            return False
        self._audit_log.record(
            event_type=AuditEventType.INSTANCE_LEFT,
            source_instance=self._local_id,
            target_instance=instance_id,
            data_type="instance",
            details=f"Instance {instance_id} removed",
        )
        return True

    @security_critical
    def request_sync(
        self,
        data_type: SyncDataType,
        target_instance: str,
        payload: Any = None,
    ) -> SyncResult:
        policy = self._policy_registry.get_policy(data_type)
        if policy is None or not policy.enabled:
            self._audit_log.record(
                event_type=AuditEventType.POLICY_VIOLATION,
                source_instance=self._local_id,
                target_instance=target_instance,
                data_type=data_type.value,
                details=f"No policy or sync disabled for {data_type.value}",
                severity="warning",
            )
            return SyncResult.BLOCKED_BY_POLICY

        if policy.direction == SyncDirection.PULL_ONLY:
            return SyncResult.BLOCKED_BY_POLICY

        instance = self._instances.get(target_instance)
        if instance is None or instance.status != InstanceStatus.ACTIVE:
            return SyncResult.INSTANCE_UNREACHABLE

        if policy.requires_consensus:
            consensus_ok = self._run_consensus(
                data_type.value, target_instance, payload
            )
            if not consensus_ok:
                self._audit_log.record(
                    event_type=AuditEventType.CONSENSUS_FAILED,
                    source_instance=self._local_id,
                    target_instance=target_instance,
                    data_type=data_type.value,
                    details=f"Consensus failed for {data_type.value} sync",
                    severity="warning",
                )
                return SyncResult.CONSENSUS_FAILED

        self._audit_log.record(
            event_type=AuditEventType.SYNC_STARTED,
            source_instance=self._local_id,
            target_instance=target_instance,
            data_type=data_type.value,
            details=f"Syncing {data_type.value} to {target_instance}",
        )
        return SyncResult.SUCCESS

    @security_critical
    def register_consensus_validator(
        self, validator: Callable[[str, str, Any], bool]
    ) -> None:
        self._consensus_validators.append(validator)

    @security_critical
    def receive_weights(
        self,
        instance_id: str,
        weights: dict[str, float],
    ) -> WeightSnapshot:
        snapshot = WeightSnapshot(
            instance_id=instance_id,
            weights=dict(weights),
        )
        self._weight_snapshots.setdefault(instance_id, []).append(snapshot)
        self._weights[instance_id] = dict(weights)

        detector = WeightPoisonDetector()
        poisoned = detector.detect_poisoning(self._weights)
        if poisoned:
            self._audit_log.record(
                event_type=AuditEventType.WEIGHT_POISON_DETECTED,
                source_instance=instance_id,
                target_instance=self._local_id,
                data_type="weights",
                details=f"Weight poisoning detected from {instance_id}: {poisoned}",
                severity="critical",
            )

        return snapshot

    def get_weight_snapshots(
        self, instance_id: str, limit: int = 10
    ) -> list[WeightSnapshot]:
        snapshots = self._weight_snapshots.get(instance_id, [])
        return snapshots[-limit:]

    def get_instances(
        self, status: InstanceStatus | None = None
    ) -> list[InstanceInfo]:
        instances = list(self._instances.values())
        if status:
            instances = [i for i in instances if i.status == status]
        return instances

    def set_instance_status(
        self, instance_id: str, status: InstanceStatus
    ) -> bool:
        instance = self._instances.get(instance_id)
        if instance is None:
            return False
        instance.status = status
        return True

    def _run_consensus(
        self, data_type: str, target: str, _payload: Any
    ) -> bool:
        for validator in self._consensus_validators:
            if not validator(self._local_id, target, data_type):
                return False
        return True

    @property
    def local_instance_id(self) -> str:
        return self._local_id

    @property
    def audit_log(self) -> FederatedAuditLog:
        return self._audit_log

    @property
    def policy_registry(self) -> SyncPolicyRegistry:
        return self._policy_registry


class WeightPoisonDetector:
    @security_critical
    def detect_poisoning(
        self, all_weights: dict[str, dict[str, float]]
    ) -> list[dict[str, Any]]:
        poisoned: list[dict[str, Any]] = []
        if len(all_weights) < 3:
            return poisoned

        weight_keys: set[str] = set()
        for w in all_weights.values():
            weight_keys.update(w.keys())

        for key in weight_keys:
            values = []
            for weights in all_weights.values():
                if key in weights:
                    values.append(weights[key])

            if len(values) < 3:
                continue

            sorted_vals = sorted(values)
            n = len(sorted_vals)
            median = sorted_vals[n // 2]
            abs_devs = sorted(abs(v - median) for v in sorted_vals)
            mad = abs_devs[n // 2] if n > 0 else 0.001
            mad = mad if mad > 0 else 0.001

            for instance_id, weights in all_weights.items():
                if key not in weights:
                    continue
                modified_z = 0.6745 * abs(weights[key] - median) / mad
                if modified_z > 3.0:
                    poisoned.append({
                        "instance_id": instance_id,
                        "key": key,
                        "value": weights[key],
                        "median": round(median, 4),
                        "modified_z_score": round(modified_z, 4),
                        "severity": "high" if modified_z > 5.0 else "medium",
                    })

        return poisoned
