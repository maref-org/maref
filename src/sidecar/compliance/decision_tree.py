from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DecisionResult:
    """Result of a policy decision tree evaluation."""
    decision: str = "allow"
    rule_id: str = ""
    risk_score: float = 0.0
    reason: str = ""


class DecisionTree:
    """Policy decision tree for compliance evaluation."""

    def evaluate(self, ctx: PolicyContext | dict[str, Any]) -> DecisionResult:
        # Stub: simple policy logic for benchmark validation
        ctx.action if hasattr(ctx, "action") else getattr(ctx, "action", "")
        has_critical = (
            getattr(ctx, "has_critical_findings", False)
            if hasattr(ctx, "has_critical_findings")
            else False
        )
        cross_border = (
            getattr(ctx, "cross_border", None)
            if hasattr(ctx, "cross_border")
            else None
        )
        entropy = getattr(ctx, "current_entropy", 0.0) if hasattr(ctx, "current_entropy") else 0.0

        if has_critical:
            return DecisionResult(decision="block", rule_id="R1-critical", risk_score=0.9)
        if cross_border is True:
            return DecisionResult(decision="warn", rule_id="R2-border", risk_score=0.6)
        if entropy > 3.0:
            return DecisionResult(decision="throttle", rule_id="R3-entropy", risk_score=0.5)
        return DecisionResult(decision="allow", rule_id="R0-default", risk_score=0.1)


class PolicyContext:
    """Policy evaluation context.

    Accepts arbitrary keyword arguments to support benchmark and
    compliance scenarios without rigid schema constraints.
    """

    def __init__(self, action: str, resource: str = "", **kwargs: Any) -> None:
        self.action = action
        self.resource = resource
        for k, v in kwargs.items():
            setattr(self, k, v)
