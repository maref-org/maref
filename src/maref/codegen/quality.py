from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QualityGateConfig:
    strict: bool = False
    run_ruff: bool = True
    run_mypy: bool = True
    run_pytest: bool = True
    run_immune_scan: bool = True
    require_verifier_consensus: bool = False
    min_coverage_delta: float = -0.05
    max_new_violations: int = 3
