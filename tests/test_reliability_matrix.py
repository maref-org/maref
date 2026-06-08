"""ReliabilityMatrix 单元测试.

覆盖 reliability_matrix.py 的 TaskOutcome、ReliabilityCell、ReliabilityMatrix。
"""
from __future__ import annotations

import pytest

from maref.recursive.reliability_matrix import (
    ReliabilityCell,
    ReliabilityMatrix,
    TaskOutcome,
)


class TestReliabilityCell:
    def test_initial_state(self) -> None:
        cell = ReliabilityCell(task_type="test")
        assert cell.total == 0
        assert cell.success_rate == 0.5
        assert not cell.is_unreliable

    def test_record_success(self) -> None:
        cell = ReliabilityCell(task_type="test")
        cell.record(True, latency_ms=100.0)
        assert cell.total == 1
        assert cell.successes == 1
        assert cell.failures == 0
        assert cell.consecutive_failures == 0
        assert cell.success_rate == 1.0

    def test_record_failure(self) -> None:
        cell = ReliabilityCell(task_type="test")
        cell.record(False, latency_ms=200.0)
        assert cell.total == 1
        assert cell.successes == 0
        assert cell.failures == 1
        assert cell.consecutive_failures == 1
        assert cell.success_rate == 0.0

    def test_consecutive_failures_triggers_unreliable(self) -> None:
        cell = ReliabilityCell(task_type="test")
        for _ in range(3):
            cell.record(False)
        assert cell.is_unreliable
        assert cell.consecutive_failures == 3

    def test_success_resets_consecutive(self) -> None:
        cell = ReliabilityCell(task_type="test")
        cell.record(False)
        cell.record(False)
        cell.record(True)
        assert cell.consecutive_failures == 0
        assert not cell.is_unreliable

    def test_to_dict_structure(self) -> None:
        cell = ReliabilityCell(task_type="test")
        cell.record(True, latency_ms=50.0)
        d = cell.to_dict()
        assert d["task_type"] == "test"
        assert d["total"] == 1
        assert d["success_rate"] == 1.0
        assert d["is_unreliable"] is False


class TestReliabilityMatrix:
    def test_record_and_get_cell(self) -> None:
        rm = ReliabilityMatrix()
        cell = rm.record("obs", "tgt", "type1", True, 100.0)
        assert cell.total == 1
        fetched = rm.get_cell("obs", "tgt", "type1")
        assert fetched is not None
        assert fetched.total == 1

    def test_get_cell_missing(self) -> None:
        rm = ReliabilityMatrix()
        assert rm.get_cell("obs", "tgt", "type1") is None

    def test_success_rate_missing(self) -> None:
        rm = ReliabilityMatrix()
        assert rm.success_rate("obs", "tgt", "type1") == 0.5

    def test_should_bypass_false_when_missing(self) -> None:
        rm = ReliabilityMatrix()
        assert not rm.should_bypass("obs", "tgt", "type1")

    def test_should_bypass_true_after_three_failures(self) -> None:
        rm = ReliabilityMatrix()
        for _ in range(3):
            rm.record("obs", "tgt", "type1", False)
        assert rm.should_bypass("obs", "tgt", "type1")

    def test_list_bypassed(self) -> None:
        rm = ReliabilityMatrix()
        rm.record("obs", "tgt1", "type1", False)
        rm.record("obs", "tgt1", "type1", False)
        rm.record("obs", "tgt1", "type1", False)
        rm.record("obs", "tgt2", "type1", True)
        bypassed = rm.list_bypassed("obs", "type1")
        assert bypassed == ["tgt1"]

    def test_best_target_excludes_bypassed(self) -> None:
        rm = ReliabilityMatrix()
        rm.record("obs", "tgt1", "type1", False)
        rm.record("obs", "tgt1", "type1", False)
        rm.record("obs", "tgt1", "type1", False)
        rm.record("obs", "tgt2", "type1", True)
        best = rm.best_target("obs", "type1", ["tgt1", "tgt2"])
        assert best == "tgt2"

    def test_best_target_all_bypassed(self) -> None:
        rm = ReliabilityMatrix()
        for _ in range(3):
            rm.record("obs", "tgt1", "type1", False)
        assert rm.best_target("obs", "type1", ["tgt1"]) is None

    def test_best_target_selects_higher_rate(self) -> None:
        rm = ReliabilityMatrix()
        rm.record("obs", "tgt1", "type1", True)
        rm.record("obs", "tgt1", "type1", False)
        rm.record("obs", "tgt2", "type1", True)
        rm.record("obs", "tgt2", "type1", True)
        best = rm.best_target("obs", "type1", ["tgt1", "tgt2"])
        assert best == "tgt2"

    def test_summary_structure(self) -> None:
        rm = ReliabilityMatrix()
        rm.record("obs", "tgt", "type1", True)
        summary = rm.summary("obs")
        assert summary["observer"] == "obs"
        assert "tgt" in summary["targets"]
