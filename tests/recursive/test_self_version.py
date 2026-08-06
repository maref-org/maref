from __future__ import annotations

import pytest

from maref.recursive.self_version import (
    CompatibilityCheck,
    CompatibilityLevel,
    SelfVersionManager,
    VersionInfo,
)


class TestVersionInfo:
    def test_parse_basic_version(self) -> None:
        v = VersionInfo.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3
        assert v.tag == ""
        assert v.build_id == ""

    def test_parse_with_tag(self) -> None:
        v = VersionInfo.parse("1.2.3-rc1")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3
        assert v.tag == "rc1"

    def test_parse_with_v_prefix(self) -> None:
        v = VersionInfo.parse("v2.0.1")
        assert v.major == 2
        assert v.minor == 0
        assert v.patch == 1

    def test_to_string(self) -> None:
        v = VersionInfo(major=1, minor=2, patch=3)
        assert v.to_string() == "1.2.3"

    def test_to_string_with_tag(self) -> None:
        v = VersionInfo(major=1, minor=2, patch=3, tag="beta")
        assert v.to_string() == "1.2.3-beta"

    def test_lt_operator(self) -> None:
        v1 = VersionInfo.parse("1.2.3")
        v2 = VersionInfo.parse("2.0.0")
        assert v1 < v2
        assert not (v2 < v1)

    def test_lt_operator_same_major(self) -> None:
        v1 = VersionInfo.parse("1.2.3")
        v2 = VersionInfo.parse("1.3.0")
        assert v1 < v2

    def test_lt_operator_same_major_minor(self) -> None:
        v1 = VersionInfo.parse("1.2.3")
        v2 = VersionInfo.parse("1.2.4")
        assert v1 < v2

    def test_eq_operator(self) -> None:
        v1 = VersionInfo.parse("1.2.3")
        v2 = VersionInfo.parse("1.2.3")
        assert v1 == v2

    def test_eq_operator_different(self) -> None:
        v1 = VersionInfo.parse("1.2.3")
        v2 = VersionInfo.parse("1.2.4")
        assert not (v1 == v2)

    def test_eq_operator_wrong_type(self) -> None:
        v1 = VersionInfo.parse("1.2.3")
        assert not (v1 == "1.2.3")


class TestSelfVersionManager:
    def test_init_default(self) -> None:
        manager = SelfVersionManager()
        assert manager.current_version.major == 0
        assert manager.current_version.minor == 4
        assert manager.current_version.patch == 0
        assert manager.upgrade_log == []

    def test_init_custom_version(self) -> None:
        manager = SelfVersionManager("2.1.0")
        assert manager.current_version.major == 2
        assert manager.current_version.minor == 1
        assert manager.current_version.patch == 0

    def test_check_compatibility_patch_upgrade(self) -> None:
        manager = SelfVersionManager("1.2.3")
        check = manager.check_compatibility("1.2.4")
        assert check.source_version == VersionInfo.parse("1.2.3")
        assert check.target_version == VersionInfo.parse("1.2.4")
        assert check.level == CompatibilityLevel.FULLY_COMPATIBLE
        assert "safe to upgrade" in check.details
        assert len(manager.upgrade_log) == 1

    def test_check_compatibility_minor_upgrade(self) -> None:
        manager = SelfVersionManager("1.2.3")
        check = manager.check_compatibility("1.3.0")
        assert check.level == CompatibilityLevel.MINOR_CHANGE
        assert "minor API additions" in check.details

    def test_check_compatibility_major_upgrade(self) -> None:
        manager = SelfVersionManager("1.2.3")
        check = manager.check_compatibility("2.0.0")
        assert check.level == CompatibilityLevel.BREAKING_CHANGE
        assert "major API changes" in check.details

    def test_check_compatibility_downgrade(self) -> None:
        manager = SelfVersionManager("2.0.0")
        check = manager.check_compatibility("1.2.3")
        assert check.level == CompatibilityLevel.UNKNOWN
        assert "downgrade not supported" in check.details

    def test_check_compatibility_same_version(self) -> None:
        manager = SelfVersionManager("1.2.3")
        check = manager.check_compatibility("1.2.3")
        assert check.level == CompatibilityLevel.FULLY_COMPATIBLE
        assert check.upgrade_path == []

    def test_propose_upgrade(self) -> None:
        manager = SelfVersionManager("1.2.3")
        check = manager.propose_upgrade("1.3.0")
        assert check.level == CompatibilityLevel.MINOR_CHANGE
        assert len(manager.upgrade_log) == 1

    def test_generate_migration_script_patch(self) -> None:
        manager = SelfVersionManager("1.2.3")
        script = manager.generate_migration_script("1.2.4")
        assert "Auto-generated migration" in script
        assert "1.2.3" in script
        assert "1.2.4" in script
        assert "fully_compatible" in script

    def test_generate_migration_script_minor(self) -> None:
        manager = SelfVersionManager("1.2.3")
        script = manager.generate_migration_script("1.3.0")
        assert "minor_change" in script
        assert "update_version()" in script
        assert "verify_compatibility()" in script

    def test_generate_migration_script_major(self) -> None:
        manager = SelfVersionManager("1.2.3")
        script = manager.generate_migration_script("2.0.0")
        assert "breaking_change" in script
        assert "WARNING: Breaking changes detected!" in script

    def test_generate_migration_script_unknown(self) -> None:
        manager = SelfVersionManager("2.0.0")
        script = manager.generate_migration_script("1.2.3")
        assert "# ERROR: Cannot generate migration for unknown compatibility" in script

    def test_plan_upgrade_path_simple(self) -> None:
        manager = SelfVersionManager("1.2.3")
        from_ver = VersionInfo.parse("1.2.3")
        to_ver = VersionInfo.parse("1.2.5")
        path = manager._plan_upgrade_path(from_ver, to_ver)
        assert path == ["1.2.4", "1.2.5"]

    def test_plan_upgrade_path_minor(self) -> None:
        manager = SelfVersionManager("1.2.3")
        from_ver = VersionInfo.parse("1.2.3")
        to_ver = VersionInfo.parse("1.4.0")
        path = manager._plan_upgrade_path(from_ver, to_ver)
        assert path == ["1.3.0", "1.4.0"]

    def test_plan_upgrade_path_major(self) -> None:
        manager = SelfVersionManager("1.2.3")
        from_ver = VersionInfo.parse("1.2.3")
        to_ver = VersionInfo.parse("3.0.0")
        path = manager._plan_upgrade_path(from_ver, to_ver)
        assert path == ["2.0.0", "3.0.0"]

    def test_plan_upgrade_path_complex(self) -> None:
        manager = SelfVersionManager("1.2.3")
        from_ver = VersionInfo.parse("1.2.3")
        to_ver = VersionInfo.parse("2.1.2")
        path = manager._plan_upgrade_path(from_ver, to_ver)
        assert path == ["2.0.0", "2.1.0", "2.1.1", "2.1.2"]

    def test_describe_level(self) -> None:
        manager = SelfVersionManager()
        assert "safe to upgrade" in manager._describe_level(CompatibilityLevel.FULLY_COMPATIBLE)
        assert "minor API additions" in manager._describe_level(CompatibilityLevel.MINOR_CHANGE)
        assert "major API changes" in manager._describe_level(CompatibilityLevel.BREAKING_CHANGE)
        assert "compatibility unknown" in manager._describe_level(CompatibilityLevel.UNKNOWN)

    def test_upgrade_log_property(self) -> None:
        manager = SelfVersionManager("1.0.0")
        manager.check_compatibility("1.1.0")
        manager.check_compatibility("1.2.0")
        assert len(manager.upgrade_log) == 2
        assert all(isinstance(check, CompatibilityCheck) for check in manager.upgrade_log)