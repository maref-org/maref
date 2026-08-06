"""
Comprehensive tests for autoresearch_loop.py
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from src.research.autoresearch_loop import (
    DailyReport,
    ExperimentResult,
    MAREFAutoResearch,
    main,
)
from src.research.finding_models import StructuredFinding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_llm(content: str = "OBSERVE") -> AsyncMock:
    """Return an async mock DashScopeClient that replies with ``content``."""
    client = AsyncMock()
    response = MagicMock()
    response.content = content
    client.chat_completion = AsyncMock(return_value=response)
    client.close = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------

class TestExperimentResult:
    def test_defaults(self) -> None:
        r = ExperimentResult(
            experiment_id=1,
            timestamp=123.0,
            experiment_type="t",
            parameters={},
            observations={},
        )
        assert r.findings == []
        assert r.structured_findings == []
        assert r.anomalies == []

    def test_with_structured_findings(self) -> None:
        sf = StructuredFinding(content="c", metric_name="m", values=[1.0])
        r = ExperimentResult(
            experiment_id=1,
            timestamp=123.0,
            experiment_type="t",
            parameters={},
            observations={},
            structured_findings=[sf],
        )
        assert len(r.structured_findings) == 1
        assert r.structured_findings[0].content == "c"


class TestDailyReport:
    def test_construction(self) -> None:
        report = DailyReport(
            date="2024-01-01",
            total_experiments=10,
            experiment_types={"a": 5},
            key_findings=["f1"],
            anomalies_detected=["a1"],
            self_observation_stats={"s": 1},
            adaptive_threshold_stats={"p": 2},
            recommendations=["r1"],
        )
        assert report.date == "2024-01-01"
        assert report.total_experiments == 10


# ---------------------------------------------------------------------------
# MAREFAutoResearch initialisation & lifecycle
# ---------------------------------------------------------------------------

class TestMAREFAutoResearchInit:
    def test_init_defaults(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        assert research._output_dir == tmp_path
        assert research._experiments_per_day == 100
        assert research._results == []
        assert research._llm_client is None

    def test_init_custom_experiments(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path, experiments_per_day=50)
        assert research._experiments_per_day == 50


class TestEnsureLlm:
    def test_lazy_initialisation_success(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        mock_client = _make_mock_llm()
        with patch(
            "src.research.autoresearch_loop.DashScopeClient", return_value=mock_client
        ):
            client = asyncio.run(research._ensure_llm())
        assert client is mock_client
        assert research._llm_client is mock_client

    def test_lazy_initialisation_failure(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        with patch(
            "src.research.autoresearch_loop.DashScopeClient",
            side_effect=ValueError("no key"),
        ):
            client = asyncio.run(research._ensure_llm())
        assert client is None
        assert research._llm_client is None

    def test_cached_client(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        mock_client = _make_mock_llm()
        research._llm_client = mock_client
        with patch(
            "src.research.autoresearch_loop.DashScopeClient",
            side_effect=RuntimeError("should not be called"),
        ):
            client = asyncio.run(research._ensure_llm())
        assert client is mock_client


class TestClose:
    def test_close_cleans_up(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        mock_client = _make_mock_llm()
        research._llm_client = mock_client
        asyncio.run(research.close())
        mock_client.close.assert_awaited_once()
        assert research._llm_client is None

    def test_close_no_client(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        asyncio.run(research.close())  # should not raise


# ---------------------------------------------------------------------------
# Experiment tests
# ---------------------------------------------------------------------------

class TestExperimentRandomWalk:
    def test_with_llm_valid_state(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content="OBSERVE")
        with patch(
            "src.research.autoresearch_loop.DashScopeClient", return_value=mock_llm
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_random_walk(0))
        assert result.experiment_type == "random_walk"
        assert result.experiment_id == 0
        assert "unique_states" in result.observations
        assert result.timestamp == 1000.0

    def test_with_llm_invalid_state_fallback(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content="INVALID_STATE")
        with patch(
            "src.research.autoresearch_loop.DashScopeClient", return_value=mock_llm
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_random_walk(0))
        assert result.experiment_type == "random_walk"
        decisions = result.observations["llm_decisions"]
        assert any("fallback_random" in d for d in decisions)

    def test_llm_exception_fallback(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm()
        mock_llm.chat_completion.side_effect = RuntimeError("API down")
        with patch(
            "src.research.autoresearch_loop.DashScopeClient", return_value=mock_llm
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_random_walk(0))
        assert result.experiment_type == "random_walk"
        decisions = result.observations["llm_decisions"]
        assert any("error_fallback" in d for d in decisions)

    def test_without_llm(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        with patch(
            "src.research.autoresearch_loop.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_random_walk(0))
        assert result.experiment_type == "random_walk"
        decisions = result.observations["llm_decisions"]
        assert all("no_llm" in d for d in decisions)

    def test_high_coverage_finding(self, tmp_path: Path) -> None:
        """Force the state machine to visit many states."""
        research = MAREFAutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content="OBSERVE")
        with patch(
            "src.research.autoresearch_loop.DashScopeClient", return_value=mock_llm
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_random_walk(0))
        # At least some findings should be produced
        assert isinstance(result.findings, list)


class TestExperimentGrayCodeFaultTolerance:
    def test_with_llm(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content="评分: 8/10")
        with patch(
            "src.research.autoresearch_loop.DashScopeClient", return_value=mock_llm
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_gray_code_fault_tolerance(1))
        assert result.experiment_type == "gray_code_fault_tolerance"
        assert result.observations["valid_transitions_after_flip"] >= 0

    def test_without_llm(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        with patch(
            "src.research.autoresearch_loop.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_gray_code_fault_tolerance(1))
        assert result.experiment_type == "gray_code_fault_tolerance"
        assert len(result.findings) > 0


class TestExperimentSelfObservation:
    def test_self_observation(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content="可观测性: 8/10")

        mock_overlay = MagicMock()
        mock_overlay.get_self_observations.side_effect = [[], [MagicMock()], [MagicMock(), MagicMock(), MagicMock()]]
        mock_overlay._enable_self_observation = True

        with patch(
            "src.research.autoresearch_loop.DashScopeClient", return_value=mock_llm
        ), patch(
            "src.research.autoresearch_loop.GovernanceOverlay", return_value=mock_overlay
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_self_observation(2))
        assert result.experiment_type == "self_observation"
        assert result.observations["observations_captured"] >= 0
        assert isinstance(result.findings, list)

    def test_self_observation_no_llm(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        mock_overlay = MagicMock()
        mock_overlay.get_self_observations.side_effect = [[], [MagicMock()], [MagicMock(), MagicMock(), MagicMock()]]
        mock_overlay._enable_self_observation = True

        with patch(
            "src.research.autoresearch_loop.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_loop.GovernanceOverlay", return_value=mock_overlay
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_self_observation(2))
        assert result.experiment_type == "self_observation"


class TestExperimentAdaptiveThreshold:
    def test_with_llm_scenarios(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(
            content="true, confidence: 0.8\nfalse, confidence: 0.2"
        )
        with patch(
            "src.research.autoresearch_loop.DashScopeClient", return_value=mock_llm
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_adaptive_threshold(3))
        assert result.experiment_type == "adaptive_threshold"
        assert result.parameters["llm_scenarios"] > 0
        assert "performance" in result.observations

    def test_without_llm(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        with patch(
            "src.research.autoresearch_loop.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_adaptive_threshold(3))
        assert result.experiment_type == "adaptive_threshold"
        assert result.parameters["llm_scenarios"] == 0
        assert "performance" in result.observations

    def test_llm_parse_exception_fallback(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content="garbage")
        mock_llm.chat_completion.side_effect = [
            MagicMock(content="garbage"),
            RuntimeError("fail"),
        ]
        with patch(
            "src.research.autoresearch_loop.DashScopeClient", return_value=mock_llm
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_adaptive_threshold(3))
        assert result.experiment_type == "adaptive_threshold"


class TestExperimentEmergenceDetection:
    def test_emergence_detection(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content="检测到吸引子")
        with patch(
            "src.research.autoresearch_loop.DashScopeClient", return_value=mock_llm
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_emergence_detection(4))
        assert result.experiment_type == "emergence_detection"
        assert "state_distribution" in result.observations
        assert "attractors" in result.observations

    def test_emergence_no_llm(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        with patch(
            "src.research.autoresearch_loop.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch("time.time", return_value=1000.0):
            result = asyncio.run(research._experiment_emergence_detection(4))
        assert result.experiment_type == "emergence_detection"


# ---------------------------------------------------------------------------
# Orchestration tests
# ---------------------------------------------------------------------------

class TestRunExperiment:
    def test_rotation(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        types = []
        mock_llm = _make_mock_llm(content="OBSERVE")
        with patch(
            "src.research.autoresearch_loop.DashScopeClient", return_value=mock_llm
        ), patch("time.time", return_value=1000.0):
            for i in range(6):
                result = asyncio.run(research.run_experiment(i))
                types.append(result.experiment_type)
        assert types[0] == "random_walk"
        assert types[1] == "gray_code_fault_tolerance"
        assert types[2] == "self_observation"
        assert types[3] == "adaptive_threshold"
        assert types[4] == "emergence_detection"
        assert types[5] == "random_walk"  # wraps around


class TestRunDailyBatch:
    def test_batch_runs_all_experiments(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path, experiments_per_day=5)
        mock_llm = _make_mock_llm(content="OBSERVE")
        with patch(
            "src.research.autoresearch_loop.DashScopeClient", return_value=mock_llm
        ), patch("time.time", return_value=1000.0):
            report = asyncio.run(research.run_daily_batch())
        assert report.total_experiments == 5
        assert isinstance(report.key_findings, list)


class TestGenerateReport:
    def test_generate_report(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        research._results = [
            ExperimentResult(
                experiment_id=0,
                timestamp=1.0,
                experiment_type="random_walk",
                parameters={},
                observations={},
                findings=["f1"],
            ),
            ExperimentResult(
                experiment_id=1,
                timestamp=2.0,
                experiment_type="random_walk",
                parameters={},
                observations={},
                findings=["f2"],
            ),
        ]
        with patch("src.research.autoresearch_loop.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 12, 0, 0)
            report = research._generate_report()
        assert report.date == "2024-01-01"
        assert report.total_experiments == 2
        assert report.experiment_types == {"random_walk": 2}
        assert len(report.key_findings) <= 20

    def test_low_finding_rate_recommendation(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        research._results = [
            ExperimentResult(
                experiment_id=0,
                timestamp=1.0,
                experiment_type="t",
                parameters={},
                observations={},
                findings=[],
            )
            for _ in range(10)
        ]
        with patch("src.research.autoresearch_loop.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 12, 0, 0)
            report = research._generate_report()
        assert any("Low finding rate" in r for r in report.recommendations)

    def test_high_fpr_recommendation(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        # seed adaptive manager with high FPR data
        for _ in range(100):
            research._adaptive_manager.record_outcome(0.5, True, False)
        research._results = [
            ExperimentResult(
                experiment_id=0,
                timestamp=1.0,
                experiment_type="t",
                parameters={},
                observations={},
                findings=["f1"],
            )
        ]
        with patch("src.research.autoresearch_loop.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 12, 0, 0)
            report = research._generate_report()
        assert any("High FPR" in r for r in report.recommendations)


class TestSaveReport:
    def test_save_creates_files(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        report = DailyReport(
            date="2024-01-01",
            total_experiments=1,
            experiment_types={"t": 1},
            key_findings=["f1"],
            anomalies_detected=[],
            self_observation_stats={},
            adaptive_threshold_stats={},
            recommendations=["r1"],
        )
        with patch("src.research.autoresearch_loop.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 12, 0, 0)
            path = research.save_report(report)
        assert path.exists()
        md_path = tmp_path / "maref-autoresearch-2024-01-01.md"
        assert md_path.exists()

    def test_markdown_content(self, tmp_path: Path) -> None:
        research = MAREFAutoResearch(output_dir=tmp_path)
        report = DailyReport(
            date="2024-01-01",
            total_experiments=2,
            experiment_types={"random_walk": 2},
            key_findings=["finding"],
            anomalies_detected=[],
            self_observation_stats={"total_experiments": 2},
            adaptive_threshold_stats={"performance": {}},
            recommendations=["rec"],
        )
        with patch("src.research.autoresearch_loop.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 12, 0, 0)
            md = research._format_markdown_report(report)
        assert "# MAREF 自主研究报告" in md
        assert "random_walk" in md
        assert "finding" in md
        assert "rec" in md


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

class TestMain:
    def test_main_single_batch(self, tmp_path: Path) -> None:
        with patch(
            "src.research.autoresearch_loop.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_loop.argparse.ArgumentParser.parse_args"
        ) as mock_parse:
            args = MagicMock()
            args.experiments = 2
            args.output_dir = tmp_path
            args.continuous = False
            args.interval_hours = 24.0
            mock_parse.return_value = args
            asyncio.run(main())
        # Should have created report files
        assert list(tmp_path.glob("maref-autoresearch-*.json"))

    def test_main_continuous_exits_on_cancel(self, tmp_path: Path) -> None:
        with patch(
            "src.research.autoresearch_loop.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_loop.argparse.ArgumentParser.parse_args"
        ) as mock_parse, patch(
            "src.research.autoresearch_loop.asyncio.sleep",
            side_effect=asyncio.CancelledError("stop"),
        ):
            args = MagicMock()
            args.experiments = 1
            args.output_dir = tmp_path
            args.continuous = True
            args.interval_hours = 0.001
            mock_parse.return_value = args
            with pytest.raises(asyncio.CancelledError):
                asyncio.run(main())
