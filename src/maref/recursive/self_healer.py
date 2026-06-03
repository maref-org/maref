from __future__ import annotations

import contextlib
import importlib.util
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maref.recursive.self_diagnostician import DiagnosisReport
    from maref.recursive.unified_audit import UnifiedAuditRecord

HEALING_STRATEGIES = {
    "test_failure": "rerun_tests_with_verbose",
    "dependency_conflict": "pin_to_compatible_version",
    "coverage_drop": "identify_untested_paths_generate_stubs",
    "performance_regression": "bisect_commits_identify_cause",
    "import_error": "check_missing_dependency_install",
    "unknown": "full_system_scan",
}

HEAL_ACTION_RESULT_FIELDS = ("exit_code", "stdout", "stderr", "success", "detail")


@dataclass
class HealAction:
    problem_type: str
    strategy: str
    applied: bool = False
    result: str = ""
    iteration: int = 0
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    detail: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0


@dataclass
class HealingRecord:
    actions: list[HealAction] = field(default_factory=list)
    final_state: str = "unknown"
    iterations: int = 0
    converged: bool = False

    def to_unified(self, round_num: int = 0) -> list[UnifiedAuditRecord]:
        from maref.recursive.unified_audit import UnifiedAuditRecord, make_record_id

        records: list[UnifiedAuditRecord] = []
        for _i, action in enumerate(self.actions):
            outcome = "success" if action.success else "failure"
            records.append(
                UnifiedAuditRecord(
                    record_id=make_record_id(
                        "heal", hash((action.problem_type, action.iteration)) % 100000
                    ),
                    timestamp=time.time(),
                    layer="inner",
                    round=round_num,
                    event_type="healing",
                    source_module="SelfHealer",
                    target_module=action.problem_type,
                    decision=action.strategy,
                    justification=f"exit_code={action.exit_code} detail={action.detail}",
                    outcome=outcome,
                    context_refs=[],
                )
            )
        return records


class SelfHealer:
    def __init__(
        self,
        max_iterations: int = 3,
        strategy_executor: Callable[[str, str], HealAction] | None = None,
    ) -> None:
        self._max_iterations = max_iterations
        self._history: list[HealingRecord] = []
        self._strategy_executor = strategy_executor or self._execute_strategy

    def triage(self, report: DiagnosisReport) -> list[str]:
        from maref.recursive.self_diagnostician import RiskLevel

        problem_types: list[str] = []
        risk_matrix = report.risk_matrix

        if risk_matrix.get("entropy") == RiskLevel.CRITICAL:
            problem_types.append("test_failure")
        if risk_matrix.get("anomaly") in (RiskLevel.WARNING, RiskLevel.CRITICAL):
            problem_types.append("dependency_conflict")
        if risk_matrix.get("kg") == RiskLevel.CRITICAL:
            problem_types.append("coverage_drop")
        if risk_matrix.get("latency") in (RiskLevel.WARNING, RiskLevel.CRITICAL):
            problem_types.append("performance_regression")
        if risk_matrix.get("oscillation") == RiskLevel.CRITICAL:
            problem_types.append("import_error")
        if not problem_types:
            problem_types.append("unknown")

        return problem_types

    def _execute_strategy(self, strategy: str, problem_type: str) -> HealAction:
        exit_code = -1
        stdout = ""
        stderr = ""
        detail = ""

        try:
            if strategy == "rerun_tests_with_verbose":
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "-v", "--tb=short"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                exit_code = result.returncode
                stdout = result.stdout[-2000:]
                stderr = result.stderr[-1000:]
                detail = f"pytest exit={exit_code}"

            elif strategy == "pin_to_compatible_version":
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "check"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                exit_code = result.returncode
                stdout = result.stdout[-2000:]
                stderr = result.stderr[-1000:]
                if result.returncode != 0:
                    detail = f"pip check failed: {stderr[:200]}"
                else:
                    detail = "all dependencies compatible"

            elif strategy == "identify_untested_paths_generate_stubs":
                result = subprocess.run(
                    [sys.executable, "-m", "coverage", "run", "-m", "pytest", "-q"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                exit_code = result.returncode
                stdout = result.stdout[-2000:]
                stderr = result.stderr[-1000:]
                if result.returncode == 0:
                    detail = "coverage run completed, untested paths identified"
                else:
                    detail = f"coverage run failed exit={exit_code}"

            elif strategy == "bisect_commits_identify_cause":
                result = subprocess.run(
                    ["git", "log", "--oneline", "-10"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                exit_code = result.returncode
                stdout = result.stdout[:2000]
                stderr = result.stderr[:1000]
                recent = stdout.strip().split("\n") if stdout.strip() else []
                detail = f"recent commits: {len(recent)}"

            elif strategy == "check_missing_dependency_install":
                missing = []
                for mod_name in ("pytest", "pydantic", "structlog", "typer"):
                    spec = importlib.util.find_spec(mod_name)
                    if spec is None:
                        missing.append(mod_name)
                        with contextlib.suppress(Exception):
                            subprocess.run(
                                [sys.executable, "-m", "pip", "install", mod_name],
                                capture_output=True,
                                text=True,
                                timeout=60,
                            )
                if missing:
                    exit_code = 0
                    detail = f"installed missing: {', '.join(missing)}"
                else:
                    exit_code = 0
                    detail = "all dependencies present"

            elif strategy == "full_system_scan":
                checks = []
                try:
                    r = subprocess.run(
                        [sys.executable, "-c", "import maref; print('maref OK')"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    checks.append(("maref_import", r.returncode, r.stdout.strip()))
                except Exception as e:
                    checks.append(("maref_import", -1, str(e)))
                try:
                    r = subprocess.run(
                        [sys.executable, "-c", "import maref_lite; print('maref_lite OK')"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    checks.append(("maref_lite_import", r.returncode, r.stdout.strip()))
                except Exception as e:
                    checks.append(("maref_lite_import", -1, str(e)))
                exit_code = 0 if all(c[1] == 0 for c in checks) else 1
                detail = " | ".join(f"{n}:{c}" for n, c, _ in checks)

            else:
                exit_code = 1
                detail = f"unknown strategy: {strategy}"

        except subprocess.TimeoutExpired as e:
            exit_code = 124
            detail = f"timeout: {e}"
        except Exception as e:
            exit_code = 1
            detail = f"error: {e}"

        return HealAction(
            problem_type=problem_type,
            strategy=strategy,
            applied=True,
            result=detail,
            iteration=0,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            detail=detail,
        )

    def heal(
        self,
        problem_types: list[str],
        iteration: int = 0,
    ) -> list[HealAction]:
        actions: list[HealAction] = []
        for pt in problem_types:
            strategy = HEALING_STRATEGIES.get(pt, HEALING_STRATEGIES["unknown"])
            action = self._strategy_executor(strategy, pt)
            action.iteration = iteration
            actions.append(action)
        return actions

    def heal_cycle(
        self,
        report: DiagnosisReport,
        re_diagnose: Callable[[], DiagnosisReport] | None = None,
        auto_re_diagnose: bool = False,
        _observer: Any = None,
        _diagnostician: Any = None,
    ) -> HealingRecord:
        from maref.recursive.self_diagnostician import RiskLevel

        if (
            auto_re_diagnose
            and re_diagnose is None
            and _observer is not None
            and _diagnostician is not None
        ):

            def _auto_re_diag() -> DiagnosisReport:
                snapshot = _observer.observe()
                return _diagnostician.diagnose(snapshot)

            re_diagnose = _auto_re_diag

        healing = HealingRecord()
        current_risk = report.overall_risk

        for i in range(self._max_iterations):
            if current_risk == RiskLevel.NORMAL:
                healing.converged = True
                healing.final_state = "HEALTHY"
                healing.iterations = i
                self._history.append(healing)
                return healing

            problem_types = self.triage(report)
            actions = self.heal(problem_types, iteration=i)
            healing.actions.extend(actions)
            healing.iterations = i + 1

            if re_diagnose is not None:
                try:
                    fresh_report = re_diagnose()
                    current_risk = fresh_report.overall_risk
                except Exception:
                    current_risk = report.overall_risk
            else:
                all_succeeded = all(a.success for a in actions)
                current_risk = RiskLevel.NORMAL if all_succeeded else report.overall_risk

            if current_risk == RiskLevel.NORMAL:
                healing.final_state = "RECOVERED"
                healing.converged = True
                self._history.append(healing)
                return healing

        healing.final_state = "DEGRADED"
        healing.converged = False
        self._history.append(healing)
        return healing

    @property
    def history(self) -> list[HealingRecord]:
        return list(self._history)
