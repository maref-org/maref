from __future__ import annotations

from maref.desktop.context_isolation import (
    ContextIsolation,
    ContextSnapshot,
    SubAgentSpawner,
    SubAgentSummary,
)


class TestSubAgentSummary:
    def test_to_dict(self) -> None:
        summary = SubAgentSummary(
            isolation_id="s1",
            findings=["found bug"],
            files_explored=["main.py"],
            confidence=0.95,
            recommendations=["fix it"],
            errors=[],
            completion_time_ms=100.0,
        )
        d = summary.to_dict()
        assert d["isolation_id"] == "s1"
        assert len(d["findings"]) == 1
        assert d["confidence"] == 0.95

    def test_from_dict(self) -> None:
        data = {
            "isolation_id": "s2",
            "findings": ["a", "b"],
            "files_explored": ["x.py"],
            "confidence": 0.8,
            "recommendations": [],
            "errors": ["timeout"],
            "completion_time_ms": 200.0,
        }
        summary = SubAgentSummary.from_dict(data)
        assert summary.isolation_id == "s2"
        assert summary.confidence == 0.8
        assert "timeout" in summary.errors

    def test_defaults(self) -> None:
        summary = SubAgentSummary(isolation_id="s3")
        assert summary.findings == []
        assert summary.confidence == 0.0
        assert summary.completion_time_ms == 0.0


class TestContextSnapshot:
    def test_context_size(self) -> None:
        snap = ContextSnapshot(
            isolation_id="s1",
            parent_id="p1",
            context={"key": "value"},
        )
        assert snap.context_size > 0

    def test_summary_size_none(self) -> None:
        snap = ContextSnapshot(isolation_id="s1", parent_id="p1")
        assert snap.summary_size == 0

    def test_summary_size_with_summary(self) -> None:
        summary = SubAgentSummary(isolation_id="s1", findings=["result"])
        snap = ContextSnapshot(
            isolation_id="s1",
            parent_id="p1",
            summary=summary,
        )
        assert snap.summary_size > 0

    def test_token_savings_pct_no_summary(self) -> None:
        snap = ContextSnapshot(isolation_id="s1", parent_id="p1")
        assert snap.token_savings_pct == 0.0

    def test_token_savings_pct_no_summary(self) -> None:
        snap = ContextSnapshot(
            isolation_id="s1",
            parent_id="p1",
            context={"k": "v" * 100},
        )
        assert snap.token_savings_pct == 0.0

    def test_token_savings_pct_calculated(self) -> None:
        summary = SubAgentSummary(isolation_id="s1", findings=["short"])
        snap = ContextSnapshot(
            isolation_id="s1",
            parent_id="p1",
            context={"very_long_key": "x" * 1000},
            summary=summary,
        )
        assert snap.token_savings_pct > 50.0

    def test_to_dict_with_summary(self) -> None:
        summary = SubAgentSummary(isolation_id="s1", findings=["result"])
        snap = ContextSnapshot(
            isolation_id="s1",
            parent_id="p1",
            summary=summary,
        )
        d = snap.to_dict()
        assert d["isolation_id"] == "s1"
        assert d["summary"] is not None

    def test_to_dict_no_summary(self) -> None:
        snap = ContextSnapshot(isolation_id="s1", parent_id="p1")
        d = snap.to_dict()
        assert d["summary"] is None


class TestContextIsolation:
    def test_snapshot_creates_and_stores(self) -> None:
        ci = ContextIsolation()
        snap = ci.snapshot("iso-1", {"agent_id": "agent-1", "data": "test"})
        assert snap.isolation_id == "iso-1"
        assert snap.parent_id == "agent-1"
        assert snap.context["data"] == "test"

    def test_isolate_returns_none_if_missing(self) -> None:
        ci = ContextIsolation()
        assert ci.isolate("nonexistent", ["key"]) is None

    def test_isolate_filters_keys(self) -> None:
        ci = ContextIsolation()
        ci.snapshot("iso-2", {"agent_id": "a1", "keep": "yes", "drop": "no"})
        snap = ci.isolate("iso-2", ["keep"])
        assert snap is not None
        assert snap.filtered_context.get("keep") == "yes"
        assert snap.filtered_context.get("drop") is None

    def test_merge_summary(self) -> None:
        ci = ContextIsolation()
        ci.snapshot("iso-3", {"agent_id": "a1"})
        summary = SubAgentSummary(isolation_id="iso-3", findings=["done"])
        result = ci.merge_summary("iso-3", summary)
        assert result is not None
        assert result.summary is not None
        assert result.summary.findings == ["done"]

    def test_merge_summary_nonexistent(self) -> None:
        ci = ContextIsolation()
        summary = SubAgentSummary(isolation_id="x", findings=["x"])
        assert ci.merge_summary("x", summary) is None

    def test_estimate_token_savings(self) -> None:
        ci = ContextIsolation()
        savings = ci.estimate_token_savings(1000, 200)
        assert abs(savings - 0.80) < 0.01

    def test_estimate_token_savings_zero_parent(self) -> None:
        ci = ContextIsolation()
        assert ci.estimate_token_savings(0, 100) == 0.0

    def test_cleanup_removes_isolation(self) -> None:
        ci = ContextIsolation()
        ci.snapshot("iso-4", {"agent_id": "a1"})
        ci.cleanup("iso-4")
        assert ci.isolate("iso-4", ["agent_id"]) is None

    def test_cleanup_nonexistent(self) -> None:
        ci = ContextIsolation()
        ci.cleanup("nonexistent")


class TestSubAgentSpawner:
    def test_spawn_creates_isolation(self) -> None:
        spawner = SubAgentSpawner()
        agent_id = spawner.spawn(
            parent_id="parent-1",
            task_description="explore codebase",
            context={"files": ["a.py", "b.py"]},
            keys_to_explore=["files"],
        )
        assert agent_id.startswith("subagent-parent-1")
        assert spawner.get_active_count() == 1

    def test_complete_creates_summary(self) -> None:
        spawner = SubAgentSpawner()
        agent_id = spawner.spawn(
            parent_id="parent-1",
            task_description="find bugs",
            context={"files": ["a.py"]},
            keys_to_explore=["files"],
        )
        summary = spawner.complete(
            isolation_id=agent_id,
            findings=["found bug in a.py"],
            files_explored=["a.py"],
            confidence=0.9,
        )
        assert summary.findings == ["found bug in a.py"]
        assert summary.completion_time_ms > 0

    def test_get_summary(self) -> None:
        spawner = SubAgentSpawner()
        agent_id = spawner.spawn("p1", "task", {"k": "v"}, ["k"])
        spawner.complete(agent_id, ["finding"], ["f.py"])
        summary = spawner.get_summary(agent_id)
        assert summary is not None
        assert summary.findings == ["finding"]

    def test_get_summary_nonexistent(self) -> None:
        spawner = SubAgentSpawner()
        assert spawner.get_summary("nonexistent") is None

    def test_get_token_savings(self) -> None:
        spawner = SubAgentSpawner()
        agent_id = spawner.spawn("p1", "task", {"k": "v" * 500}, ["k"])
        spawner.complete(agent_id, [], [])
        savings = spawner.get_token_savings(agent_id)
        assert savings > 0.0

    def test_get_token_savings_nonexistent(self) -> None:
        spawner = SubAgentSpawner()
        assert spawner.get_token_savings("nonexistent") == 0.0

    def test_cleanup(self) -> None:
        spawner = SubAgentSpawner()
        agent_id = spawner.spawn("p1", "task", {"k": "v"}, ["k"])
        spawner.cleanup(agent_id)
        assert spawner.get_active_count() == 0
        assert spawner.get_summary(agent_id) is None

    def test_cleanup_nonexistent(self) -> None:
        spawner = SubAgentSpawner()
        spawner.cleanup("nonexistent")

    def test_active_count(self) -> None:
        spawner = SubAgentSpawner()
        assert spawner.get_active_count() == 0
        a1 = spawner.spawn("p1", "t1", {"k": "v"}, ["k"])
        assert spawner.get_active_count() == 1
        a2 = spawner.spawn("p2", "t2", {"k": "v"}, ["k"])
        assert spawner.get_active_count() == 2
        spawner.complete(a1, [], [])
        assert spawner.get_active_count() == 1
        spawner.cleanup(a2)
        assert spawner.get_active_count() == 0
