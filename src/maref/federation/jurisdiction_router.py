"""Multi-Jurisdiction Governance Policy Router (F2).

Bridges :class:`EightTrigramsGovernance` (per-agent trigram state) with
jurisdiction-specific policy engines. Each jurisdiction (e.g. EU AI Act,
US Executive Order, CN Generative AI Regulation) maintains its own
:class:`FederationPolicyEngine` with trigram-aware rules.

The router:
  1. Maps an agent's current trigram to compatible jurisdictions.
  2. Evaluates the same action across all compatible jurisdictions.
  3. Resolves cross-jurisdiction conflicts using configurable strategies.
  4. Suggests the best jurisdiction for a given action based on the
     agent's evolution permission and autonomy scope.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from maref.federation.policy import (
    FederationPolicyEngine,
    PolicyDecision,
    PolicyEvaluationResult,
)
from maref.governance.federated_consensus import FederationRole
from maref.recursive.eight_trigrams_governance import TrigramsGovernance


class JurisdictionConflictStrategy(str, Enum):
    """Strategy for resolving cross-jurisdiction policy conflicts."""

    MOST_PERMISSIVE = "most_permissive"
    MOST_RESTRICTIVE = "most_restrictive"
    PREFER_JURISDICTION = "prefer_jurisdiction"
    DENY_IF_CONFLICT = "deny_if_conflict"


# Maps trigram evolution_permission → evaluation weight
_TRIGRAM_PERMISSION_WEIGHTS: dict[str, int] = {
    "full": 5,
    "collaborative": 4,
    "defensive": 3,
    "connective": 3,
    "learning_only": 2,
    "risk_assessment": 2,
    "emergency_only": 1,
    "none": 0,
}


@dataclass
class JurisdictionConfig:
    """Configuration for a single jurisdiction's policy engine.

    Attributes:
        name: Jurisdiction name (e.g. ``"eu_ai_act"``).
        description: Human-readable description.
        policy_engine: The :class:`FederationPolicyEngine` for this jurisdiction.
        allowed_trigrams: Set of trigrams permitted to operate in this
            jurisdiction. Empty set means all trigrams are allowed.
        default_decision: Default decision when no rules match (fail-closed).
        weight: Priority weight for cross-jurisdiction conflict resolution
            (higher = preferred).
        metadata: Optional metadata (e.g. regulatory reference).
    """

    name: str
    description: str = ""
    policy_engine: FederationPolicyEngine | None = None
    allowed_trigrams: set[str] = field(default_factory=set)
    default_decision: PolicyDecision = PolicyDecision.DENY
    weight: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class JurisdictionEvaluation:
    """Result of evaluating an action in a single jurisdiction.

    Attributes:
        jurisdiction: Jurisdiction name.
        compatible: Whether the agent's trigram is allowed in this jurisdiction.
        decision: The policy decision from this jurisdiction.
        trigram_allowed: Whether the specific trigram is allowed.
        evaluation_result: The raw :class:`PolicyEvaluationResult`.
    """

    jurisdiction: str
    compatible: bool
    decision: PolicyDecision
    trigram_allowed: bool = True
    evaluation_result: PolicyEvaluationResult | None = None


@dataclass
class CrossJurisdictionResult:
    """Aggregated result across all jurisdictions.

    Attributes:
        action: The action that was evaluated.
        agent_trigram: The agent's current trigram.
        final_decision: The resolved cross-jurisdiction decision.
        jurisdiction_results: Per-jurisdiction evaluation results.
        conflict_detected: Whether a cross-jurisdiction conflict was detected.
        suggested_jurisdiction: The recommended jurisdiction for this action.
        evaluated_at: Evaluation timestamp.
    """

    action: str
    agent_trigram: str
    final_decision: PolicyDecision
    jurisdiction_results: list[JurisdictionEvaluation]
    conflict_detected: bool = False
    suggested_jurisdiction: str = ""
    evaluated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for HTTP / audit consumption."""
        return {
            "action": self.action,
            "agent_trigram": self.agent_trigram,
            "final_decision": self.final_decision.value,
            "conflict_detected": self.conflict_detected,
            "suggested_jurisdiction": self.suggested_jurisdiction,
            "evaluated_at": self.evaluated_at,
            "jurisdiction_results": [
                {
                    "jurisdiction": jr.jurisdiction,
                    "compatible": jr.compatible,
                    "decision": jr.decision.value,
                    "trigram_allowed": jr.trigram_allowed,
                    "winning_rule": (
                        jr.evaluation_result.winning_rule.rule_id
                        if jr.evaluation_result is not None
                        and jr.evaluation_result.winning_rule is not None
                        else None
                    ),
                    "matched_rules": (
                        [r.rule_id for r in jr.evaluation_result.matched_rules]
                        if jr.evaluation_result is not None
                        else []
                    ),
                }
                for jr in self.jurisdiction_results
            ],
        }


class JurisdictionPolicyRouter:
    """Routes policy decisions across jurisdictions based on trigram state.

    Register jurisdictions with their policy engines, then evaluate actions
    against the agent's current trigram to get a cross-jurisdiction decision.

    Usage::

        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(
            JurisdictionConfig(
                name="eu_ai_act",
                policy_engine=FederationPolicyEngine(),
                allowed_trigrams={"dui", "li", "qian", "gen"},
                weight=2,
            )
        )
        result = router.route_action(
            trigram="dui",
            action="cross_border_transfer",
            context={"data_type": "pii"},
        )
    """

    def __init__(
        self,
        conflict_strategy: JurisdictionConflictStrategy = JurisdictionConflictStrategy.MOST_RESTRICTIVE,
        prefer_jurisdiction: str = "",
        audit_logger: Any | None = None,
        db_path: str | Path | None = None,
    ):
        self._configs: dict[str, JurisdictionConfig] = {}
        self._conflict_strategy = conflict_strategy
        self._prefer_jurisdiction = prefer_jurisdiction
        self._audit_logger = audit_logger
        self._decision_log: list[dict[str, Any]] = []
        # v0.47 F4: SQLite persistence for the decision log.
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
            CREATE TABLE IF NOT EXISTS jurisdiction_decisions (
                seq  INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            );
            """
        )

    def _load_from_disk(self) -> None:
        assert self._db is not None
        rows = self._db.fetchall("SELECT data FROM jurisdiction_decisions ORDER BY seq")
        for row in rows:
            self._decision_log.append(json.loads(row["data"]))

    def _persist_decision(self, entry: dict[str, Any]) -> None:
        if self._db is None:
            return
        self._db.execute(
            "INSERT INTO jurisdiction_decisions (data) VALUES (?)",
            (json.dumps(entry),),
        )

    # ------------------------------------------------------------------
    # Jurisdiction management
    # ------------------------------------------------------------------

    def register_jurisdiction(self, config: JurisdictionConfig) -> None:
        """Register a jurisdiction for policy routing.

        If the config has no policy engine, a fresh one is created.
        """
        if config.policy_engine is None:
            config.policy_engine = FederationPolicyEngine()
        self._configs[config.name] = config

    def unregister_jurisdiction(self, name: str) -> bool:
        """Remove a jurisdiction from the router."""
        if name not in self._configs:
            return False
        del self._configs[name]
        return True

    def get_jurisdiction(self, name: str) -> JurisdictionConfig | None:
        """Return the config for a named jurisdiction."""
        return self._configs.get(name)

    def list_jurisdictions(self) -> list[JurisdictionConfig]:
        """Return all registered jurisdictions."""
        return list(self._configs.values())

    def jurisdiction_count(self) -> int:
        return len(self._configs)

    # ------------------------------------------------------------------
    # Rule helpers
    # ------------------------------------------------------------------

    def add_jurisdiction_rule(
        self,
        jurisdiction: str,
        rule_id: str,
        action: str,
        decision: PolicyDecision,
        trigram_filter: list[str] | None = None,
        priority: int = 0,
        conditions: dict[str, Any] | None = None,
        description: str = "",
    ) -> bool:
        """Add a trigram-aware policy rule to a jurisdiction.

        The ``trigram_filter`` is stored as a policy condition so that the
        rule only fires when the agent's trigram matches.

        Returns True if the jurisdiction exists, False otherwise.
        """
        config = self._configs.get(jurisdiction)
        if config is None or config.policy_engine is None:
            return False

        full_conditions = dict(conditions or {})
        if trigram_filter is not None:
            full_conditions["trigram"] = trigram_filter

        config.policy_engine.add_local_rule(
            rule_id=rule_id,
            action=action,
            decision=decision,
            priority=priority,
            conditions=full_conditions,
            description=description,
        )
        return True

    def set_conflict_strategy(
        self,
        strategy: JurisdictionConflictStrategy,
        prefer_jurisdiction: str = "",
    ) -> None:
        self._conflict_strategy = strategy
        if strategy == JurisdictionConflictStrategy.PREFER_JURISDICTION:
            self._prefer_jurisdiction = prefer_jurisdiction

    # ------------------------------------------------------------------
    # Core routing
    # ------------------------------------------------------------------

    def route_action(
        self,
        trigram: str | TrigramsGovernance,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> CrossJurisdictionResult:
        """Route an action across all compatible jurisdictions.

        Args:
            trigram: The agent's current trigram (string or enum).
            action: The action being governed.
            context: Optional request context for condition matching.

        Returns:
            A :class:`CrossJurisdictionResult` with the resolved decision.
        """
        trigram_str = trigram.value if isinstance(trigram, TrigramsGovernance) else trigram
        context = dict(context or {})
        context["trigram"] = trigram_str

        results: list[JurisdictionEvaluation] = []
        for _name, config in self._configs.items():
            jr = self._evaluate_jurisdiction(
                config=config,
                trigram=trigram_str,
                action=action,
                context=context,
            )
            results.append(jr)

        result = self._resolve_cross_jurisdiction(
            action=action,
            trigram=trigram_str,
            results=results,
        )
        self._record_decision(result)
        return result

    def _evaluate_jurisdiction(
        self,
        config: JurisdictionConfig,
        trigram: str,
        action: str,
        context: dict[str, Any],
    ) -> JurisdictionEvaluation:
        """Evaluate an action in a single jurisdiction."""
        trigram_allowed = (
            True if not config.allowed_trigrams else trigram in config.allowed_trigrams
        )

        if not trigram_allowed:
            return JurisdictionEvaluation(
                jurisdiction=config.name,
                compatible=False,
                decision=PolicyDecision.DENY,
                trigram_allowed=False,
            )

        engine = config.policy_engine
        if engine is None:
            return JurisdictionEvaluation(
                jurisdiction=config.name,
                compatible=True,
                decision=config.default_decision,
            )

        result = engine.evaluate(action=action, context=context)
        return JurisdictionEvaluation(
            jurisdiction=config.name,
            compatible=True,
            decision=result.decision,
            trigram_allowed=True,
            evaluation_result=result,
        )

    def _resolve_cross_jurisdiction(
        self,
        action: str,
        trigram: str,
        results: list[JurisdictionEvaluation],
    ) -> CrossJurisdictionResult:
        """Resolve decisions across jurisdictions."""
        compatible = [r for r in results if r.compatible]

        if not compatible:
            return CrossJurisdictionResult(
                action=action,
                agent_trigram=trigram,
                final_decision=PolicyDecision.DENY,
                jurisdiction_results=results,
                conflict_detected=False,
                suggested_jurisdiction="",
            )

        decisions = {r.decision for r in compatible}
        has_conflict = len(decisions) > 1

        if not has_conflict:
            winner = compatible[0]
            return CrossJurisdictionResult(
                action=action,
                agent_trigram=trigram,
                final_decision=winner.decision,
                jurisdiction_results=results,
                conflict_detected=False,
                suggested_jurisdiction=winner.jurisdiction,
            )

        final = self._apply_conflict_strategy(compatible)
        suggested = self._suggest_jurisdiction(compatible, trigram)
        return CrossJurisdictionResult(
            action=action,
            agent_trigram=trigram,
            final_decision=final.decision,
            jurisdiction_results=results,
            conflict_detected=True,
            suggested_jurisdiction=suggested,
        )

    def _apply_conflict_strategy(
        self,
        compatible: list[JurisdictionEvaluation],
    ) -> JurisdictionEvaluation:
        """Apply the configured conflict strategy."""
        if self._conflict_strategy == JurisdictionConflictStrategy.MOST_PERMISSIVE:
            return max(
                compatible,
                key=lambda r: self._decision_permissiveness(r.decision),
            )

        if self._conflict_strategy == JurisdictionConflictStrategy.MOST_RESTRICTIVE:
            return min(
                compatible,
                key=lambda r: self._decision_permissiveness(r.decision),
            )

        if self._conflict_strategy == JurisdictionConflictStrategy.PREFER_JURISDICTION:
            preferred = [r for r in compatible if r.jurisdiction == self._prefer_jurisdiction]
            if preferred:
                return preferred[0]
            return compatible[0]

        # DENY_IF_CONFLICT
        return JurisdictionEvaluation(
            jurisdiction="conflict-resolver",
            compatible=True,
            decision=PolicyDecision.DENY,
        )

    def _suggest_jurisdiction(
        self,
        compatible: list[JurisdictionEvaluation],
        trigram: str,
    ) -> str:
        """Suggest the best jurisdiction based on trigram and weights."""
        permission = self._get_trigram_permission(trigram)
        base_weight = _TRIGRAM_PERMISSION_WEIGHTS.get(permission, 0)

        best: tuple[int, str, str] = (-1, "", "")
        for r in compatible:
            config = self._configs.get(r.jurisdiction)
            jw = config.weight if config else 1
            score = base_weight * jw
            if r.decision == PolicyDecision.ALLOW:
                score += 10
            elif r.decision == PolicyDecision.DEFER:
                score += 5
            entry = (score, r.jurisdiction, r.decision.value)
            if entry > best:
                best = entry

        return best[1] if best else ""

    # ------------------------------------------------------------------
    # Compatibility queries
    # ------------------------------------------------------------------

    def get_compatible_jurisdictions(
        self,
        trigram: str | TrigramsGovernance,
        action: str = "",
    ) -> list[dict[str, Any]]:
        """Return jurisdictions compatible with the given trigram."""
        trigram_str = trigram.value if isinstance(trigram, TrigramsGovernance) else trigram
        compatible: list[dict[str, Any]] = []
        for name, config in self._configs.items():
            allowed = (
                True if not config.allowed_trigrams else trigram_str in config.allowed_trigrams
            )
            if allowed:
                compatible.append(
                    {
                        "name": name,
                        "description": config.description,
                        "weight": config.weight,
                    }
                )
        return compatible

    def suggest_jurisdiction(
        self,
        trigram: str | TrigramsGovernance,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Suggest the best jurisdiction for an action and trigram.

        A convenience wrapper around :meth:`route_action` that returns
        just the jurisdiction name.
        """
        result = self.route_action(trigram=trigram, action=action, context=context)
        return result.suggested_jurisdiction

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def router_summary(self) -> dict[str, Any]:
        """Return a summary of the router state."""
        return {
            "jurisdiction_count": len(self._configs),
            "jurisdictions": [
                {
                    "name": c.name,
                    "description": c.description,
                    "allowed_trigrams": list(c.allowed_trigrams) if c.allowed_trigrams else ["*"],
                    "weight": c.weight,
                    "rule_count": c.policy_engine.rule_count() if c.policy_engine else 0,
                }
                for c in self._configs.values()
            ],
            "conflict_strategy": self._conflict_strategy.value,
            "prefer_jurisdiction": (
                self._prefer_jurisdiction
                if self._conflict_strategy == JurisdictionConflictStrategy.PREFER_JURISDICTION
                else ""
            ),
        }

    # ------------------------------------------------------------------
    # Federation role assignment (v0.44.0 F1)
    # ------------------------------------------------------------------

    def assign_federation_roles(
        self,
        members: list[str],
        leader_id: str,
    ) -> dict[str, FederationRole]:
        """Assign LEADER_WORKER roles across a federation member set.

        The leader is designated by ``leader_id``; every other member is a
        worker. A member outside the member set is not assigned a role.
        Role assignment is deterministic — the same inputs always yield the
        same mapping.

        Args:
            members: The federation member identifiers.
            leader_id: The member designated as leader.

        Returns:
            A mapping of member_id → :class:`FederationRole`.
        """
        roles: dict[str, FederationRole] = {}
        for member in members:
            if member == leader_id:
                roles[member] = FederationRole.LEADER
            else:
                roles[member] = FederationRole.WORKER
        return roles

    def suggest_consensus_topology(self, critical_topic: bool = False) -> str:
        """Suggest a consensus topology for a decision.

        Returns ``"leader_worker"`` for routine decisions (fast execution
        under leader arbitration) and ``"flat"`` for critical decisions
        (escalated to full quorum voting).

        Args:
            critical_topic: Whether the decision is critical.

        Returns:
            The suggested :class:`ConsensusTopology` value.
        """
        from maref.governance.federated_consensus import ConsensusTopology

        if critical_topic:
            return ConsensusTopology.FLAT.value
        return ConsensusTopology.LEADER_WORKER.value

    # ------------------------------------------------------------------
    # Compliance audit trail (Phase 3.5)
    # ------------------------------------------------------------------

    def decision_log(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Return the decision audit trail (newest first when limited).

        Every :meth:`route_action` call appends one entry with the action,
        trigram, per-jurisdiction decisions, winning rule ids and the final
        cross-jurisdiction decision — the "operation trace" required for
        cross-jurisdiction compliance review.
        """
        log = self._decision_log
        return list(log[-limit:]) if limit is not None else list(log)

    def compliance_report(self, limit: int = 10) -> dict[str, Any]:
        """Generate a cross-jurisdiction compliance report.

        Summarizes every recorded decision per jurisdiction (with its legal
        reference) plus the most recent decisions — the audit artefact for
        regulatory submission.

        Args:
            limit: Number of most recent decisions to include.

        Returns:
            A report dict with aggregate stats and the decision trail.
        """
        jurisdiction_stats: dict[str, dict[str, Any]] = {
            cfg.name: {
                "description": cfg.description,
                "regulation_ref": cfg.metadata.get("regulation_ref", ""),
                "rule_count": cfg.policy_engine.rule_count() if cfg.policy_engine else 0,
                "decisions": 0,
                "allow": 0,
                "deny": 0,
                "defer": 0,
            }
            for cfg in self._configs.values()
        }
        for entry in self._decision_log:
            for name, jr in entry["jurisdictions"].items():
                stats = jurisdiction_stats.setdefault(
                    name,
                    {
                        "description": "",
                        "regulation_ref": self._regulation_ref(name),
                        "rule_count": 0,
                        "decisions": 0,
                        "allow": 0,
                        "deny": 0,
                        "defer": 0,
                    },
                )
                stats["decisions"] += 1
                decision = jr["decision"]
                if decision in stats:
                    stats[decision] += 1

        return {
            "generated_at": time.time(),
            "total_decisions": len(self._decision_log),
            "conflicts_detected": sum(1 for e in self._decision_log if e["conflict_detected"]),
            "jurisdictions": jurisdiction_stats,
            "recent_decisions": self.decision_log(limit=limit),
        }

    def _record_decision(self, result: CrossJurisdictionResult) -> None:
        """Append a decision to the audit trail (and external audit logger)."""
        entry: dict[str, Any] = {
            "timestamp": result.evaluated_at,
            "action": result.action,
            "trigram": result.agent_trigram,
            "final_decision": result.final_decision.value,
            "conflict_detected": result.conflict_detected,
            "suggested_jurisdiction": result.suggested_jurisdiction,
            "jurisdictions": {
                jr.jurisdiction: {
                    "decision": jr.decision.value,
                    "compatible": jr.compatible,
                    "winning_rule": (
                        jr.evaluation_result.winning_rule.rule_id
                        if jr.evaluation_result is not None
                        and jr.evaluation_result.winning_rule is not None
                        else None
                    ),
                    "regulation_ref": self._regulation_ref(jr.jurisdiction),
                }
                for jr in result.jurisdiction_results
            },
        }
        self._decision_log.append(entry)
        self._persist_decision(entry)
        if self._audit_logger is not None:
            self._audit_logger.log(
                event_type="compliance_decision",
                actor=f"trigram:{result.agent_trigram}",
                action=result.action,
                details=(
                    f"final={result.final_decision.value} conflict={result.conflict_detected}"
                ),
                metadata={
                    "final_decision": result.final_decision.value,
                    "conflict_detected": result.conflict_detected,
                    "suggested_jurisdiction": result.suggested_jurisdiction,
                },
                layer="federation",
            )

    def _regulation_ref(self, jurisdiction: str) -> str:
        config = self._configs.get(jurisdiction)
        if config is None:
            return ""
        return str(config.metadata.get("regulation_ref", ""))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decision_permissiveness(d: PolicyDecision) -> int:
        return {
            PolicyDecision.ALLOW: 3,
            PolicyDecision.DEFER: 2,
            PolicyDecision.NOT_APPLICABLE: 1,
            PolicyDecision.DENY: 0,
        }.get(d, 0)

    @staticmethod
    def _get_trigram_permission(trigram_str: str) -> str:
        """Map trigram name to evolution_permission."""
        permission_map: dict[str, str] = {
            "qian": "full",
            "kun": "none",
            "zhen": "emergency_only",
            "xun": "learning_only",
            "kan": "risk_assessment",
            "li": "collaborative",
            "gen": "defensive",
            "dui": "connective",
        }
        return permission_map.get(trigram_str, "none")
