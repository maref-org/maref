from __future__ import annotations

from unittest.mock import patch

import pytest

from maref.evolution.rel_adapter import RELAdapter


class TestRELAdapter:
    def test_dry_run_returns_immediately(self) -> None:
        adapter = RELAdapter(dry_run=True)
        result = adapter.run_once("2026-06-28")
        assert result is not None
        assert result.dry_run is True
        assert result.real_writes_enabled is False
        assert result.stop_reason == "dry_run"

    def test_dry_run_does_not_call_rel(self) -> None:
        adapter = RELAdapter(dry_run=True)
        with patch.object(adapter._rel, "run_session") as mock_run:
            adapter.run_once("2026-06-28")
            mock_run.assert_not_called()

    def test_real_run_returns_result(self) -> None:
        adapter = RELAdapter(dry_run=False)
        with patch.object(adapter._rel, "run_session") as mock_run:
            mock_run.return_value = type("RelResult", (), {
                "success": True,
                "reason": "completed",
                "round_count": 3,
                "final_state": "STOP",
                "duration_seconds": 1.0,
            })()
            result = adapter.run_once("2026-06-28")
        assert result is not None
        assert result.dry_run is False
        assert result.real_writes_enabled is True
        assert result.priority == "medium"

    def test_real_run_success_false_returns_high_priority(self) -> None:
        adapter = RELAdapter(dry_run=False)
        with patch.object(adapter._rel, "run_session") as mock_run:
            mock_run.return_value = type("RelResult", (), {
                "success": False,
                "reason": "halted",
                "round_count": 1,
                "final_state": "HALT",
                "duration_seconds": 0.5,
            })()
            result = adapter.run_once("2026-06-28")
        assert result is not None
        assert result.priority == "high"

    def test_exception_returns_none(self) -> None:
        adapter = RELAdapter(dry_run=False)
        with patch.object(adapter._rel, "run_session", side_effect=RuntimeError("boom")):
            result = adapter.run_once("2026-06-28")
        assert result is None
