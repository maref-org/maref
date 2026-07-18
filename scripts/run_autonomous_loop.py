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
import gc
import json
import logging
import os
import shutil
import subprocess
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


def _run_subprocess_worker(
    q: "Any",
    cmd_args: list[str],
    **kwargs: Any,
) -> None:
    """Worker for ``_run_subprocess_isolated`` — module-level for pickle compatibility.

    ``multiprocessing`` on macOS defaults to the ``spawn`` start method,
    which requires the target function to be importable (not a nested/
    local function).  This module-level wrapper runs the actual
    ``subprocess.run`` call in the child process and pipes the result
    back through a ``multiprocessing.Queue`` so all memory is released
    on process exit.
    """
    # Suppress macOS MallocStackLogging warnings: the parent sets this to '0'
    # but spawned multiprocessing children inherit the env var and print
    # "can't turn off malloc stack logging because it was not enabled" to
    # stderr on every invocation.  Removing it entirely silences the noise.
    import os as _os
    _os.environ.pop("MallocStackLogging", None)

    try:
        res = subprocess.run(cmd_args, **kwargs)
        q.put({
            "returncode": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        })
    except subprocess.TimeoutExpired as e:
        q.put({
            "timeout": True,
            "stdout": e.stdout,
            "stderr": e.stderr,
        })
    except BaseException as e:
        q.put({"error": repr(e)})


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
        self._fixed_files: set[str] = set()  # Fix D: track already-adopted files

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
        # Fix 16: track files modified by apply_fn for negative-gain rollback
        self._last_modified_files: list[str] = []
        # Fix 22c: original content of ruff-autofixed files for rollback
        self._ruff_backups: dict[str, str] = {}

        # Fix 27: suppress MallocStackLogging (inherited by subprocesses,
        # accumulates memory until OS kills the parent — the #1 cause of
        # premature death across v11→v19). Set early so all subprocess
        # calls inherit a clean environment.
        #
        # IMPORTANT: the variable MUST be *removed*, not set to "0".
        # Setting it to "0" still enables the malloc stack logging
        # machinery; the child process will print "could not tag
        # MSL-related memory as no_footprint" warnings and the
        # logging pages are counted in the process footprint,
        # inflating RSS while providing no actual logging benefit.
        os.environ.pop("MallocStackLogging", None)
        self._MIN_FREE_MEM_MB = 200  # halt if < 200 MB free

        # Fix 28: checkpoint path for resume-after-crash
        self._checkpoint_path: Path | None = None

        # Fix 29: adaptive convergence interval
        self._consecutive_noop = 0  # cycles with 0 hypotheses
        self._current_interval = loop_interval_minutes * 60

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

    def _run_subprocess_isolated(
        self,
        cmd_args: list[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess:
        """Fix 30: run subprocess in an isolated process for guaranteed memory reclamation.

        On macOS, ``subprocess.run(capture_output=True)`` reads the full
        subprocess output into the parent's heap.  CPython's memory allocator
        does not reliably return freed pages to the OS, so RSS grows
        monotonically across cycles.  Wrapping each call in a
        ``multiprocessing.Process`` ensures 100% of the child's memory is
        reclaimed by the OS on exit.

        Accepts the same arguments as ``subprocess.run``
        (``capture_output``, ``text``, ``timeout``, ``cwd``, …).

        Returns ``subprocess.CompletedProcess`` with the same interface so
        callers require no changes.
        """
        import multiprocessing as _mp
        import queue as _queue

        # Use fork context to avoid Python 3.14+ spawn's
        # _check_not_importing_main() RuntimeError.  The caller is
        # single-threaded at this point, making fork safe.
        _mp_ctx = _mp.get_context("fork")
        _result_queue: "_mp.ctx.ForkContext.Queue[dict[str, Any]]" = _mp_ctx.Queue()  # type: ignore[name-defined]  # noqa: E501
        _timeout = kwargs.get("timeout")

        p = _mp_ctx.Process(
            target=_run_subprocess_worker,
            args=(_result_queue, cmd_args),
            kwargs=kwargs,
        )
        p.start()
        p.join(timeout=(_timeout or 120) + 30)  # grace period for process overhead

        if p.is_alive():
            p.terminate()
            p.join()

        try:
            result = _result_queue.get_nowait()
        except _queue.Empty:
            return subprocess.CompletedProcess(
                args=cmd_args, returncode=-1,
                stdout=b"", stderr=b"",
            )

        if "error" in result:
            raise RuntimeError(result["error"])

        if result.get("timeout"):
            raise subprocess.TimeoutExpired(
                cmd_args, _timeout or 120,
                output=result.get("stdout"),
                stderr=result.get("stderr"),
            )

        return subprocess.CompletedProcess(
            args=cmd_args,
            returncode=result["returncode"],
            stdout=result.get("stdout"),
            stderr=result.get("stderr"),
        )

    def _capture_gui_errors(self) -> list[dict]:
        """Fix 3b/8: capture concrete ESLint errors when gui_build is critical."""
        try:
            r = self._run_subprocess_isolated(
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
            proc = self._run_subprocess_isolated(
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
            # Fix 14a: use max(1.0, ...) not max(0.0, ...) so coverage_pct
            # never bottoms out at 0. When the project has 20+ ESLint errors,
            # the old mapping produced coverage_pct=0 for both before and
            # after benchmarks, making gain always 0 (the primary gain formula
            # requires before.coverage_pct > 0). With max(1.0, ...) the gain
            # formula can detect improvements even from a high-error baseline.
            result["coverage_pct"] = max(1.0, 100.0 - total_errors * 5.0)
            result["gui_error_count"] = float(total_errors)
        except Exception:
            # If GUI lint fails, fall back to 50.0 so ruff adjustments are
            # not swallowed by max(1.0, ...) in Phase 3.
            result["coverage_pct"] = 50.0
            result["gui_error_count"] = 0.0

        # Phase 3 (Fix 22): ruff lint count — when GUI is clean, Python
        # lint errors become the next improvement target. Each ruff error
        # reduces coverage_pct by 0.5, so the optimizer can detect gains
        # when the LLM fixes Python lint issues.
        try:
            ruff_proc = self._run_subprocess_isolated(
                [_sys.executable, "-m", "ruff", "check", "src/", "--statistics", "-q"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            ruff_errors = 0
            for line in ruff_proc.stdout.strip().split("\n"):
                line = line.strip()
                if line and line[0].isdigit():
                    parts = line.split()
                    if parts:
                        with contextlib.suppress(ValueError):
                            ruff_errors += int(parts[0])
            result["ruff_error_count"] = float(ruff_errors)
            # Blend GUI + ruff: weight ruff at 2.0 per error so that
            # lint-fix hypotheses produce measurable coverage change.
            # Use max(0.01, ...) instead of max(1.0, ...) so that a high
            # error count (>=25 with weight=2.0, baseline=50) still produces
            # a distinguishable coverage value — the old max(1.0, ...) caused
            # every coverage_pct to clamp to 1.0 when ruff >= 25, making
            # before == after == 1.0 and gain = 0% for every hypothesis.
            raw_coverage = result["coverage_pct"] - ruff_errors * 2.0
            result["coverage_pct"] = max(0.01, raw_coverage)
            logger.debug(
                "Benchmark ruff: errs=%d baseline=%.1f raw=%.1f clamped=%.1f",
                ruff_errors, result.get("gui_coverage_pct", 50.0),
                raw_coverage, result["coverage_pct"],
            )
        except Exception:
            result["ruff_error_count"] = 0.0

        result["execution_time_ms"] = (time.time() - start) * 1000.0
        return result

    # Fix 17: priority map for ESLint rule difficulty. Lower = easier to fix.
    # no-unused-vars is trivial (delete/rename a token); react-hooks/* errors
    # are structural (require understanding component lifecycle). The LLM
    # repeatedly failed on react-hooks/set-state-in-effect in CooldownDashboard
    # while 5+ easy no-unused-vars files sat unfixed. Sorting by difficulty
    # lets the loop accumulate easy wins instead of deadlocking on hard ones.
    _ESLINT_DIFFICULTY = {
        "no-unused-vars": 0,
        "@typescript-eslint/no-unused-vars": 0,
        "no-empty": 1,
        "no-explicit-any": 1,
        "@typescript-eslint/no-explicit-any": 1,
        "react-hooks/rules-of-hooks": 2,
        "react-hooks/exhaustive-deps": 2,
        "react-hooks/set-state-in-effect": 3,
        "react-hooks/static-components": 3,
    }
    _ESLINT_DEFAULT_DIFFICULTY = 1

    @classmethod
    def _rule_difficulty(cls, rule_id: str) -> int:
        return cls._ESLINT_DIFFICULTY.get(
            rule_id, cls._ESLINT_DEFAULT_DIFFICULTY
        )

    def _build_gui_proposal(self, gui_errors: list[dict]) -> Any:
        """Fix 3b/14b/15/17: build an ArchitectureProposal targeting the worst GUI file."""
        if not gui_errors:
            return None
        from maref.recursive.self_architect import ArchitectureProposal, ChangeType

        # Fix 15: filter out build artifacts and non-source files.
        # ESLint may report errors in src-tauri/target/ (compiled .js files),
        # node_modules/, or other generated directories. These can't be fixed
        # by the LLM (binary files, UTF-8 decode errors) and waste API calls.
        _SOURCE_EXTS = {".ts", ".tsx", ".js", ".jsx"}
        _IGNORE_SUBSTRS = (
            "src-tauri/target", "node_modules", "/dist/", "/build/",
            "/.next/", "/coverage/",
        )
        filtered = []
        for e in gui_errors:
            f = e.get("file", "")
            if any(ig in f for ig in _IGNORE_SUBSTRS):
                continue
            if not any(f.endswith(ext) for ext in _SOURCE_EXTS):
                continue
            filtered.append(e)
        if not filtered:
            return None

        # Fix 17: smart file selection. Previously `max(error_count)` always
        # returned the first file when counts were tied, deadlocking the loop
        # on CooldownDashboard.tsx (react-hooks/set-state-in-effect) while 5
        # easy no-unused-vars files sat unfixed. Now sort by:
        #   1. error_count DESC (more errors = higher ROI per LLM call)
        #   2. min rule difficulty ASC (easier errors first)
        #   3. file path ASC (stable tiebreak for reproducibility)
        # This lets the LLM rack up easy wins (no-unused-vars) before
        # attempting structural react-hooks/* errors.
        def _sort_key(e: dict) -> tuple:
            msgs = e.get("messages", []) or []
            min_difficulty = (
                min((self._rule_difficulty(m.get("ruleId", "")) for m in msgs), default=self._ESLINT_DEFAULT_DIFFICULTY)
                if msgs else self._ESLINT_DEFAULT_DIFFICULTY
            )
            return (-e.get("error_count", 0), min_difficulty, e.get("file", ""))

        filtered.sort(key=_sort_key)
        target = filtered[0]
        target_file = target["file"]
        # Fix 14b: include full ESLint error details (line numbers + messages)
        # in the rationale and affected_symbols. Previously only rule IDs were
        # passed (e.g., "@typescript-eslint/no-unused-vars"), so the LLM knew
        # WHICH rules were violated but not WHERE or WHAT the specific errors
        # were. This caused the LLM to make generic refactors instead of
        # fixing the actual errors (e.g., it changed component props but
        # didn't remove unused imports).
        short_file = target_file.split("/")[-1]
        error_details = "\n".join(
            f"  - Line {m.get('line', '?')}: {m.get('ruleId', 'unknown')} — {m.get('message', '')[:120]}"
            for m in target["messages"]
        )
        return ArchitectureProposal(
            proposal_id=f"gui_fix_{int(time.time())}",
            timestamp=time.time(),
            current_arch=target_file,
            proposed_arch=target_file,
            rationale=(
                f"Fix {target['error_count']} ESLint errors in {short_file}:\n"
                f"{error_details}\n"
                f"Remove unused imports/variables, fix type errors, and ensure "
                f"ESLint compliance. Do NOT change component logic unless required "
                f"to fix an error."
            ),
            risk_assessment="low",
            confidence=0.6,
            target_files=[target_file],
            change_type=ChangeType.GENERAL_REFACTOR,
            affected_symbols=[
                f"L{m.get('line', '?')}:{m.get('ruleId', 'unknown')} — {m.get('message', '')[:80]}"
                for m in target["messages"]
            ],
            preconditions=["gui_build probe must be critical"],
        )

    def _default_apply_fn(self) -> None:
        """Default optimization apply function — risk-driven (Fix 3c)."""
        if self._executor is None:
            return
        # Fix 16: reset modified-files tracker before each apply
        self._last_modified_files = []
        self._ruff_backups = {}  # Fix 22c: reset ruff backups
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

            # Fix 22c: when GUI is clean, run ruff --fix to auto-fix
            # Python lint errors. This is a deterministic, safe operation
            # (ruff only applies "safe" fixes by default) that produces
            # measurable gain via the Fix 22 ruff_error_count benchmark
            # dimension. The LLM is not involved — ruff fixes are rules-
            # based and well-tested.
            if proposal is None:
                self._apply_ruff_autofix()
                # Continue to LLM ruff fix regardless of auto-fix results
                # so that deep fixes (F821, F841, etc.) produce measurable
                # coverage gain through the benchmark.

            # Fix 23: when ruff --fix produces no auto-fixable changes
            # but errors remain (F821 undefined-name, F841 unused-variable,
            # E402 import-order, SIM103 needless-bool), feed the errors to
            # the LLM via ArchitectureProposal for targeted fixes.
            if proposal is None:
                proposal = self._build_ruff_proposal()
                if proposal is not None:
                    logger.info(
                        "Fix 23: LLM ruff fix for %s (%d errors)",
                        proposal.target_files[0],
                        len(proposal.affected_symbols or []),
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
                # Fix 16: record files modified by this apply for rollback
                if hasattr(proposal, "target_files"):
                    self._last_modified_files = list(proposal.target_files)
                deployer = getattr(self._executor, "_deployer", None)
                if deployer is not None and hasattr(deployer, "_deployed"):
                    self._last_modified_files.extend(deployer._deployed.keys())
        except Exception as exc:
            logger.warning("Default apply fn failed: %s", exc)

    def _build_ruff_hypothesis(self, snapshot: Any) -> Any:
        """Fix 22b: build a ruff-lint hypothesis when diagnosis finds nothing.

        Runs `ruff check src/ --statistics` and if there are errors, creates
        an OptimizationHypothesis targeting Python lint cleanup. The LLM
        will then fix ruff errors via _default_apply_fn → SelfArchitect.
        """
        try:
            import sys as _sys
            proc = self._run_subprocess_isolated(
                [_sys.executable, "-m", "ruff", "check", "src/",
                 "--statistics", "-q"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            ruff_errors = 0
            top_rules: list[str] = []
            for line in proc.stdout.strip().split("\n"):
                line = line.strip()
                if line and line[0].isdigit():
                    parts = line.split()
                    if parts:
                        with contextlib.suppress(ValueError):
                            count = int(parts[0])
                            ruff_errors += count
                            if len(top_rules) < 3:
                                top_rules.append(
                                    f"{parts[-1]}({count})"
                                )
            if ruff_errors == 0:
                return None
            from maref.recursive.self_optimizer import OptimizationHypothesis
            return OptimizationHypothesis(
                hypothesis_id=f"ruff_{snapshot.timestamp}",
                description=(
                    f"Python lint: {ruff_errors} ruff errors "
                    f"({', '.join(top_rules)}) — fix auto-fixable rules"
                ),
                target_module="python_lint",
                experiment_result={"ruff_error_count": float(ruff_errors)},
            )
        except Exception as exc:
            logger.warning("Fix 22b: ruff hypothesis build failed: %s", exc)
            return None

    def _apply_ruff_autofix(self) -> int:
        """Fix 22c: run `ruff check src/ --fix` to auto-fix Python lint errors.

        Ruff's safe fixes (applicability="safe") are deterministic and
        well-tested — they include import sorting (I001), PEP-585 annotations
        (UP006), trailing newlines (W292), etc. This avoids spending an LLM
        call on mechanical lint fixes the LLM repeatedly gets wrong.

        Backs up original file content in ``self._ruff_backups`` so Fix 16's
        ``_rollback_modified_files`` can restore it on negative gain.
        Returns the number of files actually modified.
        """
        import json as _json
        import sys as _sys

        try:
            # Phase 1: enumerate files with ruff errors (before fix)
            proc = self._run_subprocess_isolated(
                [_sys.executable, "-m", "ruff", "check", "src/",
                 "--output-format", "json", "-q"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if not proc.stdout.strip():
                return 0
            errors = _json.loads(proc.stdout)
            if not isinstance(errors, list) or not errors:
                return 0
            error_files = sorted({e["filename"] for e in errors if "filename" in e})
            if not error_files:
                return 0

            # Phase 2: back up original content of every file with errors
            backups: dict[str, str] = {}
            for fpath in error_files:
                try:
                    with open(fpath) as f:
                        backups[fpath] = f.read()
                except OSError:
                    pass

            # Phase 3: run ruff --fix (safe fixes only, the default)
            self._run_subprocess_isolated(
                [_sys.executable, "-m", "ruff", "check", "src/", "--fix", "-q"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Phase 4: detect which files actually changed
            modified: list[str] = []
            for fpath in error_files:
                original = backups.get(fpath)
                if original is None:
                    continue
                try:
                    with open(fpath) as f:
                        if f.read() != original:
                            modified.append(fpath)
                except OSError:
                    pass

            if not modified:
                return 0

            # Phase 5: store backups for Fix 16 rollback
            for fpath in modified:
                self._ruff_backups[fpath] = backups[fpath]
            self._last_modified_files.extend(modified)
            logger.info(
                "Fix 22c: ruff --fix modified %d file(s) (%d ruff errors were fixable)",
                len(modified),
                len(errors),
            )
            return len(modified)
        except Exception as exc:
            logger.warning("Fix 22c: ruff autofix failed: %s", exc)
            return 0

    def _build_ruff_proposal(self) -> Any:
        """Fix 23: build ArchitectureProposal for non-auto-fixable ruff errors.

        Feeds ruff error details to the LLM via SelfArchitect, targeting
        F821 (undefined-name), F841 (unused-variable), E402 (import-not-at-top),
        and SIM103 (needless-bool) errors that ``ruff --fix`` cannot handle
        with safe applicability.
        """
        import json as _json
        import sys as _sys

        try:
            proc = self._run_subprocess_isolated(
                [_sys.executable, "-m", "ruff", "check", "src/",
                 "--output-format", "json", "-q"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if not proc.stdout.strip():
                return None
            errors = _json.loads(proc.stdout)
            if not isinstance(errors, list) or not errors:
                return None

            # Group errors by file
            by_file: dict[str, list[dict]] = {}
            for e in errors:
                fname = e.get("filename", "")
                if not fname:
                    continue
                by_file.setdefault(fname, []).append(e)

            if not by_file:
                return None

            # Fix 27: pick the worst file that hasn't been fixed yet.
            # Once a file is adopted (Fix D), skip it so subsequent
            # cycles target other files instead of re-fixing the same one.
            sorted_files = sorted(
                [(f, es) for f, es in by_file.items() if f not in getattr(self, "_fixed_files", set())],
                key=lambda x: (-len(x[1]), x[0]),
            )
            if not sorted_files:
                # All files already fixed — nothing to do this cycle.
                return None
            target_file, file_errors = sorted_files[0]

            error_details = "\n".join(
                f"  - Line {e.get('location', {}).get('row', '?')}: "
                f"{e.get('code', 'unknown')} — {e.get('message', '')[:120]}"
                for e in file_errors
            )

            from maref.recursive.self_architect import ArchitectureProposal, ChangeType
            return ArchitectureProposal(
                proposal_id=f"ruff_fix_{int(time.time())}",
                timestamp=time.time(),
                current_arch=target_file,
                proposed_arch=target_file,
                rationale=(
                    f"Fix {len(file_errors)} ruff errors in "
                    f"{target_file.split('/')[-1]}:\n"
                    f"{error_details}\n"
                    f"Fix undefined names (F821 — variable not defined in "
                    f"scope), unused variables (F841), module-level import "
                    f"order (E402 — move to top of file), and simplify "
                    f"needless boolean returns (SIM103 — return x directly). "
                    f"Do NOT change runtime logic."
                ),
                risk_assessment="low",
                confidence=0.5,
                target_files=[target_file],
                change_type=ChangeType.GENERAL_REFACTOR,
                affected_symbols=[
                    f"L{e.get('location', {}).get('row', '?')}:"
                    f"{e.get('code', 'unknown')} — {e.get('message', '')[:80]}"
                    for e in file_errors
                ],
                preconditions=[],
            )
        except Exception as exc:
            logger.warning("Fix 23: ruff proposal build failed: %s", exc)
            return None

    def _rollback_modified_files(self) -> int:
        """Fix 16: roll back files modified by the last apply_fn.

        Two rollback mechanisms:
        - Fix 22c: ruff-autofixed files restored from ``_ruff_backups``
        - Fix 16: LLM-modified files restored via ``AtomicDeployer.rollback``
        """
        rolled_back = 0

        # Fix 22c: restore ruff-autofixed files first (deterministic restore)
        ruff_restored: set[str] = set()
        if self._ruff_backups:
            ruff_restored = set(self._ruff_backups.keys())
            for fpath, content in self._ruff_backups.items():
                try:
                    with open(fpath, "w") as f:
                        f.write(content)
                    rolled_back += 1
                except OSError as e:
                    logger.warning("Fix 16: ruff rollback failed for %s: %s", fpath, e)
            self._ruff_backups = {}

        # Fix 16: AtomicDeployer rollback for LLM-modified files
        if self._last_modified_files and self._executor is not None:
            deployer = getattr(self._executor, "_deployer", None)
            if deployer is not None:
                for file_path in self._last_modified_files:
                    if file_path in ruff_restored:
                        continue  # already restored by ruff backup path
                    try:
                        result = deployer.rollback(file_path)
                        if result.success:
                            rolled_back += 1
                    except Exception as e:
                        logger.warning("Fix 16: rollback failed for %s: %s", file_path, e)

        self._last_modified_files = []
        return rolled_back

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
            # Fix 22b: when diagnosis finds no critical risks (GUI clean,
            # latency normal), inject a ruff-lint hypothesis so the LLM
            # can continue improving Python code quality.
            if not hypotheses:
                # Fix 26: skip ruff hypothesis when error count is too low
                # (< 3). v17 saturated at 2 non-auto-fixable errors that even
                # the LLM cannot resolve (F821 forward reference, SIM103 unsafe
                # fix). Continuing to inject ruff hypotheses at this point
                # wastes ~19 minutes/cycle on guaranteed 0% gain attempts.
                ruff_h = self._build_ruff_hypothesis(snapshot)
                if ruff_h is not None:
                    ruff_count = ruff_h.experiment_result.get("ruff_error_count", 0)
                    if ruff_count < 3:
                        logger.info(
                            "Fix 26: skipping ruff hypothesis — only %d "
                            "errors remain (saturated, < 3)", ruff_count,
                        )
                    else:
                        hypotheses.append(ruff_h)
                        logger.info(
                            "Fix 22b: injected ruff hypothesis (%d errors)",
                            ruff_count,
                        )
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
                    # Fix D: record adopted files so _build_ruff_proposal
                    # skips them in subsequent cycles.
                    for f in getattr(self, "_last_modified_files", []):
                        self._fixed_files.add(f)
                    logger.info(
                        "Fix D: %d files fixed so far: %s",
                        len(self._fixed_files),
                        list(self._fixed_files)[:5],
                    )
                else:
                    logger.info("Rejected hypothesis %s: gain=%.2f%%", hypothesis.hypothesis_id, hypothesis.gain_pct * 100)
                    # Fix 16: auto-rollback on negative gain to prevent regression accumulation
                    if hypothesis.gain_pct < 0:
                        self._optimizer.revert_if_regression(hypothesis)
                        rolled_back = self._rollback_modified_files()
                        logger.warning(
                            "Fix 16: negative gain %.2f%% — rolled back %d file(s): %s",
                            hypothesis.gain_pct * 100,
                            rolled_back,
                            self._last_modified_files[:3],
                        )

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

        # Fix (memory): force GC after each cycle to reclaim Python heap pages
        # that accumulated during engine / snapshot / benchmark runs.
        gc.collect()

        return result

    def run(self) -> None:
        """Run the autonomous loop for the configured duration."""
        start_time = time.time()
        end_time = start_time + self._duration_hours * 3600

        # Fix 28: try to restore state from previous run
        self._load_checkpoint()

        logger.info("=" * 60)
        logger.info("AUTONOMOUS LOOP START")
        logger.info("  Duration:     %.1f hours", self._duration_hours)
        logger.info("  Interval:     %.0f minutes (base)", self._loop_interval / 60)
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

            # Fix 27: halt check 4 — memory pressure (prevents OS-induced death)
            if not self._check_memory_pressure():
                self._halt_reason = "memory_pressure"
                break

            cycle_start = time.time()
            result = self.run_one_cycle()

            # Save per-cycle report
            report_path = self._output_dir / f"cycle-{self._cycle_count:04d}.json"
            with open(report_path, "w") as f:
                json.dump(result, f, indent=2, default=str)

            # Fix 28: persist checkpoint for resume-after-crash
            self._save_checkpoint()

            # Fix 30: force memory reclamation after each cycle
            self._force_memory_reclaim()

            # Fix 29: adaptive convergence interval
            hypothesis_count = result.get("phases", {}).get("diagnosis", {}).get("hypothesis_count", 0)
            adopted = any(
                h.get("gain_pct", 0) >= 0.05
                for h in result.get("phases", {}).get("hypotheses", [])
            ) if "hypotheses" in result.get("phases", {}).get("diagnosis", {}) else False
            if hypothesis_count == 0:
                self._consecutive_noop += 1
                if self._consecutive_noop >= 3 and self._current_interval < 3600:
                    self._current_interval = min(3600, self._current_interval * 2)
                    logger.info(
                        "Fix 29: %d consecutive noop cycles — "
                        "extended interval to %.0f min",
                        self._consecutive_noop,
                        self._current_interval / 60,
                    )
            else:
                if self._consecutive_noop >= 3:
                    logger.info(
                        "Fix 29: hypothesis detected after %d noop cycles — "
                        "resuming base interval",
                        self._consecutive_noop,
                    )
                self._consecutive_noop = 0
                self._current_interval = self._loop_interval

            # Check if we should stop early due to wall clock
            elapsed = time.time() - cycle_start
            remaining = end_time - time.time()
            if remaining <= 0:
                break

            # Sleep if we finished faster than the interval
            sleep_time = min(self._current_interval - elapsed, remaining)
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


    def _check_memory_pressure(self) -> bool:
        """Fix 27: check available memory. Returns True if OK to continue.

        On macOS, ``vm_stat`` reports ``pages free`` (completely untouched)
        and ``pages inactive`` (used but immediately reclaimable by the
        kernel).  Counting only ``free`` underestimates available memory on
        systems with large file caches.  We use ``free + inactive`` as the
        true available memory — matching macOS's own memory-pressure
        calculation (``vm_page_free_count + vm_page_inactive_count``).
        """
        try:
            proc = self._run_subprocess_isolated(
                ["vm_stat"],
                capture_output=True, text=True, timeout=5,
            )
            # macOS Apple Silicon page size = 16384 bytes
            _PAGE_SIZE = 16384
            _MB = 1024.0 * 1024.0
            free_pages = 0
            inactive_pages = 0
            for line in proc.stdout.split("\n"):
                lower = line.lower()
                try:
                    if "pages free" in lower:
                        free_pages = int(
                            line.split(":")[1].strip().rstrip(".")
                        )
                    elif "pages inactive" in lower:
                        inactive_pages = int(
                            line.split(":")[1].strip().rstrip(".")
                        )
                except (ValueError, IndexError):
                    pass
            available_mb = (free_pages + inactive_pages) * _PAGE_SIZE / _MB
            if available_mb < self._MIN_FREE_MEM_MB:
                logger.critical(
                    "Fix 27: low memory — %.0f MB available "
                    "(free=%d, inactive=%d, threshold: %d MB). "
                    "Halting to avoid OS kill.",
                    available_mb, free_pages, inactive_pages,
                    self._MIN_FREE_MEM_MB,
                )
                return False
            if available_mb < self._MIN_FREE_MEM_MB * 2:
                logger.warning(
                    "Fix 27: memory pressure — only %.0f MB available "
                    "(free=%d, inactive=%d, threshold: %d MB). "
                    "Continuing with caution.",
                    available_mb, free_pages, inactive_pages,
                    self._MIN_FREE_MEM_MB,
                )
            elif free_pages * _PAGE_SIZE / _MB < self._MIN_FREE_MEM_MB:
                logger.info(
                    "Fix 27: free pages low (%d) but inactive pages (%d) "
                    "provide %.0f MB available — OK to continue.",
                    free_pages, inactive_pages, available_mb,
                )
            return True
        except Exception as exc:
            logger.debug("Fix 27: memory check failed (fail open): %s", exc)
            return True  # fail open — don't halt on check error

    def _force_memory_reclaim(self) -> int:
        """Fix 30: force garbage collection to reduce memory fragmentation.

        Despite subprocess isolation (Fix 30 Process wrapper), CPython's
        generational GC may still hold cross-cycle references (e.g. metrics
        history, cached ASTs).  This method forces collection of all three
        generations and, on platforms that support it (Linux w/ glibc), asks
        the system allocator to return free pages to the OS.

        Returns the number of collected objects.
        """
        import gc as _gc
        collected = _gc.collect()
        collected += _gc.collect(2)  # also sweep oldest generation
        # macOS libc does not export malloc_trim, but calling it on
        # unsupported platforms is a harmless no-op (returns 0).
        with contextlib.suppress(Exception):
            import ctypes as _ctypes
            _libc = _ctypes.CDLL("libc.dylib")
            if hasattr(_libc, "malloc_trim"):
                _libc.malloc_trim(0)
        if collected > 0:
            logger.debug("Fix 30: GC reclaimed %d objects", collected)
        return collected

    def _save_checkpoint(self) -> None:
        """Fix 28: persist cycle state so crashed runs can resume."""
        if self._checkpoint_path is None:
            self._checkpoint_path = self._output_dir / ".checkpoint.json"
        try:
            data = {
                "cycle_count": self._cycle_count,
                "success_count": self._success_count,
                "failure_count": self._failure_count,
                "consecutive_noop": self._consecutive_noop,
                "consecutive_failures": self._consecutive_failures,
                "system_critical_streak": self._system_critical_streak,
            }
            with open(self._checkpoint_path, "w") as f:
                json.dump(data, f)
        except OSError as exc:
            logger.warning("Fix 28: checkpoint save failed: %s", exc)

    def _load_checkpoint(self) -> None:
        """Fix 28: restore state from checkpoint on restart."""
        if self._checkpoint_path is None:
            self._checkpoint_path = self._output_dir / ".checkpoint.json"
        if not self._checkpoint_path.exists():
            return  # no checkpoint — fresh start
        try:
            with open(self._checkpoint_path) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            for key, default in [
                ("cycle_count", 0),
                ("success_count", 0),
                ("failure_count", 0),
                ("consecutive_noop", 0),
                ("consecutive_failures", 0),
                ("system_critical_streak", 0),
            ]:
                setattr(self, f"_{key}", data.get(key, default))
            logger.info(
                "Fix 28: restored checkpoint — resuming at cycle-%04d "
                "(cumulative: %d ok / %d fail)",
                self._cycle_count, self._success_count, self._failure_count,
            )
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Fix 28: checkpoint load failed: %s", exc)


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
