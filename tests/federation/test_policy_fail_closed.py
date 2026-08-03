"""v0.47 S3 — policy fail-closed.

Two behaviour changes on :class:`FederationPolicyEngine.evaluate`:

1. **Default deny**: when no rule matches an action the engine returns
   ``PolicyDecision.DENY`` (previously ALLOW) and marks
   ``no_rule_match=True`` on the result so callers can raise an
   ``E1006``-style audit event.  Explicit rules still decide.
2. **Ad-hoc layer demoted**: ad-hoc rules no longer unconditionally
   override the federation layer.  They are merged into the federation
   layer (same precedence tier) and compete by ``priority``; ties are
   broken toward the most restrictive decision (fail-closed).

Three-state coverage per the v0.47 test plan: normal (explicit rule),
bypass (no matching rule), demotion (ad-hoc vs federation).
"""

from __future__ import annotations

from maref.federation.policy import (
    ConflictStrategy,
    FederationPolicyEngine,
    PolicyDecision,
    PolicyEvaluationResult,
    PolicyRule,
    PolicyScope,
)


# ── Change 1: default deny + no_rule_match ────────────────────────────────


def test_no_rules_defaults_to_deny() -> None:
    engine = FederationPolicyEngine()
    result = engine.evaluate("any_action")
    assert result.decision == PolicyDecision.DENY
    assert result.winning_rule is None
    assert result.matched_rules == []
    assert result.no_rule_match is True


def test_unmatched_action_defaults_to_deny() -> None:
    """A rule exists for another action — this action is denied."""
    engine = FederationPolicyEngine()
    engine.add_federation_rule("f1", "dispatch_task", PolicyDecision.ALLOW)
    result = engine.evaluate("unrelated_action")
    assert result.decision == PolicyDecision.DENY
    assert result.no_rule_match is True


def test_condition_mismatch_defaults_to_deny() -> None:
    """Rule exists but its conditions do not match — denied, not allowed."""
    engine = FederationPolicyEngine()
    engine.add_federation_rule(
        "f1", "cross_border_transfer", PolicyDecision.ALLOW,
        conditions={"data_type": "pii"},
    )
    result = engine.evaluate("cross_border_transfer", {"data_type": "public"})
    assert result.decision == PolicyDecision.DENY
    assert result.no_rule_match is True


def test_explicit_allow_rule_still_allows() -> None:
    """An explicit matching ALLOW rule wins (normal state)."""
    engine = FederationPolicyEngine()
    engine.add_federation_rule("f1", "dispatch_task", PolicyDecision.ALLOW)
    result = engine.evaluate("dispatch_task")
    assert result.decision == PolicyDecision.ALLOW
    assert result.no_rule_match is False
    assert result.winning_rule is not None


def test_explicit_deny_rule_still_denies() -> None:
    engine = FederationPolicyEngine()
    engine.add_local_rule("l1", "dangerous", PolicyDecision.DENY)
    result = engine.evaluate("dangerous")
    assert result.decision == PolicyDecision.DENY
    assert result.no_rule_match is False


def test_removed_rule_denies_again() -> None:
    """After removing the only matching rule the action falls back to deny."""
    engine = FederationPolicyEngine()
    engine.add_federation_rule("f1", "x", PolicyDecision.ALLOW)
    assert engine.remove_rule("f1") is True
    result = engine.evaluate("x")
    assert result.decision == PolicyDecision.DENY
    assert result.no_rule_match is True


def test_result_exposes_no_rule_match_flag() -> None:
    """The audit signal must be visible on the result object and its dict."""
    engine = FederationPolicyEngine()
    denied = engine.evaluate("unknown")
    assert denied.no_rule_match is True
    assert denied.to_dict()["no_rule_match"] is True
    engine.add_federation_rule("f1", "known", PolicyDecision.ALLOW)
    allowed = engine.evaluate("known")
    assert allowed.no_rule_match is False
    assert allowed.to_dict()["no_rule_match"] is False


# ── Change 2: ad-hoc layer demotion ───────────────────────────────────────


def test_adhoc_no_longer_overrides_federation_by_default() -> None:
    """Ad-hoc ALLOW(0) vs federation DENY(0): equal priority → most
    restrictive wins → DENY.  The unconditional override is removed."""
    engine = FederationPolicyEngine()
    engine.add_federation_rule("f1", "x", PolicyDecision.DENY)
    engine.add_rule(
        PolicyRule(
            rule_id="a1", action="x", scope=PolicyScope.AD_HOC,
            decision=PolicyDecision.ALLOW,
        )
    )
    result = engine.evaluate("x")
    assert result.decision == PolicyDecision.DENY


def test_adhoc_higher_priority_wins() -> None:
    """Ad-hoc with higher priority than the federation rule wins."""
    engine = FederationPolicyEngine()
    engine.add_federation_rule("f1", "x", PolicyDecision.DENY, priority=1)
    engine.add_rule(
        PolicyRule(
            rule_id="a1", action="x", scope=PolicyScope.AD_HOC,
            decision=PolicyDecision.ALLOW, priority=10,
        )
    )
    result = engine.evaluate("x")
    assert result.decision == PolicyDecision.ALLOW
    assert result.winning_rule is not None
    assert result.winning_rule.rule_id == "a1"


def test_adhoc_deny_overrides_federation_allow_same_priority() -> None:
    """Ad-hoc DENY(0) vs federation ALLOW(0): restrictive tie-break → DENY."""
    engine = FederationPolicyEngine()
    engine.add_federation_rule("f1", "x", PolicyDecision.ALLOW)
    engine.add_rule(
        PolicyRule(
            rule_id="a1", action="x", scope=PolicyScope.AD_HOC,
            decision=PolicyDecision.DENY,
        )
    )
    result = engine.evaluate("x")
    assert result.decision == PolicyDecision.DENY


def test_adhoc_still_resolves_against_local_under_conflict_strategy() -> None:
    """Ad-hoc now participates in conflict resolution like the federation
    layer (FEDERATION_WINS keeps the merged fed/ad-hoc winner)."""
    engine = FederationPolicyEngine()
    engine.add_local_rule("l1", "x", PolicyDecision.ALLOW)
    engine.add_rule(
        PolicyRule(
            rule_id="a1", action="x", scope=PolicyScope.AD_HOC,
            decision=PolicyDecision.DENY, priority=5,
        )
    )
    result = engine.evaluate("x")
    assert result.decision == PolicyDecision.DENY
    assert result.winning_rule is not None
    assert result.winning_rule.rule_id == "a1"


def test_adhoc_only_rule_still_decides() -> None:
    """A lone ad-hoc rule behaves like a normal rule (no override needed)."""
    engine = FederationPolicyEngine()
    engine.add_rule(
        PolicyRule(
            rule_id="a1", action="x", scope=PolicyScope.AD_HOC,
            decision=PolicyDecision.DENY,
        )
    )
    result = engine.evaluate("x")
    assert result.decision == PolicyDecision.DENY


def test_existing_conflict_strategy_untouched() -> None:
    """Federation/local conflict resolution still honours the strategy."""
    engine = FederationPolicyEngine(
        conflict_strategy=ConflictStrategy.LOCAL_WINS
    )
    engine.add_federation_rule("f1", "x", PolicyDecision.DENY)
    engine.add_local_rule("l1", "x", PolicyDecision.ALLOW)
    result = engine.evaluate("x")
    assert result.decision == PolicyDecision.ALLOW
    assert result.conflict_detected is True


def test_result_type_is_policy_evaluation_result() -> None:
    result = FederationPolicyEngine().evaluate("any")
    assert isinstance(result, PolicyEvaluationResult)
