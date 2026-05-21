from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CompatibilityLevel(Enum):
    FULLY_COMPATIBLE = "fully_compatible"
    MINOR_CHANGE = "minor_change"
    BREAKING_CHANGE = "breaking_change"
    UNKNOWN = "unknown"


@dataclass
class VersionInfo:
    major: int
    minor: int
    patch: int
    tag: str = ""
    build_id: str = ""

    @classmethod
    def parse(cls, version_str: str) -> VersionInfo:
        parts = version_str.replace("v", "").split("-")[0].split(".")
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        tag = version_str.split("-")[1] if "-" in version_str else ""
        return cls(major=major, minor=minor, patch=patch, tag=tag)

    def to_string(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.tag}" if self.tag else base

    def __lt__(self, other: VersionInfo) -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VersionInfo):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)


@dataclass
class CompatibilityCheck:
    source_version: VersionInfo
    target_version: VersionInfo
    level: CompatibilityLevel
    details: str
    upgrade_path: list[str] = field(default_factory=list)


class SelfVersionManager:
    _COMPATIBILITY_MATRIX = {
        ("0.2.0", "0.3.0"): CompatibilityLevel.MINOR_CHANGE,
        ("0.3.0", "0.4.0"): CompatibilityLevel.MINOR_CHANGE,
    }

    def __init__(self, current_version: str = "0.4.0-r17") -> None:
        self._current = VersionInfo.parse(current_version)
        self._upgrade_log: list[CompatibilityCheck] = []

    def check_compatibility(self, target_version: str) -> CompatibilityCheck:
        target = VersionInfo.parse(target_version)

        if target < self._current:
            return CompatibilityCheck(
                source_version=self._current,
                target_version=target,
                level=CompatibilityLevel.UNKNOWN,
                details="downgrade not supported",
            )

        level = CompatibilityLevel.FULLY_COMPATIBLE
        if target.major > self._current.major:
            level = CompatibilityLevel.BREAKING_CHANGE
        elif target.minor > self._current.minor:
            level = CompatibilityLevel.MINOR_CHANGE
        elif target.patch > self._current.patch:
            level = CompatibilityLevel.FULLY_COMPATIBLE

        upgrade_path = self._plan_upgrade_path(self._current, target)

        check = CompatibilityCheck(
            source_version=self._current,
            target_version=target,
            level=level,
            details=self._describe_level(level),
            upgrade_path=upgrade_path,
        )
        self._upgrade_log.append(check)
        return check

    def propose_upgrade(self, version_str: str) -> CompatibilityCheck:
        return self.check_compatibility(version_str)

    def generate_migration_script(self, target_version: str) -> str:
        check = self.check_compatibility(target_version)
        if check.level == CompatibilityLevel.UNKNOWN:
            return "# ERROR: Cannot generate migration for unknown compatibility"

        steps = [
            "#!/usr/bin/env python3",
            f"# Auto-generated migration from {check.source_version.to_string()} to {check.target_version.to_string()}",
            f"# Compatibility level: {check.level.value}",
            "",
            "def migrate():",
        ]

        if check.level == CompatibilityLevel.BREAKING_CHANGE:
            steps.append("    print('WARNING: Breaking changes detected!')")
            steps.append("    print('  - API may have changed significantly')")
            steps.append("    print('  - Please review changelog before proceeding')")

        if check.level in (CompatibilityLevel.MINOR_CHANGE, CompatibilityLevel.BREAKING_CHANGE):
            steps.append("    update_version()")
            steps.append("    verify_compatibility()")

        steps.extend([
            "    print('Migration complete.')",
            "",
            "def update_version():",
            "    from pathlib import Path",
            "    import re",
            "    pp = Path('pyproject.toml')",
            "    content = pp.read_text()",
            f"    content = re.sub(r'version = \".*\"', 'version = \"{target_version}\"', content)",
            "    pp.write_text(content)",
            "",
            "def verify_compatibility():",
            "    import subprocess, sys",
            "    result = subprocess.run([sys.executable, '-m', 'pytest', '--tb=short', '-q'], capture_output=True, text=True)",
            "    if result.returncode != 0:",
            "        print('ERROR: Tests failed after migration!')",
            "        print(result.stdout[-500:])",
            "        sys.exit(1)",
            "    print('Verification passed.')",
            "",
            "if __name__ == '__main__':",
            "    migrate()",
        ])

        return "\n".join(steps)

    def _plan_upgrade_path(self, from_ver: VersionInfo, to_ver: VersionInfo) -> list[str]:
        path: list[str] = []
        current = VersionInfo(from_ver.major, from_ver.minor, from_ver.patch)

        while current < to_ver:
            if current.major < to_ver.major:
                next_ver = VersionInfo(current.major + 1, 0, 0)
                path.append(next_ver.to_string())
                current = next_ver
            elif current.minor < to_ver.minor:
                next_ver = VersionInfo(current.major, current.minor + 1, 0)
                path.append(next_ver.to_string())
                current = next_ver
            elif current.patch < to_ver.patch:
                next_ver = VersionInfo(current.major, current.minor, current.patch + 1)
                path.append(next_ver.to_string())
                current = next_ver
            else:
                break

        return path

    def _describe_level(self, level: CompatibilityLevel) -> str:
        descriptions = {
            CompatibilityLevel.FULLY_COMPATIBLE: "no breaking changes, safe to upgrade",
            CompatibilityLevel.MINOR_CHANGE: "minor API additions, backward compatible",
            CompatibilityLevel.BREAKING_CHANGE: "major API changes, requires manual review",
            CompatibilityLevel.UNKNOWN: "compatibility unknown",
        }
        return descriptions.get(level, "unknown")

    @property
    def current_version(self) -> VersionInfo:
        return self._current

    @property
    def upgrade_log(self) -> list[CompatibilityCheck]:
        return list(self._upgrade_log)
