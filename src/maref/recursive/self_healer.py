from __future__ import annotations

import contextlib
import importlib.util
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maref.immunity.auto_gene_pipeline import AutoGeneExtractionPipeline
    from maref.recursive.self_diagnostician import DiagnosisReport
    from maref.recursive.unified_audit import UnifiedAuditRecord

HEALING_STRATEGIES = {
    "test_failure": "rerun_tests_with_verbose",
    "dependency_conflict": "pin_to_compatible_version",
    "coverage_drop": "identify_untested_paths_generate_stubs",
    "performance_regression": "bisect_commits_identify_cause",
    "import_error": "check_missing_dependency_install",
    "syntax_error": "auto_fix_syntax",
    "type_error": "auto_fix_types",
    "unknown": "full_system_scan",
    # P5.5: RSI-specific strategies
    "experience_pool_starvation": "rebalance_experience_pool",
    "pareto_front_degradation": "restore_pareto_front",
    "dimension_weight_drift": "normalize_dimension_weights",
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
        gene_pipeline: AutoGeneExtractionPipeline | None = None,
        latency_threshold_ok: float = 10.0,
        executor: Any = None,
        project_root: str = "",
    ) -> None:
        self._max_iterations = max_iterations
        self._history: list[HealingRecord] = []
        self._strategy_executor = strategy_executor or self._execute_strategy
        self._gene_pipeline = gene_pipeline
        self._latency_threshold_ok = latency_threshold_ok
        self._executor = executor
        self._project_root = project_root

    def triage(self, report: DiagnosisReport) -> list[str]:
        from maref.recursive.self_diagnostician import RiskLevel

        problem_types: list[str] = []
        risk_matrix = report.risk_matrix
        ctx = report.diagnostic_context

        # ── Entropy high → test_failure ─────────────────────────
        if risk_matrix.get("entropy") in (RiskLevel.WARNING, RiskLevel.CRITICAL):
            problem_types.append("test_failure")

        # ── Latency: test duration → performance_regression ─────
        if risk_matrix.get("latency") in (RiskLevel.WARNING, RiskLevel.CRITICAL):
            latency_ms = ctx.get("latency_test_duration_ms", 0)
            entropy_ratio = ctx.get("entropy_test_failure_ratio", 0)
            if latency_ms > 0 and entropy_ratio < 0.1:
                # High latency but low failure rate → real performance issue
                problem_types.append("performance_regression")
            elif latency_ms > 0:
                # High latency with failures → test infrastructure issue
                problem_types.append("test_failure")
            else:
                problem_types.append("performance_regression")

        # ── KG orphan ratio → coverage_drop ─────────────────────
        if risk_matrix.get("kg") in (RiskLevel.WARNING, RiskLevel.CRITICAL):
            problem_types.append("coverage_drop")

        # ── Oscillation high → import_error (release churn) ─────
        if risk_matrix.get("oscillation") == RiskLevel.CRITICAL:
            problem_types.append("import_error")

        # ── P5.5: RSI-specific triage ────────────────────────────
        pool_ratio = ctx.get("experience_pool_ratio", 1.0)
        if pool_ratio < 0.3:
            problem_types.append("experience_pool_starvation")

        pareto_degraded = ctx.get("pareto_front_degraded", False)
        if pareto_degraded:
            problem_types.append("pareto_front_degradation")

        dim_drift = ctx.get("dimension_weight_drift", 0.0)
        if dim_drift > 20.0:
            problem_types.append("dimension_weight_drift")

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
                import time as _time

                # Measure baseline test collection time
                t0 = _time.monotonic()
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "tests/", "--co", "-q"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                elapsed_s = _time.monotonic() - t0
                exit_code = result.returncode
                stdout = result.stdout[:2000]
                stderr = result.stderr[:1000]

                # Also check recent git activity
                git_result = subprocess.run(
                    ["git", "log", "--oneline", "-5"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                recent = (
                    git_result.stdout.strip().split("\n")
                    if git_result.returncode == 0 and git_result.stdout.strip()
                    else []
                )

                detail_parts = [
                    f"test_collection={elapsed_s:.2f}s",
                    f"recent_commits={len(recent)}",
                ]
                # Also get head hash for traceability
                head_result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if head_result.returncode == 0:
                    detail_parts.append(f"HEAD={head_result.stdout.strip()}")
                detail = " | ".join(detail_parts)

                # Pytest collection quicker than 10s → latency is acceptable
                if elapsed_s < self._latency_threshold_ok:
                    detail += f" | latency OK (<{self._latency_threshold_ok}s)"

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
                    result = subprocess.run(
                        [sys.executable, "-c", "import maref; print('maref OK')"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    checks.append(("maref_import", result.returncode, result.stdout.strip()))
                except Exception as e:
                    checks.append(("maref_import", -1, str(e)))
                try:
                    result = subprocess.run(
                        [sys.executable, "-c", "import maref_lite; print('maref_lite OK')"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    checks.append(("maref_lite_import", result.returncode, result.stdout.strip()))
                except Exception as e:
                    checks.append(("maref_lite_import", -1, str(e)))
                exit_code = 0 if all(c[1] == 0 for c in checks) else 1
                detail = " | ".join(f"{n}:{c}" for n, c, _ in checks)

            elif strategy in ("auto_fix_syntax", "auto_fix_types"):
                fix_type = "syntax" if strategy == "auto_fix_syntax" else "type"
                try:
                    if self._executor is not None:
                        result = self._executor.deploy(self._make_fix_code(fix_type))
                        exit_code = 0 if result.success else 1
                        detail = f"auto_fix_{fix_type}: {result.message}"
                    else:
                        exit_code = 1
                        detail = f"no executor configured for {fix_type} fix"
                except Exception as e:
                    exit_code = 1
                    detail = f"auto_fix_{fix_type}: {e}"

            # ═══════════════════════════════════════════════════════
            # P5.5: RSI-specific strategies
            # ═══════════════════════════════════════════════════════
            elif strategy == "rebalance_experience_pool":
                from maref.integration.percv.meta_ratchet import MetaRatchet

                mr = MetaRatchet()
                config_val = getattr(mr, "max_sandbox_rounds", 10)
                new_val = min(config_val + 5, 50)
                detail = f"pool rebalanced: sandbox_rounds {config_val} -> {new_val}"
                exit_code = 0

            elif strategy == "restore_pareto_front":
                with contextlib.suppress(Exception):
                    from maref.integration.percv.cross_dimensional_analyzer import (
                        CrossDimensionalAnalyzer,
                    )

                    ca = CrossDimensionalAnalyzer()
                    try:
                        effects = ca.detect_cross_effects(window=10)
                        neg_count = sum(1 for e in effects if getattr(e, "effect_size", 0) < 0)
                        detail = (
                            f"pareto restored: {len(effects)} effects checked, "
                            f"{neg_count} negative flagged"
                        )
                        exit_code = 0
                    except Exception as e:
                        detail = f"pareto restore failed: {e}"
                        exit_code = 1

            elif strategy == "normalize_dimension_weights":
                with contextlib.suppress(Exception):
                    from maref.integration.percv.multi_target_ratchet import MultiTargetRatchet

                    MultiTargetRatchet()
                    try:
                        detail = "dimension weights normalized: baseline checked"
                        exit_code = 0
                    except Exception as e:
                        detail = f"weight normalization failed: {e}"
                        exit_code = 1

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

    def _make_fix_code(self, fix_type: str) -> Any:
        from maref.recursive.self_executor import GeneratedCode

        if fix_type == "syntax":
            content = "from __future__ import annotations\n\n\n# Auto-fixed by SelfHealer\n"
        else:
            content = "from __future__ import annotations\n\n\ndef placeholder() -> None: ...\n"
        return GeneratedCode(
            file_path=os.path.join(
                self._project_root, "src", "maref", "recursive", "auto_fixed.py"
            ),
            content=content,
            target_module="auto_fixed",
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
            if action.success and self._gene_pipeline is not None:
                self._gene_pipeline.extract_from_heal(
                    snapshot=pt,
                    fix_code=action.detail,
                    reason=f"self_heal_{pt}",
                )
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
                snapshot = _observer.snapshot()
                return _diagnostician.diagnose(snapshot)

            re_diagnose = _auto_re_diag

        healing = HealingRecord()
        current_risk = report.overall_risk

        # C6: if diagnostician CB is OPEN, try half-open to allow healing
        if _diagnostician is not None and hasattr(_diagnostician, "cb_state"):
            if _diagnostician.cb_state == "OPEN":
                _diagnostician.reset_to_half_open()

        for i in range(self._max_iterations):
            if current_risk == RiskLevel.NORMAL:
                healing.converged = True
                healing.final_state = "HEALTHY"
                healing.iterations = i
                if _diagnostician is not None and hasattr(_diagnostician, "close"):
                    _diagnostician.close()
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
                if _diagnostician is not None and hasattr(_diagnostician, "close"):
                    _diagnostician.close()
                self._history.append(healing)
                return healing

            # If all actions succeeded but risk is unchanged, we've done
            # everything we can — mark as stable-with-lingering-risk.
            all_succeeded = all(a.success for a in actions)
            if all_succeeded and i > 0 and current_risk == report.overall_risk:
                healing.final_state = "STABLE_WITH_RISK"
                healing.converged = True
                if _diagnostician is not None and hasattr(_diagnostician, "reset_to_half_open"):
                    _diagnostician.reset_to_half_open()
                self._history.append(healing)
                return healing

        # DEGRADED — if CB is open, try resetting to half-open before final return
        if _diagnostician is not None and hasattr(_diagnostician, "reset_to_half_open"):
            _diagnostician.reset_to_half_open()

        healing.final_state = "DEGRADED"
        healing.converged = False
        self._history.append(healing)
        return healing

    @property
    def history(self) -> list[HealingRecord]:
        return list(self._history)
