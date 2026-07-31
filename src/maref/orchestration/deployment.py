from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.governance.audit import AuditLogger
from maref.integration.flag_bridge import FeatureFlag, FlagBridge, PolicySnapshot, RolloutStage
from maref.learning.ab_test import ABResult, ABWinner, StrategyComparator


class DeploymentStatus(Enum):
    PROPOSED = "proposed"
    VALIDATED = "validated"
    CANARY = "canary"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class CanaryDecision(Enum):
    PROMOTE = "promote"
    HOLD = "hold"
    ROLLBACK = "rollback"


@dataclass
class DeploymentRecord:
    id: str
    policy_name: str
    baseline: PolicySnapshot
    candidate: PolicySnapshot
    status: DeploymentStatus
    gates_passed: list[str] = field(default_factory=list)
    gates_failed: list[str] = field(default_factory=list)
    canary_ab_result: ABResult | None = None
    canary_decision: CanaryDecision | None = None
    created_at: float = field(default_factory=time.time)
    promoted_at: float = 0.0
    rolled_back_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "policy_name": self.policy_name,
            "status": self.status.value,
            "gates_passed": self.gates_passed,
            "gates_failed": self.gates_failed,
            "canary_decision": self.canary_decision.value if self.canary_decision else None,
            "created_at": self.created_at,
            "promoted_at": self.promoted_at,
            "rolled_back_at": self.rolled_back_at,
            "metadata": self.metadata,
        }


class DeploymentOrchestrator:
    def __init__(
        self,
        flag_bridge: FlagBridge | None = None,
        audit_logger: AuditLogger | None = None,
        ed25519_signer: Any | None = None,
    ) -> None:
        self._flag_bridge = flag_bridge or FlagBridge()
        self._audit_logger = audit_logger
        self._signer = ed25519_signer
        self._deployments: dict[str, DeploymentRecord] = {}
        self._comparators: dict[str, StrategyComparator] = {}
        self._canary_flags: dict[str, FeatureFlag] = {}

    def propose(
        self,
        policy_name: str,
        baseline: PolicySnapshot,
        candidate: PolicySnapshot,
        gates: list[tuple[str, bool]] | None = None,
    ) -> DeploymentRecord:
        dep_id = f"deploy-{uuid.uuid4().hex[:12]}"
        gates_passed: list[str] = []
        gates_failed: list[str] = []
        if gates:
            for name, passed in gates:
                if passed:
                    gates_passed.append(name)
                else:
                    gates_failed.append(name)

        status = DeploymentStatus.PROPOSED if gates_failed else DeploymentStatus.VALIDATED

        record = DeploymentRecord(
            id=dep_id,
            policy_name=policy_name,
            baseline=baseline,
            candidate=candidate,
            status=status,
            gates_passed=gates_passed,
            gates_failed=gates_failed,
        )
        self._deployments[dep_id] = record

        if self._audit_logger is not None:
            metadata = {
                "deployment_id": dep_id,
                "policy_name": policy_name,
                "gates_passed": gates_passed,
                "gates_failed": gates_failed,
                "status": status.value,
            }
            self._audit_logger.log(
                event_type="deployment_proposed",
                actor="DeploymentOrchestrator",
                action="propose",
                details=f"Deployment {dep_id}: {policy_name} — {status.value}",
                metadata=metadata,
            )

        return record

    def start_canary(
        self,
        deployment_id: str,
        initial_stage: RolloutStage = RolloutStage.CANARY_1,
    ) -> FeatureFlag | None:
        record = self._deployments.get(deployment_id)
        if record is None or record.status not in (
            DeploymentStatus.VALIDATED,
            DeploymentStatus.PROPOSED,
        ):
            return None

        flag = self._flag_bridge.create_flag(
            baseline=record.baseline,
            candidate=record.candidate,
            policy_name=record.policy_name,
            initial_stage=initial_stage,
        )
        self._canary_flags[deployment_id] = flag

        record.status = DeploymentStatus.CANARY
        record.metadata["flag_key"] = flag.key
        record.metadata["canary_stage"] = initial_stage.value

        comparator = StrategyComparator()
        self._comparators[deployment_id] = comparator

        if self._audit_logger is not None:
            self._audit_logger.log(
                event_type="canary_started",
                actor="DeploymentOrchestrator",
                action="start_canary",
                details=f"Canary {flag.key} at {initial_stage.value}% for {deployment_id}",
                metadata={
                    "deployment_id": deployment_id,
                    "flag_key": flag.key,
                    "stage": initial_stage.value,
                    "stage_name": initial_stage.name,
                },
            )

        return flag

    def record_canary_metrics(
        self,
        deployment_id: str,
        ab_result: ABResult,
    ) -> None:
        record = self._deployments.get(deployment_id)
        if record is None or record.status != DeploymentStatus.CANARY:
            return
        record.canary_ab_result = ab_result

    def evaluate_canary(
        self,
        deployment_id: str,
        force_decision: CanaryDecision | None = None,
    ) -> CanaryDecision | None:
        record = self._deployments.get(deployment_id)
        if record is None or record.status != DeploymentStatus.CANARY:
            return None

        if force_decision is not None:
            decision = force_decision
        elif record.canary_ab_result is not None:
            ab = record.canary_ab_result
            if ab.winner == ABWinner.STRATEGY_B:
                decision = CanaryDecision.PROMOTE
            elif ab.winner == ABWinner.STRATEGY_A:
                decision = CanaryDecision.ROLLBACK
            else:
                decision = CanaryDecision.HOLD
        else:
            decision = CanaryDecision.HOLD

        record.canary_decision = decision
        record.metadata["evaluated_at"] = time.time()
        return decision

    def promote(
        self,
        deployment_id: str,
        reason: str = "",
    ) -> bool:
        record = self._deployments.get(deployment_id)
        if record is None:
            return False

        flag = self._canary_flags.get(deployment_id)
        if flag is not None:
            self._flag_bridge.advance_stage(flag, RolloutStage.FULL, reason)

        record.status = DeploymentStatus.PROMOTED
        record.promoted_at = time.time()

        if self._audit_logger is not None:
            self._audit_logger.log(
                event_type="deployment_promoted",
                actor="DeploymentOrchestrator",
                action="promote",
                details=f"Deployment {deployment_id} promoted: {reason}",
                metadata={
                    "deployment_id": deployment_id,
                    "policy_name": record.policy_name,
                    "reason": reason,
                },
            )

        return True

    def rollback(
        self,
        deployment_id: str,
        reason: str = "",
    ) -> bool:
        record = self._deployments.get(deployment_id)
        if record is None:
            return False

        flag = self._canary_flags.get(deployment_id)
        if flag is not None:
            self._flag_bridge.rollback(flag, reason)

        record.status = DeploymentStatus.ROLLED_BACK
        record.rolled_back_at = time.time()

        if self._audit_logger is not None:
            self._audit_logger.log(
                event_type="deployment_rolled_back",
                actor="DeploymentOrchestrator",
                action="rollback",
                details=f"Deployment {deployment_id} rolled back: {reason}",
                metadata={
                    "deployment_id": deployment_id,
                    "policy_name": record.policy_name,
                    "reason": reason,
                },
            )

        return True

    def get_deployment(self, deployment_id: str) -> DeploymentRecord | None:
        return self._deployments.get(deployment_id)

    def list_deployments(
        self,
        status: DeploymentStatus | None = None,
    ) -> list[DeploymentRecord]:
        if status is None:
            return list(self._deployments.values())
        return [d for d in self._deployments.values() if d.status == status]

    def summary(self) -> dict[str, Any]:
        stages: dict[str, int] = {}
        for d in self._deployments.values():
            s = d.status.value
            stages[s] = stages.get(s, 0) + 1
        return {
            "total_deployments": len(self._deployments),
            "by_status": stages,
            "active_canaries": len(
                [d for d in self._deployments.values() if d.status == DeploymentStatus.CANARY]
            ),
        }
