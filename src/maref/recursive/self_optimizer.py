from __future__ import annotations

import contextlib
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

logger = structlog.get_logger()

if TYPE_CHECKING:
    from maref.recursive.self_observer import SystemSnapshot


@dataclass
class OptimizationHypothesis:
    hypothesis_id: str
    description: str
    target_module: str
    experiment_result: dict[str, float] = field(default_factory=dict)
    gain_pct: float = 0.0
    adopted: bool = False
    reverted: bool = False
    conclusion: str = ""


@dataclass
class BenchmarkResult:
    before: dict[str, float]
    after: dict[str, float]
    gain_pct: float = 0.0


def _run_real_benchmark(timeout: int = 180, test_path: str | None = None, perf_mode: bool = False) -> dict[str, float]:
    result: dict[str, float] = {
        "test_count": 0.0,
        "coverage_pct": 0.0,
        "execution_time_ms": 0.0,
        "tests_passed": 0.0,
        "tests_failed": 0.0,
    }
    pytest_args = [sys.executable, "-m", "pytest", "--tb=no", "-q"]
    if perf_mode:
        pytest_args.append("--durations=0")
    if test_path:
        pytest_args.append(test_path)
    start = time.time()
    try:
        proc = subprocess.run(
            pytest_args,
            capture_output=True, text=True, timeout=timeout,
        )
        result["execution_time_ms"] = (time.time() - start) * 1000.0
        result["exit_code"] = float(proc.returncode)
        output = proc.stdout + proc.stderr
        for line in output.split("\n"):
            stripped = line.strip()
            if "passed" in stripped and ("failed" in stripped or "error" in stripped):
                parts = stripped.split()
                for i, p in enumerate(parts):
                    if p.endswith("passed") and i > 0:
                        with contextlib.suppress(ValueError):
                            result["tests_passed"] = float(parts[i - 1])
                        with contextlib.suppress(ValueError):
                            result["test_count"] = float(parts[i - 1])
                    elif p.endswith("failed") and i > 0:
                        with contextlib.suppress(ValueError):
                            result["tests_failed"] = float(parts[i - 1])
                        with contextlib.suppress(ValueError):
                            result["test_count"] = result.get("test_count", 0.0) + float(parts[i - 1])
    except subprocess.TimeoutExpired:
        result["execution_time_ms"] = float(timeout * 1000)
        result["exit_code"] = 124.0
    except Exception:
        result["execution_time_ms"] = (time.time() - start) * 1000.0
        result["exit_code"] = -1.0

    try:
        cov_proc = subprocess.run(
            [sys.executable, "-m", "coverage", "report", "-m"],
            capture_output=True, text=True, timeout=30,
        )
        for line in cov_proc.stdout.split("\n"):
            if "TOTAL" in line:
                parts = line.split()
                for part in parts:
                    if part.endswith("%"):
                        with contextlib.suppress(ValueError):
                            result["coverage_pct"] = float(part.replace("%", ""))
    except Exception:
        logger.debug("Coverage report read failed", exc_info=True)

    return result


class SelfOptimizer:
    def __init__(
        self,
        adopt_threshold: float = 0.05,
        benchmark_fn: Callable[[], dict[str, float]] | None = None,
    ) -> None:
        self._adopt_threshold = adopt_threshold
        self._hypotheses: list[OptimizationHypothesis] = []
        self._adopted: list[OptimizationHypothesis] = []
        self._reverted: list[OptimizationHypothesis] = []
        self._benchmark_fn = benchmark_fn or _run_real_benchmark

    def propose_optimizations(self, snapshot: SystemSnapshot) -> list[OptimizationHypothesis]:
        import uuid

        hypotheses: list[OptimizationHypothesis] = []
        module_graph = snapshot.module_graph

        modules_with_many_deps = sorted(
            module_graph.items(), key=lambda x: len(x[1]), reverse=True
        )[:3]

        for _i, (mod, deps) in enumerate(modules_with_many_deps):
            if len(deps) > 3:
                hypotheses.append(OptimizationHypothesis(
                    hypothesis_id=str(uuid.uuid4())[:8],
                    description=f"reduce dependencies for {mod} (currently {len(deps)})",
                    target_module=mod,
                ))

        if snapshot.source_file_count > 30:
            hypotheses.append(OptimizationHypothesis(
                hypothesis_id=str(uuid.uuid4())[:8],
                description=f"module split: currently {snapshot.source_file_count} source files",
                target_module="src/",
            ))

        if not hypotheses:
            hypotheses.append(OptimizationHypothesis(
                hypothesis_id=str(uuid.uuid4())[:8],
                description="code health is good, recommend regular maintenance",
                target_module="all",
            ))

        self._hypotheses = hypotheses
        return hypotheses

    def run_experiment(
        self,
        hypothesis: OptimizationHypothesis,
        apply_fn: Callable[[], None] | None = None,
    ) -> BenchmarkResult:
        before = self._benchmark_fn()

        if apply_fn is not None:
            with contextlib.suppress(ValueError, TypeError):
                apply_fn()

        after = self._benchmark_fn() if apply_fn is not None else dict(before)

        hypothesis.experiment_result = {"before": before, "after": after}  # type: ignore[dict-item]

        if before.get("coverage_pct", 0) > 0:
            gain = (after.get("coverage_pct", 0) - before.get("coverage_pct", 0)) / before.get("coverage_pct", 1)
        elif before.get("execution_time_ms", 0) > 0 and after.get("execution_time_ms", 0) > 0:
            gain = (before.get("execution_time_ms", 0) - after.get("execution_time_ms", 0)) / before.get("execution_time_ms", 1)
        else:
            gain = 0.0

        hypothesis.gain_pct = gain
        return BenchmarkResult(before=before, after=after, gain_pct=hypothesis.gain_pct)

    def adopt_if_gain(self, hypothesis: OptimizationHypothesis) -> bool:
        if hypothesis.gain_pct >= self._adopt_threshold and not hypothesis.reverted:
            hypothesis.adopted = True
            hypothesis.conclusion = f"adopted: gain {hypothesis.gain_pct:.1%} >= threshold {self._adopt_threshold:.0%}"
            self._adopted.append(hypothesis)
            return True
        hypothesis.conclusion = f"rejected: gain {hypothesis.gain_pct:.1%} < threshold {self._adopt_threshold:.0%}"
        return False

    def revert_if_regression(self, hypothesis: OptimizationHypothesis) -> bool:
        if hypothesis.gain_pct < 0:
            hypothesis.reverted = True
            hypothesis.adopted = False
            hypothesis.conclusion = f"rolled back: regression {abs(hypothesis.gain_pct):.1%}"
            self._reverted.append(hypothesis)
            return True
        return False

    @property
    def hypotheses(self) -> list[OptimizationHypothesis]:
        return list(self._hypotheses)

    @property
    def adopted(self) -> list[OptimizationHypothesis]:
        return list(self._adopted)

    @property
    def reverted(self) -> list[OptimizationHypothesis]:
        return list(self._reverted)
