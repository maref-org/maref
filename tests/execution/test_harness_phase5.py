"""Phase 5 测试：多Agent 协调 — MultiAgentCoordinator + HarnessTaskDecomposer。"""

from __future__ import annotations

from maref.execution.harness.base import BaseHarness
from maref.execution.harness.types import HarnessConfig, HarnessResult, HarnessStatus
from maref.execution.multi_agent.coordinator import MultiAgentCoordinator
from maref.execution.multi_agent.decomposer import HarnessTaskDecomposer


# ── Dummy harness for testing ──────────────────────────────────────────────

class _DummyHarness(BaseHarness):
    def __init__(self, name: str = "dummy", fail: bool = False) -> None:
        super().__init__()
        self._name = name
        self._fail = fail
        self._configured = False

    def configure(self, config: HarnessConfig) -> None:
        self._config = config
        self._configured = True

    def run(self, round_id: str = "") -> HarnessResult:
        if self._fail:
            return HarnessResult(
                harness_type=self._name,
                round_id=round_id,
                status=HarnessStatus.FAILED,
                errors=["simulated failure"],
            )
        return HarnessResult(
            harness_type=self._name,
            round_id=round_id,
            status=HarnessStatus.SUCCEEDED,
            duration_s=0.01,
            metrics={"name": self._name},
        )


# ── MultiAgentCoordinator ──────────────────────────────────────────────────

class TestMultiAgentCoordinator:
    def test_add_agent_and_count(self) -> None:
        c = MultiAgentCoordinator()
        c.add_agent(_DummyHarness("a"), "reader")
        c.add_agent(_DummyHarness("b"), "writer")
        assert c.agent_count == 2
        assert c.roles == ["reader", "writer"]

    def test_run_all_sequential(self) -> None:
        c = MultiAgentCoordinator()
        c.add_agent(_DummyHarness("a"), "reader")
        c.add_agent(_DummyHarness("b"), "writer")
        results = c.run_all("test_task")
        assert len(results) == 2
        for r in results.values():
            assert r.status == HarnessStatus.SUCCEEDED

    def test_run_all_with_failure(self) -> None:
        c = MultiAgentCoordinator()
        c.add_agent(_DummyHarness("ok"), "ok")
        c.add_agent(_DummyHarness("bad", fail=True), "bad")
        results = c.run_all("test")
        assert results["agent_1"].status == HarnessStatus.SUCCEEDED
        assert results["agent_2"].status == HarnessStatus.FAILED

    def test_aggregate_all_success(self) -> None:
        c = MultiAgentCoordinator()
        c.add_agent(_DummyHarness("a"), "reader")
        c.add_agent(_DummyHarness("b"), "writer")
        results = c.run_all()
        agg = c.aggregate(results)
        assert agg["total_agents"] == 2
        assert agg["succeeded"] == 2
        assert agg["failed"] == 0

    def test_aggregate_with_failures(self) -> None:
        c = MultiAgentCoordinator()
        c.add_agent(_DummyHarness("ok"), "ok")
        c.add_agent(_DummyHarness("bad", fail=True), "bad")
        results = c.run_all()
        agg = c.aggregate(results)
        assert agg["succeeded"] == 1
        assert agg["failed"] == 1

    def test_run_all_with_config(self) -> None:
        c = MultiAgentCoordinator()
        h = _DummyHarness("cfg")
        c.add_agent(h, "tester")
        config = HarnessConfig(harness_type="test", level="L3")
        c.run_all(config=config)
        assert h._configured

    def test_empty_coordinator(self) -> None:
        c = MultiAgentCoordinator()
        assert c.agent_count == 0
        assert c.run_all() == {}
        assert c.aggregate({})["total_agents"] == 0


# ── HarnessTaskDecomposer ──────────────────────────────────────────────────

class TestHarnessTaskDecomposer:
    def test_decompose(self) -> None:
        d = HarnessTaskDecomposer()
        agents = {"a1": "reader", "a2": "writer", "a3": "reviewer"}
        tasks = d.decompose("build report", agents)
        assert len(tasks) == 3
        assert "[reader]" in tasks["a1"]
        assert "[writer]" in tasks["a2"]
        assert "[reviewer]" in tasks["a3"]

    def test_merge_all_success(self) -> None:
        d = HarnessTaskDecomposer()
        results = {
            "a1": HarnessResult(status=HarnessStatus.SUCCEEDED, duration_s=1.0),
            "a2": HarnessResult(status=HarnessStatus.SUCCEEDED, duration_s=2.0),
        }
        merged = d.merge(results)
        assert merged.status == HarnessStatus.SUCCEEDED
        assert merged.duration_s == 2.0  # max

    def test_merge_with_errors(self) -> None:
        d = HarnessTaskDecomposer()
        results = {
            "a1": HarnessResult(status=HarnessStatus.SUCCEEDED),
            "a2": HarnessResult(status=HarnessStatus.FAILED, errors=["err1"]),
        }
        merged = d.merge(results)
        assert merged.status == HarnessStatus.FAILED
        assert any("a2" in e for e in merged.errors)

    def test_merge_includes_metrics(self) -> None:
        d = HarnessTaskDecomposer()
        results = {
            "a1": HarnessResult(status=HarnessStatus.SUCCEEDED, metrics={"score": 95}),
        }
        merged = d.merge(results)
        assert merged.metrics["a1/score"] == 95
