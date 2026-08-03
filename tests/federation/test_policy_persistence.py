"""v0.47 F4 — FederationPolicyEngine decision log + SQLite persistence."""

from __future__ import annotations

from pathlib import Path

from maref.federation.policy import (
    ConflictStrategy,
    FederationPolicyEngine,
    PolicyDecision,
    PolicyRule,
    PolicyScope,
)


def _engine(db_path: Path | None = None) -> FederationPolicyEngine:
    return FederationPolicyEngine(db_path=db_path)


class TestPolicyDecisionLog:
    def test_evaluate_records_decision(self) -> None:
        engine = _engine()
        engine.add_federation_rule("f1", "x", PolicyDecision.DENY)
        engine.evaluate("x")
        engine.evaluate("unknown-action")
        log = engine.decision_log()
        assert len(log) == 2
        assert log[0]["action"] == "x"
        assert log[0]["decision"] == "deny"
        assert log[1]["no_rule_match"] is True

    def test_decision_log_capacity(self) -> None:
        engine = _engine()
        engine.add_federation_rule("f1", "x", PolicyDecision.DENY)
        for _ in range(5):
            engine.evaluate("x")
        assert len(engine.decision_log()) == 5


class TestPolicyPersistence:
    def test_rules_recovered_after_reload(self, tmp_path: Path) -> None:
        db = tmp_path / "policy.db"
        engine = _engine(db)
        engine.add_federation_rule("f1", "x", PolicyDecision.DENY, priority=3)
        engine.add_local_rule("l1", "y", PolicyDecision.ALLOW)
        engine.set_conflict_strategy(ConflictStrategy.MOST_RESTRICTIVE)

        reloaded = _engine(db)
        assert reloaded.rule_count(PolicyScope.FEDERATION) == 1
        assert reloaded.rule_count(PolicyScope.LOCAL) == 1
        assert reloaded.conflict_strategy == ConflictStrategy.MOST_RESTRICTIVE
        rule = reloaded.list_rules(PolicyScope.FEDERATION)[0]
        assert rule.decision == PolicyDecision.DENY
        assert rule.priority == 3

    def test_decision_log_recovered(self, tmp_path: Path) -> None:
        db = tmp_path / "policy.db"
        engine = _engine(db)
        engine.add_federation_rule("f1", "x", PolicyDecision.DENY)
        engine.evaluate("x")

        reloaded = _engine(db)
        log = reloaded.decision_log()
        assert len(log) == 1
        assert log[0]["decision"] == "deny"

    def test_no_db_path_in_memory(self) -> None:
        engine = _engine()
        engine.add_federation_rule("f1", "x", PolicyDecision.DENY)
        assert engine.evaluate("x").decision == PolicyDecision.DENY
