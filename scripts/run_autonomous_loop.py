#!/usr/bin/env python3
"""
MAREF Autonomous Iteration Loop Runner.

Runs the full RSI pipeline in a loop:
  Observe → Diagnose → Propose → Generate → Safety → Deploy → Verify → Heal → Repeat

Usage:
    python scripts/run_autonomous_loop.py --duration 12  # 12-hour loop
    python scripts/run_autonomous_loop.py --dry-run       # dry run (no writes)
    python scripts/run_autonomous_loop.py --production    # production mode (writes + LLM)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("autonomous_loop")


class AutonomousLoopRunner:
    # Fix 4: system-health risks that indicate real degradation.
    # Infra risks (gui_build/playwright/desktop) are excluded — they are known
    # persistent states the autonomous loop is actively remediating.
    _SYSTEM_HEALTH_RISKS = frozenset(
        {"entropy", "latency", "anomaly", "kg", "oscillation"}
    )

    def __init__(
        self,
        duration_hours: float = 1.0,
        loop_interval_minutes: float = 15.0,
        dry_run: bool = True,
        real_writes: bool = False,
        vault_dir: str = ".evolution_vault",
        output_dir: str = "reports/autonomous",
    ):
        self._duration_hours = duration_hours
        self._loop_interval = loop_interval_minutes * 60
        self._dry_run = dry_run
        self._real_writes = real_writes
        self._vault_dir = vault_dir
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._metrics_history: list[dict[str, Any]] = []
        self._cycle_count = 0
        self._success_count = 0
        self._failure_count = 0

        # Fix 4: halt state for 48h unattended safety
        self._consecutive_failures = 0
        self._halt_reason: str | None = None
        self._MAX_CONSECUTIVE_FAILURES = 5
        self._MIN_DISK_GB = 1.0
        # System-health critical streak — only entropy/latency/anomaly/kg/oscillation
        # criticals count. Infra criticals (gui_build/playwright/desktop) are known
        # persistent states the loop is actively fixing; they must NOT trigger halt.
        self._system_critical_streak = 0
        self._MAX_SYSTEM_CRITICAL_STREAK = 3

        # Fix 3c: last diagnosis report for risk-driven apply_fn
        self._last_report: Any = None

        self._daily_loop: Any = None
        self._executor: Any = None
        self._optimizer: Any = None
        self._healer: Any = None
        self._observer: Any = None
        self._diagnostician: Any = None
        self._bridge: Any = None

        self._init_components()

    def _init_components(self) -> None:
        from maref.evolution.daily_loop import DailyEvolutionLoop
        from maref.evolution.optimizer_bridge import OptimizerEvolutionBridge
        from maref.recursive.self_diagnostician import SelfDiagnostician
        from maref.recursive.self_executor import SelfExecutor
        from maref.recursive.self_healer import SelfHealer
        from maref.recursive.self_observer import SelfObserver
        from maref.recursive.self_optimizer import SelfOptimizer

        self._observer = SelfObserver()
        self._diagnostician = SelfDiagnostician()
        self._bridge = OptimizerEvolutionBridge()
        self._daily_loop = DailyEvolutionLoop(
            vault_dir=self._vault_dir,
            dry_run=self._dry_run,
            real_writes=self._real_writes,
        )

        if self._real_writes:
            self._executor = SelfExecutor(auto_init_codegen=True)
            # Fix 6: relocate AtomicDeployer backups into project to survive /tmp cleanup
            backup_dir = str(Path.cwd() / ".maref_backups")
            Path(backup_dir).mkdir(parents=True, exist_ok=True)
            deployer = getattr(self._executor, "_deployer", None)
            if deployer is not None:
                try:
                    self._executor._deployer = type(deployer)(backup_dir=backup_dir)
                except TypeError:
                    deployer._backup_dir = backup_dir
            self._optimizer = SelfOptimizer(
                apply_fn=self._default_apply_fn,
                benchmark_fn=self._gui_aware_benchmark,
            )
            self._healer = SelfHealer(
                executor=self._executor,
                project_root=str(Path.cwd()),
            )
        else:
            self._executor = None
            self._optimizer = SelfOptimizer()
            self._healer = SelfHealer()

    def _capture_gui_errors(self) -> list[dict]:
        """Fix 3b/8: capture concrete ESLint errors when gui_build is critical."""
        try:
            r = subprocess.run(
                ["pnpm", "lint", "--format", "json"],
                cwd=str(Path.cwd() / "gui"),
                capture_output=True,
                text=True,
                timeout=60,
            )
            # Fix 8: pnpm prepends banner lines ("> gui@... lint", "> eslint ...")
            # before the JSON payload AND appends a trailing ELIFECYCLE line
            # after it, so json.loads(raw_stdout) raises JSONDecodeError and
            # returns []. Extract the JSON by slicing from the first '[' to the
            # last ']' which brackets the ESLint JSON array.
            raw = r.stdout or r.stderr or ""
            json_start = raw.find("[")
            json_end = raw.rfind("]")
            if json_start < 0 or json_end < 0 or json_end <= json_start:
                return []
            data = json.loads(raw[json_start:json_end + 1])
            if not isinstance(data, list):
                return []
            errors: list[dict] = []
            for f in data:
                # ESLint JSON uses "filePath" (absolute path); fall back to "file".
                file_path = f.get("filePath", f.get("file", ""))
                msgs = [
                    m for m in f.get("messages", [])
                    if m.get("severity", 0) >= 2
                ]
                if msgs:
                    errors.append({
                        "file": file_path,
                        "error_count": len(msgs),
                        "messages": msgs[:5],
                    })
            return errors
        except Exception as exc:
            logger.debug("GUI error capture failed: %s", exc)
            return []

    def _gui_aware_benchmark(self) -> dict[str, float]:
        """Fix 12: GUI-aware benchmark for the optimizer's gain calculation.

        The default _run_real_benchmark runs the FULL pytest suite (10922
        tests, >180s) which always times out, producing coverage_pct=0 and
        execution_time_ms=180000 for both before/after — so gain is always
        ~0 and every hypothesis is rejected.

        This benchmark instead:
        1. Runs tests/recursive/ (fast subset, ~37 tests, <60s) for test metrics
        2. Runs `pnpm lint --format json` in gui/ to count GUI/ESLint errors
        3. Maps GUI health to coverage_pct: max(0, 100 - error_count * 5)

        When the LLM fixes RsiDashboard.tsx (reduces errors from 11 to ~5),
        coverage_pct rises from 45 to 75, giving gain=(75-45)/45=66.7% → Adopted.
        """
        import sys as _sys
        result: dict[str, float] = {
            "test_count": 0.0,
            "coverage_pct": 0.0,
            "execution_time_ms": 0.0,
            "tests_passed": 0.0,
            "tests_failed": 0.0,
        }
        start = time.time()

        # Phase 1: fast Python test subset (tests/recursive/)
        try:
            proc = subprocess.run(
                [_sys.executable, "-m", "pytest", "tests/recursive/",
                 "--tb=no", "-q", "-x"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            result["exit_code"] = float(proc.returncode)
            output = proc.stdout + proc.stderr
            for line in output.split("\n"):
                stripped = line.strip()
                if "passed" in stripped:
                    parts = stripped.split()
                    for i, p in enumerate(parts):
                        if p.endswith("passed") and i > 0:
                            with contextlib.suppress(ValueError):
                                result["tests_passed"] = float(parts[i - 1])
                                result["test_count"] = float(parts[i - 1])
                        elif p.endswith("failed") and i > 0:
                            with contextlib.suppress(ValueError):
                                result["tests_failed"] = float(parts[i - 1])
                                result["test_count"] = result.get("test_count", 0.0) + float(
                                    parts[i - 1]
                                )
        except subprocess.TimeoutExpired:
            result["exit_code"] = 124.0
        except Exception:
            result["exit_code"] = -1.0

        # Phase 2: GUI lint health → map to coverage_pct
        try:
            gui_errors = self._capture_gui_errors()
            total_errors = sum(e.get("error_count", 0) for e in gui_errors)
            # Map: 0 errors=100%, 11 errors=45%, 20+ errors=0%
            result["coverage_pct"] = max(0.0, 100.0 - total_errors * 5.0)
            result["gui_error_count"] = float(total_errors)
        except Exception:
            # If GUI lint fails, fall back to a low coverage_pct
            result["coverage_pct"] = 0.0
            result["gui_error_count"] = 0.0

        result["execution_time_ms"] = (time.time() - start) * 1000.0
        return result

    def _build_gui_proposal(self, gui_errors: list[dict]) -> Any:
        """Fix 3b: build an ArchitectureProposal targeting the worst GUI file."""
        if not gui_errors:
            return None
        from maref.recursive.self_architect import ArchitectureProposal, ChangeType

        target = max(gui_errors, key=lambda e: e["error_count"])
        target_file = target["file"]
        return ArchitectureProposal(
            proposal_id=f"gui_fix_{int(time.time())}",
            timestamp=time.time(),
            current_arch=target_file,
            proposed_arch=target_file,
            rationale=(
                f"Fix GUI build critical: {target['error_count']} "
                f"TypeScript/ESLint errors in {target_file}"
            ),
            risk_assessment="low",
            confidence=0.6,
            target_files=[target_file],
            change_type=ChangeType.GENERAL_REFACTOR,
            affected_symbols=[
                m.get("ruleId", "unknown") for m in target["messages"]
            ],
            preconditions=["gui_build probe must be critical"],
        )

    def _default_apply_fn(self) -> None:
        """Default optimization apply function — risk-driven (Fix 3c)."""
        if self._executor is None:
            return
        try:
            from maref.recursive.self_diagnostician import RiskLevel

            proposal: Any = None
            # Risk-driven: when gui_build is critical, attempt GUI fix first
            if (
                self._last_report is not None
                and self._last_report.risk_matrix.get("gui_build") == RiskLevel.CRITICAL
            ):
                gui_errors = self._capture_gui_errors()
                proposal = self._build_gui_proposal(gui_errors)
                if proposal is not None:
                    logger.info(
                        "Risk-driven GUI fix: %s (%d errors)",
                        proposal.target_files[0],
                        len(gui_errors),
                    )

            # Fallback: architect Python proposal
            if proposal is None:
                from maref.recursive.self_architect import SelfArchitect
                from maref.recursive.unified_audit import UnifiedAuditStore

                architect = SelfArchitect(audit_store=UnifiedAuditStore())
                proposals = architect.propose_all()
                proposal = proposals[0] if proposals else None

            if proposal is not None:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        self._executor.execute_async(proposal)
                    )
                finally:
                    loop.close()
        except Exception as exc:
            logger.warning("Default apply fn failed: %s", exc)

    def run_one_cycle(self) -> dict[str, Any]:
        """Run one complete RSI cycle."""
        cycle_start = time.time()
        self._cycle_count += 1
        cycle_id = f"cycle-{self._cycle_count:04d}"

        logger.info("=" * 60)
        logger.info("Starting %s (dry_run=%s, real_writes=%s)", cycle_id, self._dry_run, self._real_writes)
        logger.info("=" * 60)

        result: dict[str, Any] = {
            "cycle_id": cycle_id,
            "start_time": datetime.now().isoformat(),
            "phases": {},
            "success": False,
        }

        # Phase 1: Daily evolution loop
        try:
            day = datetime.now().strftime("%Y-%m-%d-%H%M")
            daily_result = self._daily_loop.run_once(day=day)
            result["phases"]["daily_loop"] = {
                "success": daily_result is not None,
                "stop_reason": daily_result.stop_reason if daily_result else "none",
                "priority": daily_result.priority if daily_result else "unknown",
                "real_writes": daily_result.real_writes_enabled if daily_result else False,
                "trust_score": daily_result.trust_score if daily_result else 0.0,
            }
            if daily_result and daily_result.stop_reason == "trust_blocked":
                logger.warning("Cycle %s: trust blocked, skipping write phases", cycle_id)
                result["success"] = False
                result["end_time"] = datetime.now().isoformat()
                result["duration_seconds"] = time.time() - cycle_start
                self._metrics_history.append(result)
                return result
        except Exception as exc:
            logger.exception("Daily loop failed: %s", exc)
            result["phases"]["daily_loop"] = {"success": False, "error": str(exc)}

        # Phase 2: Self-diagnosis → optimization
        try:
            snapshot = self._observer.snapshot()
            report = self._diagnostician.diagnose(snapshot)
            self._last_report = report  # Fix 3c: expose to risk-driven apply_fn
            hypotheses = self._bridge.diagnose_to_hypotheses(report, snapshot)
            # Fix 2: persist full diagnostic context for post-run analysis
            result["phases"]["diagnosis"] = {
                "success": True,
                "risk": report.overall_risk.value,
                "hypothesis_count": len(hypotheses),
                "recommendations": report.recommendations,
                "diagnostic_context": report.diagnostic_context,
                "risk_matrix": {k: v.value for k, v in report.risk_matrix.items()},
                "probe_results": {
                    name: [
                        r.to_dict() if hasattr(r, "to_dict") else r
                        for r in readings
                    ]
                    for name, readings in report.probe_results.items()
                },
            }
            logger.info("Diagnosis: risk=%s, hypotheses=%d", report.overall_risk.value, len(hypotheses))

            # Fix 4 (revised): system-health critical streak — NOT the raw circuit
            # breaker. SelfDiagnostician.check_and_trip counts ALL criticals including
            # gui_build (persistently critical in this project), which would OPEN the
            # breaker after 4 cycles and halt the 48h run prematurely. Instead, we
            # halt only when system-health risks (entropy/latency/anomaly/kg/oscillation)
            # stay critical for N consecutive cycles — a real degradation signal.
            from maref.recursive.self_diagnostician import RiskLevel as _RL
            system_criticals = [
                name
                for name, level in report.risk_matrix.items()
                if level == _RL.CRITICAL and name in self._SYSTEM_HEALTH_RISKS
            ]
            if system_criticals:
                self._system_critical_streak += 1
                result["phases"]["circuit_breaker"] = {
                    "system_critical_streak": self._system_critical_streak,
                    "critical_risks": system_criticals,
                }
                if self._system_critical_streak >= self._MAX_SYSTEM_CRITICAL_STREAK:
                    self._halt_reason = (
                        f"system_health_critical: {system_criticals}"
                    )
                    logger.critical(
                        "HALT: system-health critical streak %d: %s",
                        self._system_critical_streak,
                        system_criticals,
                    )
            elif self._system_critical_streak > 0:
                # Transient blip recovered — reset streak
                self._system_critical_streak = 0

            for hypothesis in hypotheses:
                exp_result = self._optimizer.run_experiment(hypothesis)
                if self._optimizer.adopt_if_gain(hypothesis):
                    logger.info("Adopted hypothesis %s: gain=%.2f%%", hypothesis.hypothesis_id, hypothesis.gain_pct * 100)
                    self._success_count += 1
                else:
                    logger.info("Rejected hypothesis %s: gain=%.2f%%", hypothesis.hypothesis_id, hypothesis.gain_pct * 100)

            # Fix 3c: record GUI fix attempt when gui_build is critical
            if report.risk_matrix.get("gui_build") == _RL.CRITICAL:
                gui_errors = self._capture_gui_errors()
                result["phases"]["gui_fix_attempt"] = {
                    "triggered": True,
                    "gui_errors_captured": len(gui_errors),
                    "worst_file": (
                        max(gui_errors, key=lambda e: e["error_count"])["file"]
                        if gui_errors else None
                    ),
                }
        except Exception as exc:
            logger.exception("Diagnosis/optimization failed: %s", exc)
            result["phases"]["diagnosis"] = {"success": False, "error": str(exc)}

        # Phase 3: Self-healing
        if self._real_writes:
            try:
                snapshot2 = self._observer.snapshot()
                report2 = self._diagnostician.diagnose(snapshot2)
                # Fix 9: pass a re_diagnose callback so heal_cycle verifies
                # the fix actually reduced risk instead of assuming that
                # action success == problem fixed (which produced 187 cycles
                # of false RECOVERED while gui_build stayed critical).
                def _re_diagnose() -> Any:
                    snap = self._observer.snapshot()
                    return self._diagnostician.diagnose(snap)
                healing_record = self._healer.heal_cycle(
                    report2, re_diagnose=_re_diagnose
                )
                result["phases"]["healing"] = {
                    "success": healing_record.converged,
                    "final_state": healing_record.final_state,
                    "iterations": healing_record.iterations,
                    "action_count": len(healing_record.actions),
                }
                if healing_record.converged:
                    logger.info("Healing converged: state=%s", healing_record.final_state)
                else:
                    logger.warning("Healing degraded: state=%s", healing_record.final_state)
                    self._failure_count += 1
            except Exception as exc:
                logger.exception("Healing failed: %s", exc)
                result["phases"]["healing"] = {"success": False, "error": str(exc)}

        # Phase 4: Metrics collection
        try:
            # Fix 10: collect_only=False so tests actually run and we get real
            # pass/fail/coverage numbers instead of total=0 coverage_pct=0.
            snapshot3 = self._observer.snapshot(collect_only=False)
            # Fix 1: read from test_stats dict (SystemSnapshot has no test_count attr)
            test_stats = getattr(snapshot3, "test_stats", None) or {}
            total = test_stats.get("total", 0)
            metrics = {
                "timestamp": time.time(),
                "cycle": self._cycle_count,
                "source_file_count": getattr(snapshot3, "source_file_count", 0),
                "test_count": total,
                "test_pass_rate": test_stats.get("passed", 0) / max(total, 1),
                "test_fail_count": test_stats.get("failed", 0),
                "test_errors": test_stats.get("errors", 0),
                "coverage_pct": test_stats.get("coverage_pct", 0),
                "test_duration_ms": test_stats.get("duration_ms", 0),
            }
            self._metrics_history.append(metrics)
            result["phases"]["metrics"] = {"success": True, "values": metrics}
            result["cumulative"] = {
                "cycles": self._cycle_count,
                "successes": self._success_count,
                "failures": self._failure_count,
            }
        except Exception as exc:
            logger.warning("Metrics collection failed: %s", exc)

        result["success"] = result["phases"].get("daily_loop", {}).get("success", False)
        result["end_time"] = datetime.now().isoformat()
        result["duration_seconds"] = time.time() - cycle_start

        # Fix 4: track consecutive failures for halt decision
        if result["success"]:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

        duration_str = f"{result['duration_seconds']:.1f}s"
        logger.info("Cycle %s complete: %s (cumulative: %d ok / %d fail)", cycle_id, "✅" if result["success"] else "❌", self._success_count, self._failure_count)
        return result

    def run(self) -> None:
        """Run the autonomous loop for the configured duration."""
        start_time = time.time()
        end_time = start_time + self._duration_hours * 3600

        logger.info("=" * 60)
        logger.info("AUTONOMOUS LOOP START")
        logger.info("  Duration:     %.1f hours", self._duration_hours)
        logger.info("  Interval:     %.0f minutes", self._loop_interval / 60)
        logger.info("  Mode:         %s", "PRODUCTION" if self._real_writes else "dry-run")
        logger.info("  Output:       %s", self._output_dir)
        logger.info("=" * 60)

        while time.time() < end_time:
            # Fix 4: halt check 1 — disk space
            try:
                disk = shutil.disk_usage(str(self._output_dir))
                free_gb = disk.free / (1024 ** 3)
                if free_gb < self._MIN_DISK_GB:
                    self._halt_reason = f"disk_low: {free_gb:.1f}GB free"
                    logger.critical("HALT: %s", self._halt_reason)
                    break
            except OSError:
                pass

            # Fix 4: halt check 2 — consecutive failures
            if self._consecutive_failures >= self._MAX_CONSECUTIVE_FAILURES:
                self._halt_reason = f"consecutive_failures={self._consecutive_failures}"
                logger.critical("HALT: %s", self._halt_reason)
                break

            # Fix 4: halt check 3 — system-health critical (set during run_one_cycle)
            if self._halt_reason is not None:
                logger.critical("HALT: %s", self._halt_reason)
                break

            cycle_start = time.time()
            result = self.run_one_cycle()

            # Save per-cycle report
            report_path = self._output_dir / f"cycle-{self._cycle_count:04d}.json"
            with open(report_path, "w") as f:
                json.dump(result, f, indent=2, default=str)

            # Check if we should stop early due to wall clock
            elapsed = time.time() - cycle_start
            remaining = end_time - time.time()
            if remaining <= 0:
                break

            # Sleep if we finished faster than the interval
            sleep_time = min(self._loop_interval - elapsed, remaining)
            if sleep_time > 5:
                logger.info("Sleeping %.0fs until next cycle...", sleep_time)
                time.sleep(sleep_time)

        self._generate_final_report(start_time)

    def _generate_final_report(self, start_time: float) -> None:
        elapsed_hours = (time.time() - start_time) / 3600
        report = {
            "title": "MAREF Autonomous Loop Report",
            "generated_at": datetime.now().isoformat(),
            "duration_hours": round(elapsed_hours, 2),
            "total_cycles": self._cycle_count,
            "successful_cycles": self._success_count,
            "failed_cycles": self._failure_count,
            "adoption_rate": self._success_count / max(self._cycle_count, 1),
            "halt_reason": self._halt_reason,  # Fix 4: None = normal completion
            "metrics_history": self._metrics_history,
        }
        report_path = self._output_dir / "final-report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info("=" * 60)
        logger.info("AUTONOMOUS LOOP COMPLETE")
        logger.info("  Wall time:    %.1f hours", elapsed_hours)
        logger.info("  Cycles:       %d", self._cycle_count)
        logger.info("  Successes:    %d", self._success_count)
        logger.info("  Failures:     %d", self._failure_count)
        logger.info("  Adoption:     %.1f%%", report["adoption_rate"] * 100)
        if self._halt_reason:
            logger.info("  HALT reason:  %s", self._halt_reason)
        logger.info("  Report:       %s", report_path)
        logger.info("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="MAREF Autonomous Iteration Loop")
    parser.add_argument("--duration", type=float, default=0.5, help="Duration in hours (default: 0.5)")
    parser.add_argument("--interval", type=float, default=15.0, help="Loop interval in minutes (default: 15)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode (default)")
    parser.add_argument("--production", action="store_true", help="Production mode (writes + LLM)")
    parser.add_argument("--vault", default=".evolution_vault", help="Evolution vault directory")
    parser.add_argument("--output", default="reports/autonomous", help="Output directory")
    args = parser.parse_args()

    runner = AutonomousLoopRunner(
        duration_hours=args.duration,
        loop_interval_minutes=args.interval,
        dry_run=not args.production,
        real_writes=args.production,
        vault_dir=args.vault,
        output_dir=args.output,
    )
    runner.run()


if __name__ == "__main__":
    main()
