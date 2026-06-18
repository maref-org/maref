from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from maref.recursive.self_architect import (
    ArchitectureProposal,
    ChangeType,
    SelfArchitect,
)
from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore


class TestChangeType:
    def test_values(self) -> None:
        assert ChangeType.ADD_TEST.value == "add_test"
        assert ChangeType.EXTRACT_FUNCTION.value == "extract_function"
        assert ChangeType.REMOVE_UNUSED_IMPORT.value == "remove_unused_import"
        assert ChangeType.SPLIT_MODULE.value == "split_module"
        assert ChangeType.GENERAL_REFACTOR.value == "general_refactor"


class TestArchitectureProposal:
    def test_default_construction(self) -> None:
        p = ArchitectureProposal(
            proposal_id="p1",
            timestamp=100.0,
            current_arch="v1",
            proposed_arch="v2",
            rationale="test",
            risk_assessment="low",
            confidence=0.9,
        )
        assert p.proposal_id == "p1"
        assert p.confidence == 0.9
        assert p.coupling_metrics == {}
        assert p.target_files == []
        assert p.change_type == ChangeType.GENERAL_REFACTOR
        assert p.affected_symbols == []
        assert p.estimated_new_lines == 0
        assert p.preconditions == []


class TestSelfArchitect:
    def test_construction(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        assert sa._audit_store is store
        assert sa._proposals == []
        assert sa._arch_snapshot == {}
        assert sa.proposals == []

    def test_snapshot_architecture(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        modules = {"mod_a": {"path": "src/mod_a.py"}, "mod_b": {"path": "src/mod_b.py"}}
        snap = sa.snapshot_architecture(modules)
        assert snap["module_count"] == 2
        assert snap["modules"] == modules
        assert "timestamp" in snap
        assert sa._arch_snapshot["module_count"] == 2

    def test_analyze_bottlenecks_no_events(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        bottlenecks = sa.analyze_bottlenecks()
        assert bottlenecks == []

    def test_analyze_bottlenecks_with_high_failures(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        for _ in range(5):
            store.append(
                UnifiedAuditRecord(
                    record_id="r1",
                    timestamp=time.time(),
                    layer="inner",
                    round=1,
                    event_type="healing",
                    source_module="mod_x",
                    target_module="mod_y",
                    decision="rerun",
                    justification="fix",
                )
            )
        bottlenecks = sa.analyze_bottlenecks()
        assert len(bottlenecks) == 1
        assert bottlenecks[0]["module"] == "mod_x"
        assert bottlenecks[0]["heal_attempts"] == 5
        assert bottlenecks[0]["severity"] == "high"

    def test_analyze_bottlenecks_medium_severity(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        for _ in range(3):
            store.append(
                UnifiedAuditRecord(
                    record_id="r2",
                    timestamp=time.time(),
                    layer="inner",
                    round=1,
                    event_type="healing",
                    source_module="mod_z",
                    target_module="mod_w",
                    decision="rerun",
                    justification="fix",
                )
            )
        bottlenecks = sa.analyze_bottlenecks()
        assert len(bottlenecks) == 1
        assert bottlenecks[0]["severity"] == "medium"

    def test_analyze_low_coverage_exception(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = RuntimeError("no coverage")
            result = sa.analyze_low_coverage()
            assert result == []

    def test_analyze_low_coverage_parsing(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        # The parsing expects percentage to be the last column
        # Let's format it without the Missing column
        cov_output = (
            "Name                 Stmts   Miss  Cover\n"
            "----------------------------------------\n"
            "src/maref/core.py      100     50    50%\n"
            "src/maref/utils.py      50      5    90%\n"
            "----------------------------------------\n"
            "TOTAL                  150     55    63%\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=cov_output, stderr="")
            result = sa.analyze_low_coverage(threshold=80.0)
            assert len(result) == 1
            assert result[0]["file"] == "src/maref/core.py"
            assert result[0]["coverage_pct"] == 50.0

    def test_analyze_module_dependencies_nonexistent_dir(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        result = sa.analyze_module_dependencies(source_dir="/nonexistent_dir_xyz")
        assert result == {}

    @patch("maref.recursive.self_architect.Path")
    def test_analyze_module_dependencies_with_files(self, mock_path_cls: MagicMock) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)

        mock_path = MagicMock(spec=Path)
        mock_path_cls.return_value = mock_path
        mock_path.exists.return_value = True

        mock_file = MagicMock(spec=Path)
        mock_file.name = "core.py"
        mock_file.__str__.return_value = "src/maref/core.py"
        mock_file.read_text.return_value = "import os\nimport sys\n"
        mock_path.rglob.return_value = [mock_file]

        result = sa.analyze_module_dependencies(source_dir="src")
        assert len(result) >= 1

    def test_compute_coupling_metrics_empty(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        assert sa.compute_coupling_metrics({}) == {}

    def test_compute_coupling_metrics_basic(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        graph = {
            "mod_a": {"imports": ["mod_b", "mod_c"], "import_count": 2},
            "mod_b": {"imports": ["mod_c"], "import_count": 1},
            "mod_c": {"imports": ["os"], "import_count": 1},
        }
        metrics = sa.compute_coupling_metrics(graph)
        assert "mod_a" in metrics
        assert "mod_b" in metrics
        assert "mod_c" in metrics
        assert metrics["mod_a"]["fan_out"] == 2
        assert metrics["mod_a"]["fan_in"] == 0
        assert metrics["mod_b"]["fan_in"] == 1
        assert metrics["mod_c"]["fan_in"] == 2
        assert metrics["mod_a"]["instability"] == 1.0
        assert metrics["mod_c"]["instability"] == 0.0

    def test_detect_unused_imports_nonexistent_dir(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        result = sa.detect_unused_imports(source_dir="/nonexistent")
        assert result == {}

    def test_propose_test_addition_empty(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        proposals = sa.propose_test_addition([])
        assert proposals == []

    def test_propose_test_addition_with_modules(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        low_cov = [
            {"file": "src/maref/core.py", "coverage_pct": 45.0},
            {"file": "src/maref/utils.py", "coverage_pct": 30.0},
        ]
        proposals = sa.propose_test_addition(low_cov)
        assert len(proposals) == 2
        assert all(p.change_type == ChangeType.ADD_TEST for p in proposals)
        assert proposals[0].target_files == ["tests/maref/core_test.py"]
        assert proposals[0].confidence == 0.85
        assert proposals[0].estimated_new_lines == 30

    def test_propose_test_addition_missing_file_key(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        proposals = sa.propose_test_addition([{"coverage_pct": 50.0}])
        assert proposals == []

    def test_propose_import_cleanup_empty(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        proposals = sa.propose_import_cleanup({})
        assert proposals == []

    def test_propose_import_cleanup_with_unused(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        unused = {
            "src/maref/old.py": ["os", "sys"],
            "src/maref/dead.py": ["json", "math"],
        }
        proposals = sa.propose_import_cleanup(unused)
        assert len(proposals) == 2
        assert all(p.change_type == ChangeType.REMOVE_UNUSED_IMPORT for p in proposals)
        assert proposals[0].confidence == 0.95
        assert proposals[0].estimated_new_lines == -2

    def test_propose_redesign_no_bottlenecks(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        sa._arch_snapshot = {"module_count": 10}
        proposal = sa.propose_redesign()
        assert proposal.risk_assessment == "low"
        assert proposal.confidence == 0.95
        assert proposal.change_type == ChangeType.GENERAL_REFACTOR
        assert "No significant bottlenecks" in proposal.rationale

    def test_propose_redesign_with_bottlenecks(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        sa._arch_snapshot = {"module_count": 10}
        for _ in range(5):
            store.append(
                UnifiedAuditRecord(
                    record_id="r",
                    timestamp=time.time(),
                    layer="inner",
                    round=1,
                    event_type="healing",
                    source_module="bottleneck_mod",
                    target_module="t",
                    decision="rerun",
                    justification="fix",
                )
            )
        proposal = sa.propose_redesign()
        assert proposal.risk_assessment == "medium"
        assert proposal.confidence == 0.75

    def test_propose_redesign_many_bottlenecks(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        sa._arch_snapshot = {"module_count": 10}
        for mod in ("a", "b", "c"):
            for _ in range(3):
                store.append(
                    UnifiedAuditRecord(
                        record_id="r",
                        timestamp=time.time(),
                        layer="inner",
                        round=1,
                        event_type="healing",
                        source_module=mod,
                        target_module="t",
                        decision="rerun",
                        justification="fix",
                    )
                )
        proposal = sa.propose_redesign()
        assert proposal.risk_assessment == "high"
        assert proposal.confidence == 0.55

    def test_validate_proposal_low_confidence(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        p = ArchitectureProposal(
            proposal_id="p1",
            timestamp=time.time(),
            current_arch="v1",
            proposed_arch="v2",
            rationale="test",
            risk_assessment="low",
            confidence=0.3,
        )
        assert sa.validate_proposal(p) is False

    def test_validate_proposal_high_risk_low_confidence(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        p = ArchitectureProposal(
            proposal_id="p1",
            timestamp=time.time(),
            current_arch="v1",
            proposed_arch="v2",
            rationale="test",
            risk_assessment="high",
            confidence=0.6,
        )
        assert sa.validate_proposal(p) is False

    def test_validate_proposal_valid(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        p = ArchitectureProposal(
            proposal_id="p1",
            timestamp=time.time(),
            current_arch="v1",
            proposed_arch="v2",
            rationale="test",
            risk_assessment="medium",
            confidence=0.8,
        )
        assert sa.validate_proposal(p) is True

    def test_audit_all_decisions_empty(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        results = sa.audit_all_decisions()
        assert results == []

    def test_audit_all_decisions_with_records(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        store.append(
            UnifiedAuditRecord(
                record_id="r1", timestamp=time.time(), layer="inner", round=1,
                event_type="test", source_module="sm", target_module="tm",
                decision="d", justification="j", outcome="success",
            )
        )
        results = sa.audit_all_decisions()
        assert len(results) > 0
        inner = [r for r in results if r["layer"] == "inner"]
        assert len(inner) == 1
        assert inner[0]["decision_count"] == 1

    def test_propose_all(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        sa._arch_snapshot = {"module_count": 5}

        with (
            patch.object(sa, "detect_unused_imports", return_value={"src/a.py": ["os"]}),
            patch.object(sa, "analyze_low_coverage", return_value=[{"file": "src/a.py", "coverage_pct": 50.0}]),
        ):
            proposals = sa.propose_all()
            assert len(proposals) >= 2

    def test_propose_all_fallback_on_exception(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        sa._arch_snapshot = {"module_count": 5}

        with (
            patch.object(sa, "detect_unused_imports", side_effect=RuntimeError("fail")),
            patch.object(sa, "analyze_low_coverage", side_effect=RuntimeError("fail")),
        ):
            proposals = sa.propose_all()
            assert len(proposals) == 1

    def test_proposals_property_returns_copy(self) -> None:
        store = UnifiedAuditStore()
        sa = SelfArchitect(store)
        sa._proposals.append(
            ArchitectureProposal(
                proposal_id="p1", timestamp=time.time(),
                current_arch="v1", proposed_arch="v2",
                rationale="test", risk_assessment="low", confidence=0.9,
            )
        )
        props = sa.proposals
        assert len(props) == 1
        props.clear()
        assert len(sa.proposals) == 1
