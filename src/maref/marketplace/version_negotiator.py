"""Version Negotiator — schema version compatibility for skill calls.

Rules:
- v2 backward compatible → direct call
- v2 not compatible → return VERSION_MISMATCH
- v2发布后v1继续服务90天强制向后兼容期
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Compatibility(Enum):
    COMPATIBLE = "compatible"  # Direct call
    BACKWARD_COMPATIBLE = "backward"  # v1 client → v2 skill, with adapter
    INCOMPATIBLE = "incompatible"  # VERSION_MISMATCH
    UNKNOWN = "unknown"


@dataclass
class VersionNegotiationResult:
    skill_id: str
    requested_version: str
    available_version: str
    compatibility: Compatibility
    message: str = ""
    adapter_needed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "requested_version": self.requested_version,
            "available_version": self.available_version,
            "compatibility": self.compatibility.value,
            "message": self.message,
            "adapter_needed": self.adapter_needed,
        }


class VersionNegotiator:
    """Negotiate schema versions between agent and skill.

    Usage:
        vn = VersionNegotiator()
        result = vn.negotiate("skill-123", "1.0.0", "2.0.0")
        if result.compatibility == Compatibility.INCOMPATIBLE:
            raise VersionMismatch(result.message)
    """

    BACKWARD_COMPATIBLE_DAYS = 90

    def __init__(self) -> None:
        self._version_history: dict[str, list[tuple[str, float]]] = {}
        # skill_id -> [(version, release_timestamp), ...]

    def register_version(self, skill_id: str, version: str, released_at: float) -> None:
        """Record a version release."""
        self._version_history.setdefault(skill_id, []).append((version, released_at))

    def negotiate(
        self,
        skill_id: str,
        requested_version: str,
        available_version: str,
    ) -> VersionNegotiationResult:
        """Check compatibility between requested and available versions."""
        if requested_version == available_version:
            return VersionNegotiationResult(
                skill_id=skill_id,
                requested_version=requested_version,
                available_version=available_version,
                compatibility=Compatibility.COMPATIBLE,
                message="Exact version match",
            )

        req_major, req_minor, _ = self._parse_semver(requested_version)
        avail_major, avail_minor, _ = self._parse_semver(available_version)

        # Same major, higher minor → backward compatible
        if req_major == avail_major and avail_minor >= req_minor:
            return VersionNegotiationResult(
                skill_id=skill_id,
                requested_version=requested_version,
                available_version=available_version,
                compatibility=Compatibility.BACKWARD_COMPATIBLE,
                message=f"v{available_version} backward compatible with v{requested_version}",
                adapter_needed=False,
            )

        # Major version bump → check if old version still within 90-day window
        if req_major < avail_major:
            if self._is_within_grace_period(skill_id, requested_version):
                return VersionNegotiationResult(
                    skill_id=skill_id,
                    requested_version=requested_version,
                    available_version=available_version,
                    compatibility=Compatibility.BACKWARD_COMPATIBLE,
                    message=f"v{requested_version} still in {self.BACKWARD_COMPATIBLE_DAYS}-day grace period",
                    adapter_needed=True,
                )
            return VersionNegotiationResult(
                skill_id=skill_id,
                requested_version=requested_version,
                available_version=available_version,
                compatibility=Compatibility.INCOMPATIBLE,
                message=f"VERSION_MISMATCH: v{requested_version} no longer supported",
            )

        # Requested newer than available
        return VersionNegotiationResult(
            skill_id=skill_id,
            requested_version=requested_version,
            available_version=available_version,
            compatibility=Compatibility.INCOMPATIBLE,
            message=f"Skill v{available_version} is older than requested v{requested_version}",
        )

    def _parse_semver(self, version: str) -> tuple[int, int, int]:
        """Parse simple semver string."""
        parts = version.lstrip("v").split(".")
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return major, minor, patch

    def _is_within_grace_period(self, skill_id: str, version: str) -> bool:
        import time

        history = self._version_history.get(skill_id, [])
        for v, released_at in history:
            if v == version:
                return (time.time() - released_at) < self.BACKWARD_COMPATIBLE_DAYS * 86400
        return False

    def get_supported_versions(self, skill_id: str) -> list[str]:
        """List all versions still within grace period."""
        import time

        history = self._version_history.get(skill_id, [])
        cutoff = time.time() - self.BACKWARD_COMPATIBLE_DAYS * 86400
        return [v for v, released_at in history if released_at >= cutoff]
