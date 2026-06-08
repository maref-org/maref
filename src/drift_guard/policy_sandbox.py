"""
MAREF Policy Sandbox

Phase 9: Safe self-modification mechanism for governance policies.
Ensures that policy updates are:
1. Versioned and auditable
2. Tested before activation
3. Rollback-capable
4. Human-approved for critical changes

This is the "safety cage" that allows MAREF to modify its own
behavior without risking system instability.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import hmac
import json
import logging
import os as _os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

from drift_guard.types import PipelineConfig

logger = logging.getLogger(__name__)


class PolicyChangeType(Enum):
    """Types of policy changes that can be proposed."""

    THRESHOLD_ADJUSTMENT = auto()  # Modify drift detection thresholds
    MONITOR_CONFIG = auto()        # Change monitoring parameters
    STATE_MACHINE_RULE = auto()    # Update state transition rules
    ACTION_POLICY = auto()         # Modify response actions


class PolicyStatus(Enum):
    """Lifecycle status of a policy change."""

    PROPOSED = auto()
    UNDER_REVIEW = auto()
    A_B_TESTING = auto()
    APPROVED = auto()
    REJECTED = auto()
    ROLLED_BACK = auto()


@dataclass
class PolicyVersion:
    """A versioned policy configuration."""

    version_id: str
    timestamp: float
    config: PipelineConfig
    change_type: PolicyChangeType
    description: str
    parent_version: str | None = None
    performance_baseline: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "timestamp": self.timestamp,
            "config": self.config.to_dict(),
            "change_type": self.change_type.name,
            "description": self.description,
            "parent_version": self.parent_version,
            "performance_baseline": self.performance_baseline,
        }


@dataclass
class PolicyChange:
    """A proposed change to governance policy."""

    change_id: str
    version_id: str
    change_type: PolicyChangeType
    description: str
    proposed_config: PipelineConfig
    status: PolicyStatus
    proposed_at: float
    reviewed_at: float | None = None
    approved_at: float | None = None
    test_results: dict[str, Any] = field(default_factory=dict)
    reviewer: str = "auto"

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "version_id": self.version_id,
            "change_type": self.change_type.name,
            "description": self.description,
            "proposed_config": self.proposed_config.to_dict(),
            "status": self.status.name,
            "proposed_at": self.proposed_at,
            "reviewed_at": self.reviewed_at,
            "approved_at": self.approved_at,
            "test_results": self.test_results,
            "reviewer": self.reviewer,
        }


class PolicySandbox:
    """
    Safe policy update sandbox.

    Manages the lifecycle of policy changes:
    1. Propose: Create a new policy version
    2. Test: Run A/B tests against baseline
    3. Review: Human or automated review
    4. Activate: Deploy if approved
    5. Monitor: Watch for degradation
    6. Rollback: Revert if issues detected
    """

    def __init__(
        self,
        baseline_config: PipelineConfig | None = None,
        storage_path: Path | None = None,
        max_memory_versions: int = 10,
        max_memory_changes: int = 50,
    ) -> None:
        self._baseline = baseline_config or PipelineConfig()
        self._storage = storage_path or Path("policy_versions")
        self._storage.mkdir(parents=True, exist_ok=True)

        self._versions: dict[str, PolicyVersion] = {}
        self._changes: dict[str, PolicyChange] = {}
        self._max_memory_versions = max_memory_versions
        self._max_memory_changes = max_memory_changes
        self._active_version: str = "baseline"
        self._version_history: list[str] = ["baseline"]

        # Initialize baseline version
        self._versions["baseline"] = PolicyVersion(
            version_id="baseline",
            timestamp=time.time(),
            config=copy.deepcopy(self._baseline),
            change_type=PolicyChangeType.THRESHOLD_ADJUSTMENT,
            description="Initial baseline configuration",
        )

        # Callbacks for policy change events
        self._callbacks: list[Callable[[PolicyChange], None]] = []

        # HMAC-SHA256 key for policy version integrity
        _hmac_key = _os.environ.get("POLICY_SANDBOX_HMAC_KEY")
        self._hmac_key = _hmac_key or hashlib.sha256(uuid.uuid4().bytes).hexdigest()

    def _evict_old_entries(self) -> None:
        """Remove old versions/changes from memory, keep them on disk."""
        if len(self._versions) > self._max_memory_versions:
            versions_to_keep = set(self._version_history[-self._max_memory_versions:])
            versions_to_keep.add("baseline")
            versions_to_keep.add(self._active_version)
            for version_id in list(self._versions.keys()):
                if version_id not in versions_to_keep:
                    del self._versions[version_id]

        if len(self._changes) > self._max_memory_changes:
            active_statuses = {
                PolicyStatus.PROPOSED,
                PolicyStatus.A_B_TESTING,
                PolicyStatus.UNDER_REVIEW,
            }
            changes_to_keep: list[str] = []
            for change_id, change in sorted(
                self._changes.items(), key=lambda x: x[1].proposed_at, reverse=True
            ):
                if change.status in active_statuses or len(changes_to_keep) < self._max_memory_changes:
                    changes_to_keep.append(change_id)
                else:
                    break
            changes_to_keep_set = set(changes_to_keep)
            for change_id in list(self._changes.keys()):
                if change_id not in changes_to_keep_set:
                    del self._changes[change_id]

    def _load_version_from_disk(self, version_id: str) -> PolicyVersion | None:
        """Load a version from disk if not in memory, verifying HMAC signature."""
        filepath = self._storage / f"version_{version_id}.json"
        if not filepath.exists():
            return None
        data = json.loads(filepath.read_text(encoding="utf-8"))

        # Verify HMAC-SHA256 integrity
        stored_hmac = data.pop("_hmac", "")
        if stored_hmac:
            serialized = json.dumps(data, sort_keys=True, default=str)
            expected = hmac.new(
                self._hmac_key.encode(), serialized.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(stored_hmac, expected):
                logger.error("HMAC mismatch for version %s — possible tampering", version_id)
                return None

        return PolicyVersion(
            version_id=data["version_id"],
            timestamp=data["timestamp"],
            config=PipelineConfig(**data["config"]),
            change_type=PolicyChangeType[data["change_type"]],
            description=data["description"],
            parent_version=data.get("parent_version"),
            performance_baseline=data.get("performance_baseline", {}),
        )

    def _get_version(self, version_id: str) -> PolicyVersion | None:
        """Get version from memory or load from disk."""
        if version_id in self._versions:
            return self._versions[version_id]
        version = self._load_version_from_disk(version_id)
        if version:
            self._versions[version_id] = version
            self._evict_old_entries()
        return version

    def add_callback(self, callback: Callable[[PolicyChange], None]) -> None:
        """Register a callback for policy change events."""
        self._callbacks.append(callback)

    def _notify(self, change: PolicyChange) -> None:
        """Notify all callbacks of a policy change."""
        for cb in self._callbacks:
            with contextlib.suppress(Exception):
                cb(change)

    def propose_change(
        self,
        change_type: PolicyChangeType,
        description: str,
        new_config: PipelineConfig,
    ) -> PolicyChange:
        """
        Propose a new policy change.

        Args:
            change_type: Type of change being proposed
            description: Human-readable description
            new_config: The proposed configuration

        Returns:
            The created PolicyChange object
        """
        version_id = f"v_{uuid.uuid4().hex[:8]}"
        change_id = f"change_{uuid.uuid4().hex[:8]}"

        version = PolicyVersion(
            version_id=version_id,
            timestamp=time.time(),
            config=copy.deepcopy(new_config),
            change_type=change_type,
            description=description,
            parent_version=self._active_version,
        )

        change = PolicyChange(
            change_id=change_id,
            version_id=version_id,
            change_type=change_type,
            description=description,
            proposed_config=new_config,
            status=PolicyStatus.PROPOSED,
            proposed_at=time.time(),
        )

        self._versions[version_id] = version
        self._changes[change_id] = change

        self._save_version(version)
        self._save_change(change)

        self._evict_old_entries()

        return change

    def start_a_b_test(self, change_id: str) -> bool:
        """
        Start A/B testing for a proposed change.

        Args:
            change_id: ID of the change to test

        Returns:
            True if testing started successfully
        """
        if change_id not in self._changes:
            return False

        change = self._changes[change_id]
        if change.status != PolicyStatus.PROPOSED:
            return False

        change.status = PolicyStatus.A_B_TESTING
        change.test_results = {
            "started_at": time.time(),
            "baseline_version": self._active_version,
            "test_version": change.version_id,
            "metrics": {},
        }

        self._save_change(change)
        self._notify(change)
        return True

    def record_test_results(
        self, change_id: str, metrics: dict[str, Any]
    ) -> bool:
        """
        Record A/B test results for a policy change.

        Args:
            change_id: ID of the change
            metrics: Test metrics (e.g., FPR, FNR, latency)

        Returns:
            True if results recorded successfully
        """
        if change_id not in self._changes:
            return False

        change = self._changes[change_id]
        if change.status != PolicyStatus.A_B_TESTING:
            return False

        change.test_results["metrics"] = metrics
        change.test_results["completed_at"] = time.time()

        self._save_change(change)
        return True

    def approve_change(
        self, change_id: str, reviewer: str = "auto"
    ) -> bool:
        """
        Approve and activate a policy change.

        Args:
            change_id: ID of the change to approve
            reviewer: Who approved the change

        Returns:
            True if change was approved and activated
        """
        if change_id not in self._changes:
            return False

        change = self._changes[change_id]
        if change.status not in (PolicyStatus.A_B_TESTING,):
            return False

        change.status = PolicyStatus.APPROVED
        change.approved_at = time.time()
        change.reviewer = reviewer

        # Activate the new version
        self._active_version = change.version_id
        self._version_history.append(change.version_id)

        self._save_change(change)
        self._notify(change)
        return True

    def reject_change(self, change_id: str, reason: str = "") -> bool:
        """
        Reject a proposed change.

        Args:
            change_id: ID of the change to reject
            reason: Rejection reason

        Returns:
            True if change was rejected
        """
        if change_id not in self._changes:
            return False

        change = self._changes[change_id]
        if change.status in (PolicyStatus.APPROVED, PolicyStatus.ROLLED_BACK):
            return False

        change.status = PolicyStatus.REJECTED
        change.test_results["rejection_reason"] = reason

        self._save_change(change)
        self._notify(change)
        return True

    def rollback(self) -> bool:
        """
        Rollback to the previous active version.

        Returns:
            True if rollback was successful
        """
        if len(self._version_history) < 2:
            return False

        current_version = self._version_history.pop()
        previous_version = self._version_history[-1]

        # Mark current version as rolled back
        for change in self._changes.values():
            if change.version_id == current_version:
                change.status = PolicyStatus.ROLLED_BACK
                change.test_results["rolled_back_at"] = time.time()
                change.test_results["rolled_back_to"] = previous_version
                self._save_change(change)
                break

        self._active_version = previous_version
        return True

    def get_active_config(self) -> PipelineConfig:
        """Get the currently active policy configuration."""
        version = self._get_version(self._active_version)
        if version:
            return copy.deepcopy(version.config)
        return copy.deepcopy(self._baseline)

    def get_version_history(self) -> list[dict[str, Any]]:
        """Get the version history as a list of dicts."""
        result = []
        for v in self._version_history:
            version = self._get_version(v)
            if version:
                result.append(version.to_dict())
        return result

    def get_pending_changes(self) -> list[PolicyChange]:
        """Get all changes awaiting review."""
        return [
            c
            for c in self._changes.values()
            if c.status in (PolicyStatus.PROPOSED, PolicyStatus.A_B_TESTING)
        ]

    def get_stats(self) -> dict[str, Any]:
        """Get sandbox statistics."""
        return {
            "total_versions": len(self._versions),
            "total_changes": len(self._changes),
            "active_version": self._active_version,
            "version_history": self._version_history,
            "pending_changes": len(self.get_pending_changes()),
            "approved_changes": sum(
                1 for c in self._changes.values() if c.status == PolicyStatus.APPROVED
            ),
            "rejected_changes": sum(
                1 for c in self._changes.values() if c.status == PolicyStatus.REJECTED
            ),
            "rolled_back_changes": sum(
                1 for c in self._changes.values() if c.status == PolicyStatus.ROLLED_BACK
            ),
        }

    def _save_version(self, version: PolicyVersion) -> None:
        """Persist a version to disk with HMAC-SHA256 integrity check."""
        data = version.to_dict()
        serialized = json.dumps(data, sort_keys=True, default=str)
        signature = hmac.new(
            self._hmac_key.encode(), serialized.encode(), hashlib.sha256
        ).hexdigest()
        data["_hmac"] = signature

        filepath = self._storage / f"version_{version.version_id}.json"
        tmppath = filepath.with_suffix(".tmp")
        tmppath.write_text(json.dumps(data, sort_keys=True, indent=2, default=str), encoding="utf-8")
        _os.replace(str(tmppath), str(filepath))

    def _save_change(self, change: PolicyChange) -> None:
        """Persist a change to disk with HMAC-SHA256 integrity check."""
        data = change.to_dict()
        serialized = json.dumps(data, sort_keys=True, default=str)
        signature = hmac.new(
            self._hmac_key.encode(), serialized.encode(), hashlib.sha256
        ).hexdigest()
        data["_hmac"] = signature

        filepath = self._storage / f"change_{change.change_id}.json"
        tmppath = filepath.with_suffix(".tmp")
        tmppath.write_text(json.dumps(data, sort_keys=True, indent=2, default=str), encoding="utf-8")
        _os.replace(str(tmppath), str(filepath))
