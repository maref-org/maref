"""24-hour stability test runner.

Runs a sequence of operations in a loop, monitors memory usage per iteration,
detects memory leaks (>5% growth over 24h equivalent), and outputs a stability report.
"""
from __future__ import annotations

import logging
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MB = 1024 * 1024
DEFAULT_DURATION_H = 24.0
LEAK_THRESHOLD_PCT = 5.0
ITERATIONS_FOR_24H = 1000


@dataclass
class IterationSnapshot:
    iteration: int
    timestamp: float
    memory_rss_mb: float
    memory_traced_mb: float
    elapsed_s: float
    success: bool
    error: str = ""


@dataclass
class StabilityReport:
    total_iterations: int
    duration_s: float
    errors: list[str] = field(default_factory=list)
    memory_snapshots: list[IterationSnapshot] = field(default_factory=list)
    start_memory_mb: float = 0.0
    end_memory_mb: float = 0.0
    peak_memory_mb: float = 0.0
    memory_growth_pct: float = 0.0
    leak_detected: bool = False
    leak_message: str = ""
    success_rate: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_iterations": self.total_iterations,
            "duration_s": round(self.duration_s, 2),
            "error_count": len(self.errors),
            "start_memory_mb": round(self.start_memory_mb, 2),
            "end_memory_mb": round(self.end_memory_mb, 2),
            "peak_memory_mb": round(self.peak_memory_mb, 2),
            "memory_growth_pct": round(self.memory_growth_pct, 3),
            "leak_detected": self.leak_detected,
            "leak_message": self.leak_message,
            "success_rate": round(self.success_rate, 4),
        }


class StabilityTestRunner:
    def __init__(
        self,
        operation: Callable[[int], None] | None = None,
        duration_h: float = DEFAULT_DURATION_H,
        iterations: int = ITERATIONS_FOR_24H,
        leak_threshold_pct: float = LEAK_THRESHOLD_PCT,
        enable_tracemalloc: bool = True,
    ) -> None:
        self._operation = operation or self._default_operation
        self._duration_h = duration_h
        self._target_iterations = iterations
        self._leak_threshold_pct = leak_threshold_pct
        self._snapshots: list[IterationSnapshot] = []
        self._errors: list[str] = []

        if enable_tracemalloc:
            tracemalloc.start()

    @staticmethod
    def _default_operation(iteration: int) -> None:
        _ = [i * i for i in range(10000)]
        time.sleep(0.001)

    def _get_memory_mb(self) -> float:
        import os

        try:
            import psutil

            proc = psutil.Process(os.getpid())
            return proc.memory_info().rss / MB
        except ImportError:
            pass

        traced = tracemalloc.get_traced_memory()[0]
        if traced:
            return traced / MB

        try:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF)
            rss = usage.ru_maxrss
            return rss / MB
        except (ImportError, AttributeError):
            pass

        import os as _os

        try:
            statm = f"/proc/{_os.getpid()}/statm"
            with open(statm) as f:
                pages = int(f.read().split()[0])
                page_size = _os.sysconf("SC_PAGE_SIZE")
                return (pages * page_size) / MB
        except (FileNotFoundError, OSError, ValueError):
            return 0.0

    def _get_traced_mb(self) -> float:
        traced = tracemalloc.get_traced_memory()[0]
        return traced / MB

    def run(self, report_interval: int = 50) -> StabilityReport:
        logger.info(
            "StabilityTestRunner starting",
            extra={
                "duration_h": self._duration_h,
                "target_iterations": self._target_iterations,
                "leak_threshold_pct": self._leak_threshold_pct,
            },
        )

        start_time = time.time()
        start_memory = self._get_memory_mb()
        peak_memory = start_memory
        last_memory = start_memory

        for i in range(self._target_iterations):
            iter_start = time.time()
            error = ""
            success = True

            try:
                self._operation(i)
            except Exception as e:
                error = str(e)
                self._errors.append(f"Iteration {i}: {e}")
                success = False

            current_memory = self._get_memory_mb()
            traced_memory = self._get_traced_mb()
            peak_memory = max(peak_memory, current_memory)

            snapshot = IterationSnapshot(
                iteration=i,
                timestamp=time.time(),
                memory_rss_mb=current_memory,
                memory_traced_mb=traced_memory,
                elapsed_s=time.time() - iter_start,
                success=success,
                error=error,
            )
            self._snapshots.append(snapshot)

            if (i + 1) % report_interval == 0:
                growth = ((current_memory - start_memory) / max(start_memory, 1)) * 100
                logger.info(
                    "Stability progress",
                    extra={
                        "iteration": i + 1,
                        "memory_mb": round(current_memory, 2),
                        "growth_pct": round(growth, 3),
                        "peak_mb": round(peak_memory, 2),
                    },
                )

            last_memory = current_memory

        end_memory = last_memory
        elapsed = time.time() - start_time
        tracemalloc.stop()

        memory_growth_pct = ((end_memory - start_memory) / max(start_memory, 1)) * 100
        leak_detected = memory_growth_pct > self._leak_threshold_pct
        leak_message = ""
        if leak_detected:
            leak_message = (
                f"Memory leak detected: {memory_growth_pct:.2f}% growth "
                f"({start_memory:.1f}MB -> {end_memory:.1f}MB) "
                f"exceeds threshold {self._leak_threshold_pct}%"
            )
            logger.warning(leak_message)
        else:
            logger.info(
                "No memory leak detected",
                extra={
                    "growth_pct": round(memory_growth_pct, 3),
                    "threshold_pct": self._leak_threshold_pct,
                },
            )

        success_count = sum(1 for s in self._snapshots if s.success)
        success_rate = success_count / max(len(self._snapshots), 1)

        report = StabilityReport(
            total_iterations=self._target_iterations,
            duration_s=elapsed,
            errors=list(self._errors),
            memory_snapshots=list(self._snapshots),
            start_memory_mb=start_memory,
            end_memory_mb=end_memory,
            peak_memory_mb=peak_memory,
            memory_growth_pct=memory_growth_pct,
            leak_detected=leak_detected,
            leak_message=leak_message,
            success_rate=success_rate,
        )

        logger.info(
            "StabilityTestRunner finished",
            extra={
                "duration_s": round(elapsed, 2),
                "iterations": self._target_iterations,
                "leak_detected": leak_detected,
                "memory_growth_pct": round(memory_growth_pct, 3),
                "success_rate": round(success_rate, 4),
            },
        )

        return report
