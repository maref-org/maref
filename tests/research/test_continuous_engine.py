"""Comprehensive tests for continuous_engine.py."""

from __future__ import annotations

import asyncio
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Patch heavy/IO dependencies before importing the module under test.
# This avoids importing chromadb, aiohttp, dotenv, structlog, etc.
sys.modules["dotenv"] = MagicMock()
sys.modules["structlog"] = MagicMock()

# Provide a dummy logger that supports .info(), .warning(), .debug(), .error()
_dummy_logger = MagicMock()
sys.modules["structlog"].get_logger = lambda *a, **k: _dummy_logger

# Build lightweight fake classes for dependencies.


@dataclass
class FakeBatchAnalysis:
    key_insights: list[str] = None  # type: ignore[assignment]
    patterns_detected: list[str] = None  # type: ignore[assignment]
    anomalies_flagged: list[str] = None  # type: ignore[assignment]
    recommendations: list[str] = None  # type: ignore[assignment]
    overall_assessment: str = "good"


class FakeDashScopeClient:
    def __init__(self, model: str | None = None) -> None:
        self.model = model
        self.closed = False

    async def analyze_batch(self, **kwargs: Any) -> FakeBatchAnalysis:
        return FakeBatchAnalysis(
            key_insights=["insight1"],
            patterns_detected=["pattern1"],
            anomalies_flagged=[],
            recommendations=["rec1"],
            overall_assessment="ok",
        )

    async def close(self) -> None:
        self.closed = True


class FakeKnowledgeGraph:
    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path
        self._findings: list[dict[str, Any]] = []
        self._hypotheses: list[dict[str, Any]] = []

    def add_finding(self, content: str, source: str, metadata: dict[str, Any] | None = None) -> None:
        self._findings.append({"content": content, "source": source, "metadata": metadata or {}})

    def add_hypothesis(self, content: str, source: str) -> None:
        self._hypotheses.append({"content": content, "source": source})

    def get_stats(self) -> dict[str, Any]:
        return {"total_nodes": len(self._findings) + len(self._hypotheses)}

    def query(self, metric_name: str) -> list[Any]:
        return []

    def get_open_questions(self) -> list[Any]:
        return []


class FakeVectorStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._findings: list[dict[str, Any]] = []

    def add_finding(self, content: str, metadata: dict[str, Any] | None = None) -> None:
        self._findings.append({"content": content, "metadata": metadata or {}})

    def count(self) -> int:
        return len(self._findings)

    def search(self, query: str, n_results: int = 5) -> list[Any]:
        return []


@dataclass
class FakeExpResult:
    findings: list[str]
    novelty: float = 0.5
    duration_ms: float = 100.0


class FakeOrchestrator:
    def __init__(self, registry: Any = None, criteria: Any = None, vector_store: Any = None) -> None:
        self._registry = registry
        self._criteria = criteria
        self._vector_store = vector_store
        self._batch_results: list[Any] = []
        self._stop_after: int = 0
        self._calls = 0
        self._exp_fn: Any = None
        self._exp_name: str = ""

    def reset_batch(self) -> None:
        self._batch_results.clear()
        self._calls = 0

    def should_stop(self) -> bool:
        return self._calls >= self._stop_after

    def select_next_experiment(self) -> tuple[str, Any]:
        self._calls += 1
        if self._calls > self._stop_after:
            return "none", None
        return self._exp_name or "random_walk", self._exp_fn

    def record_result(self, name: str, result: Any) -> None:
        self._batch_results.append(result)

    def get_stats(self) -> dict[str, Any]:
        return {"batch_size": len(self._batch_results)}


class FakeRecovery:
    def __init__(self) -> None:
        self._results: list[Any] = []
        self._idx = 0

    async def run_with_recovery(self, fn: Any, degrade_fn: Any = None) -> Any:
        result = self._results[self._idx % len(self._results)]
        self._idx += 1
        # simulate coroutine if fn is one
        if asyncio.iscoroutinefunction(fn):
            await fn()
        else:
            fn()
        return result

    def get_stats(self) -> dict[str, Any]:
        return {"consecutive_failures": 0, "total_failures": 0, "needs_attention": False}


class FakeDiscovery:
    def __init__(self, knowledge_graph: Any = None) -> None:
        self._kg = knowledge_graph

    def get_insights(self) -> list[str]:
        return ["insight_a"]

    def generate_hypotheses(self) -> list[Any]:
        return []


class FakeGeneratedHypothesis:
    def __init__(self, hypothesis: str, suggested_experiment: str) -> None:
        self.hypothesis = hypothesis
        self.suggested_experiment = suggested_experiment


# Pre-populate fake submodules so continuous_engine imports lightweight stubs.
_dashscope_mod = types.ModuleType("research.dashscope_client")
_dashscope_mod.DashScopeClient = FakeDashScopeClient  # type: ignore[attr-defined]
sys.modules["research.dashscope_client"] = _dashscope_mod

_discovery_mod = types.ModuleType("research.discovery_engine")
_discovery_mod.DiscoveryEngine = FakeDiscovery  # type: ignore[attr-defined]
_discovery_mod.GeneratedHypothesis = FakeGeneratedHypothesis  # type: ignore[attr-defined]
sys.modules["research.discovery_engine"] = _discovery_mod

_registry_mod = types.ModuleType("research.experiment_registry")
_registry_mod.ExperimentRegistry = MagicMock  # type: ignore[attr-defined]
sys.modules["research.experiment_registry"] = _registry_mod

_recovery_mod = types.ModuleType("research.fault_recovery")
_recovery_mod.FaultRecovery = FakeRecovery  # type: ignore[attr-defined]
_recovery_mod.RecoveryResult = lambda **kw: MagicMock(**kw)  # type: ignore[attr-defined]
sys.modules["research.fault_recovery"] = _recovery_mod

_kg_mod = types.ModuleType("research.knowledge_graph")
_kg_mod.KnowledgeGraph = FakeKnowledgeGraph  # type: ignore[attr-defined]
sys.modules["research.knowledge_graph"] = _kg_mod

_orchestrator_mod = types.ModuleType("research.orchestrator")
_orchestrator_mod.ExperimentOrchestrator = FakeOrchestrator  # type: ignore[attr-defined]
_orchestrator_mod.StoppingCriteria = MagicMock  # type: ignore[attr-defined]
sys.modules["research.orchestrator"] = _orchestrator_mod

_vs_mod = types.ModuleType("research.vector_store")
_vs_mod.VectorKnowledgeStore = FakeVectorStore  # type: ignore[attr-defined]
sys.modules["research.vector_store"] = _vs_mod

# Now safe to import the module under test.
from research.continuous_engine import ContinuousAutoResearch, ContinuousReport, main


# ---------------------------------------------------------------------------
# ContinuousReport tests
# ---------------------------------------------------------------------------


class TestContinuousReport:
    def test_construction_all_fields(self) -> None:
        report = ContinuousReport(
            timestamp="2024-01-01T00:00:00",
            batch_id=1,
            experiments_run=10,
            findings_count=5,
            experiments_by_type={"random_walk": 5},
            top_findings=["finding1"],
            insights=["insight1"],
            knowledge_graph_stats={"nodes": 3},
            orchestrator_stats={"score": 0.5},
            recovery_stats={"failures": 0},
            llm_analysis={"key": "value"},
        )
        assert report.batch_id == 1
        assert report.llm_analysis == {"key": "value"}

    def test_default_llm_analysis_is_none(self) -> None:
        report = ContinuousReport(
            timestamp="2024-01-01T00:00:00",
            batch_id=0,
            experiments_run=0,
            findings_count=0,
            experiments_by_type={},
            top_findings=[],
            insights=[],
            knowledge_graph_stats={},
            orchestrator_stats={},
            recovery_stats={},
        )
        assert report.llm_analysis is None

    def test_to_dict(self) -> None:
        report = ContinuousReport(
            timestamp="2024-01-01T00:00:00",
            batch_id=2,
            experiments_run=5,
            findings_count=3,
            experiments_by_type={"a": 1},
            top_findings=["f1"],
            insights=["i1"],
            knowledge_graph_stats={"n": 1},
            orchestrator_stats={"s": 1},
            recovery_stats={"r": 1},
            llm_analysis=None,
        )
        d = report.to_dict()
        assert d["batch_id"] == 2
        assert d["llm_analysis"] is None
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# ContinuousAutoResearch construction / init tests
# ---------------------------------------------------------------------------


class TestContinuousAutoResearchInit:
    def test_default_values(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path)
        assert engine._output_dir == tmp_path
        assert engine._experiments_per_batch == 50
        assert engine._batch_interval == 10.0 * 60.0
        assert engine._batch_count == 0
        assert engine._enable_llm_analysis is True
        assert engine._llm_model is None
        assert engine._llm_client is None

    def test_custom_values(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(
            output_dir=tmp_path,
            experiments_per_batch=20,
            batch_interval_minutes=5.0,
            enable_llm_analysis=False,
            llm_model="qwen-max",
        )
        assert engine._experiments_per_batch == 20
        assert engine._batch_interval == 5.0 * 60.0
        assert engine._enable_llm_analysis is False
        assert engine._llm_model == "qwen-max"

    def test_knowledge_graph_path(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path)
        assert isinstance(engine._kg, FakeKnowledgeGraph)
        assert engine._kg.storage_path == tmp_path / "knowledge_graph.json"

    def test_components_initialized(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path)
        assert isinstance(engine._vks, FakeVectorStore)
        assert isinstance(engine._orchestrator, FakeOrchestrator)
        assert isinstance(engine._discovery, FakeDiscovery)
        assert isinstance(engine._recovery, FakeRecovery)


# ---------------------------------------------------------------------------
# _ensure_llm_client tests
# ---------------------------------------------------------------------------


class TestEnsureLlmClient:
    async def test_disabled_returns_none(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path, enable_llm_analysis=False)
        result = await engine._ensure_llm_client()
        assert result is None

    async def test_returns_existing_client(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path)
        client = FakeDashScopeClient()
        engine._llm_client = client
        result = await engine._ensure_llm_client()
        assert result is client

    async def test_lazy_initialization(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path, llm_model="qwen-turbo")
        result = await engine._ensure_llm_client()
        assert isinstance(result, FakeDashScopeClient)
        assert result.model == "qwen-turbo"
        assert engine._llm_client is result

    async def test_value_error_disables_llm(self, tmp_path: Path) -> None:
        # Simulate DashScopeClient raising ValueError on init.
        class BadClient:
            def __init__(self, model: str | None = None) -> None:
                raise ValueError("no key")

        with patch.dict("sys.modules", {"research.dashscope_client": MagicMock(DashScopeClient=BadClient)}):
            # Need to re-import or patch directly on the class.
            pass

        # Simpler: monkey-patch the reference inside continuous_engine.
        import research.continuous_engine as ce_mod

        original = ce_mod.DashScopeClient
        try:
            ce_mod.DashScopeClient = BadClient
            engine = ContinuousAutoResearch(output_dir=tmp_path)
            result = await engine._ensure_llm_client()
            assert result is None
            assert engine._enable_llm_analysis is False
        finally:
            ce_mod.DashScopeClient = original


# ---------------------------------------------------------------------------
# run_batch tests
# ---------------------------------------------------------------------------


class TestRunBatch:
    @pytest.fixture
    def engine(self, tmp_path: Path) -> ContinuousAutoResearch:
        return ContinuousAutoResearch(output_dir=tmp_path, enable_llm_analysis=False)

    async def test_empty_batch_when_no_experiments(self, engine: ContinuousAutoResearch) -> None:
        engine._orchestrator._stop_after = 0
        report = await engine.run_batch()
        assert report.experiments_run == 0
        assert report.findings_count == 0
        assert report.batch_id == 0
        assert report.experiments_by_type == {}

    async def test_batch_with_findings_no_llm(self, engine: ContinuousAutoResearch) -> None:
        fake_result = MagicMock(success=True, result=FakeExpResult(findings=["finding1", "finding2"]))
        engine._recovery._results = [fake_result]
        engine._orchestrator._stop_after = 1
        engine._orchestrator._exp_name = "random_walk"
        engine._orchestrator._exp_fn = lambda batch: None

        report = await engine.run_batch()
        assert report.experiments_run == 1
        assert report.findings_count == 2
        assert report.experiments_by_type.get("random_walk") == 1
        assert "finding1" in report.top_findings
        assert report.insights == ["insight_a"]
        assert report.llm_analysis is None
        assert engine._batch_count == 1

    async def test_batch_with_llm_analysis(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path, enable_llm_analysis=True)
        fake_result = MagicMock(success=True, result=FakeExpResult(findings=["f1"]))
        engine._recovery._results = [fake_result]
        engine._orchestrator._stop_after = 1
        engine._orchestrator._exp_name = "random_walk"
        engine._orchestrator._exp_fn = lambda batch: None

        report = await engine.run_batch()
        assert report.llm_analysis is not None
        assert report.llm_analysis["overall_assessment"] == "ok"

    async def test_batch_llm_analysis_failure(self, tmp_path: Path) -> None:
        class FailingClient(FakeDashScopeClient):
            async def analyze_batch(self, **kwargs: Any) -> FakeBatchAnalysis:
                raise RuntimeError("api down")

        engine = ContinuousAutoResearch(output_dir=tmp_path, enable_llm_analysis=True)
        engine._llm_client = FailingClient()
        fake_result = MagicMock(success=True, result=FakeExpResult(findings=["f1"]))
        engine._recovery._results = [fake_result]
        engine._orchestrator._stop_after = 1
        engine._orchestrator._exp_name = "random_walk"
        engine._orchestrator._exp_fn = lambda batch: None

        report = await engine.run_batch()
        assert report.llm_analysis is not None
        assert "error" in report.llm_analysis
        assert engine._llm_client.closed is True

    async def test_batch_records_kg_and_vks(self, engine: ContinuousAutoResearch) -> None:
        fake_result = MagicMock(success=True, result=FakeExpResult(findings=["kf1"]))
        engine._recovery._results = [fake_result]
        engine._orchestrator._stop_after = 1
        engine._orchestrator._exp_name = "self_observation"
        engine._orchestrator._exp_fn = lambda batch: None

        await engine.run_batch()
        assert len(engine._kg._findings) == 1
        assert engine._kg._findings[0]["content"] == "kf1"
        assert len(engine._vks._findings) == 1

    async def test_batch_hypotheses_added(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path, enable_llm_analysis=False)

        class HypDiscovery(FakeDiscovery):
            def generate_hypotheses(self) -> list[Any]:
                return [FakeGeneratedHypothesis("hyp1", "exp_a")]

        engine._discovery = HypDiscovery()
        fake_result = MagicMock(success=True, result=FakeExpResult(findings=["f"]))
        engine._recovery._results = [fake_result]
        engine._orchestrator._stop_after = 1
        engine._orchestrator._exp_fn = lambda batch: None

        await engine.run_batch()
        assert len(engine._kg._hypotheses) == 1
        assert engine._kg._hypotheses[0]["content"] == "hyp1"

    async def test_result_without_findings_attr(self, engine: ContinuousAutoResearch) -> None:
        fake_result = MagicMock(success=True, result=MagicMock())
        # result has no .findings
        del fake_result.result.findings
        engine._recovery._results = [fake_result]
        engine._orchestrator._stop_after = 1
        engine._orchestrator._exp_fn = lambda batch: None

        report = await engine.run_batch()
        assert report.findings_count == 0

    async def test_failed_experiment_not_counted(self, engine: ContinuousAutoResearch) -> None:
        fake_result = MagicMock(success=False, result=None, error="boom")
        engine._recovery._results = [fake_result]
        engine._orchestrator._stop_after = 1
        engine._orchestrator._exp_name = "random_walk"
        engine._orchestrator._exp_fn = lambda batch: None

        report = await engine.run_batch()
        assert report.experiments_run == 0
        assert report.findings_count == 0


# ---------------------------------------------------------------------------
# save_report tests
# ---------------------------------------------------------------------------


class TestSaveReport:
    def test_creates_json_and_markdown(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path)
        report = ContinuousReport(
            timestamp="2024-06-15T12:00:00",
            batch_id=3,
            experiments_run=5,
            findings_count=2,
            experiments_by_type={"random_walk": 5},
            top_findings=["f1"],
            insights=["i1"],
            knowledge_graph_stats={"n": 1},
            orchestrator_stats={"s": 1},
            recovery_stats={"r": 1},
            llm_analysis=None,
        )
        md_path = engine.save_report(report)
        assert md_path.exists()
        json_path = tmp_path / "batch_0003_2024-06-15.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert data["batch_id"] == 3

    def test_creates_output_dir_if_missing(self, tmp_path: Path) -> None:
        out = tmp_path / "nested" / "out"
        engine = ContinuousAutoResearch(output_dir=out)
        report = ContinuousReport(
            timestamp="2024-06-15T12:00:00",
            batch_id=0,
            experiments_run=0,
            findings_count=0,
            experiments_by_type={},
            top_findings=[],
            insights=[],
            knowledge_graph_stats={},
            orchestrator_stats={},
            recovery_stats={},
            llm_analysis=None,
        )
        engine.save_report(report)
        assert out.exists()


# ---------------------------------------------------------------------------
# _format_markdown tests
# ---------------------------------------------------------------------------


class TestFormatMarkdown:
    def test_contains_header_and_stats(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path)
        report = ContinuousReport(
            timestamp="2024-06-15T12:00:00",
            batch_id=7,
            experiments_run=10,
            findings_count=3,
            experiments_by_type={"random_walk": 5, "self_observation": 5},
            top_findings=["f1", "f2"],
            insights=["i1"],
            knowledge_graph_stats={"n": 2},
            orchestrator_stats={"s": 1},
            recovery_stats={"consecutive_failures": 0, "total_failures": 0, "needs_attention": False},
            llm_analysis=None,
        )
        md = engine._format_markdown(report)
        assert "# MAREF 持续研究 - 批次 7" in md
        assert "**实验运行数**: 10" in md
        assert "随机路径分析" in md
        assert "自观测" in md
        assert "f1" in md
        assert "i1" in md

    def test_llm_analysis_section(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path)
        report = ContinuousReport(
            timestamp="2024-06-15T12:00:00",
            batch_id=1,
            experiments_run=1,
            findings_count=1,
            experiments_by_type={},
            top_findings=["f"],
            insights=["i"],
            knowledge_graph_stats={},
            orchestrator_stats={},
            recovery_stats={},
            llm_analysis={
                "overall_assessment": "great",
                "key_insights": ["k1"],
                "patterns_detected": ["p1"],
                "anomalies_flagged": ["a1"],
                "recommendations": ["r1"],
            },
        )
        md = engine._format_markdown(report)
        assert "LLM 分析" in md
        assert "great" in md
        assert "k1" in md
        assert "p1" in md
        assert "a1" in md
        assert "r1" in md


# ---------------------------------------------------------------------------
# _detect_truncation tests
# ---------------------------------------------------------------------------


class TestDetectTruncation:
    def test_empty_string(self) -> None:
        assert ContinuousAutoResearch._detect_truncation("") is False

    def test_short_string(self) -> None:
        assert ContinuousAutoResearch._detect_truncation("hi") is False

    def test_natural_endings(self) -> None:
        ends = [
            "\u3002", "\uff01", "\uff1f", "\u2026", "\u201d",
            '"', ")", "\u3015", "]", "}", ">", ".", "!", "?",
        ]
        for end in ends:
            assert ContinuousAutoResearch._detect_truncation(f"some text{end}") is False

    def test_truncation_markers(self) -> None:
        for marker in (",", "，", "、", "：", ":", "；", ";"):
            text = "a" * 15 + marker
            assert ContinuousAutoResearch._detect_truncation(text) is True

    def test_long_chinese_no_end(self) -> None:
        text = "这是一个非常长的中文句子没有任何结尾符号超过二十个字符"
        assert ContinuousAutoResearch._detect_truncation(text) is True

    def test_long_chinese_with_end(self) -> None:
        text = "这是一个非常长的中文句子没有任何结尾符号。"
        assert ContinuousAutoResearch._detect_truncation(text) is False

    def test_just_above_threshold(self) -> None:
        text = "1234567890"
        assert ContinuousAutoResearch._detect_truncation(text) is False

    def test_stripped_empty(self) -> None:
        assert ContinuousAutoResearch._detect_truncation("     ") is False


# ---------------------------------------------------------------------------
# _compute_similarity tests
# ---------------------------------------------------------------------------


class TestComputeSimilarity:
    def test_identical(self) -> None:
        assert ContinuousAutoResearch._compute_similarity("abcdef", "abcdef") == 1.0

    def test_too_short(self) -> None:
        assert ContinuousAutoResearch._compute_similarity("abc", "def") == 0.0

    def test_completely_different(self) -> None:
        a = "the quick brown fox"
        b = "lorem ipsum dolor sit amet"
        sim = ContinuousAutoResearch._compute_similarity(a, b)
        assert sim >= 0.0
        assert sim < 0.3

    def test_partial_overlap(self) -> None:
        a = "hello world this is a test"
        b = "hello world this is another test"
        sim = ContinuousAutoResearch._compute_similarity(a, b)
        assert sim > 0.3
        assert sim < 1.0

    def test_newlines_collapsed(self) -> None:
        a = "hello\nworld\ntest"
        b = "hello world test"
        sim = ContinuousAutoResearch._compute_similarity(a, b)
        assert sim == 1.0


# ---------------------------------------------------------------------------
# _post_process_findings tests
# ---------------------------------------------------------------------------


class TestPostProcessFindings:
    def test_exact_deduplication(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path)
        findings = ["a", "b", "a", "c"]
        result = engine._post_process_findings(findings)
        assert result == ["a", "b", "c"]

    def test_truncation_marked(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path)
        findings = ["这是一个非常长的中文句子没有任何结尾符号超过二十个字符"]
        result = engine._post_process_findings(findings)
        assert result[0].endswith("…[截断]")

    def test_semantic_dedup(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path)
        a = "the quick brown fox jumps over the lazy dog"
        b = "the quick brown fox jumps over the lazy dog today"
        # Similarity should be > 0.75, so second is dropped.
        result = engine._post_process_findings([a, b])
        assert len(result) == 1
        assert result[0] == a

    def test_unique_preserved(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path)
        findings = ["apple", "banana", "cherry"]
        result = engine._post_process_findings(findings)
        assert result == findings


# ---------------------------------------------------------------------------
# run_continuous tests
# ---------------------------------------------------------------------------


class TestRunContinuous:
    async def test_runs_specified_batches(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path, batch_interval_minutes=0.0)
        # Mock run_batch to avoid full orchestration.
        batch_reports: list[int] = []

        async def fake_run_batch() -> ContinuousReport:
            report = ContinuousReport(
                timestamp="2024-01-01T00:00:00",
                batch_id=engine._batch_count,
                experiments_run=1,
                findings_count=0,
                experiments_by_type={},
                top_findings=[],
                insights=[],
                knowledge_graph_stats={},
                orchestrator_stats={},
                recovery_stats={},
            )
            engine._batch_count += 1
            return report

        engine.run_batch = fake_run_batch  # type: ignore[method-assign]
        engine.save_report = lambda r: tmp_path / "report.md"  # type: ignore[method-assign]

        await engine.run_continuous(max_batches=3)
        assert engine._batch_count == 3

    async def test_keyboard_interrupt_stops(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path, batch_interval_minutes=0.0)
        call_count = 0

        async def failing_batch() -> ContinuousReport:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise KeyboardInterrupt()
            engine._batch_count += 1
            return ContinuousReport(
                timestamp="2024-01-01T00:00:00",
                batch_id=engine._batch_count - 1,
                experiments_run=1,
                findings_count=0,
                experiments_by_type={},
                top_findings=[],
                insights=[],
                knowledge_graph_stats={},
                orchestrator_stats={},
                recovery_stats={},
            )

        engine.run_batch = failing_batch  # type: ignore[method-assign]
        engine.save_report = lambda r: tmp_path / "r.md"  # type: ignore[method-assign]

        await engine.run_continuous(max_batches=None)
        assert call_count == 2

    async def test_exception_continues_after_wait(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path, batch_interval_minutes=0.0)
        call_count = 0

        async def flaky_batch() -> ContinuousReport:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")
            engine._batch_count += 1
            return ContinuousReport(
                timestamp="2024-01-01T00:00:00",
                batch_id=engine._batch_count - 1,
                experiments_run=1,
                findings_count=0,
                experiments_by_type={},
                top_findings=[],
                insights=[],
                knowledge_graph_stats={},
                orchestrator_stats={},
                recovery_stats={},
            )

        engine.run_batch = flaky_batch  # type: ignore[method-assign]
        engine.save_report = lambda r: tmp_path / "r.md"  # type: ignore[method-assign]

        # Speed up error retry sleep.
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await engine.run_continuous(max_batches=2)

        assert call_count == 3
        mock_sleep.assert_awaited()

    async def test_infinite_loop_respects_max_batches(self, tmp_path: Path) -> None:
        engine = ContinuousAutoResearch(output_dir=tmp_path, batch_interval_minutes=0.0)
        call_count = 0

        async def counting_batch() -> ContinuousReport:
            nonlocal call_count
            call_count += 1
            engine._batch_count += 1
            return ContinuousReport(
                timestamp="2024-01-01T00:00:00",
                batch_id=engine._batch_count - 1,
                experiments_run=1,
                findings_count=0,
                experiments_by_type={},
                top_findings=[],
                insights=[],
                knowledge_graph_stats={},
                orchestrator_stats={},
                recovery_stats={},
            )

        engine.run_batch = counting_batch  # type: ignore[method-assign]
        engine.save_report = lambda r: tmp_path / "r.md"  # type: ignore[method-assign]

        await engine.run_continuous(max_batches=4)
        assert engine._batch_count == 4
        assert call_count == 4


# ---------------------------------------------------------------------------
# main tests
# ---------------------------------------------------------------------------


class TestMain:
    @pytest.mark.asyncio
    async def test_argument_parsing_defaults(self, tmp_path: Path) -> None:
        with patch("research.continuous_engine.ContinuousAutoResearch") as MockEngine:
            instance = AsyncMock()
            MockEngine.return_value = instance
            with patch("sys.argv", ["continuous_engine"]):
                await main()
            MockEngine.assert_called_once_with(
                output_dir=Path("research_output"),
                experiments_per_batch=50,
                batch_interval_minutes=10.0,
                enable_llm_analysis=True,
                llm_model=None,
            )
            instance.run_continuous.assert_awaited_once_with(max_batches=None)

    @pytest.mark.asyncio
    async def test_argument_parsing_custom(self, tmp_path: Path) -> None:
        out = tmp_path / "out"
        with patch("research.continuous_engine.ContinuousAutoResearch") as MockEngine:
            instance = AsyncMock()
            MockEngine.return_value = instance
            with patch(
                "sys.argv",
                [
                    "continuous_engine",
                    "--output-dir",
                    str(out),
                    "--experiments-per-batch",
                    "10",
                    "--batch-interval",
                    "2.5",
                    "--max-batches",
                    "5",
                    "--no-llm",
                    "--llm-model",
                    "qwen-max",
                ],
            ):
                await main()
            MockEngine.assert_called_once_with(
                output_dir=out,
                experiments_per_batch=10,
                batch_interval_minutes=2.5,
                enable_llm_analysis=False,
                llm_model="qwen-max",
            )
            instance.run_continuous.assert_awaited_once_with(max_batches=5)

    @pytest.mark.asyncio
    async def test_env_output_dir(self, tmp_path: Path) -> None:
        custom = tmp_path / "custom_out"
        with patch.dict("os.environ", {"MAREF_OUTPUT_DIR": str(custom)}):
            with patch("research.continuous_engine.ContinuousAutoResearch") as MockEngine:
                instance = AsyncMock()
                MockEngine.return_value = instance
                with patch("sys.argv", ["continuous_engine"]):
                    await main()
                args = MockEngine.call_args.kwargs
                assert args["output_dir"] == Path(str(custom))
