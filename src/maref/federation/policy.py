"""Federation Policy Engine.

Layered policy engine for federated governance: combines **federation-level
policies** (agreed upon by all federation members) with **local policies**
(organization-specific overrides). When the two conflict, the engine applies
a configurable conflict resolution strategy.

Policy layers (in precedence order, lowest to highest):
1. **Federation policy**: rules agreed by federation consensus.
2. **Local policy**: organization-specific rules.
3. **Ad-hoc policy**: per-request overrides (e.g. compliance exceptions).

Conflict resolution strategies:
- ``FEDERATION_WINS``: federation policy takes precedence (default).
- ``LOCAL_WINS``: local policy takes precedence (sovereignty-first).
- ``DENY_IF_CONFLICT``: deny the action if local and federation conflict.
- ``MOST_RESTRICTIVE``: apply the stricter of the two policies.

Reference: AIP-ACPs-Technical-Analysis.md section 4.5 (Federation Policy).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PolicyDecision(str, Enum):
    """Outcome of a policy evaluation."""

    ALLOW = "allow"
    DENY = "deny"
    DEFER = "defer"  # requires human approval (HITL)
    NOT_APPLICABLE = "not_applicable"


class ConflictStrategy(str, Enum):
    """Strategy for resolving federation/local policy conflicts."""

    FEDERATION_WINS = "federation_wins"
    LOCAL_WINS = "local_wins"
    DENY_IF_CONFLICT = "deny_if_conflict"
    MOST_RESTRICTIVE = "most_restrictive"


class PolicyScope(str, Enum):
    """Scope at which a policy applies."""

    FEDERATION = "federation"
    LOCAL = "local"
    AD_HOC = "ad_hoc"


# Restrictiveness ordering for tie-breaks and conflict resolution
# (higher = more restrictive).  Used to fail-closed when rules tie.
_RESTRICTIVENESS: dict[PolicyDecision, int] = {
    PolicyDecision.DENY: 3,
    PolicyDecision.DEFER: 2,
    PolicyDecision.ALLOW: 1,
    PolicyDecision.NOT_APPLICABLE: 0,
}


@dataclass(frozen=True)
class PolicyRule:
    """A single policy rule.

    Attributes:
        rule_id: Unique rule identifier.
        action: The action being governed (e.g. "dispatch_task", "cross_border_transfer").
        scope: The scope at which this rule applies.
        decision: The policy decision (ALLOW/DENY/DEFER).
        priority: Higher priority rules override lower priority ones within
            the same scope. Defaults to 0.
        conditions: Optional conditions dict (matched against request context).
        description: Human-readable description.
        created_at: Creation timestamp.
    """

    rule_id: str
    action: str
    scope: PolicyScope
    decision: PolicyDecision
    priority: int = 0
    conditions: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    created_at: float = field(default_factory=time.time)

    def matches(self, action: str, context: dict[str, Any] | None = None) -> bool:
        """Check whether this rule applies to the given action and context.

        A rule matches if:
        - ``action`` equals ``self.action`` (or ``self.action`` is ``"*"``).
        - All conditions in ``self.conditions`` are satisfied by ``context``.
        """
        if self.action != "*" and self.action != action:
            return False
        if not self.conditions:
            return True
        if context is None:
            return False
        for key, expected in self.conditions.items():
            actual = context.get(key)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "action": self.action,
            "scope": self.scope.value,
            "decision": self.decision.value,
            "priority": self.priority,
            "conditions": dict(self.conditions),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyRule:
        """Reconstruct a rule from :meth:`to_dict` output (v0.47 F4)."""
        return cls(
            rule_id=data["rule_id"],
            action=data["action"],
            scope=PolicyScope(data["scope"]),
            decision=PolicyDecision(data["decision"]),
            priority=int(data.get("priority", 0)),
            conditions=dict(data.get("conditions", {})),
            description=data.get("description", ""),
            created_at=float(data.get("created_at", time.time())),
        )


@dataclass
class PolicyEvaluationResult:
    """Result of evaluating a policy request.

    Attributes:
        action: The action that was evaluated.
        decision: The final policy decision.
        matched_rules: All rules that matched the request.
        winning_rule: The rule that determined the final decision.
        conflict_detected: Whether a federation/local conflict was detected.
        conflict_strategy: The strategy used to resolve the conflict.
        context: The request context that was evaluated.
        evaluated_at: Evaluation timestamp.
    """

    action: str
    decision: PolicyDecision
    matched_rules: list[PolicyRule] = field(default_factory=list)
    winning_rule: PolicyRule | None = None
    conflict_detected: bool = False
    conflict_strategy: ConflictStrategy = ConflictStrategy.FEDERATION_WINS
    context: dict[str, Any] = field(default_factory=dict)
    evaluated_at: float = field(default_factory=time.time)
    no_rule_match: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "decision": self.decision.value,
            "matched_rules": [r.to_dict() for r in self.matched_rules],
            "winning_rule": self.winning_rule.to_dict() if self.winning_rule else None,
            "conflict_detected": self.conflict_detected,
            "conflict_strategy": self.conflict_strategy.value,
            "evaluated_at": self.evaluated_at,
            "no_rule_match": self.no_rule_match,
        }


class FederationPolicyEngine:
    """Layered policy engine for federated governance.

    Maintains three policy layers (federation, local, ad-hoc) and resolves
    conflicts using a configurable :class:`ConflictStrategy`.

    Usage:
        engine = FederationPolicyEngine()
        engine.add_federation_rule(PolicyRule(
            rule_id="fed-001",
            action="cross_border_transfer",
            scope=PolicyScope.FEDERATION,
            decision=PolicyDecision.DENY,
        ))
        result = engine.evaluate("cross_border_transfer", {"data_type": "pii"})
    """

    def __init__(
        self,
        conflict_strategy: ConflictStrategy = ConflictStrategy.FEDERATION_WINS,
        db_path: str | Path | None = None,
    ) -> None:
        self._conflict_strategy = conflict_strategy
        self._federation_rules: dict[str, PolicyRule] = {}
        self._local_rules: dict[str, PolicyRule] = {}
        self._adhoc_rules: dict[str, PolicyRule] = {}
        # v0.47 F4: decision log (action → decision) for auditability.
        self._decision_log: list[dict[str, Any]] = []
        self._db = None
        if db_path is not None:
            from maref.governance.db import DatabaseManager

            self._db = DatabaseManager(db_path)
            self._init_schema()
            self._load_from_disk()

    def _init_schema(self) -> None:
        assert self._db is not None
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS policy_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS policy_rules (
                rule_id TEXT PRIMARY KEY,
                data    TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS policy_decisions (
                seq  INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            );
            """
        )

    def _load_from_disk(self) -> None:
        assert self._db is not None
        meta_rows = self._db.fetchall("SELECT key, value FROM policy_meta")
        for row in meta_rows:
            if row["key"] == "conflict_strategy":
                self._conflict_strategy = ConflictStrategy(row["value"])
        rows = self._db.fetchall("SELECT rule_id, data FROM policy_rules")
        for row in rows:
            rule = PolicyRule.from_dict(json.loads(row["data"]))
            self._rules_for_scope(rule.scope)[rule.rule_id] = rule
        decision_rows = self._db.fetchall("SELECT data FROM policy_decisions ORDER BY seq")
        for row in decision_rows:
            self._decision_log.append(json.loads(row["data"]))

    def _persist_rule(self, rule: PolicyRule) -> None:
        if self._db is None:
            return
        self._db.execute(
            "INSERT OR REPLACE INTO policy_rules (rule_id, data) VALUES (?, ?)",
            (rule.rule_id, json.dumps(rule.to_dict())),
        )

    def _delete_rule(self, rule_id: str) -> None:
        if self._db is None:
            return
        self._db.execute("DELETE FROM policy_rules WHERE rule_id = ?", (rule_id,))

    def _persist_decision(self, decision: dict[str, Any]) -> None:
        if self._db is None:
            return
        self._db.execute(
            "INSERT INTO policy_decisions (data) VALUES (?)",
            (json.dumps(decision),),
        )

    def decision_log(self, limit: int = 500) -> list[dict[str, Any]]:
        """Return the decision audit log (most recent last, capped)."""
        return list(self._decision_log[-limit:])

    def _record_decision(self, result: PolicyEvaluationResult) -> None:
        """Append an evaluation to the decision log (v0.47 F4)."""
        entry = result.to_dict()
        self._decision_log.append(entry)
        self._persist_decision(entry)
        if len(self._decision_log) > 2000:
            self._decision_log = self._decision_log[-2000:]

    @property
    def conflict_strategy(self) -> ConflictStrategy:
        return self._conflict_strategy

    def set_conflict_strategy(self, strategy: ConflictStrategy) -> None:
        self._conflict_strategy = strategy
        if self._db is not None:
            self._db.execute(
                "INSERT OR REPLACE INTO policy_meta (key, value) VALUES ('conflict_strategy', ?)",
                (strategy.value,),
            )

    def add_rule(self, rule: PolicyRule) -> None:
        """Add a rule to the appropriate layer based on its scope."""
        target = self._rules_for_scope(rule.scope)
        target[rule.rule_id] = rule
        self._persist_rule(rule)

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule from any layer.

        Returns:
            True if the rule was found and removed, False otherwise.
        """
        for rules in (self._federation_rules, self._local_rules, self._adhoc_rules):
            if rule_id in rules:
                del rules[rule_id]
                self._delete_rule(rule_id)
                return True
        return False

    def add_federation_rule(
        self,
        rule_id: str,
        action: str,
        decision: PolicyDecision,
        priority: int = 0,
        conditions: dict[str, Any] | None = None,
        description: str = "",
    ) -> PolicyRule:
        """Convenience helper for adding a federation-scope rule."""
        rule = PolicyRule(
            rule_id=rule_id,
            action=action,
            scope=PolicyScope.FEDERATION,
            decision=decision,
            priority=priority,
            conditions=conditions or {},
            description=description,
        )
        self.add_rule(rule)
        return rule

    def add_local_rule(
        self,
        rule_id: str,
        action: str,
        decision: PolicyDecision,
        priority: int = 0,
        conditions: dict[str, Any] | None = None,
        description: str = "",
    ) -> PolicyRule:
        """Convenience helper for adding a local-scope rule."""
        rule = PolicyRule(
            rule_id=rule_id,
            action=action,
            scope=PolicyScope.LOCAL,
            decision=decision,
            priority=priority,
            conditions=conditions or {},
            description=description,
        )
        self.add_rule(rule)
        return rule

    def evaluate(
        self,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> PolicyEvaluationResult:
        """Evaluate a policy request against all applicable rules.

        Args:
            action: The action being governed.
            context: Optional request context for condition matching.

        Returns:
            A :class:`PolicyEvaluationResult` with the final decision.
        """
        result = self._evaluate_impl(action, context)
        self._record_decision(result)
        return result

    def _evaluate_impl(
        self,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> PolicyEvaluationResult:
        """Core evaluation (decision log recorded by :meth:`evaluate`)."""
        context = context or {}
        fed_matches = self._matching_rules(self._federation_rules, action, context)
        local_matches = self._matching_rules(self._local_rules, action, context)
        adhoc_matches = self._matching_rules(self._adhoc_rules, action, context)

        # Ad-hoc rules are merged into the federation tier (same precedence).
        # They no longer unconditionally override the federation layer; they
        # compete by priority, with ties broken toward the most restrictive
        # decision (v0.47 S3, fail-closed).
        fed_matches = fed_matches + adhoc_matches

        all_matches = fed_matches + local_matches

        # If only one layer has matches, use its highest-priority rule.
        if fed_matches and not local_matches:
            winner = self._highest_priority(fed_matches)
            return PolicyEvaluationResult(
                action=action,
                decision=winner.decision,
                matched_rules=all_matches,
                winning_rule=winner,
                conflict_detected=False,
                conflict_strategy=self._conflict_strategy,
                context=context,
            )
        if local_matches and not fed_matches:
            winner = self._highest_priority(local_matches)
            return PolicyEvaluationResult(
                action=action,
                decision=winner.decision,
                matched_rules=all_matches,
                winning_rule=winner,
                conflict_detected=False,
                conflict_strategy=self._conflict_strategy,
                context=context,
            )

        # No matches at all — default DENY (fail-closed) with an audit signal.
        if not fed_matches and not local_matches:
            return PolicyEvaluationResult(
                action=action,
                decision=PolicyDecision.DENY,
                matched_rules=[],
                winning_rule=None,
                conflict_detected=False,
                conflict_strategy=self._conflict_strategy,
                context=context,
                no_rule_match=True,
            )

        # Both layers have matches — resolve conflict.
        fed_winner = self._highest_priority(fed_matches)
        local_winner = self._highest_priority(local_matches)
        conflict = fed_winner.decision != local_winner.decision

        if not conflict:
            # Agreement — use the higher-priority rule.
            winner = fed_winner if fed_winner.priority >= local_winner.priority else local_winner
            return PolicyEvaluationResult(
                action=action,
                decision=winner.decision,
                matched_rules=all_matches,
                winning_rule=winner,
                conflict_detected=False,
                conflict_strategy=self._conflict_strategy,
                context=context,
            )

        # Conflict — apply conflict strategy.
        winner = self._resolve_conflict(fed_winner, local_winner)
        return PolicyEvaluationResult(
            action=action,
            decision=winner.decision,
            matched_rules=all_matches,
            winning_rule=winner,
            conflict_detected=True,
            conflict_strategy=self._conflict_strategy,
            context=context,
        )

    def _matching_rules(
        self,
        rules: dict[str, PolicyRule],
        action: str,
        context: dict[str, Any],
    ) -> list[PolicyRule]:
        """Return all rules in a layer that match the action and context."""
        return [r for r in rules.values() if r.matches(action, context)]

    @staticmethod
    def _highest_priority(rules: list[PolicyRule]) -> PolicyRule:
        """Return the highest-priority rule; ties broken toward the most
        restrictive decision, then by rule_id for determinism (fail-closed)."""
        return max(
            rules,
            key=lambda r: (
                r.priority,
                _RESTRICTIVENESS.get(r.decision, 0),
                r.rule_id,
            ),
        )

    def _resolve_conflict(self, fed_rule: PolicyRule, local_rule: PolicyRule) -> PolicyRule:
        """Resolve a conflict between federation and local rules."""
        if self._conflict_strategy == ConflictStrategy.FEDERATION_WINS:
            return fed_rule
        if self._conflict_strategy == ConflictStrategy.LOCAL_WINS:
            return local_rule
        if self._conflict_strategy == ConflictStrategy.DENY_IF_CONFLICT:
            # Return a synthetic DENY rule.
            return PolicyRule(
                rule_id="conflict-deny",
                action=fed_rule.action,
                scope=PolicyScope.FEDERATION,
                decision=PolicyDecision.DENY,
                priority=max(fed_rule.priority, local_rule.priority) + 1,
                description="Auto-DENY due to federation/local conflict",
            )
        # MOST_RESTRICTIVE: DENY wins over DEFER, DEFER wins over ALLOW.
        if _RESTRICTIVENESS[fed_rule.decision] >= _RESTRICTIVENESS[local_rule.decision]:
            return fed_rule
        return local_rule

    def _rules_for_scope(self, scope: PolicyScope) -> dict[str, PolicyRule]:
        """Return the rule dict for a given scope."""
        if scope == PolicyScope.FEDERATION:
            return self._federation_rules
        if scope == PolicyScope.LOCAL:
            return self._local_rules
        return self._adhoc_rules

    def list_rules(self, scope: PolicyScope | None = None) -> list[PolicyRule]:
        """List rules, optionally filtered by scope."""
        if scope is None:
            return (
                list(self._federation_rules.values())
                + list(self._local_rules.values())
                + list(self._adhoc_rules.values())
            )
        return list(self._rules_for_scope(scope).values())

    def rule_count(self, scope: PolicyScope | None = None) -> int:
        """Count rules, optionally filtered by scope."""
        return len(self.list_rules(scope))

    def policy_summary(self) -> dict[str, Any]:
        """Return a summary of the policy engine state."""
        return {
            "conflict_strategy": self._conflict_strategy.value,
            "federation_rules": len(self._federation_rules),
            "local_rules": len(self._local_rules),
            "adhoc_rules": len(self._adhoc_rules),
            "total_rules": (
                len(self._federation_rules) + len(self._local_rules) + len(self._adhoc_rules)
            ),
        }


__all__ = [
    "ConflictStrategy",
    "FederationPolicyEngine",
    "PolicyDecision",
    "PolicyEvaluationResult",
    "PolicyRule",
    "PolicyScope",
]
