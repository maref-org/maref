"""
v0.50 W5-S2 — A4 TaskPreflight 生产真接线

覆盖：
- _run_harness_in_thread 生产实例化 UnifiedHarness 时注入 task_preflight
- 生产路径缺证据触发 preflight gate（fail-closed → FAILED + errors）
- TaskPreflight.execute 无独立取证证据时标记 self_declared=True
- 带独立证据时 self_declared=False
"""

from __future__ import annotations

import pytest

from maref.execution.harness.types import HarnessStatus
from maref.governance.task_preflight import TaskPreflight


class TestProdWiringInjectsPreflight:
    def test_run_harness_in_thread_constructs_with_task_preflight(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import maref.execution.server as server_mod

        captured: dict = {}

        class FakeHarness:
            def __init__(self, **kwargs) -> None:
                captured["task_preflight"] = kwargs.get("task_preflight")

            def configure(self, config) -> None:
                self._config = config

            def preflight(self, context=None) -> list[str]:
                return []

            def run(self, round_id: str) -> None:
                return None

        monkeypatch.setattr(server_mod, "UnifiedHarness", FakeHarness)
        server_mod._harness_results.clear()
        server_mod._run_harness_in_thread(
            "run_prod", {"harness_type": "unified", "level": "L1"}
        )
        assert captured.get("task_preflight") is not None
        assert isinstance(captured["task_preflight"], TaskPreflight)

    def test_prod_path_fails_closed_on_missing_evidence(self) -> None:
        import maref.execution.server as server_mod

        server_mod._harness_results.clear()
        server_mod._run_harness_in_thread(
            "run_gate", {"harness_type": "unified", "level": "L1"}
        )
        result = server_mod._harness_results["run_gate"]
        assert result.status == HarnessStatus.FAILED
        assert any("preflight" in e.lower() for e in result.errors)


class TestSelfDeclaredMarker:
    def test_no_evidence_marks_self_declared(self) -> None:
        result = TaskPreflight().execute({"agent_id": "a1", "task_description": "t"})
        assert result.self_declared is True

    def test_with_evidence_not_self_declared(self) -> None:
        context = {
            "agent_id": "a1",
            "task_description": "t",
            "readme_read": True,
            "readme_summary": "README covers pipeline",
            "selected_pipeline": "video_producer",
            "git_log_consulted": True,
            "git_log_entries": 3,
            "alternatives_considered": ["alt_a", "alt_b"],
            "alternatives_rationale": "chose alt_b",
            "decision_logged": True,
            "decision_log_location": "audit://x/1",
            "action": "file.read",
        }
        result = TaskPreflight().execute(context)
        assert result.self_declared is False

    def test_self_declared_in_to_dict(self) -> None:
        result = TaskPreflight().execute({"agent_id": "a1", "task_description": "t"})
        payload = result.to_dict()
        assert payload["self_declared"] is True
