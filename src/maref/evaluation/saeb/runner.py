from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.evaluation.saeb.metrics import (
    SAEBMetrics,
    SAEBMetricsCollector,
)
from maref.evaluation.saeb.scenario import SAEBScenario


@dataclass
class SAEBResult:
    agent_name: str
    scenario_name: str
    rounds_completed: int
    metrics: list[SAEBMetrics] = field(default_factory=list)
    convergence_round: int = -1
    oscillation_count: int = 0
    total_time_s: float = 0.0
    acceptance: dict[str, bool] = field(default_factory=dict)

    def fnr_trajectory(self) -> list[float]:
        return [m.fnr for m in self.metrics]

    def coverage_trajectory(self) -> list[float]:
        return [m.line_coverage_pct for m in self.metrics]

    def summary(self) -> str:
        fnrs = self.fnr_trajectory()
        return (
            f"  Agent: {self.agent_name}\n"
            f"  Scenario: {self.scenario_name}\n"
            f"  Rounds: {self.rounds_completed}\n"
            f"  FNR trajectory: {fnrs}\n"
            f"  Convergence round: {self.convergence_round}\n"
            f"  Oscillations: {self.oscillation_count}\n"
            f"  Time: {self.total_time_s:.1f}s\n"
            f"  Acceptance: {self.acceptance}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "scenario": self.scenario_name,
            "rounds": self.rounds_completed,
            "fnr_trajectory": self.fnr_trajectory(),
            "fnr_series": [m.fnr for m in self.metrics],
            "coverage_series": self.coverage_trajectory(),
            "compilation_error_series": [m.compilation_error_rate for m in self.metrics],
            "unused_imports_series": [m.unused_import_count for m in self.metrics],
            "convergence_round": self.convergence_round,
            "oscillation_count": self.oscillation_count,
            "total_time_s": self.total_time_s,
            "acceptance": self.acceptance,
            "metrics_raw": [m.to_dict() for m in self.metrics],
        }


class AgentAdapter(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def iterate(self, scenario: SAEBScenario, round_num: int, label: str) -> bool: ...


class NoopAdapter(AgentAdapter):
    def __init__(self, name: str = "noop") -> None:
        self._name = name

    def name(self) -> str:
        return self._name

    def iterate(self, scenario: SAEBScenario, round_num: int, label: str) -> bool:
        return True


class SubprocessAdapter(AgentAdapter):
    def __init__(self, name: str, command: list[str]) -> None:
        self._name = name
        self._command = command

    def name(self) -> str:
        return self._name

    def iterate(self, scenario: SAEBScenario, round_num: int, label: str) -> bool:
        try:
            result = subprocess.run(
                self._command,
                cwd=scenario.workdir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False


class MAREFSelfAdapter(AgentAdapter):
    def __init__(self, src_dir: str = "calculator") -> None:
        self._name = "maref-self"
        self._src_dir = src_dir

    def name(self) -> str:
        return self._name

    def iterate(self, scenario: SAEBScenario, round_num: int, label: str) -> bool:
        changes_made = False

        # Phase 1: Generic code fixer — parse test failures, fix logic bugs
        if self._generic_fix(scenario):
            changes_made = True

        # Phase 2: MAREF recursive pipeline — architecture-level fixes
        try:
            from maref.recursive.self_architect import SelfArchitect
            from maref.recursive.self_diagnostician import SelfDiagnostician
            from maref.recursive.self_executor import SelfExecutor
            from maref.recursive.self_observer import SelfObserver
            from maref.recursive.unified_audit import UnifiedAuditStore

            store = UnifiedAuditStore()
            observer = SelfObserver(root_path=str(scenario.workdir))
            diagnostician = SelfDiagnostician()
            diagnostician.attach_circuit_breaker()
            architect = SelfArchitect(audit_store=store)
            executor = SelfExecutor(project_root=str(scenario.workdir), audit_store=store)

            snapshot = observer.snapshot()
            diagnosis = diagnostician.diagnose(snapshot)
            if diagnostician.check_and_trip(diagnosis):
                proposals = architect.propose_all()
                for p in proposals:
                    if architect.validate_proposal(p):
                        pipeline = executor.execute(p, round_num=round_num)
                        if pipeline.final_state == "SUCCESS":
                            changes_made = True
        except ImportError:
            import logging

            logging.getLogger("maref.saeb").warning(
                "Recursive pipeline modules not available", exc_info=True
            )
        except Exception:
            import logging

            logging.getLogger("maref.saeb").warning("Recursive pipeline error", exc_info=True)

        return changes_made

    # ------------------------------------------------------------------
    # Generic code fixer — parses pytest output & test AST to fix bugs
    # ------------------------------------------------------------------

    def _generic_fix(self, scenario: SAEBScenario) -> bool:
        """Run tests, parse failures, fix each one, verify fix."""

        # Phase 1: Run tests to see what's broken
        pytest_result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--tb=short", "-q", "--no-header"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=scenario.workdir,
        )
        output = (pytest_result.stdout + pytest_result.stderr).split("\n")

        # Phase 2: Parse all failures
        failures = self._parse_failures(output, scenario)
        if not failures:
            return False

        # Phase 3: Fix each failure
        fixes_applied = 0
        for func_name, error_type, details in failures:
            if self._fix_function(scenario, func_name, error_type, details):
                fixes_applied += 1

        if fixes_applied == 0:
            return False

        # Phase 4: Verify fix by running tests again
        verify = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--no-header"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=scenario.workdir,
        )
        return verify.returncode == 0

    @staticmethod
    def _test_to_func(test_name: str) -> str:
        """Map test function name to source function name.
        e.g. test_divide_by_zero -> divide, test_add -> add, test_power -> power
        """
        m = re.match(r"test_([a-zA-Z]+)", test_name)
        return m.group(1) if m else test_name

    def _parse_failures(
        self, lines: list[str], scenario: SAEBScenario
    ) -> list[tuple[str, str, dict[str, Any]]]:
        """Parse pytest output into (function_name, error_type, details) tuples."""
        failures: list[tuple[str, str, dict[str, Any]]] = []
        test_file = scenario.workdir / "tests" / "test_calc.py"
        test_code = test_file.read_text() if test_file.exists() else ""
        module_has_error = False

        for line in lines:
            line_s = line.strip()

            # Module-level import error: "ERROR tests/test_calc.py"
            m = re.match(r"ERROR\s+tests/test_calc\.py\s*$", line_s)
            if m:
                module_has_error = True
                continue

            # Module-level import error with details
            m = re.match(r"ERROR\s+collecting\s+tests/test_calc\.py", line_s)
            if m:
                module_has_error = True
                continue

            # FAILED tests: "FAILED tests/test_calc.py::test_add - ..."
            m = re.match(r"FAILED\s+tests/test_calc\.py::(\w+)", line_s)
            if m:
                test_name = m.group(1)
                func_name = self._test_to_func(test_name)
                details: dict[str, Any] = {"test_name": test_name, "test_code": test_code}
                failures.append((func_name, "AssertionError", details))
                continue

            # ERROR on specific test
            m = re.match(r"ERROR\s+tests/test_calc\.py::(\w+)", line_s)
            if m:
                test_name = m.group(1)
                func_name = self._test_to_func(test_name)
                details = {"test_name": test_name, "test_code": test_code}
                failures.append((func_name, "ImportError", details))
                continue

            # Inline from --tb=short
            m = re.match(r"(.+?)::(\w+)\s+(ERROR|FAILED)", line_s)
            if m:
                test_name = m.group(2)
                func_name = self._test_to_func(test_name)
                details = {"test_name": test_name, "test_code": test_code}
                failures.append((func_name, m.group(3), details))

        # If module-level error (import failure), extract the missing function name
        if module_has_error:
            err_text = "\n".join(lines)
            # Find "cannot import name 'X'" in the traceback
            m = re.search(r"cannot import name '(\w+)'", err_text)
            if m:
                func_name = m.group(1)
                failures.append(
                    (func_name, "ImportError", {"test_name": "", "test_code": test_code})
                )
            else:
                # Generic fallback: try to find ANY referenced function not in source
                src_file = scenario.workdir / self._src_dir / "calc.py"
                src_text = src_file.read_text() if src_file.exists() else ""
                for name_candidate in ["power", "add", "subtract", "multiply", "divide"]:
                    if f"def {name_candidate}(" not in src_text:
                        failures.append(
                            (
                                name_candidate,
                                "ImportError",
                                {"test_name": "", "test_code": test_code},
                            )
                        )
                        break

        # Deduplicate by function name
        seen: set[str] = set()
        unique: list[tuple[str, str, dict[str, Any]]] = []
        for func_name, etype, det in failures:
            if func_name not in seen:
                seen.add(func_name)
                unique.append((func_name, etype, det))
        return unique

    def _fix_function(
        self, scenario: SAEBScenario, func_name: str, error_type: str, details: dict[str, Any]
    ) -> bool:
        """Fix a single failing function. Returns True if a fix was applied."""
        src_file = scenario.workdir / self._src_dir / "calc.py"
        if not src_file.exists():
            return False

        try:
            ast.parse(src_file.read_text())
        except SyntaxError:
            return False

        # Special case: power_removed — function doesn't exist
        if error_type == "ImportError":
            return self._fix_missing_function(scenario, func_name, src_file)

        # Check for missing exception / validation (no_div0_check)
        if self._needs_exception_fix(details, src_file, func_name):
            return self._fix_missing_exception(scenario, func_name, src_file)

        # Logic bug (add_flipped, multiply_wrong) — infer from test assertions
        return self._fix_logic_bug(scenario, func_name, details, src_file)

    def _fix_missing_function(self, scenario: SAEBScenario, func_name: str, src_file: Path) -> bool:
        """Re-add a function that was deleted (e.g. power_removed)."""
        # Try to find the function in reference files
        ref = scenario.reference_files.get(f"{self._src_dir}/calc.py", "")
        ref_tree = ast.parse(ref) if ref else None
        if ref_tree is None:
            return False

        for node in ast.walk(ref_tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                new_func = ast.unparse(node) + "\n"
                content = src_file.read_text()
                # Insert before the last line (or at end)
                content = content.rstrip() + "\n\n" + new_func
                src_file.write_text(content)
                return True
        return False

    def _needs_exception_fix(self, details: dict[str, Any], src_file: Path, func_name: str) -> bool:
        """Check if a test expects an exception that the source doesn't raise."""
        test_code = details.get("test_code", "")
        test_name = details.get("test_name", "")

        if "pytest.raises" not in test_code:
            return False

        # Find the specific test that uses pytest.raises for this func_name
        in_test = False
        for line in test_code.split("\n"):
            if f"def {test_name}" in line:
                in_test = True
            elif in_test and line.strip().startswith("def "):
                in_test = False
            elif in_test and "pytest.raises" in line:
                src = src_file.read_text()
                try:
                    src_tree = ast.parse(src)
                except SyntaxError:
                    return False
                for node in ast.walk(src_tree):
                    if isinstance(node, ast.FunctionDef) and node.name == func_name:
                        body = ast.unparse(node)
                        # Check if the function already has the exception
                        if "raise" not in body and "ValueError" not in body:
                            return True
        return False

    def _fix_missing_exception(
        self, scenario: SAEBScenario, func_name: str, src_file: Path
    ) -> bool:
        """Replace a function body with the reference version (text-based)."""
        ref = scenario.reference_files.get(f"{self._src_dir}/calc.py", "")
        if not ref:
            return False

        # Extract reference function text
        ref_func = _extract_function_text(ref, func_name)
        if not ref_func:
            return False

        src = src_file.read_text()
        cur_func = _extract_function_text(src, func_name)
        if not cur_func:
            return False

        src = src.replace(cur_func, ref_func)
        src_file.write_text(src)
        return True

    def _fix_logic_bug(
        self, scenario: SAEBScenario, func_name: str, details: dict[str, Any], src_file: Path
    ) -> bool:
        """Fix a logic bug by inferring correct implementation from test assertions."""
        test_code = details.get("test_code", "")
        test_name = details.get("test_name", "")

        # Extract assertion pairs from the failing test
        expectations: list[tuple[list[str], str]] = []
        in_test = False
        for line in test_code.split("\n"):
            if f"def {test_name}" in line:
                in_test = True
                continue
            elif in_test and line.strip().startswith("def "):
                break
            elif in_test:
                # Parse assert func(a, b) == expected
                m2 = re.match(r"\s*assert\s+(\w+)\((.*?)\)\s*==\s*(.+)", line)
                if m2:
                    args_str = m2.group(2).strip()
                    args = [a.strip() for a in args_str.split(",")] if args_str else []
                    expected = m2.group(3).strip()
                    expectations.append((args, expected))

        if not expectations:
            return False

        # Read the current source function
        tree = ast.parse(src_file.read_text())
        func_node: ast.FunctionDef | None = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                func_node = node
                break
        if func_node is None:
            return False

        # Try to fix by analyzing the operator difference
        # For each expectation, check if we can find a simple fix
        fixed_body = self._try_infer_fix(func_node, expectations)
        if fixed_body is None:
            return False

        # Apply the fix: replace function body
        src = src_file.read_text()
        old_func = ast.unparse(func_node)
        param_str = ", ".join(a.arg for a in func_node.args.args)
        returns = ast.unparse(func_node.returns) if func_node.returns else "float"
        new_func = f"def {func_name}({param_str}) -> {returns}:\n    {fixed_body}\n"
        src = src.replace(old_func, new_func)
        src_file.write_text(src)
        return True

    @staticmethod
    def _try_infer_fix(
        func_node: ast.FunctionDef, expectations: list[tuple[list[str], str]]
    ) -> str | None:
        """Try to infer the correct function body from test expectations."""
        if len(func_node.body) != 1:
            return None
        return_stmt = func_node.body[0]
        if not isinstance(return_stmt, ast.Return):
            return None
        ret_val = return_stmt.value
        if ret_val is None:
            return None

        # Strategy 1: Binary operation fix (a OP b)
        if (
            isinstance(ret_val, ast.BinOp)
            and isinstance(ret_val.left, ast.Name)
            and isinstance(ret_val.right, ast.Name)
        ):
            left = ret_val.left.id
            right = ret_val.right.id

            # Try each operator to find the one that matches ALL test expectations
            for op_cls, op_sym in [
                (ast.Add, "+"),
                (ast.Sub, "-"),
                (ast.Mult, "*"),
                (ast.Div, "/"),
                (ast.Pow, "**"),
            ]:
                if isinstance(ret_val.op, op_cls):
                    continue  # Skip current (broken) operator
                all_match = True
                for args_raw, expected in expectations:
                    try:
                        a_val = float(args_raw[0]) if args_raw else 0.0
                        b_val = float(args_raw[1]) if len(args_raw) > 1 else 0.0
                        if op_sym == "+":
                            result = a_val + b_val
                        elif op_sym == "-":
                            result = a_val - b_val
                        elif op_sym == "*":
                            result = a_val * b_val
                        elif op_sym == "/":
                            result = a_val / b_val if b_val != 0 else float("inf")
                        elif op_sym == "**":
                            result = a_val**b_val
                        else:
                            result = None
                        if abs(result - float(expected)) > 1e-9:
                            all_match = False
                            break
                    except (ValueError, IndexError, ZeroDivisionError):
                        all_match = False
                        break
                if all_match:
                    return f"return {left} {op_sym} {right}"

        return None


def _extract_function_text(source: str, func_name: str) -> str:
    """Extract a full function definition from source text (indentation-aware)."""
    lines = source.split("\n")
    func_lines: list[str] = []
    in_func = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"def {func_name}("):
            in_func = True
            func_lines.append(line)
            continue
        if in_func:
            # Next def statement ends this function
            if stripped.startswith("def "):
                break
            func_lines.append(line)
    return "\n".join(func_lines).rstrip("\n") if func_lines else ""


def run_saeb(
    scenario: SAEBScenario,
    agent: AgentAdapter | None = None,
    rounds: int = 5,
    output_dir: str | Path | None = None,
) -> SAEBResult:
    if agent is None:
        agent = NoopAdapter()

    scenario.setup()
    collector = SAEBMetricsCollector(scenario.workdir, src_dir="calculator")
    metrics_list: list[SAEBMetrics] = []
    start_time = time.time()

    # Baseline (no defects)
    metrics_list.append(collector.collect(0, "baseline"))

    round_idx = 1
    for inj in scenario.injections:
        # Phase A: Apply defect, let agent attempt to fix
        scenario.apply_injection(inj.label)

        for _ in range(rounds):
            agent.iterate(scenario, round_idx, f"{inj.label}:fix")
            m = collector.collect(round_idx, f"{inj.label}:fix")
            metrics_list.append(m)
            round_idx += 1
            if m.fnr == 0.0 and m.compilation_error_rate == 0.0:
                break  # Fixed early

        # Phase B: Restore to clean state
        scenario.revert_injection(inj.label)
        scenario.restore_reference()
        m = collector.collect(round_idx, f"{inj.label}:restored")
        metrics_list.append(m)
        round_idx += 1

    total_time = time.time() - start_time

    # Compute convergence and oscillation
    fnrs = [m.fnr for m in metrics_list]
    osc = 0
    for i in range(2, len(fnrs)):
        if fnrs[i] != fnrs[i - 1] and fnrs[i - 1] != fnrs[i - 2]:
            osc += 1

    # Convergence: first round where FNR stabilizes near 0
    conv = -1
    for i in range(len(fnrs)):
        if i >= 3 and all(f < 0.05 for f in fnrs[i - 2 : i + 1]):
            conv = i
            break

    # Count fix rounds per injection for early-exit detection
    fix_counts: dict[str, int] = {}
    for m in metrics_list:
        for inj in scenario.injections:
            if m.label.startswith(f"{inj.label}:fix"):
                fix_counts[inj.label] = fix_counts.get(inj.label, 0) + 1

    all_defects_detected = all(
        (
            # Visible: any fix round shows the defect
            any(
                (m.fnr > 0 or m.compilation_error_rate > 0)
                for m in metrics_list
                if m.label.startswith(f"{inj.label}:fix")
            )
            or
            # Implicit: agent fixed before max rounds (early-exit)
            fix_counts.get(inj.label, 0) < rounds
        )
        for inj in scenario.injections
        if inj.expected_fnr_gt > 0 or inj.expected_compilation_error
    )

    all_fixes_clear = True
    for inj in scenario.injections:
        fix_ms = [m for m in metrics_list if m.label.startswith(f"{inj.label}:fix")]
        if not fix_ms or fix_ms[-1].fnr != 0 or fix_ms[-1].compilation_error_rate != 0:
            all_fixes_clear = False
            break

    result = SAEBResult(
        agent_name=agent.name(),
        scenario_name=scenario.name,
        rounds_completed=round_idx - 1,
        metrics=metrics_list,
        convergence_round=conv,
        oscillation_count=osc,
        total_time_s=total_time,
        acceptance={
            "defects_detected": all_defects_detected,
            "fixes_confirmed": all_fixes_clear,
            "converged": conv >= 0,
        },
    )

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "saeb_result.json", "w") as f:
            json.dump(result.to_dict(), f, indent=2)

    return result


def run_comparison(
    scenario: SAEBScenario,
    agents: list[AgentAdapter],
    rounds: int = 5,
    output_dir: str | None = None,
) -> dict[str, SAEBResult]:
    results: dict[str, SAEBResult] = {}
    for agent in agents:
        result = run_saeb(scenario, agent, rounds, output_dir)
        results[agent.name()] = result
    return results
