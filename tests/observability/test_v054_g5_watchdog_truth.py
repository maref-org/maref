"""Tests for watchdog truthfulness fix (INC-2026-08-13-001 / G5).

Verifies check_audit_log_growth no longer self-touches and
check_audit_noise detects pollution.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from maref.observability.meta_monitor import check_audit_log_growth, check_audit_noise


class TestWatchdogTruthful:
    def test_touch_file_does_not_pass(self, tmp_path: Path) -> None:
        """核心：meta_monitor 自己 touch 的文件不能通过审计新鲜度检查。"""
        (tmp_path / "governance_audit_state_machine.jsonl").write_text(
            json.dumps({"_meta_monitor_touch": True, "timestamp": time.time()}) + "\n"
        )
        result = check_audit_log_growth(max_age=600.0, audit_base=tmp_path)
        assert result["passed"] is False

    def test_real_event_passes(self, tmp_path: Path) -> None:
        (tmp_path / "governance_audit.jsonl").write_text(
            json.dumps({"event_type": "governance_decision", "timestamp": time.time(),
                        "actor": "test", "action": "x"}) + "\n"
        )
        result = check_audit_log_growth(max_age=600.0, audit_base=tmp_path)
        assert result["passed"] is True
        assert result["newest_event_type"] == "governance_decision"

    def test_stale_real_event_fails(self, tmp_path: Path) -> None:
        (tmp_path / "governance_audit.jsonl").write_text(
            json.dumps({"event_type": "governance_decision", "timestamp": time.time() - 5000,
                        "actor": "test", "action": "x"}) + "\n"
        )
        result = check_audit_log_growth(max_age=600.0, audit_base=tmp_path)
        assert result["passed"] is False


class TestAuditNoise:
    def _write(self, tmp_path: Path, records: list[dict]) -> Path:
        p = tmp_path / "governance_audit.jsonl"
        with open(p, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return p

    def test_all_state_transition_polluted(self, tmp_path: Path) -> None:
        now = time.time()
        records = [{"event_type": "state_transition", "timestamp": now - i, "actor": "state_machine"} for i in range(1500)]
        self._write(tmp_path, records)
        result = check_audit_noise(audit_base=tmp_path)
        assert result["passed"] is False
        assert result["detail"] == "noise_pollution"

    def test_low_volume_state_transitions_not_polluted(self, tmp_path: Path) -> None:
        """健康静默系统：少量 state_transition 不判污染（I6 修复）。"""
        now = time.time()
        records = [{"event_type": "state_transition", "timestamp": now - i, "actor": "state_machine"} for i in range(20)]
        self._write(tmp_path, records)
        result = check_audit_noise(audit_base=tmp_path)
        assert result["passed"] is True

    def test_mixed_events_ok(self, tmp_path: Path) -> None:
        now = time.time()
        records = [
            {"event_type": "state_transition", "timestamp": now - i, "actor": "state_machine"}
            for i in range(50)
        ]
        records.append({"event_type": "governance_decision", "timestamp": now, "actor": "test", "action": "x"})
        self._write(tmp_path, records)
        result = check_audit_noise(audit_base=tmp_path)
        assert result["passed"] is True
        assert result["noise_ratio"] < 1.0

    def test_no_file_passes(self, tmp_path: Path) -> None:
        result = check_audit_noise(audit_base=tmp_path)
        assert result["passed"] is True

    def test_stale_window_ignored(self, tmp_path: Path) -> None:
        old = time.time() - 100000
        records = [{"event_type": "state_transition", "timestamp": old, "actor": "state_machine"}]
        self._write(tmp_path, records)
        result = check_audit_noise(audit_base=tmp_path, window_hours=24.0)
        assert result["passed"] is True  # 窗口外不判污染
