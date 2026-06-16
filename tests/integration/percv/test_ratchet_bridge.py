"""Tests for RatchetBridge — PERCV ratchet loop to MAREF MetaLearner bridge."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maref.integration.percv.ratchet_bridge import RatchetBridge


class TestRatchetBridge:
    def test_init_defaults(self) -> None:
        bridge = RatchetBridge()
        assert bridge._vault_path == Path("vault")
        assert bridge._cycle_history == []

    def test_extract_score(self) -> None:
        bridge = RatchetBridge()
        assert bridge._extract_score("score: 0.85") == 0.85
        assert bridge._extract_score("quality: 0.92") == 0.92
        assert bridge._extract_score("Score: 0.75") == 0.75
        assert bridge._extract_score("no match here") == 0.0

    def test_read_program_config_no_file(self) -> None:
        bridge = RatchetBridge(vault_path=Path("/tmp/nonexistent_vault_xyz"))
        config = bridge._read_program_config()
        assert config == {}

    def test_sync_metrics_no_data(self) -> None:
        bridge = RatchetBridge()
        result = bridge.sync_metrics_to_maref()
        assert result["status"] == "no_data"

    def test_sync_metrics_with_data(self) -> None:
        bridge = RatchetBridge()
        bridge._cycle_history = [
            {"score": 0.5, "approved": True, "duration_s": 10.0},
            {"score": 0.8, "approved": True, "duration_s": 12.0},
            {"score": 0.6, "approved": False, "duration_s": 11.0},
        ]
        result = bridge.sync_metrics_to_maref()
        assert result["status"] == "ok"
        assert result["total_iterations"] == 3
        assert result["approved_count"] == 2
        assert result["best_score"] == 0.8
        assert result["avg_score"] == pytest.approx(0.633, rel=0.1)

    def test_get_history(self) -> None:
        bridge = RatchetBridge()
        assert bridge.get_history() == []
        bridge._cycle_history.append({"score": 0.9})
        assert len(bridge.get_history()) == 1

    def test_reset(self) -> None:
        bridge = RatchetBridge()
        bridge._cycle_history.append({"score": 0.9})
        bridge.reset()
        assert bridge._cycle_history == []

    def test_improvement_cycle_subprocess_failure(self) -> None:
        bridge = RatchetBridge(vault_path=Path("/tmp"))
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            iterations = bridge.run_improvement_cycle(budget=1)
        assert len(iterations) == 1
        assert iterations[0]["error"] == "percv_cli_not_found"
        assert iterations[0]["score"] == 0.0

    def test_improvement_cycle_timeout(self) -> None:
        bridge = RatchetBridge(vault_path=Path("/tmp"))
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = __import__("subprocess").TimeoutExpired(
                cmd="percv",
                timeout=300,
            )
            iterations = bridge.run_improvement_cycle(budget=1)
        assert iterations[0]["error"] == "timeout"

    def test_improvement_cycle_with_meta_learner(self) -> None:
        ml = MagicMock()
        ml.evaluate_strategy_alignment.return_value = {"aligned": True}
        bridge = RatchetBridge(meta_learner=ml, vault_path=Path("/tmp"))

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "score: 0.95"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            with patch.object(bridge, "_get_git_diff", return_value="diff content"):
                iterations = bridge.run_improvement_cycle(budget=2)

        assert len(iterations) == 2
        approved = [i for i in iterations if i["approved"]]
        assert len(approved) > 0
