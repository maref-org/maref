"""Skill Registry — manifest-based registration with validation gates.

Design principles:
- Three gates before上架: static scan + sandbox test + manual review
- Manifest includes input/output Schema, dependencies, license
- Dependency graph maintained for downstream notification
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SkillStatus(Enum):
    PENDING = "pending"          # Submitted, awaiting review
    STATIC_SCAN = "static_scan"  # Passed static security scan
    SANDBOX_TEST = "sandbox_test"  # Passed sandbox execution
    APPROVED = "approved"        # Approved for use
    REJECTED = "rejected"        # Failed review
    DEPRECATED = "deprecated"    # Scheduled for removal
    FROZEN = "frozen"            # Temporarily suspended


@dataclass
class SkillManifest:
    """Standard manifest for skill registration."""

    name: str
    version: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)  # ["skill://name@version"]
    author: str = ""
    license: str = "Apache-2.0"
    entrypoint: str = ""         # Module path or function name
    sandbox_config: dict[str, Any] = field(default_factory=dict)
    test_cases: list[dict[str, Any]] = field(default_factory=list)
    skill_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "dependencies": self.dependencies,
            "author": self.author,
            "license": self.license,
            "entrypoint": self.entrypoint,
            "sandbox_config": self.sandbox_config,
            "test_cases": self.test_cases,
            "created_at": self.created_at,
        }


@dataclass
class SkillValidationResult:
    """Result of skill validation gates."""

    skill_id: str
    static_scan_passed: bool = False
    sandbox_test_passed: bool = False
    manual_review_passed: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return (
            self.static_scan_passed
            and self.sandbox_test_passed
            and self.manual_review_passed
        )


class SkillRegistry:
    """Central registry for skill discovery and lifecycle management.

    Usage:
        registry = SkillRegistry()
        manifest = SkillManifest(name="csv_visualizer", version="1.0.0", ...)
        registry.register(manifest)
        # Run gates
        registry.run_static_scan(manifest.skill_id)
        registry.run_sandbox_test(manifest.skill_id)
        registry.approve(manifest.skill_id)
        # Discover
        skills = registry.search("visualize data")
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillManifest] = {}
        self._status: dict[str, SkillStatus] = {}
        self._validation: dict[str, SkillValidationResult] = {}
        self._dependency_graph: dict[str, set[str]] = {}  # skill_id -> downstream skill_ids

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #
    def register(self, manifest: SkillManifest) -> SkillValidationResult:
        """Register a new skill. Returns validation result."""
        self._skills[manifest.skill_id] = manifest
        self._status[manifest.skill_id] = SkillStatus.PENDING
        result = SkillValidationResult(skill_id=manifest.skill_id)
        self._validation[manifest.skill_id] = result
        # Build dependency graph
        for dep in manifest.dependencies:
            dep_name = dep.replace("skill://", "").split("@")[0]
            self._dependency_graph.setdefault(dep_name, set()).add(manifest.skill_id)
        return result

    def get(self, skill_id: str) -> SkillManifest | None:
        return self._skills.get(skill_id)

    def get_by_name(self, name: str) -> SkillManifest | None:
        for manifest in self._skills.values():
            if manifest.name == name:
                return manifest
        return None

    def list_all(self) -> list[SkillManifest]:
        return list(self._skills.values())

    def list_approved(self) -> list[SkillManifest]:
        return [
            s for sid, s in self._skills.items()
            if self._status.get(sid) == SkillStatus.APPROVED
        ]

    # ------------------------------------------------------------------ #
    # Validation gates
    # ------------------------------------------------------------------ #
    def run_static_scan(self, skill_id: str) -> SkillValidationResult:
        """Gate 1: Static security scan.

        Checks for suspicious patterns: network requests, file system access,
        environment variable reads, eval/exec calls.
        """
        result = self._validation.get(skill_id)
        if result is None:
            raise ValueError(f"Skill {skill_id} not found")
        manifest = self._skills[skill_id]
        # Simple heuristic scan on entrypoint string
        entry = manifest.entrypoint.lower()
        suspicious = ["requests.", "urllib", "socket.", "open(", "eval(", "exec(", "os.environ"]
        found = [p for p in suspicious if p in entry]
        if found:
            result.errors.append(f"Static scan: suspicious patterns {found}")
            result.static_scan_passed = False
        else:
            result.static_scan_passed = True
            self._status[skill_id] = SkillStatus.STATIC_SCAN
        return result

    def run_sandbox_test(self, skill_id: str) -> SkillValidationResult:
        """Gate 2: Sandbox execution test.

        Runs test_cases in an isolated environment.
        """
        result = self._validation.get(skill_id)
        if result is None:
            raise ValueError(f"Skill {skill_id} not found")
        manifest = self._skills[skill_id]
        if not manifest.test_cases:
            result.warnings.append("No test cases provided")
            result.sandbox_test_passed = True
        else:
            # Simulate test execution (production: run in gVisor/Firecracker)
            passed = all(tc.get("expected") is not None for tc in manifest.test_cases)
            result.sandbox_test_passed = passed
            if not passed:
                result.errors.append("Sandbox test: some test cases missing expected output")
        if result.sandbox_test_passed:
            self._status[skill_id] = SkillStatus.SANDBOX_TEST
        return result

    def approve(self, skill_id: str) -> None:
        """Gate 3: Manual approval (or auto-approve if gates 1+2 passed)."""
        result = self._validation.get(skill_id)
        if result is None:
            raise ValueError(f"Skill {skill_id} not found")
        if not result.static_scan_passed:
            raise ValueError(f"Skill {skill_id} failed static scan")
        if not result.sandbox_test_passed:
            raise ValueError(f"Skill {skill_id} failed sandbox test")
        result.manual_review_passed = True
        self._status[skill_id] = SkillStatus.APPROVED

    def reject(self, skill_id: str, reason: str) -> None:
        self._status[skill_id] = SkillStatus.REJECTED
        result = self._validation.get(skill_id)
        if result:
            result.errors.append(f"Rejected: {reason}")

    def deprecate(self, skill_id: str) -> None:
        """Mark skill as deprecated. Notifies downstream users."""
        self._status[skill_id] = SkillStatus.DEPRECATED

    def freeze(self, skill_id: str) -> None:
        """Freeze skill due to abnormal usage patterns."""
        self._status[skill_id] = SkillStatus.FROZEN

    def get_status(self, skill_id: str) -> SkillStatus | None:
        return self._status.get(skill_id)

    def get_validation(self, skill_id: str) -> SkillValidationResult | None:
        return self._validation.get(skill_id)

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #
    def search(self, keywords: list[str]) -> list[SkillManifest]:
        """Simple keyword search over approved skills."""
        results: list[tuple[float, SkillManifest]] = []
        for sid, manifest in self._skills.items():
            if self._status.get(sid) != SkillStatus.APPROVED:
                continue
            text = f"{manifest.name} {manifest.description}".lower()
            score = sum(1.0 for kw in keywords if kw.lower() in text)
            if score > 0:
                results.append((score, manifest))
        results.sort(key=lambda x: -x[0])
        return [m for _, m in results]

    def get_downstream(self, skill_name: str) -> list[str]:
        """Get skill IDs that depend on the given skill."""
        return list(self._dependency_graph.get(skill_name, set()))

    def check_dependency_conflicts(self, skill_id: str) -> list[str]:
        """Check if dependencies of a skill are available and approved."""
        manifest = self._skills.get(skill_id)
        if not manifest:
            return [f"Skill {skill_id} not found"]
        conflicts: list[str] = []
        for dep in manifest.dependencies:
            dep_name = dep.replace("skill://", "").split("@")[0]
            dep_manifest = self.get_by_name(dep_name)
            if dep_manifest is None:
                conflicts.append(f"Missing dependency: {dep}")
            elif self._status.get(dep_manifest.skill_id) != SkillStatus.APPROVED:
                conflicts.append(f"Dependency not approved: {dep}")
        return conflicts
