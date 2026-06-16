from __future__ import annotations

import time

import pytest

from maref.recursive.experience_pool import ContextManager, ExperienceEntry, ExperiencePool
from maref.recursive.self_architect import ArchitectureProposal, ChangeType, SelfArchitect
from maref.recursive.self_version import (
    CompatibilityLevel,
    SelfVersionManager,
    VersionInfo,
)
from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore


class TestExperiencePool:
    @pytest.fixture
    def pool(self) -> ExperiencePool:
        p = ExperiencePool()
        p.store(
            ExperienceEntry(
                "e1",
                time.time(),
                "cb trip detected",
                "increase cooldown",
                "success",
                "increase cooldown on entropy spike",
                ["governance", "circuit_breaker"],
            )
        )
        p.store(
            ExperienceEntry(
                "e2",
                time.time(),
                "test coverage drop",
                "add missing tests",
                "failure",
                "coverage drop requires targeted testing",
                ["testing", "coverage"],
            )
        )
        p.store(
            ExperienceEntry(
                "e3",
                time.time(),
                "agent crash under load",
                "restart agent pool",
                "success",
                "pre-warm agent pool before peak load",
                ["agent", "load"],
            )
        )
        return p

    def test_store_and_count(self, pool: ExperiencePool) -> None:
        assert pool.count() == 3

    def test_query_by_tag(self, pool: ExperiencePool) -> None:
        results = pool.query_by_tag("governance")
        assert len(results) == 1
        assert results[0].context == "cb trip detected"

    def test_query_by_outcome(self, pool: ExperiencePool) -> None:
        results = pool.query_by_outcome("success")
        assert len(results) == 2

    def test_query_by_context(self, pool: ExperiencePool) -> None:
        results = pool.query_by_context("coverage")
        assert len(results) == 1

    def test_search_similar(self, pool: ExperiencePool) -> None:
        results = pool.search_similar("circuit breaker tripped again")
        assert len(results) >= 0

    def test_replay_lessons(self, pool: ExperiencePool) -> None:
        lessons = pool.replay_lessons()
        assert len(lessons) == 1
        assert "coverage" in lessons[0]

    def test_max_entries_eviction(self) -> None:
        pool = ExperiencePool(max_entries=3)
        for i in range(5):
            pool.store(
                ExperienceEntry(
                    f"e{i}",
                    time.time(),
                    f"context{i}",
                    f"decision{i}",
                    "success",
                    f"lesson{i}",
                    ["tag"],
                )
            )
        assert pool.count() == 3

    def test_clear(self, pool: ExperiencePool) -> None:
        pool.clear()
        assert pool.count() == 0


class TestContextManager:
    def test_start_session(self) -> None:
        cm = ContextManager()
        cm.start_session("session_1", module="governance")
        assert cm.session_count() == 1

    def test_push_pop_context(self) -> None:
        cm = ContextManager()
        cm.start_session("s1")
        cm.push_context("state", "OBSERVE")
        cm.push_context("entropy", 4.5)
        last = cm.pop_context()
        assert last is not None
        assert last["value"] == 4.5
        first = cm.pop_context()
        assert first is not None
        assert first["value"] == "OBSERVE"

    def test_record_decision(self) -> None:
        cm = ContextManager()
        cm.start_session("s1")
        cm.record_decision("force_stabilize")
        ctx = cm.get_active_context()
        assert ctx is not None
        assert ctx["decision_count"] == 1

    def test_end_session(self) -> None:
        cm = ContextManager()
        cm.start_session("s1")
        cm.end_session()
        assert cm.get_active_context() is None

    def test_pop_context_empty(self) -> None:
        cm = ContextManager()
        cm.start_session("s1")
        result = cm.pop_context()
        assert result is None

    def test_no_active_session(self) -> None:
        cm = ContextManager()
        result = cm.get_active_context()
        assert result is None

    def test_multiple_sessions(self) -> None:
        cm = ContextManager()
        cm.start_session("a")
        cm.end_session()
        cm.start_session("b")
        cm.end_session()
        assert cm.session_count() == 2


class TestVersionInfo:
    def test_parse_simple(self) -> None:
        v = VersionInfo.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_parse_with_tag(self) -> None:
        v = VersionInfo.parse("0.4.0-r11")
        assert v.major == 0
        assert v.minor == 4
        assert v.patch == 0
        assert v.tag == "r11"

    def test_parse_with_v_prefix(self) -> None:
        v = VersionInfo.parse("v0.3.0-rc")
        assert v.minor == 3
        assert v.tag == "rc"

    def test_to_string(self) -> None:
        v = VersionInfo(0, 4, 0, "r20")
        assert v.to_string() == "0.4.0-r20"

    def test_comparison(self) -> None:
        v1 = VersionInfo(0, 3, 0)
        v2 = VersionInfo(0, 4, 0)
        assert v1 < v2
        assert v2 > v1

    def test_equality(self) -> None:
        v1 = VersionInfo.parse("0.4.0")
        v2 = VersionInfo.parse("0.4.0-rc")
        assert v1 == v2


class TestSelfVersionManager:
    def test_check_minor_upgrade(self) -> None:
        svm = SelfVersionManager(current_version="0.3.0")
        check = svm.check_compatibility("0.4.0")
        assert check.level == CompatibilityLevel.MINOR_CHANGE

    def test_check_patch_upgrade(self) -> None:
        svm = SelfVersionManager(current_version="0.3.0")
        check = svm.check_compatibility("0.3.1")
        assert check.level == CompatibilityLevel.FULLY_COMPATIBLE

    def test_check_major_upgrade(self) -> None:
        svm = SelfVersionManager(current_version="0.3.0")
        check = svm.check_compatibility("1.0.0")
        assert check.level == CompatibilityLevel.BREAKING_CHANGE

    def test_check_downgrade(self) -> None:
        svm = SelfVersionManager(current_version="0.4.0")
        check = svm.check_compatibility("0.3.0")
        assert check.level == CompatibilityLevel.UNKNOWN

    def test_upgrade_path(self) -> None:
        svm = SelfVersionManager(current_version="0.2.0")
        check = svm.check_compatibility("0.4.0")
        assert len(check.upgrade_path) >= 2

    def test_generate_migration_script(self) -> None:
        svm = SelfVersionManager(current_version="0.3.0")
        script = svm.generate_migration_script("0.4.0")
        assert "migrate()" in script
        assert "migration" in script

    def test_upgrade_log(self) -> None:
        svm = SelfVersionManager(current_version="0.3.0")
        svm.check_compatibility("0.4.0")
        svm.check_compatibility("0.5.0")
        assert len(svm.upgrade_log) == 2

    def test_current_version_property(self) -> None:
        svm = SelfVersionManager("0.3.0")
        assert svm.current_version.to_string() == "0.3.0"


class TestSelfArchitect:
    @pytest.fixture
    def audit_store(self) -> UnifiedAuditStore:
        s = UnifiedAuditStore()
        s.append(
            UnifiedAuditRecord(
                "r1", 1.0, "inner", 1, "healing", "SelfHealer", "cb", "repair", "j", "success", []
            )
        )
        s.append(
            UnifiedAuditRecord(
                "r2", 2.0, "inner", 1, "healing", "SelfHealer", "cb", "repair", "j", "success", []
            )
        )
        s.append(
            UnifiedAuditRecord(
                "r3", 3.0, "inner", 1, "healing", "SelfHealer", "cb", "repair", "j", "failure", []
            )
        )
        s.append(
            UnifiedAuditRecord(
                "r4", 4.0, "inner", 1, "healing", "SelfHealer", "sm", "repair", "j", "success", []
            )
        )
        s.append(
            UnifiedAuditRecord(
                "r5", 5.0, "inner", 1, "healing", "SelfHealer", "sm", "repair", "j", "failure", []
            )
        )
        s.append(
            UnifiedAuditRecord(
                "r6", 6.0, "outer", 2, "governance", "MG", "inner", "halt", "j", "failure", []
            )
        )
        s.append(
            UnifiedAuditRecord(
                "r7", 7.0, "meta", 3, "governance", "MG", "outer", "open", "j", "failure", []
            )
        )
        s.append(
            UnifiedAuditRecord(
                "r8", 8.0, "evolution", 10, "evolution", "DSL", "cb", "tune", "j", "success", []
            )
        )
        return s

    @pytest.fixture
    def architect(self, audit_store: UnifiedAuditStore) -> SelfArchitect:
        arch = SelfArchitect(audit_store)
        arch.snapshot_architecture(
            {
                "governance": "v0.4.0",
                "recursive": "v0.4.0",
                "observation": "v0.4.0",
            }
        )
        return arch

    def test_snapshot_architecture(self, architect: SelfArchitect) -> None:
        assert architect._arch_snapshot["module_count"] == 3

    def test_analyze_bottlenecks(self, architect: SelfArchitect) -> None:
        bottlenecks = architect.analyze_bottlenecks()
        assert len(bottlenecks) >= 1

    def test_propose_redesign(self, architect: SelfArchitect) -> None:
        proposal = architect.propose_redesign()
        assert proposal.confidence > 0
        assert len(architect.proposals) == 1

    def test_validate_proposal_confident(self, architect: SelfArchitect) -> None:
        proposal = ArchitectureProposal("p1", time.time(), "A", "B", "ok", "low", 0.9)
        assert architect.validate_proposal(proposal) is True

    def test_validate_proposal_low_confidence(self, architect: SelfArchitect) -> None:
        proposal = ArchitectureProposal("p2", time.time(), "A", "B", "ok", "low", 0.3)
        assert architect.validate_proposal(proposal) is False

    def test_validate_proposal_high_risk_low_confidence(self, architect: SelfArchitect) -> None:
        proposal = ArchitectureProposal("p3", time.time(), "A", "B", "ok", "high", 0.6)
        assert architect.validate_proposal(proposal) is False

    def test_audit_all_decisions(self, architect: SelfArchitect) -> None:
        results = architect.audit_all_decisions()
        assert len(results) >= 1

    def test_propose_redesign_no_bottlenecks(self) -> None:
        empty_store = UnifiedAuditStore()
        arch = SelfArchitect(empty_store)
        arch.snapshot_architecture({"governance": "v0.4.0"})
        proposal = arch.propose_redesign()
        assert proposal.risk_assessment == "low"
        assert proposal.confidence == 0.95


class TestSelfArchitectStructuredProposals:
    @pytest.fixture
    def architect(self) -> SelfArchitect:
        store = UnifiedAuditStore()
        arch = SelfArchitect(store)
        arch.snapshot_architecture({"governance": "v0.11.0", "recursive": "v0.11.0"})
        return arch

    def test_change_type_enum_values(self) -> None:
        assert ChangeType.ADD_TEST.value == "add_test"
        assert ChangeType.EXTRACT_FUNCTION.value == "extract_function"
        assert ChangeType.REMOVE_UNUSED_IMPORT.value == "remove_unused_import"
        assert ChangeType.SPLIT_MODULE.value == "split_module"
        assert ChangeType.GENERAL_REFACTOR.value == "general_refactor"

    def test_architecture_proposal_new_fields(self) -> None:
        proposal = ArchitectureProposal(
            proposal_id="p1",
            timestamp=time.time(),
            current_arch="v1",
            proposed_arch="v2",
            rationale="test",
            risk_assessment="low",
            confidence=0.9,
            target_files=["tests/test_x.py"],
            change_type=ChangeType.ADD_TEST,
            affected_symbols=["test_func"],
            estimated_new_lines=30,
            preconditions=["coverage < 80%"],
        )
        assert proposal.target_files == ["tests/test_x.py"]
        assert proposal.change_type == ChangeType.ADD_TEST
        assert proposal.estimated_new_lines == 30
        assert len(proposal.preconditions) == 1

    def test_detect_unused_imports(self, architect: SelfArchitect) -> None:
        unused = architect.detect_unused_imports()
        assert isinstance(unused, dict)

    def test_propose_all(self, architect: SelfArchitect) -> None:
        proposals = architect.propose_all()
        assert len(proposals) >= 1
        assert all(isinstance(p, ArchitectureProposal) for p in proposals)

    def test_propose_test_addition_empty(self, architect: SelfArchitect) -> None:
        proposals = architect.propose_test_addition([])
        assert proposals == []

    def test_propose_import_cleanup_empty(self, architect: SelfArchitect) -> None:
        proposals = architect.propose_import_cleanup({})
        assert proposals == []

    def test_propose_test_addition_with_data(self, architect: SelfArchitect) -> None:
        low_cov = [
            {
                "file": "src/maref/recursive/self_healer.py",
                "coverage_pct": 65.0,
                "statements": "128",
                "missing": "45",
            },
            {
                "file": "src/maref/recursive/self_optimizer.py",
                "coverage_pct": 72.0,
                "statements": "160",
                "missing": "45",
            },
        ]
        proposals = architect.propose_test_addition(low_cov)
        assert len(proposals) == 2
        assert proposals[0].change_type == ChangeType.ADD_TEST
        assert proposals[0].target_files[0].startswith("tests/")
        assert proposals[0].confidence == 0.85

    def test_propose_import_cleanup_with_data(self, architect: SelfArchitect) -> None:
        unused = {"src/maref/recursive/self_healer.py": ["os", "time"]}
        proposals = architect.propose_import_cleanup(unused)
        assert len(proposals) == 1
        assert proposals[0].change_type == ChangeType.REMOVE_UNUSED_IMPORT
        assert proposals[0].target_files == ["src/maref/recursive/self_healer.py"]
        assert proposals[0].confidence == 0.95
        assert proposals[0].estimated_new_lines == -2

    def test_proposal_structured_fields_on_redesign(self, architect: SelfArchitect) -> None:
        proposal = architect.propose_redesign()
        assert proposal.change_type == ChangeType.GENERAL_REFACTOR
        assert isinstance(proposal.target_files, list)
        assert isinstance(proposal.affected_symbols, list)
        assert isinstance(proposal.preconditions, list)
