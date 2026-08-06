from __future__ import annotations

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
