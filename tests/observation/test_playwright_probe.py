from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from maref.observation.probes import BaseProbe, ProbeSeverity
from maref.observation.probes.playwright_probe import PlaywrightProbe


class TestPlaywrightProbe:
    def test_name_and_description(self) -> None:
        probe = PlaywrightProbe()
        assert probe.name == "playwright"
        assert "Playwright" in probe.description

    def test_probe_inherits_base_probe(self) -> None:
        probe = PlaywrightProbe()
        assert isinstance(probe, BaseProbe)

    @patch("importlib.util.find_spec", return_value=None)
    def test_measure_when_not_installed(self, mock_find_spec: MagicMock) -> None:
        probe = PlaywrightProbe()
        reading = probe.measure()
        assert reading.probe_name == "playwright"
        assert reading.value == 0.0
        assert reading.context["installed"] is False
        assert reading.context["chromium_available"] is False
        assert reading.context["version"] == ""
        mock_find_spec.assert_called_once_with("playwright")

    @patch("importlib.util.find_spec")
    @patch("subprocess.run")
    def test_measure_when_installed_with_chromium(
        self, mock_run: MagicMock, mock_find_spec: MagicMock
    ) -> None:
        mock_find_spec.return_value = MagicMock()

        def run_side_effect(cmd: list[str], *args: list, **kwargs: object) -> MagicMock:
            result = MagicMock()
            if "install" in cmd:
                result.stdout = "chromium"
                result.stderr = ""
            else:
                result.stdout = "1.48.0"
                result.stderr = ""
            return result

        mock_run.side_effect = run_side_effect

        probe = PlaywrightProbe()
        reading = probe.measure()

        assert reading.value == 1.0
        assert reading.context["installed"] is True
        assert reading.context["chromium_available"] is True
        assert reading.context["firefox_available"] is False
        assert reading.context["webkit_available"] is False
        assert reading.context["version"] == "1.48.0"

    @patch("importlib.util.find_spec")
    @patch("subprocess.run")
    def test_measure_subprocess_timeout_handled(
        self, mock_run: MagicMock, mock_find_spec: MagicMock
    ) -> None:
        mock_find_spec.return_value = MagicMock()
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="playwright", timeout=30)

        probe = PlaywrightProbe()
        reading = probe.measure()

        assert reading.value == 0.0
        assert reading.context["installed"] is True
        assert "error" in reading.context["version"]

    @patch("importlib.util.find_spec", return_value=None)
    def test_reading_severity_threshold(self, mock_find_spec: MagicMock) -> None:
        probe = PlaywrightProbe(critical_threshold=1.0)
        reading = probe.measure()
        assert reading.value == 0.0
        assert reading.severity == ProbeSeverity.CRITICAL
        assert reading.threshold == 1.0
