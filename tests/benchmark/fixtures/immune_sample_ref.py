from __future__ import annotations

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
