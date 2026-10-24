"""
Comprehensive tests for autoresearch_phase9.py
"""

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from src.drift_guard.policy_sandbox import PolicyChangeType, PolicyStatus
from src.drift_guard.types import PipelineConfig
from src.research.autoresearch_phase9 import (
    Phase9AutoResearch,
    Phase9ExperimentResult,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_llm(content: str = "{}") -> AsyncMock:
    client = AsyncMock()
    response = MagicMock()
    response.content = content
    client.chat_completion = AsyncMock(return_value=response)
    client.close = AsyncMock()
    return client


def _make_mock_sandbox() -> MagicMock:
    sandbox = MagicMock()
    baseline = PipelineConfig(kl_warning=0.1, kl_critical=0.5)
    sandbox.get_active_config.return_value = baseline
    change = MagicMock()
    change.change_id = "change_abc"
    change.status = MagicMock()
    change.status.name = "APPROVED"
    sandbox.propose_change.return_value = change
    sandbox.start_a_b_test.return_value = True
    sandbox.record_test_results.return_value = True
    sandbox.approve_change.return_value = True
    sandbox.reject_change.return_value = True
    sandbox.rollback.return_value = True
    sandbox._versions = {"baseline": MagicMock()}
    return sandbox


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------

class TestPhase9ExperimentResult:
    def test_defaults(self) -> None:
        r = Phase9ExperimentResult(
            experiment_id=1,
            experiment_type="t",
            parameters={},
            observations={},
        )
        assert r.findings == []

    def test_with_findings(self) -> None:
        r = Phase9ExperimentResult(
            experiment_id=1,
            experiment_type="t",
            parameters={},
            observations={},
            findings=["f1"],
        )
        assert r.findings == ["f1"]


# ---------------------------------------------------------------------------
# Init & lifecycle
# ---------------------------------------------------------------------------

class TestPhase9AutoResearchInit:
    def test_defaults(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        assert research._output_dir == tmp_path
        assert research._experiments == 50
        assert research._results == []

    def test_custom_experiments(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path, experiments=10)
        assert research._experiments == 10


class TestEnsureLlm:
    def test_success(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_client = _make_mock_llm()
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            return_value=mock_client,
        ):
            client = asyncio.run(research._ensure_llm())
        assert client is mock_client

    def test_failure(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            side_effect=ValueError("no key"),
        ):
            client = asyncio.run(research._ensure_llm())
        assert client is None

    def test_cached(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_client = _make_mock_llm()
        research._llm_client = mock_client
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            side_effect=RuntimeError("should not call"),
        ):
            client = asyncio.run(research._ensure_llm())
        assert client is mock_client


class TestClose:
    def test_close(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_client = _make_mock_llm()
        research._llm_client = mock_client
        asyncio.run(research.close())
        mock_client.close.assert_awaited_once()
        assert research._llm_client is None

    def test_close_no_client(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        asyncio.run(research.close())


# ---------------------------------------------------------------------------
# Experiment: policy lifecycle
# ---------------------------------------------------------------------------

class TestExperimentPolicyLifecycle:
    def test_with_llm_json(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm()
        mock_llm.chat_completion.side_effect = [
            MagicMock(content='{"kl_warning": 0.15, "kl_critical": 0.6}'),
            MagicMock(content='{"fpr": 0.02, "fnr": 0.01, "f1": 0.92}'),
        ]
        mock_sandbox = _make_mock_sandbox()
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase9.PolicySandbox",
            return_value=mock_sandbox,
        ):
            result = asyncio.run(research._experiment_policy_lifecycle(0))
        assert result.experiment_type == "policy_lifecycle"
        assert "status" in result.observations
        mock_sandbox.propose_change.assert_called_once()
        mock_sandbox.start_a_b_test.assert_called_once()

    def test_with_llm_no_json_match(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content="no json here")
        mock_sandbox = _make_mock_sandbox()
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase9.PolicySandbox",
            return_value=mock_sandbox,
        ):
            result = asyncio.run(research._experiment_policy_lifecycle(0))
        assert result.experiment_type == "policy_lifecycle"

    def test_with_llm_exception(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm()
        mock_llm.chat_completion.side_effect = RuntimeError("API down")
        mock_sandbox = _make_mock_sandbox()
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase9.PolicySandbox",
            return_value=mock_sandbox,
        ):
            result = asyncio.run(research._experiment_policy_lifecycle(0))
        assert result.experiment_type == "policy_lifecycle"

    def test_without_llm(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_sandbox = _make_mock_sandbox()
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_phase9.PolicySandbox",
            return_value=mock_sandbox,
        ):
            result = asyncio.run(research._experiment_policy_lifecycle(0))
        assert result.experiment_type == "policy_lifecycle"

    def test_approve_when_f1_high(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content='{"fpr": 0.02, "fnr": 0.01, "f1": 0.92}')
        mock_sandbox = _make_mock_sandbox()
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase9.PolicySandbox",
            return_value=mock_sandbox,
        ):
            result = asyncio.run(research._experiment_policy_lifecycle(0))
        assert any("已批准" in f for f in result.findings)

    def test_reject_when_f1_low(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content='{"fpr": 0.2, "fnr": 0.2, "f1": 0.7}')
        mock_sandbox = _make_mock_sandbox()
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase9.PolicySandbox",
            return_value=mock_sandbox,
        ):
            result = asyncio.run(research._experiment_policy_lifecycle(0))
        assert any("已拒绝" in f for f in result.findings)


# ---------------------------------------------------------------------------
# Experiment: rollback safety
# ---------------------------------------------------------------------------

class TestExperimentRollbackSafety:
    def test_rollback_matches(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content='{"kl_warning": 0.15, "kl_critical": 0.5}')
        mock_sandbox = _make_mock_sandbox()
        original = PipelineConfig(kl_warning=0.1, kl_critical=0.5)
        # After rollback, restored should match original
        mock_sandbox.get_active_config.side_effect = [
            original,   # for original
            original,   # for restored after rollback
        ]
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase9.PolicySandbox",
            return_value=mock_sandbox,
        ):
            result = asyncio.run(research._experiment_rollback_safety(1))
        assert result.experiment_type == "rollback_safety"
        assert result.observations["match"] is True
        assert any("回滚成功" in f for f in result.findings)

    def test_rollback_mismatch(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_sandbox = _make_mock_sandbox()
        original = PipelineConfig(kl_warning=0.1, kl_critical=0.5)
        # After rollback, restored does NOT match original
        mock_sandbox.get_active_config.side_effect = [
            original,                           # for original
            PipelineConfig(kl_warning=0.99, kl_critical=0.5),  # for restored
        ]
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_phase9.PolicySandbox",
            return_value=mock_sandbox,
        ):
            result = asyncio.run(research._experiment_rollback_safety(1))
        assert result.observations["match"] is False
        assert any("回滚失败" in f for f in result.findings)

    def test_without_llm(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_sandbox = _make_mock_sandbox()
        original = PipelineConfig(kl_warning=0.1, kl_critical=0.5)
        mock_sandbox.get_active_config.side_effect = [
            original,   # for original
            original,   # for restored
        ]
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_phase9.PolicySandbox",
            return_value=mock_sandbox,
        ):
            result = asyncio.run(research._experiment_rollback_safety(1))
        assert result.experiment_type == "rollback_safety"


# ---------------------------------------------------------------------------
# Experiment: A/B test winner
# ---------------------------------------------------------------------------

class TestExperimentABTestWinner:
    def test_ab_test_winner(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(
            content='{"A": {"kl_warning": 0.1}, "B": {"kl_warning": 0.15}}'
        )
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            return_value=mock_llm,
        ):
            result = asyncio.run(research._experiment_ab_test_winner(2))
        assert result.experiment_type == "ab_test_winner"
        assert "胜出者" in str(result.findings)

    def test_ab_test_no_llm(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            side_effect=ValueError("no key"),
        ):
            result = asyncio.run(research._experiment_ab_test_winner(2))
        assert result.experiment_type == "ab_test_winner"


# ---------------------------------------------------------------------------
# Experiment: degradation prevention
# ---------------------------------------------------------------------------

class TestExperimentDegradationPrevention:
    def test_degradation_prevention(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content="0.9")
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            return_value=mock_llm,
        ):
            result = asyncio.run(research._experiment_degradation_prevention(3))
        assert result.experiment_type == "degradation_prevention"
        assert result.parameters["bad_kl_warning"] >= 0.5

    def test_degradation_no_llm(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            side_effect=ValueError("no key"),
        ):
            result = asyncio.run(research._experiment_degradation_prevention(3))
        assert result.experiment_type == "degradation_prevention"
        assert result.parameters["bad_kl_warning"] == 0.9


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

class TestRunExperiment:
    def test_rotation(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        types = []
        mock_llm = _make_mock_llm(content="{}")
        mock_sandbox = _make_mock_sandbox()
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase9.PolicySandbox",
            return_value=mock_sandbox,
        ):
            for i in range(5):
                result = asyncio.run(research.run_experiment(i))
                types.append(result.experiment_type)
        assert types[0] == "policy_lifecycle"
        assert types[1] == "rollback_safety"
        assert types[2] == "ab_test_winner"
        assert types[3] == "degradation_prevention"
        assert types[4] == "policy_lifecycle"


class TestRunBatch:
    def test_batch(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path, experiments=4)
        mock_llm = _make_mock_llm(content="{}")
        mock_sandbox = _make_mock_sandbox()
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase9.PolicySandbox",
            return_value=mock_sandbox,
        ):
            report = asyncio.run(research.run_batch())
        assert report["phase"] == "Phase 9"
        assert report["total_experiments"] == 4
        assert "experiment_types" in report


class TestGenerateReport:
    def test_report_structure(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        research._results = [
            Phase9ExperimentResult(
                experiment_id=0,
                experiment_type="policy_lifecycle",
                parameters={},
                observations={"status": "APPROVED", "f1_score": 0.9},
                findings=["f1"],
            ),
            Phase9ExperimentResult(
                experiment_id=1,
                experiment_type="rollback_safety",
                parameters={},
                observations={"match": True},
                findings=["f2"],
            ),
            Phase9ExperimentResult(
                experiment_id=2,
                experiment_type="degradation_prevention",
                parameters={},
                observations={},
                findings=["True"],
            ),
        ]
        report = research._generate_report()
        assert report["safety_metrics"]["rollback_failures"] == 0
        assert report["safety_metrics"]["degradation_prevented"] == 1
        assert 0 <= report["safety_metrics"]["safety_score"] <= 100

    def test_report_empty(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        report = research._generate_report()
        assert report["total_experiments"] == 0
        assert report["safety_metrics"]["safety_score"] == []


class TestSaveReport:
    def test_save_creates_files(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        report = {
            "date": "2024-01-01",
            "phase": "Phase 9",
            "total_experiments": 1,
            "experiment_types": {"t": 1},
            "key_findings": ["f1"],
            "safety_metrics": {
                "rollback_failures": 0,
                "degradation_prevented": 0,
                "safety_score": 100.0,
            },
        }
        path = research.save_report(report)
        assert path.exists()
        json_path = tmp_path / "maref-phase9-2024-01-01.json"
        assert json_path.exists()
        with open(json_path) as f:
            data = json.load(f)
        assert data["phase"] == "Phase 9"


class TestFormatMarkdown:
    def test_markdown_content(self, tmp_path: Path) -> None:
        research = Phase9AutoResearch(output_dir=tmp_path)
        report = {
            "date": "2024-01-01",
            "phase": "Phase 9",
            "total_experiments": 2,
            "experiment_types": {"policy_lifecycle": 2},
            "key_findings": ["finding"],
            "safety_metrics": {
                "rollback_failures": 0,
                "degradation_prevented": 1,
                "safety_score": 100.0,
            },
        }
        md = research._format_markdown(report)
        assert "# MAREF Phase 9 研究报告" in md
        assert "policy_lifecycle" in md
        assert "finding" in md
        assert "100.0%" in md


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

class TestMain:
    def test_main(self, tmp_path: Path) -> None:
        with patch(
            "src.research.autoresearch_phase9.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch.dict(
            "os.environ", {"MAREF_RESEARCH_OUTPUT": str(tmp_path)}
        ):
            asyncio.run(main())
        assert list(tmp_path.glob("maref-phase9-*.json"))
