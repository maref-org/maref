"""Real metrics collection for recursive evolution — replaces simulated FNR/FPR."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RealMetrics:
    fnr: float
    fpr: float
    test_pass_rate: float
    coverage_pct: float
    total_tests: int
    import_time_ms: float
    cb_state: str
    errors: list[str] = field(default_factory=list)
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fnr": self.fnr,
            "fpr": self.fpr,
            "test_pass_rate": self.test_pass_rate,
            "coverage_pct": self.coverage_pct,
            "total_tests": self.total_tests,
            "import_time_ms": self.import_time_ms,
            "cb_state": self.cb_state,
        }


class RealMetricsCollector:
    """Collect real metrics from the MAREF codebase via subprocess calls."""

    def __init__(self, src_dir: str | None = None) -> None:
        self._src = Path(src_dir) if src_dir else Path("src")
        self._baseline: RealMetrics | None = None
        self._baseline_cache_seconds = 300.0
        self._last_baseline_time = 0.0

    def collect_baseline(self) -> RealMetrics:
        now = time.time()
        if (
            self._baseline is not None
            and (now - self._last_baseline_time) < self._baseline_cache_seconds
        ):
            return self._baseline

        self._baseline = self._run_all_checks()
        self._last_baseline_time = now
        return self._baseline

    def collect_incremental(self) -> RealMetrics:
        return self._run_quick_checks()

    def _run_all_checks(self) -> RealMetrics:
        errors: list[str] = []

        test_pass, total, failed = self._run_pytest()
        cov_pct = self._run_coverage()
        import_ms = self._measure_import_time()
        cb_state = self._check_cb_state()
        if import_ms < 0:
            errors.append("import_time_failed")
        if cov_pct == 0.0:
            errors.append("coverage_unavailable")

        fnr = failed / max(total, 1)
        fpr = 0.0

        try:
            from maref.observation.probes import EntropyProbe

            probe = EntropyProbe(primary_threshold=3.0, shadow_threshold=1.5)
            readings = probe.read()
            if readings:
                fpr = min(readings[0].value, 1.0)
        except Exception:
            pass

        return RealMetrics(
            fnr=round(fnr, 4),
            fpr=round(fpr, 4),
            test_pass_rate=round(test_pass, 4),
            coverage_pct=round(cov_pct, 1),
            total_tests=total,
            import_time_ms=round(import_ms, 1),
            cb_state=cb_state,
            errors=errors,
        )

    def _run_quick_checks(self) -> RealMetrics:
        errors: list[str] = []
        test_pass, total, failed = self._run_pytest(quick=True)
        import_ms = self._measure_import_time()
        if import_ms < 0:
            errors.append("import_time_failed")

        return RealMetrics(
            fnr=round(failed / max(total, 1), 4),
            fpr=0.0,
            test_pass_rate=round(test_pass, 4),
            coverage_pct=0.0,
            total_tests=total,
            import_time_ms=round(import_ms, 1),
            cb_state="CLOSED",
            errors=errors,
        )

    @staticmethod
    def _run_pytest(quick: bool = False) -> tuple[float, int, int]:
        try:
            test_dirs = ["tests/cli/", "tests/unit/", "tests/governance/", "tests/redblue/"]
            if quick:
                test_dirs = test_dirs[:2]
            cmd = ["pytest", "--tb=no", "-q", "--no-header"] + test_dirs
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            output = result.stdout + result.stderr
            import re

            match = re.search(r"(\d+)\s+passed", output)
            total_passed = int(match.group(1)) if match else 0
            match_fail = re.search(r"(\d+)\s+failed", output)
            total_failed = int(match_fail.group(1)) if match_fail else 0
            total = total_passed + total_failed
            pass_rate = total_passed / max(total, 1)
            return round(pass_rate, 4), total, total_failed
        except Exception:
            return 0.0, 1, 1

    @staticmethod
    def _run_coverage() -> float:
        try:
            result = subprocess.run(
                ["coverage", "report", "-m"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout
            import re

            match = re.search(r"TOTAL.*?(\d+)%", output)
            if match:
                return float(match.group(1))
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _measure_import_time() -> float:
        try:
            t0 = time.perf_counter()
            result = subprocess.run(
                ["python3", "-c", "import maref; import maref_lite"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            return elapsed if result.returncode == 0 else -1.0
        except Exception:
            return -1.0

    @staticmethod
    def _check_cb_state() -> str:
        try:
            from maref.governance import CircuitBreaker

            cb = CircuitBreaker(max_depth=3, max_consecutive_failures=3, cooldown_seconds=30.0)
            return cb.get_stats().get("state", "CLOSED")
        except Exception:
            return "CLOSED"
