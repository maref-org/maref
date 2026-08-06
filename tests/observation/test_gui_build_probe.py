from __future__ import annotations

from unittest.mock import patch

from maref.observation.probes import BaseProbe
from maref.observation.probes.gui_build_probe import GUIBuildProbe


class TestGUIBuildProbe:
    def test_name_and_description(self) -> None:
        probe = GUIBuildProbe()
        assert probe.name == "gui_build"
        assert "GUI" in probe.description

    def test_measure_when_gui_dir_missing(self) -> None:
        probe = GUIBuildProbe(gui_dir="/nonexistent/path")
        reading = probe.measure()
        assert reading.value == 0.0
        assert "not found" in reading.context.get("error", "")

    def test_measure_lint_failure_reduces_value(self) -> None:
        with (
            patch("os.path.isdir", return_value=True),
            patch.object(GUIBuildProbe, "_run_pnpm") as mock_run,
            patch.object(GUIBuildProbe, "_measure_bundle_size", return_value=100.0),
        ):
            def side_effect(args, **kw):
                if "lint" in args:
                    return 1, "error TS2345: type mismatch", ""
                if "outdated" in args:
                    return 0, "{}", ""
                return 0, "", ""

            mock_run.side_effect = side_effect

            probe = GUIBuildProbe()
            reading = probe.measure()
            assert reading.value < 1.0
            assert reading.context["lint_passes"] is False
            assert reading.context["ts_errors"] >= 1

    def test_measure_full_pass(self) -> None:
        with (
            patch("os.path.isdir", return_value=True),
            patch.object(GUIBuildProbe, "_run_pnpm") as mock_run,
            patch.object(GUIBuildProbe, "_measure_bundle_size", return_value=500.0),
        ):
            def side_effect(args, **kw):
                if "lint" in args:
                    return 0, "", ""
                if "build" in args:
                    return 0, "Build succeeded", ""
                if "outdated" in args:
                    return 0, '{"dep1": {"current": "1.0", "wanted": "2.0"}}', ""
                return 0, "", ""

            mock_run.side_effect = side_effect

            probe = GUIBuildProbe()
            reading = probe.measure()
            assert reading.value == 1.0
            assert reading.context["lint_passes"] is True
            assert reading.context["build_success"] is True
            assert reading.context["stale_dependencies"] == 1

    def test_measure_pnpm_not_found(self) -> None:
        with (
            patch("os.path.isdir", return_value=True),
            patch.object(
                GUIBuildProbe, "_run_pnpm", return_value=(-1, "", "pnpm not found")
            ),
            patch.object(GUIBuildProbe, "_measure_bundle_size", return_value=0.0),
        ):
            probe = GUIBuildProbe()
            reading = probe.measure()
            assert reading.value <= 0.6  # build failed

    def test_count_ts_errors(self) -> None:
        probe = GUIBuildProbe()
        text = "error TS2345: type mismatch\nSome warning\nCannot find name 'foo'"
        assert probe._count_ts_errors(text) == 2

    def test_parse_outdated_valid(self) -> None:
        probe = GUIBuildProbe()
        assert probe._parse_outdated('{"dep1": {}, "dep2": {}}') == 2

    def test_parse_outdated_invalid_json(self) -> None:
        probe = GUIBuildProbe()
        assert probe._parse_outdated("not json") == -1

    def test_probe_inherits_base_probe(self) -> None:
        assert issubclass(GUIBuildProbe, BaseProbe)
