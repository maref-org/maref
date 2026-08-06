from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maref.integration.percv.ratchet_bridge import RatchetBridge, RatchetIterationRecord


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
            RatchetIterationRecord(iteration=0, score=0.5, approved=True, best_score=0.5, best_iteration=0, duration_s=10.0),
            RatchetIterationRecord(iteration=1, score=0.8, approved=True, best_score=0.8, best_iteration=1, duration_s=12.0),
            RatchetIterationRecord(iteration=2, score=0.6, approved=False, best_score=0.8, best_iteration=1, duration_s=11.0),
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
        bridge._cycle_history.append(RatchetIterationRecord(iteration=0, score=0.9, approved=True, best_score=0.9, best_iteration=0, duration_s=5.0))
        assert len(bridge.get_history()) == 1

    def test_reset(self) -> None:
        bridge = RatchetBridge()
        bridge._cycle_history.append(RatchetIterationRecord(iteration=0, score=0.9, approved=True, best_score=0.9, best_iteration=0, duration_s=5.0))
        bridge.reset()
        assert bridge._cycle_history == []

    def test_improvement_cycle_subprocess_failure(self) -> None:
        bridge = RatchetBridge(vault_path=Path("/tmp"))
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            iterations = bridge.run_improvement_cycle(budget=1)
        assert len(iterations) == 1
        assert iterations[0].error == "percv_cli_not_found"
        assert iterations[0].score == 0.0

    def test_improvement_cycle_timeout(self) -> None:
        bridge = RatchetBridge(vault_path=Path("/tmp"))
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = __import__("subprocess").TimeoutExpired(
                cmd="percv",
                timeout=300,
            )
            iterations = bridge.run_improvement_cycle(budget=1)
        assert iterations[0].error == "timeout"

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
        approved = [i for i in iterations if i.approved]
        assert len(approved) > 0

    def test_masts_integration_on_run(self) -> None:
        mas_ts_mock = MagicMock()
        mas_ts_mock.run_fast_screen.return_value = {"overall_score": 85.0, "level": "L0"}
        bridge = RatchetBridge(vault_path=Path("/tmp"), mas_ts_bridge=mas_ts_mock)

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "score: 0.90"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            with patch.object(bridge, "_get_git_diff", return_value=""):
                iterations = bridge.run_improvement_cycle(budget=1)

        assert len(iterations) == 1
        assert iterations[0].mas_ts_score == 85.0
        assert iterations[0].mas_ts_level == "L0"

    def test_check_redlines_no_violation(self) -> None:
        bridge = RatchetBridge()
        violations = bridge.check_redlines("some_target", score=75.0)
        assert isinstance(violations, list)
        assert len(violations) == 0

    def test_check_redlines_rl001_human_gate_false(self) -> None:
        bridge = RatchetBridge()
        violations = bridge.check_redlines("target", score=0, human_gate=False)
        assert any("RL-001" in v for v in violations)

    def test_check_redlines_rl004_low_masts(self) -> None:
        bridge = RatchetBridge()
        violations = bridge.check_redlines("target", score=0, mas_ts_score=50.0)
        assert any("RL-004" in v for v in violations)

    def test_enforce_redlines_discard_on_low_masts(self) -> None:
        bridge = RatchetBridge()
        result = bridge._enforce_redlines("target", mas_ts_score=50.0, human_gate=True)
        assert result.get("action") == "DISCARD"

    def test_enforce_redlines_halt_on_no_human_gate(self) -> None:
        bridge = RatchetBridge()
        result = bridge._enforce_redlines("target", mas_ts_score=0, human_gate=False)
        assert result.get("action") == "HALT"

    def test_enforce_redlines_no_violation(self) -> None:
        bridge = RatchetBridge()
        result = bridge._enforce_redlines("target", mas_ts_score=75.0, human_gate=True)
        assert result == {}

    def test_ratchet_iteration_record_to_dict(self) -> None:
        record = RatchetIterationRecord(
            iteration=0, score=0.85, approved=True, best_score=0.85,
            best_iteration=0, duration_s=10.0, target="test.yaml",
        )
        d = record.to_dict()
        assert d["score"] == 0.85
        assert d["target"] == "test.yaml"
        assert d["approved"] is True
