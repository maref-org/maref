from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maref.recursive.self_observer import SelfObserver, SystemSnapshot


class TestSystemSnapshot:
    def test_default_construction(self) -> None:
        s = SystemSnapshot()
        assert s.module_graph == {}
        assert s.test_stats == {}
        assert s.git_stats == {}
        assert s.state_machine_status == {}
        assert s.probe_readings == []
        assert s.source_file_count == 0
        assert s.total_lines == 0
        assert s.timestamp > 0

    def test_with_values(self) -> None:
        s = SystemSnapshot(
            timestamp=100.0,
            module_graph={"a": ["b"]},
            test_stats={"total": 5},
            git_stats={"tags": ["v1"]},
            source_file_count=10,
            total_lines=500,
        )
        assert s.timestamp == 100.0
        assert s.module_graph == {"a": ["b"]}
        assert s.test_stats == {"total": 5}
        assert s.source_file_count == 10
        assert s.total_lines == 500


class TestSelfObserver:
    def test_default_construction(self) -> None:
        o = SelfObserver()
        assert o._root is not None

    def test_custom_root(self) -> None:
        o = SelfObserver(root_path="/tmp")
        assert str(o._root) == "/tmp"

    def test_observe_codebase_handles_exceptions(self) -> None:
        o = SelfObserver(root_path="/tmp")
        graph = o.observe_codebase(root_path="/nonexistent_path_xyz")
        assert graph == {}

    def test_observe_codebase_parses_imports(self, tmp_path) -> None:
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "mod_a.py").write_text("import os\nimport sys\n")
        (src / "mod_b.py").write_text("from pathlib import Path\n")
        o = SelfObserver(root_path=str(tmp_path))
        graph = o.observe_codebase()
        assert len(graph) == 2
        rel_keys = {k.split(".")[-1] for k in graph}
        assert "mod_a" in rel_keys
        assert "mod_b" in rel_keys

    def test_observe_codebase_skips_pycache(self, tmp_path) -> None:
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "__pycache__").mkdir()
        (src / "__pycache__" / "cached.py").write_text("import os\n")
        (src / "real.py").write_text("import sys\n")
        o = SelfObserver(root_path=str(tmp_path))
        graph = o.observe_codebase()
        assert len(graph) == 1

    def test_observe_codebase_skips_bad_files(self, tmp_path) -> None:
        src = tmp_path / "src"
        src.mkdir(parents=True)
        bad = src / "bad.py"
        bad.write_text("this is not valid python \x00 null bytes")
        good = src / "good.py"
        good.write_text("import os\n")
        o = SelfObserver(root_path=str(tmp_path))
        graph = o.observe_codebase()
        # Both files are added to graph, but bad file has empty imports
        assert len(graph) == 2
        assert "src.good" in graph
        assert "src.bad" in graph
        assert graph["src.good"] == ["os"]
        assert graph["src.bad"] == []

    def test_observe_tests_collect_only(self) -> None:
        o = SelfObserver(root_path="/tmp")
        with patch("maref.recursive.self_observer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="10 tests collected in 0.1s\n", stderr=""
            )
            stats = o.observe_tests(collect_only=True)
            assert stats["total"] == 10
            assert "duration_ms" in stats

    def test_observe_tests_run_mode_passed(self) -> None:
        o = SelfObserver(root_path="/tmp")
        output = "100 passed in 1.5s\n"
        with patch("maref.recursive.self_observer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=output, stderr="")
            stats = o.observe_tests(collect_only=False)
            assert stats["passed"] == 100
            assert stats["failed"] == 0
            assert stats["errors"] == 0

    def test_observe_tests_run_mode_failed(self) -> None:
        o = SelfObserver(root_path="/tmp")
        output = "3 failed, 50 passed in 2.0s\n"
        with patch("maref.recursive.self_observer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=output, stderr="")
            stats = o.observe_tests(collect_only=False)
            assert stats["failed"] == 3
            assert stats["passed"] == 50

    def test_observe_tests_run_mode_errors(self) -> None:
        o = SelfObserver(root_path="/tmp")
        output = "10 errors, 100 passed in 3.0s\n"
        with patch("maref.recursive.self_observer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=output, stderr="")
            stats = o.observe_tests(collect_only=False)
            assert stats["errors"] == 10
            assert stats["passed"] == 100

    def test_observe_tests_timeout(self) -> None:
        import subprocess

        o = SelfObserver(root_path="/tmp")
        with patch("maref.recursive.self_observer.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=300)
            stats = o.observe_tests(collect_only=False)
            assert stats["total"] == 0
            assert stats["timeout"] is True

    def test_observe_git_no_tags(self) -> None:
        o = SelfObserver(root_path="/tmp")
        with patch("maref.recursive.self_observer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="fatal")
            stats = o.observe_git()
            assert stats["tags"] == []
            assert stats["commits_30d"] == 0
            assert stats["hot_files"] == []

    def test_observe_git_with_data(self) -> None:
        o = SelfObserver(root_path="/tmp")
        with patch("maref.recursive.self_observer.subprocess.run") as mock_run:
            def side_effect(*args, **kwargs):
                cmd = kwargs.get("args") or args[0]
                if "tag" in cmd:
                    return MagicMock(returncode=0, stdout="v1.0\nv2.0\n", stderr="")
                if "rev-list" in cmd:
                    return MagicMock(returncode=0, stdout="15\n", stderr="")
                if "log" in cmd:
                    return MagicMock(
                        returncode=0,
                        stdout="src/a.py\nsrc/b.py\nsrc/a.py\n",
                        stderr="",
                    )
                return MagicMock(returncode=0, stdout="", stderr="")
            mock_run.side_effect = side_effect
            stats = o.observe_git()
            assert stats["tags"] == ["v1.0", "v2.0"]
            assert stats["commits_30d"] == 15
            assert "src/a.py" in stats["hot_files"]

    def test_build_state_machine_status_success(self) -> None:
        o = SelfObserver(root_path="/tmp")
        with patch(
            "maref.governance.state_machine.GovernanceStateMachine"
        ) as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.current_state = "RUNNING"
            mock_sm.get_entropy_trend.return_value = 0.5
            mock_sm.transition_count = 3
            mock_sm_cls.return_value = mock_sm
            status = o._build_state_machine_status()
            assert status["current_state"] == "RUNNING"
            assert status["entropy"] == 0.5
            assert status["transition_count"] == 3

    def test_build_state_machine_status_failure(self) -> None:
        o = SelfObserver(root_path="/tmp")
        with patch(
            "maref.governance.state_machine.GovernanceStateMachine"
        ) as mock_sm_cls:
            mock_sm_cls.side_effect = ImportError("no module")
            status = o._build_state_machine_status()
            assert "error" in status

    def test_snapshot(self) -> None:
        o = SelfObserver(root_path="/tmp")
        with (
            patch.object(o, "observe_codebase", return_value={"mod": []}),
            patch.object(o, "observe_tests", return_value={"total": 10, "failed": 0}),
            patch.object(o, "observe_git", return_value={"tags": []}),
            patch.object(o, "_build_state_machine_status", return_value={}),
        ):
            snap = o.snapshot()
            assert isinstance(snap, SystemSnapshot)
            assert snap.module_graph == {"mod": []}
            assert snap.test_stats["total"] == 10