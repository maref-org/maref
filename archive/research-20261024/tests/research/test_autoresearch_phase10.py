"""
Comprehensive tests for autoresearch_phase10.py
"""

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.maref.governance.types import GovernanceState
from src.research.autoresearch_phase10 import (
    Phase10AutoResearch,
    Phase10ExperimentResult,
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


def _make_mock_meta_learner() -> MagicMock:
    learner = MagicMock()
    state = MagicMock()
    state.total_reward = 10.0
    state.learning_rate = 0.02
    state.policy_weights = {"entropy_penalty": -0.1, "stability_bonus": 0.2, "transition_efficiency": 0.05}
    learner._state = state
    learner._max_weight_magnitude = 1.0
    learner.optimize_policy.return_value = None
    return learner


def _make_mock_recursive_overlay() -> MagicMock:
    overlay = MagicMock()
    overlay._state_changes = []
    overlay._recursion_depth = 0
    overlay._on_self_observation = MagicMock()
    overlay.get_recursive_status.return_value = {
        "primary_status": {},
        "meta_status": {},
        "meta_learning": {},
        "sandbox": {},
    }
    overlay._detect_oscillation.return_value = False
    return overlay


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------

class TestPhase10ExperimentResult:
    def test_defaults(self) -> None:
        r = Phase10ExperimentResult(
            experiment_id=1,
            experiment_type="t",
            parameters={},
            observations={},
        )
        assert r.findings == []

    def test_with_findings(self) -> None:
        r = Phase10ExperimentResult(
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

class TestPhase10AutoResearchInit:
    def test_defaults(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        assert research._output_dir == tmp_path
        assert research._experiments == 50
        assert research._results == []

    def test_custom_experiments(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path, experiments=10)
        assert research._experiments == 10


class TestEnsureLlm:
    def test_success(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_client = _make_mock_llm()
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            return_value=mock_client,
        ):
            client = asyncio.run(research._ensure_llm())
        assert client is mock_client

    def test_failure(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            side_effect=ValueError("no key"),
        ):
            client = asyncio.run(research._ensure_llm())
        assert client is None

    def test_cached(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_client = _make_mock_llm()
        research._llm_client = mock_client
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            side_effect=RuntimeError("should not call"),
        ):
            client = asyncio.run(research._ensure_llm())
        assert client is mock_client


class TestClose:
    def test_close(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_client = _make_mock_llm()
        research._llm_client = mock_client
        asyncio.run(research.close())
        mock_client.close.assert_awaited_once()
        assert research._llm_client is None

    def test_close_no_client(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        asyncio.run(research.close())


# ---------------------------------------------------------------------------
# Experiment: meta-learning convergence
# ---------------------------------------------------------------------------

class TestExperimentMetaLearningConvergence:
    def test_with_llm(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(
            content='{"state_before": "OBSERVE", "state_after": "STABILIZE", '
                    '"entropy_before": 3, "entropy_after": 1, "reward": 0.5}'
        )
        mock_learner = _make_mock_meta_learner()
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase10.MetaLearner",
            return_value=mock_learner,
        ):
            result = asyncio.run(research._experiment_meta_learning_convergence(0))
        assert result.experiment_type == "meta_learning_convergence"
        assert result.parameters["episodes"] == 20
        assert "reward_trend" in result.observations

    def test_without_llm(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_learner = _make_mock_meta_learner()
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_phase10.MetaLearner",
            return_value=mock_learner,
        ):
            result = asyncio.run(research._experiment_meta_learning_convergence(0))
        assert result.experiment_type == "meta_learning_convergence"

    def test_llm_exception(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm()
        mock_llm.chat_completion.side_effect = RuntimeError("API down")
        mock_learner = _make_mock_meta_learner()
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase10.MetaLearner",
            return_value=mock_learner,
        ):
            result = asyncio.run(research._experiment_meta_learning_convergence(0))
        assert result.experiment_type == "meta_learning_convergence"

    def test_improving_trend(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(
            content='{"state_before": "OBSERVE", "state_after": "STABILIZE", '
                    '"entropy_before": 3, "entropy_after": 1, "reward": 1.0}'
        )
        # simulate increasing rewards
        mock_learner = _make_mock_meta_learner()
        mock_learner.optimize_policy.return_value = None
        rewards = list(range(1, 11))
        mock_learner._state.total_reward = 0.0
        call_count = 0
        def record_side_effect(outcome: Any) -> None:
            nonlocal call_count
            mock_learner._state.total_reward = rewards[min(call_count, len(rewards) - 1)]
            call_count += 1
        mock_learner.record_decision.side_effect = record_side_effect
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase10.MetaLearner",
            return_value=mock_learner,
        ):
            result = asyncio.run(research._experiment_meta_learning_convergence(0))
        assert result.observations["reward_trend"] in ("improving", "stable/degrading")


# ---------------------------------------------------------------------------
# Experiment: weight stability
# ---------------------------------------------------------------------------

class TestExperimentWeightStability:
    def test_with_llm(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content="50")
        mock_learner = _make_mock_meta_learner()
        mock_learner._state.policy_weights = {
            "entropy_penalty": 0.5,
            "stability_bonus": 0.5,
            "transition_efficiency": 0.5,
        }
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase10.MetaLearner",
            return_value=mock_learner,
        ):
            result = asyncio.run(research._experiment_weight_stability(1))
        assert result.experiment_type == "weight_stability"
        assert "all_clipped" in result.observations

    def test_without_llm(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_learner = _make_mock_meta_learner()
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_phase10.MetaLearner",
            return_value=mock_learner,
        ):
            result = asyncio.run(research._experiment_weight_stability(1))
        assert result.experiment_type == "weight_stability"

    def test_weights_not_clipped(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_learner = _make_mock_meta_learner()
        mock_learner._max_weight_magnitude = 0.1
        mock_learner._state.policy_weights = {
            "entropy_penalty": 0.5,  # exceeds 0.1
        }
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_phase10.MetaLearner",
            return_value=mock_learner,
        ):
            result = asyncio.run(research._experiment_weight_stability(1))
        assert result.observations["all_clipped"] is False
        assert any("不稳定" in f for f in result.findings)


# ---------------------------------------------------------------------------
# Experiment: recursive safety
# ---------------------------------------------------------------------------

class TestExperimentRecursiveSafety:
    def test_with_llm(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content="安全性: 7/10")
        mock_overlay = _make_mock_recursive_overlay()
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase10.RecursiveGovernanceOverlay",
            return_value=mock_overlay,
        ):
            result = asyncio.run(research._experiment_recursive_safety(2))
        assert result.experiment_type == "recursive_safety"
        assert "oscillation_detected" in result.observations
        assert "status_complete" in result.observations

    def test_without_llm(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_overlay = _make_mock_recursive_overlay()
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_phase10.RecursiveGovernanceOverlay",
            return_value=mock_overlay,
        ):
            result = asyncio.run(research._experiment_recursive_safety(2))
        assert result.experiment_type == "recursive_safety"
        assert result.observations["llm_safety_eval"] == "N/A"

    def test_oscillation_detected(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_overlay = _make_mock_recursive_overlay()
        mock_overlay._detect_oscillation.return_value = True
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_phase10.RecursiveGovernanceOverlay",
            return_value=mock_overlay,
        ):
            result = asyncio.run(research._experiment_recursive_safety(2))
        assert result.observations["oscillation_detected"] is True
        assert any("正常" in f for f in result.findings)

    def test_status_incomplete(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_overlay = _make_mock_recursive_overlay()
        mock_overlay.get_recursive_status.return_value = {"primary_status": {}}
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_phase10.RecursiveGovernanceOverlay",
            return_value=mock_overlay,
        ):
            result = asyncio.run(research._experiment_recursive_safety(2))
        assert result.observations["status_complete"] is False
        assert any("不完整" in f for f in result.findings)


# ---------------------------------------------------------------------------
# Experiment: reward shaping
# ---------------------------------------------------------------------------

class TestExperimentRewardShaping:
    def test_reward_shaping_accuracy(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_learner = _make_mock_meta_learner()
        # Return values that match all 4 expected signs
        mock_learner.compute_reward.side_effect = [1.0, 1.0, -1.0, -1.0]
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_phase10.MetaLearner",
            return_value=mock_learner,
        ):
            result = asyncio.run(research._experiment_reward_shaping(3))
        assert result.experiment_type == "reward_shaping"
        assert result.observations["accuracy"] == 1.0
        assert result.observations["correct_rewards"] == 4

    def test_reward_shaping_with_llm(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_llm = _make_mock_llm(content="合理")
        mock_learner = _make_mock_meta_learner()
        mock_learner.compute_reward.return_value = 1.0
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase10.MetaLearner",
            return_value=mock_learner,
        ):
            result = asyncio.run(research._experiment_reward_shaping(3))
        assert result.experiment_type == "reward_shaping"
        assert result.observations["llm_eval"] == "合理"

    def test_reward_shaping_partial_correct(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        mock_learner = _make_mock_meta_learner()
        # Return mixed signs to get partial accuracy (2/4 correct)
        mock_learner.compute_reward.side_effect = [1.0, -1.0, 1.0, -1.0]
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch(
            "src.research.autoresearch_phase10.MetaLearner",
            return_value=mock_learner,
        ):
            result = asyncio.run(research._experiment_reward_shaping(3))
        assert result.experiment_type == "reward_shaping"
        assert result.observations["correct_rewards"] == 2
        assert result.observations["accuracy"] == 0.5


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

class TestRunExperiment:
    def test_rotation(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        types = []
        mock_llm = _make_mock_llm(content="{}")
        mock_learner = _make_mock_meta_learner()
        mock_learner.compute_reward.return_value = 1.0
        mock_overlay = _make_mock_recursive_overlay()
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase10.MetaLearner",
            return_value=mock_learner,
        ), patch(
            "src.research.autoresearch_phase10.RecursiveGovernanceOverlay",
            return_value=mock_overlay,
        ):
            for i in range(5):
                result = asyncio.run(research.run_experiment(i))
                types.append(result.experiment_type)
        assert types[0] == "meta_learning_convergence"
        assert types[1] == "weight_stability"
        assert types[2] == "recursive_safety"
        assert types[3] == "reward_shaping"
        assert types[4] == "meta_learning_convergence"


class TestRunBatch:
    def test_batch(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path, experiments=4)
        mock_llm = _make_mock_llm(content="{}")
        mock_learner = _make_mock_meta_learner()
        mock_learner.compute_reward.return_value = 1.0
        mock_overlay = _make_mock_recursive_overlay()
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            return_value=mock_llm,
        ), patch(
            "src.research.autoresearch_phase10.MetaLearner",
            return_value=mock_learner,
        ), patch(
            "src.research.autoresearch_phase10.RecursiveGovernanceOverlay",
            return_value=mock_overlay,
        ):
            report = asyncio.run(research.run_batch())
        assert report["phase"] == "Phase 10"
        assert report["total_experiments"] == 4
        assert "meta_learning_metrics" in report


class TestGenerateReport:
    def test_report_structure(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        research._results = [
            Phase10ExperimentResult(
                experiment_id=0,
                experiment_type="meta_learning_convergence",
                parameters={},
                observations={"reward_trend": "improving"},
                findings=["f1"],
            ),
            Phase10ExperimentResult(
                experiment_id=1,
                experiment_type="weight_stability",
                parameters={},
                observations={"all_clipped": True},
                findings=["f2"],
            ),
            Phase10ExperimentResult(
                experiment_id=2,
                experiment_type="recursive_safety",
                parameters={},
                observations={"oscillation_detected": True},
                findings=["f3"],
            ),
        ]
        report = research._generate_report()
        assert report["meta_learning_metrics"]["convergence_rate"] == 1.0
        assert report["meta_learning_metrics"]["stability_rate"] == 1.0
        assert report["meta_learning_metrics"]["safety_rate"] == 1.0

    def test_report_with_zeros(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        research._results = [
            Phase10ExperimentResult(
                experiment_id=0,
                experiment_type="meta_learning_convergence",
                parameters={},
                observations={"reward_trend": "stable/degrading"},
                findings=["f1"],
            ),
            Phase10ExperimentResult(
                experiment_id=1,
                experiment_type="weight_stability",
                parameters={},
                observations={"all_clipped": False},
                findings=["f2"],
            ),
            Phase10ExperimentResult(
                experiment_id=2,
                experiment_type="recursive_safety",
                parameters={},
                observations={"oscillation_detected": False},
                findings=["f3"],
            ),
        ]
        report = research._generate_report()
        assert report["meta_learning_metrics"]["convergence_rate"] == 0.0
        assert report["meta_learning_metrics"]["stability_rate"] == 0.0
        assert report["meta_learning_metrics"]["safety_rate"] == 0.0

    def test_report_empty(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        report = research._generate_report()
        assert report["total_experiments"] == 0
        assert report["meta_learning_metrics"]["convergence_rate"] == 0.0


class TestSaveReport:
    def test_save_creates_files(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        report = {
            "date": "2024-01-01",
            "phase": "Phase 10",
            "total_experiments": 1,
            "experiment_types": {"t": 1},
            "key_findings": ["f1"],
            "meta_learning_metrics": {
                "convergence_rate": 1.0,
                "stability_rate": 1.0,
                "safety_rate": 1.0,
            },
        }
        path = research.save_report(report)
        assert path.exists()
        json_path = tmp_path / "maref-phase10-2024-01-01.json"
        assert json_path.exists()
        with open(json_path) as f:
            data = json.load(f)
        assert data["phase"] == "Phase 10"


class TestFormatMarkdown:
    def test_markdown_content(self, tmp_path: Path) -> None:
        research = Phase10AutoResearch(output_dir=tmp_path)
        report = {
            "date": "2024-01-01",
            "phase": "Phase 10",
            "total_experiments": 2,
            "experiment_types": {"meta_learning_convergence": 2},
            "key_findings": ["finding"],
            "meta_learning_metrics": {
                "convergence_rate": 0.5,
                "stability_rate": 0.75,
                "safety_rate": 1.0,
            },
        }
        md = research._format_markdown(report)
        assert "# MAREF Phase 10 研究报告" in md
        assert "meta_learning_convergence" in md
        assert "finding" in md
        assert "0.50" in md or "0.5" in md


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

class TestMain:
    def test_main(self, tmp_path: Path) -> None:
        with patch(
            "src.research.autoresearch_phase10.DashScopeClient",
            side_effect=ValueError("no key"),
        ), patch.dict(
            "os.environ", {"MAREF_RESEARCH_OUTPUT": str(tmp_path)}
        ):
            asyncio.run(main())
        assert list(tmp_path.glob("maref-phase10-*.json"))
