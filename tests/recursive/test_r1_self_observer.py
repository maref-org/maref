from __future__ import annotations

import pytest

from maref.observation.probes import ProbeReading
from maref.recursive.self_observer import SelfObserver, SystemSnapshot


class TestSelfObserver:
    @pytest.fixture
    def observer(self) -> SelfObserver:
        return SelfObserver()

    @pytest.mark.slow
    def test_snapshot_returns_system_snapshot(self, observer: SelfObserver) -> None:
        snapshot = observer.snapshot()
        assert isinstance(snapshot, SystemSnapshot)
        assert snapshot.timestamp > 0

    @pytest.mark.slow
    def test_observe_codebase_scans_source_files(self, observer: SelfObserver) -> None:
        module_graph = observer.observe_codebase()
        assert len(module_graph) >= 20, f"Expected >=20 modules, got {len(module_graph)}"
        for module_name, deps in module_graph.items():
            assert isinstance(module_name, str)
            assert isinstance(deps, list)

    @pytest.mark.slow
    def test_observe_tests_collects_statistics(self, observer: SelfObserver) -> None:
        stats = observer.observe_tests(collect_only=True)
        assert stats["total"] >= 649, f"Expected >=649 tests, got {stats['total']}"
        assert "passed" in stats
        assert "coverage_pct" in stats

    @pytest.mark.slow
    def test_observe_git_returns_tags(self, observer: SelfObserver) -> None:
        git_stats = observer.observe_git()
        assert len(git_stats["tags"]) >= 9, f"Expected >=9 tags, got {len(git_stats['tags'])}"
        assert "v0.52.0" in git_stats["tags"]

    @pytest.mark.slow
    def test_snapshot_includes_module_graph(self, observer: SelfObserver) -> None:
        snapshot = observer.snapshot()
        assert len(snapshot.module_graph) >= 20

    @pytest.mark.slow
    def test_snapshot_includes_test_stats(self, observer: SelfObserver) -> None:
        snapshot = observer.snapshot(collect_only=True)
        assert snapshot.test_stats["total"] >= 649

    @pytest.mark.slow
    def test_snapshot_includes_git_stats(self, observer: SelfObserver) -> None:
        snapshot = observer.snapshot()
        assert len(snapshot.git_stats["tags"]) >= 9

    @pytest.mark.slow
    def test_snapshot_probe_readings_normal(self, observer: SelfObserver) -> None:
        snapshot = observer.snapshot()
        for reading in snapshot.probe_readings:
            assert isinstance(reading, ProbeReading)

    @pytest.mark.slow
    def test_self_observer_uses_root_path(self) -> None:
        import pathlib

        custom_root = pathlib.Path(__file__).resolve().parent.parent.parent
        observer = SelfObserver(root_path=custom_root)
        module_graph = observer.observe_codebase()
        assert len(module_graph) >= 1

    @pytest.mark.slow
    def test_system_snapshot_defaults(self) -> None:
        snapshot = SystemSnapshot()
        assert snapshot.module_graph == {}
        assert snapshot.source_file_count == 0
