"""Collaboration Rule Engine — DSL for human-agent collaboration policies.

Syntax:
    WHEN <condition> THEN <action> ELSE <escalation>

Examples:
    WHEN cost > $500 OR data_classification == 'PII' THEN HITL ELSE HOTL
    WHEN risk_score > 0.8 THEN HALT ELSE NOTIFY

Rules support runtime hot-update without restarting the orchestrator.
"""

from __future__ import annotations

import operator
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CollaborationAction(Enum):
    """What to do when a rule matches."""

    HITL = "hitl"  # Human-in-the-loop: pause, wait for approval
    HOTL = "hotl"  # Human-on-the-loop: execute, notify after
    HATL = "hatl"  # Human-at-the-loop: fully autonomous
    HALT = "halt"  # Stop everything
    NOTIFY = "notify"  # Send notification, don't pause
    ESCALATE = "escalate"  # Route to higher authority
    DELEGATE = "delegate"  # Route to fallback agent


@dataclass
class RuleCondition:
    """A single condition: field operator value."""

    field: str  # e.g. "cost", "data_classification", "risk_score"
    op: str  # e.g. ">", "==", "in", "contains"
    value: Any

    # Operator mapping
    _OPS: dict[str, Callable[[Any, Any], bool]] = field(  # type: ignore[operator]
        default_factory=lambda: {
            ">": operator.gt,
            ">=": operator.ge,
            "<": operator.lt,
            "<=": operator.le,
            "==": operator.eq,
            "!=": operator.ne,
            "in": lambda a, b: a in b,
            "contains": lambda a, b: b in a,
        }
    )

    def evaluate(self, context: dict[str, Any]) -> bool:
        actual = context.get(self.field)
        if actual is None:
            return False
        fn = self._OPS.get(self.op)
        if fn is None:
            raise ValueError(f"Unknown operator: {self.op}")
        return fn(actual, self.value)


@dataclass
class CollaborationRule:
    """A single collaboration rule."""

    name: str
    when: list[RuleCondition]  # All must match (AND logic)
    then: CollaborationAction
    else_: CollaborationAction | None = None
    priority: int = 0  # Higher = evaluated first
    enabled: bool = True
    created_at: float = field(default_factory=time.time)

    def evaluate(self, context: dict[str, Any]) -> CollaborationAction | None:
        """Evaluate rule against context. Returns action if matched, None otherwise."""
        if not self.enabled:
            return None
        matched = all(cond.evaluate(context) for cond in self.when)
        if matched:
            return self.then
        return self.else_ if self.else_ else None


class CollaborationRuleEngine:
    """Rule engine for dynamic collaboration mode switching.

    Usage:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(
            name="high_cost_pii",
            when=[
                RuleCondition("cost", ">", 500),
                RuleCondition("data_classification", "==", "PII"),
            ],
            then=CollaborationAction.HITL,
            else_=CollaborationAction.HOTL,
        ))
        action = engine.evaluate({"cost": 600, "data_classification": "PII"})
        # → CollaborationAction.HITL
    """

    def __init__(self) -> None:
        self._rules: list[CollaborationRule] = []
        self._history: list[tuple[float, dict[str, Any], CollaborationAction]] = []

    # ------------------------------------------------------------------ #
    # Rule management
    # ------------------------------------------------------------------ #
    def add_rule(self, rule: CollaborationRule) -> None:
        """Add a rule. Rules are evaluated by priority (high first)."""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name."""
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        return len(self._rules) < before

    def enable_rule(self, name: str) -> bool:
        """Enable a rule by name."""
        for r in self._rules:
            if r.name == name:
                r.enabled = True
                return True
        return False

    def disable_rule(self, name: str) -> bool:
        """Disable a rule by name."""
        for r in self._rules:
            if r.name == name:
                r.enabled = False
                return True
        return False

    def list_rules(self) -> list[CollaborationRule]:
        """List all rules."""
        return list(self._rules)

    # ------------------------------------------------------------------ #
    # Evaluation
    # ------------------------------------------------------------------ #
    def evaluate(self, context: dict[str, Any]) -> CollaborationAction:
        """Evaluate all rules against context. Returns first matching action.

        Default: HATL (fully autonomous) if no rules match.
        """
        for rule in self._rules:
            action = rule.evaluate(context)
            if action is not None:
                self._history.append((time.time(), dict(context), action))
                return action
        return CollaborationAction.HATL

    def evaluate_with_trace(self, context: dict[str, Any]) -> tuple[CollaborationAction, list[str]]:
        """Evaluate with trace: returns action + list of rule names evaluated."""
        trace: list[str] = []
        for rule in self._rules:
            trace.append(rule.name)
            action = rule.evaluate(context)
            if action is not None:
                self._history.append((time.time(), dict(context), action))
                return action, trace
        return CollaborationAction.HATL, trace

    # ------------------------------------------------------------------ #
    # DSL parser (simple string → rule)
    # ------------------------------------------------------------------ #
    @classmethod
    def parse_rule(cls, name: str, dsl: str) -> CollaborationRule:
        """Parse a simple DSL string into a CollaborationRule.

        Format:
            WHEN <field> <op> <value> [AND <field> <op> <value>...] THEN <action> [ELSE <escalation>]

        Example:
            WHEN cost > 500 AND data_classification == PII THEN HITL ELSE HOTL
        """
        pattern = re.compile(
            r"WHEN\s+(?P<when>.+?)\s+THEN\s+(?P<then>\w+)"
            r"(?:\s+ELSE\s+(?P<else>\w+))?",
            re.IGNORECASE,
        )
        m = pattern.match(dsl.strip())
        if not m:
            raise ValueError(f"Invalid DSL: {dsl}")

        when_part = m.group("when")
        then_str = m.group("then").upper()
        else_str = m.group("else")

        # Parse conditions
        conditions: list[RuleCondition] = []
        # Split by AND (simple approach)
        for cond_str in re.split(r"\s+AND\s+", when_part, flags=re.IGNORECASE):
            cond_str = cond_str.strip()
            # Match: field op value
            cond_match = re.match(r"(\w+)\s*(>=|<=|>|<|==|!=|in|contains)\s*(.+)", cond_str)
            if not cond_match:
                raise ValueError(f"Invalid condition: {cond_str}")
            field, op, value_str = cond_match.groups()
            # Try to convert value
            value = cls._parse_value(value_str.strip())
            conditions.append(RuleCondition(field, op, value))

        then_action = CollaborationAction[then_str]
        else_action = CollaborationAction[else_str.upper()] if else_str else None

        return CollaborationRule(
            name=name,
            when=conditions,
            then=then_action,
            else_=else_action,
        )

    @staticmethod
    def _parse_value(value_str: str) -> Any:
        """Parse a value string into int, float, or string."""
        # Remove quotes
        if (value_str.startswith("'") and value_str.endswith("'")) or (
            value_str.startswith('"') and value_str.endswith('"')
        ):
            return value_str[1:-1]
        # Try int
        try:
            return int(value_str)
        except ValueError:
            pass
        # Try float
        try:
            return float(value_str)
        except ValueError:
            pass
        # Return as string
        return value_str

    # ------------------------------------------------------------------ #
    # History / audit
    # ------------------------------------------------------------------ #
    def get_history(
        self, limit: int = 100
    ) -> list[tuple[float, dict[str, Any], CollaborationAction]]:
        """Get evaluation history."""
        return self._history[-limit:]
