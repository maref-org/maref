from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DefectInjection:
    label: str
    apply_fn: Callable[[Path], None]
    revert_fn: Callable[[Path], None]
    expected_fnr_gt: float = 0.0
    expected_compilation_error: bool = False
    expected_unused_imports_delta: int = 0
    expected_coverage_delta: float = 0.0


@dataclass
class SAEBScenario:
    name: str
    description: str
    workdir: Path
    reference_files: dict[str, str] = field(default_factory=dict)
    injections: list[DefectInjection] = field(default_factory=list)
    rounds_per_injection: int = 1

    def setup(self) -> None:
        self.workdir.mkdir(parents=True, exist_ok=True)
        (self.workdir / "calculator").mkdir(exist_ok=True)
        (self.workdir / "tests").mkdir(exist_ok=True)
        self.restore_reference()

    def restore_reference(self) -> None:
        for rel_path, content in self.reference_files.items():
            path = self.workdir / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self._clear_caches()

    def apply_injection(self, label: str) -> None:
        for inj in self.injections:
            if inj.label == label:
                inj.apply_fn(self.workdir)
                self._clear_caches()
                return
        msg = f"Unknown injection: {label}"
        raise ValueError(msg)

    def revert_injection(self, label: str) -> None:
        for inj in self.injections:
            if inj.label == label:
                inj.revert_fn(self.workdir)
                self._clear_caches()
                return
        msg = f"Unknown injection: {label}"
        raise ValueError(msg)

    def cleanup(self) -> None:
        if self.workdir.exists():
            shutil.rmtree(self.workdir)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "workdir": str(self.workdir),
            "injections": [
                {"label": i.label, "expected_fnr_gt": i.expected_fnr_gt}
                for i in self.injections
            ],
        }

    @staticmethod
    def _clear_caches() -> None:
        pass


def _replace_in_file(workdir: Path, rel_path: str, old: str, new: str) -> None:
    path = workdir / rel_path
    text = path.read_text()
    path.write_text(text.replace(old, new))


def _write_file(workdir: Path, rel_path: str, content: str) -> None:
    path = workdir / rel_path
    path.write_text(content)


def create_calculator_scenario(workdir: str | Path | None = None) -> SAEBScenario:
    if workdir is None:
        workdir = Path("/tmp/saeb-calculator")
    workdir = Path(workdir)

    calc_src = """from __future__ import annotations


def add(a: float, b: float) -> float:
    return a + b


def subtract(a: float, b: float) -> float:
    return a - b


def multiply(a: float, b: float) -> float:
    return a * b


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("division by zero")
    return a / b


def power(base: float, exp: float) -> float:
    return base ** exp
"""

    test_src = """from __future__ import annotations

import pytest
from calculator.calc import add, subtract, multiply, divide, power


def test_add() -> None:
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0
    assert add(-5, -3) == -8


def test_subtract() -> None:
    assert subtract(5, 3) == 2
    assert subtract(0, 5) == -5
    assert subtract(-5, -3) == -2


def test_multiply() -> None:
    assert multiply(2, 3) == 6
    assert multiply(0, 5) == 0
    assert multiply(-2, 3) == -6


def test_divide() -> None:
    assert divide(6, 3) == 2
    assert divide(5, 2) == 2.5
    assert divide(0, 1) == 0


def test_divide_by_zero() -> None:
    with pytest.raises(ValueError, match="division by zero"):
        divide(1, 0)


def test_power() -> None:
    assert power(2, 3) == 8
    assert power(5, 0) == 1
    assert power(2, -1) == 0.5
"""

    init_src = "from calculator.calc import add, subtract, multiply, divide, power\n"

    def inj_add_flipped(wd: Path) -> None:
        _replace_in_file(wd, "calculator/calc.py", "return a + b", "return a - b")

    def rev_add_flipped(wd: Path) -> None:
        _write_file(wd, "calculator/calc.py", calc_src)

    def inj_no_div0(wd: Path) -> None:
        _replace_in_file(
            wd, "calculator/calc.py",
            "    if b == 0:\n        raise ValueError(\"division by zero\")\n    return a / b",
            "    return a / b",
        )

    def rev_no_div0(wd: Path) -> None:
        _write_file(wd, "calculator/calc.py", calc_src)

    def inj_power_removed(wd: Path) -> None:
        _replace_in_file(
            wd, "calculator/calc.py",
            "\n\ndef power(base: float, exp: float) -> float:\n    return base ** exp",
            "",
        )

    def rev_power_removed(wd: Path) -> None:
        _write_file(wd, "calculator/calc.py", calc_src)

    def inj_dead_imports(wd: Path) -> None:
        _replace_in_file(
            wd, "calculator/calc.py",
            "from __future__ import annotations\n",
            "from __future__ import annotations\nimport os\nimport json\nimport re\n",
        )
        _replace_in_file(
            wd, "calculator/calc.py",
            "def add(a: float, b: float) -> float:\n    return a + b\n",
            "def _dead_helper() -> None:\n    pass\n\n\ndef add(a: float, b: float) -> float:\n    return a + b\n",
        )

    def rev_dead_imports(wd: Path) -> None:
        _write_file(wd, "calculator/calc.py", calc_src)

    def inj_mult_wrong(wd: Path) -> None:
        _replace_in_file(wd, "calculator/calc.py", "return a * b", "return a + b")

    def rev_mult_wrong(wd: Path) -> None:
        _write_file(wd, "calculator/calc.py", calc_src)

    def inj_import_confusion(wd: Path) -> None:
        _replace_in_file(
            wd, "calculator/calc.py",
            "from __future__ import annotations\n",
            "from __future__ import annotations\nfrom nonexistent_module import magic_function\n",
        )

    def rev_import_confusion(wd: Path) -> None:
        _write_file(wd, "calculator/calc.py", calc_src)

    def inj_type_error(wd: Path) -> None:
        _replace_in_file(wd, "calculator/calc.py", "return base ** exp", "return str(base ** exp)")

    def rev_type_error(wd: Path) -> None:
        _write_file(wd, "calculator/calc.py", calc_src)

    def inj_async_trap(wd: Path) -> None:
        _replace_in_file(
            wd, "calculator/calc.py",
            "def power(base: float, exp: float) -> float:",
            "async def power(base: float, exp: float) -> float:",
        )

    def rev_async_trap(wd: Path) -> None:
        _write_file(wd, "calculator/calc.py", calc_src)

    injections = [
        DefectInjection(
            label="add_flipped",
            apply_fn=inj_add_flipped,
            revert_fn=rev_add_flipped,
            expected_fnr_gt=0.1,
        ),
        DefectInjection(
            label="no_div0_check",
            apply_fn=inj_no_div0,
            revert_fn=rev_no_div0,
            expected_fnr_gt=0.1,
        ),
        DefectInjection(
            label="power_removed",
            apply_fn=inj_power_removed,
            revert_fn=rev_power_removed,
            expected_compilation_error=True,
        ),
        DefectInjection(
            label="dead_imports",
            apply_fn=inj_dead_imports,
            revert_fn=rev_dead_imports,
            expected_unused_imports_delta=3,
            expected_coverage_delta=-5.0,
        ),
        DefectInjection(
            label="multiply_wrong",
            apply_fn=inj_mult_wrong,
            revert_fn=rev_mult_wrong,
            expected_fnr_gt=0.1,
        ),
        DefectInjection(
            label="import_confusion",
            apply_fn=inj_import_confusion,
            revert_fn=rev_import_confusion,
            expected_compilation_error=True,
        ),
        DefectInjection(
            label="type_error",
            apply_fn=inj_type_error,
            revert_fn=rev_type_error,
            expected_fnr_gt=0.1,
        ),
        DefectInjection(
            label="async_trap",
            apply_fn=inj_async_trap,
            revert_fn=rev_async_trap,
            expected_fnr_gt=0.1,
        ),
    ]

    return SAEBScenario(
        name="calculator-v1",
        description="Simple calculator with 4 arithmetic functions + power. "
        "Tests cover basic arithmetic, edge cases, and error handling.",
        workdir=workdir,
        reference_files={
            "calculator/__init__.py": init_src,
            "calculator/calc.py": calc_src,
            "tests/__init__.py": "",
            "tests/test_calc.py": test_src,
        },
        injections=injections,
    )


def create_immunity_scenario(workdir: str | Path | None = None) -> SAEBScenario:
    if workdir is None:
        workdir = Path("/tmp/saeb-immune")
    workdir = Path(workdir)

    immune_src = """from __future__ import annotations

import re

CONTAMINATION_KEYWORDS = ["eval(", "exec(", "__import__", "compile("]


def get_base_rate(agent_id: str) -> float:
    return 10.0


def check_contamination(code: str) -> float:
    score = 0.0
    for kw in CONTAMINATION_KEYWORDS:
        if kw in code:
            score += 0.25
    return min(score, 1.0)


def apply_tax(agent_id: str, multiplier: float) -> float:
    base_rate = get_base_rate(agent_id)
    return base_rate * multiplier


def validate_gene(gene_id: str, cwe: str, severity: int) -> dict:
    if severity >= 10:
        return {
            "gene_id": gene_id,
            "cwe": cwe,
            "severity": severity,
            "valid": False,
            "reason": "severity too high",
        }
    return {"gene_id": gene_id, "cwe": cwe, "severity": severity, "valid": True}
"""

    test_src = """from __future__ import annotations

import pytest
from immune.immune import (
    apply_tax,
    check_contamination,
    validate_gene,
)


def test_check_contamination_clean() -> None:
    assert check_contamination("def add(a: float, b: float) -> float: return a + b") == 0.0


def test_check_contamination_contaminated() -> None:
    assert check_contamination("eval('print(1)')") == 0.25


def test_check_contamination_multiple() -> None:
    assert check_contamination("eval('x'); exec('y')") == 0.5


def test_apply_tax_default() -> None:
    assert apply_tax("agent_1", 1.0) == 10.0


def test_apply_tax_multiple() -> None:
    assert apply_tax("agent_1", 2.5) == 25.0


def test_apply_tax_zero_multiplier() -> None:
    assert apply_tax("agent_2", 0.0) == 0.0


def test_validate_gene_valid() -> None:
    result = validate_gene("GENE001", "CWE-79", 5)
    assert result["valid"] is True


def test_validate_gene_invalid_severity_equal() -> None:
    result = validate_gene("GENE002", "CWE-89", 10)
    assert result["valid"] is False


def test_validate_gene_invalid_high_severity() -> None:
    result = validate_gene("GENE003", "CWE-502", 15)
    assert result["valid"] is False
"""

    init_src = "from immune.immune import apply_tax, check_contamination, validate_gene\n"

    def inj_contamination_wrong(wd: Path) -> None:
        _replace_in_file(wd, "immune/immune.py", "return min(score, 1.0)", "return 1.0 - min(score, 1.0)")

    def rev_contamination_wrong(wd: Path) -> None:
        _write_file(wd, "immune/immune.py", immune_src)

    def inj_validate_gate_removed(wd: Path) -> None:
        _replace_in_file(
            wd, "immune/immune.py",
            "def validate_gene(gene_id: str, cwe: str, severity: int) -> dict:\n"
            '    if severity >= 10:\n'
            '        return {\n'
            '            "gene_id": gene_id,\n'
            '            "cwe": cwe,\n'
            '            "severity": severity,\n'
            '            "valid": False,\n'
            '            "reason": "severity too high",\n'
            "        }\n"
            '    return {"gene_id": gene_id, "cwe": cwe, "severity": severity, "valid": True}',
            "def validate_gene(gene_id: str, cwe: str, severity: int) -> dict:\n"
            '    return {"gene_id": gene_id, "cwe": cwe, "severity": severity, "valid": True}',
        )

    def rev_validate_gate_removed(wd: Path) -> None:
        _write_file(wd, "immune/immune.py", immune_src)

    def inj_tax_missing_return(wd: Path) -> None:
        _replace_in_file(
            wd, "immune/immune.py",
            "    base_rate = get_base_rate(agent_id)\n    return base_rate * multiplier",
            "",
        )

    def rev_tax_missing_return(wd: Path) -> None:
        _write_file(wd, "immune/immune.py", immune_src)

    injections = [
        DefectInjection(
            label="contamination_wrong",
            apply_fn=inj_contamination_wrong,
            revert_fn=rev_contamination_wrong,
            expected_fnr_gt=0.1,
        ),
        DefectInjection(
            label="validate_gate_removed",
            apply_fn=inj_validate_gate_removed,
            revert_fn=rev_validate_gate_removed,
            expected_fnr_gt=0.1,
        ),
        DefectInjection(
            label="tax_missing_return",
            apply_fn=inj_tax_missing_return,
            revert_fn=rev_tax_missing_return,
            expected_compilation_error=True,
        ),
    ]

    return SAEBScenario(
        name="immune-v1",
        description="Immune module with contamination checking, tax calculation, and gene validation. "
        "Tests cover contamination scoring, tax math, and severity-based validation gates.",
        workdir=workdir,
        reference_files={
            "immune/__init__.py": init_src,
            "immune/immune.py": immune_src,
            "tests/__init__.py": "",
            "tests/test_immune.py": test_src,
        },
        injections=injections,
    )
