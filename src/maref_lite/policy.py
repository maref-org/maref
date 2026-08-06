"""
MAREF-Lite Policy Engine

Defines governance policies that map observations and drift events
to state transition decisions. Policies are configurable rules that
determine how the governance overlay responds to system conditions.
"""
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from maref_lite.state_machine import GovernanceState


class PolicyTrigger(Enum):
    """Types of events that can trigger a policy."""
    ENTROPY_THRESHOLD = auto()
    ANOMALY_DETECTED = auto()
    DRIFT_DETECTED = auto()
    STATE_TIMEOUT = auto()
    MANUAL_OVERRIDE = auto()

class PolicyAction(Enum):
    """Actions a policy can take."""
    TRANSITION = auto()
    FORCE_STABILIZE = auto()
    FORCE_HALT = auto()
    ALERT = auto()
    NOOP = auto()

@dataclass
class PolicyRule:
    """A single governance policy rule."""
    name: str
    trigger: PolicyTrigger
    condition: Callable[[dict[str, Any]], bool]
    action: PolicyAction
    target_state: GovernanceState | None = None
    priority: int = 0
    enabled: bool = True

    def evaluate(self, context: dict[str, Any]) -> PolicyAction | None:
        """Evaluate policy against context."""
        if not self.enabled:
            return None
        if self.condition(context):
            return self.action
        return None

class PolicyEngine:
    """
    MAREF-Lite policy engine.

    Manages a set of policy rules and evaluates them against
    system context to make governance decisions.
    """

    def __init__(self) -> None:
        self._rules: list[PolicyRule] = []
        self._default_policy = PolicyRule(name='default_noop', trigger=PolicyTrigger.MANUAL_OVERRIDE, condition=lambda ctx: True, action=PolicyAction.NOOP, priority=-1)

    def add_rule(self, rule: PolicyRule) -> None:
        """Add a policy rule."""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def evaluate(self, context: dict[str, Any]) -> list[PolicyRule]:
        """
        Evaluate all policies against context.

        Returns list of triggered policies sorted by priority.
        """
        triggered: list[PolicyRule] = []
        for rule in self._rules:
            if rule.evaluate(context):
                triggered.append(rule)
        return triggered

    def get_rules(self) -> list[PolicyRule]:
        """Get all registered rules."""
        return list(self._rules)

def create_default_policies() -> PolicyEngine:
    """Create default MAREF-Lite governance policies."""
    engine = PolicyEngine()
    engine.add_rule(PolicyRule(name='critical_entropy', trigger=PolicyTrigger.ENTROPY_THRESHOLD, condition=lambda ctx: ctx.get('entropy', 0) >= 4, action=PolicyAction.FORCE_STABILIZE, priority=100))
    engine.add_rule(PolicyRule(name='high_entropy', trigger=PolicyTrigger.ENTROPY_THRESHOLD, condition=lambda ctx: ctx.get('entropy', 0) >= 3, action=PolicyAction.TRANSITION, target_state=GovernanceState.ANALYZE, priority=80))
    engine.add_rule(PolicyRule(name='critical_anomaly', trigger=PolicyTrigger.ANOMALY_DETECTED, condition=lambda ctx: ctx.get('anomaly_severity') == 'critical', action=PolicyAction.FORCE_HALT, priority=200))
    engine.add_rule(PolicyRule(name='drift_verify', trigger=PolicyTrigger.DRIFT_DETECTED, condition=lambda ctx: ctx.get('drift_severity') in ('high', 'critical'), action=PolicyAction.TRANSITION, target_state=GovernanceState.VERIFY, priority=150))
    engine.add_rule(PolicyRule(name='state_timeout', trigger=PolicyTrigger.STATE_TIMEOUT, condition=lambda ctx: ctx.get('state_duration', 0) > 300, action=PolicyAction.ALERT, priority=50))
    return engine
