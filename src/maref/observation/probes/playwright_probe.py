from __future__ import annotations

import logging
import subprocess
import sys
from typing import Any

from maref.observation.probes import BaseProbe, ProbeReading, ProbeSeverity

logger = logging.getLogger(__name__)


class PlaywrightProbe(BaseProbe):
    """检测 Playwright 安装状态和浏览器引擎可用性。

    Metrics:
    - playwright_installed: bool
    - chromium/firefox/webkit_available: bool
    - browsers_version: str
    - value: 1.0 if installed + any browser available, else 0.0
    """

    def __init__(self, critical_threshold: float = 0.0, warning_threshold: float = 0.0) -> None:
        super().__init__(
            name="playwright",
            description="Playwright 浏览器引擎安装状态",
            critical_threshold=critical_threshold,
            warning_threshold=warning_threshold,
        )

    def measure(self, context: dict[str, Any] | None = None) -> ProbeReading:
        import importlib.util

        playwright_spec = importlib.util.find_spec("playwright")
        installed = playwright_spec is not None
        browsers: dict[str, bool] = {}
        version = ""
        if installed:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "--dry-run"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                for b in ("chromium", "firefox", "webkit"):
                    browsers[b] = b in result.stdout
                version = subprocess.run(
                    [sys.executable, "-m", "playwright", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                ).stdout.strip()
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
                version = f"error: {e}"
        value = 1.0 if installed and any(browsers.values()) else 0.0
        severity = (
            ProbeSeverity.CRITICAL if value < self.critical_threshold else ProbeSeverity.NORMAL
        )
        reading = ProbeReading(
            probe_name=self.name,
            severity=severity,
            value=value,
            threshold=self.critical_threshold,
            context={
                "installed": installed,
                "chromium_available": browsers.get("chromium", False),
                "firefox_available": browsers.get("firefox", False),
                "webkit_available": browsers.get("webkit", False),
                "version": version,
            },
        )
        self._readings.append(reading)
        return reading
