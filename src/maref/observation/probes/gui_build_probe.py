from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

from maref.observation.probes import BaseProbe, ProbeReading, ProbeSeverity

logger = logging.getLogger(__name__)


class GUIBuildProbe(BaseProbe):
    """检测 GUI (Electron + React) 构建健康。

    Metrics:
    - lint_passes: bool
    - build_success: bool
    - ts_errors: int (count from lint output)
    - bundle_size_kb: float
    - stale_dependencies: int (-1 = unknown)
    - value: composite 0.0–1.0
    """

    def __init__(
        self,
        gui_dir: str = "gui",
        critical_threshold: float = 0.3,
        warning_threshold: float = 0.6,
    ) -> None:
        super().__init__(
            name="gui_build",
            description="GUI Electron 构建与 TypeScript 健康",
            critical_threshold=critical_threshold,
            warning_threshold=warning_threshold,
        )
        self.gui_dir = gui_dir

    def _run_pnpm(self, args: list[str], timeout: int = 120) -> tuple[int, str, str]:
        try:
            r = subprocess.run(
                ["pnpm", *args],
                cwd=self.gui_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return r.returncode, r.stdout, r.stderr
        except (FileNotFoundError, OSError):
            return -1, "", "pnpm not found"
        except subprocess.TimeoutExpired:
            return -1, "", "timeout"

    def measure(self, context: dict[str, Any] | None = None) -> ProbeReading:
        if not os.path.isdir(self.gui_dir):
            reading = ProbeReading(
                probe_name=self.name,
                severity=ProbeSeverity.CRITICAL,
                value=0.0,
                threshold=self.critical_threshold,
                context={"error": f"gui_dir not found: {self.gui_dir}"},
            )
            self._readings.append(reading)
            return reading

        lint_code, lint_out, lint_err = self._run_pnpm(["lint"])
        ts_errors = self._count_ts_errors(lint_err + lint_out)

        build_code, build_out, build_err = self._run_pnpm(["build"], timeout=300)
        bundle_size = self._measure_bundle_size()

        deps_code, deps_out, _ = self._run_pnpm(["outdated", "--json"])
        stale_deps = self._parse_outdated(deps_out) if deps_code == 0 else -1

        value = 1.0
        if lint_code != 0:
            value -= 0.3
        if build_code != 0:
            value -= 0.4
        if ts_errors > 0:
            value -= 0.1 * min(ts_errors, 5)
        value = max(0.0, value)

        if value < self.critical_threshold:
            severity = ProbeSeverity.CRITICAL
        elif value < self.warning_threshold:
            severity = ProbeSeverity.WARNING
        else:
            severity = ProbeSeverity.NORMAL

        reading = ProbeReading(
            probe_name=self.name,
            severity=severity,
            value=value,
            threshold=self.critical_threshold,
            context={
                "lint_passes": lint_code == 0,
                "build_success": build_code == 0,
                "ts_errors": ts_errors,
                "bundle_size_kb": bundle_size,
                "stale_dependencies": stale_deps,
            },
        )
        self._readings.append(reading)
        return reading

    def _count_ts_errors(self, text: str) -> int:
        count = 0
        for line in text.split("\n"):
            if "error TS" in line or "Cannot find name" in line or "Type '" in line:
                count += 1
        return count

    def _measure_bundle_size(self) -> float:
        dist = os.path.join(self.gui_dir, "dist")
        if not os.path.isdir(dist):
            return 0.0
        total = 0.0
        for dirpath, _, filenames in os.walk(dist):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
        return round(total / 1024, 1)

    def _parse_outdated(self, json_text: str) -> int:
        try:
            data = json.loads(json_text)
            return len(data) if isinstance(data, dict) else 0
        except (json.JSONDecodeError, TypeError):
            return -1
