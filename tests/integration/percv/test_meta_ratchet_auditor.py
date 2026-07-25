"""P5.1 MetaRatchetAuditor tests + ratchet freeze zone verification.

Validates:
- Config changes to immutables are blocked
- Trigger threshold relaxation is blocked
- Ratchet source files are protected from recursive evolution
- Baseline regression is blocked
- Freeze zone and RED_LINE_FILES include ratchet components
"""

from __future__ import annotations

import pytest

from maref.evolution.constitution_harness import ConstitutionHarness
from maref.integration.percv.meta_ratchet_auditor import (
    MetaRatchetAuditor,
    RATCHET_SOURCE_FILES,
)
from maref.recursive.rule_freeze_zone import ALL_FROZEN, FROZEN_TARGETS


class TestConfigChangeAudit:
    def test_constitutional_immutable_blocked(self) -> None:
        auditor = MetaRatchetAuditor()
        v = auditor.audit_config_change("branch_prefix", "main", "feature")
        assert v.blocked is True
        assert "constitutional" in v.reason

    def test_configurational_immutable_blocked(self) -> None:
        auditor = MetaRatchetAuditor()
        v = auditor.audit_config_change("TRIGGER_CONDITIONS", {}, {"new": True})
        assert v.blocked is True
        assert "configurational" in v.reason

    def test_trigger_threshold_relaxation_blocked(self) -> None:
        auditor = MetaRatchetAuditor()
        old = {"threshold": 5, "cooldown_rounds": 20}
        new = {"threshold": 10, "cooldown_rounds": 20}
        v = auditor.audit_config_change(
            "TRIGGER_CONDITIONS.consecutive_discards", old, new
        )
        assert v.blocked is True
        assert "threshold relaxed" in v.reason

    def test_cooldown_decrease_blocked(self) -> None:
        auditor = MetaRatchetAuditor()
        old = {"threshold": 5, "cooldown_rounds": 20}
        new = {"threshold": 5, "cooldown_rounds": 5}
        v = auditor.audit_config_change("TRIGGER_CONDITIONS.test", old, new)
        assert v.blocked is True

    def test_non_meta_ratchet_source_warning(self) -> None:
        auditor = MetaRatchetAuditor()
        v = auditor.audit_config_change(
            "some_key", 1, 2, source="recursive_evolution"
        )
        assert v.warning is True
        assert v.blocked is False

    def test_meta_ratchet_source_allowed(self) -> None:
        auditor = MetaRatchetAuditor()
        v = auditor.audit_config_change("some_key", 1, 2, source="meta_ratchet")
        assert v.blocked is False
        assert v.warning is False


class TestFileChangeAudit:
    def test_ratchet_file_blocked_from_evolution(self) -> None:
        auditor = MetaRatchetAuditor()
        v = auditor.audit_file_change(
            "src/maref/integration/percv/meta_ratchet.py"
        )
        assert v.blocked is True
        assert "protected" in v.reason

    def test_ratchet_bridge_blocked(self) -> None:
        auditor = MetaRatchetAuditor()
        v = auditor.audit_file_change(
            "src/maref/integration/percv/ratchet_bridge.py"
        )
        assert v.blocked is True

    def test_auditor_file_blocked(self) -> None:
        auditor = MetaRatchetAuditor()
        v = auditor.audit_file_change(
            "src/maref/integration/percv/meta_ratchet_auditor.py"
        )
        assert v.blocked is True

    def test_non_ratchet_file_allowed(self) -> None:
        auditor = MetaRatchetAuditor()
        v = auditor.audit_file_change("src/maref/some_other.py")
        assert v.blocked is False
        assert v.warning is False

    def test_manual_ratchet_file_warning(self) -> None:
        auditor = MetaRatchetAuditor()
        v = auditor.audit_file_change(
            "src/maref/integration/percv/meta_ratchet.py", source="manual"
        )
        assert v.blocked is False
        assert v.warning is True


class TestBaselineAudit:
    def test_baseline_regression_blocked(self) -> None:
        auditor = MetaRatchetAuditor()
        v = auditor.audit_baseline(0.85, 0.80)
        assert v.blocked is True
        assert "regression" in v.reason

    def test_baseline_improvement_allowed(self) -> None:
        auditor = MetaRatchetAuditor()
        v = auditor.audit_baseline(0.80, 0.85)
        assert v.blocked is False

    def test_baseline_maintained_allowed(self) -> None:
        auditor = MetaRatchetAuditor()
        v = auditor.audit_baseline(0.85, 0.85)
        assert v.blocked is False


class TestAuditLog:
    def test_log_accumulates(self) -> None:
        auditor = MetaRatchetAuditor()
        auditor.audit_config_change("some_key", 1, 2, source="meta_ratchet")
        auditor.audit_file_change("meta_ratchet.py")
        assert auditor.audit_count == 2
        assert auditor.blocked_count == 1

    def test_get_audit_log(self) -> None:
        auditor = MetaRatchetAuditor()
        auditor.audit_baseline(0.9, 0.8)
        log = auditor.get_audit_log()
        assert len(log) == 1
        assert log[0]["type"] == "baseline"
        assert log[0]["blocked"] is True


class TestFreezeZoneExtension:
    def test_ratchet_protection_in_frozen_targets(self) -> None:
        assert "ratchet_protection" in FROZEN_TARGETS

    def test_ratchet_keys_in_all_frozen(self) -> None:
        assert "MetaRatchet" in ALL_FROZEN
        assert "best_score" in ALL_FROZEN
        assert "CONSTITUTIONAL_IMMUTABLES" in ALL_FROZEN

    def test_red_line_files_include_ratchet(self) -> None:
        assert any(
            "meta_ratchet.py" in f for f in ConstitutionHarness.RED_LINE_FILES
        )
        assert any(
            "ratchet_bridge.py" in f for f in ConstitutionHarness.RED_LINE_FILES
        )
        assert any(
            "meta_ratchet_auditor.py" in f
            for f in ConstitutionHarness.RED_LINE_FILES
        )

    def test_ratchet_source_files_set(self) -> None:
        assert "meta_ratchet.py" in RATCHET_SOURCE_FILES
        assert "ratchet_bridge.py" in RATCHET_SOURCE_FILES
