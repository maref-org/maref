"""Tests for F3: Federated Policy Push / Subscribe."""

from __future__ import annotations

from maref.federation.policy import (
    FederationPolicyEngine,
    PolicyDecision,
    PolicyRule,
    PolicyScope,
)
from maref.federation.policy_subscriber import (
    FederatedPolicySubscriber,
    PolicyChangeType,
    PolicyPushEvent,
    PolicySubscription,
    SubscriptionStatus,
)


def _make_engine() -> FederationPolicyEngine:
    return FederationPolicyEngine()


def _make_rule(
    rule_id: str = "rule-001",
    action: str = "deploy",
    decision: PolicyDecision = PolicyDecision.ALLOW,
    conditions: dict | None = None,
) -> PolicyRule:
    return PolicyRule(
        rule_id=rule_id,
        action=action,
        scope=PolicyScope.FEDERATION,
        decision=decision,
        conditions=conditions or {},
    )


# ------------------------------------------------------------------ #
# PolicyPushEvent
# ------------------------------------------------------------------ #

class TestPolicyPushEvent:
    def test_to_dict(self) -> None:
        rule = _make_rule()
        event = PolicyPushEvent(
            event_id="evt-001",
            publisher_org="org-beta",
            change_type=PolicyChangeType.RULE_ADDED,
            rule=rule,
        )
        d = event.to_dict()
        assert d["event_id"] == "evt-001"
        assert d["change_type"] == "rule_added"
        assert d["rule"] is not None


# ------------------------------------------------------------------ #
# PolicySubscription
# ------------------------------------------------------------------ #

class TestPolicySubscription:
    def test_defaults(self) -> None:
        sub = PolicySubscription(
            subscription_id="sub-1",
            subscriber_org="org-alpha",
            publisher_org="org-beta",
        )
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.auto_import is True
        assert sub.action_filter == "*"

    def test_matches_rule_by_action(self) -> None:
        sub = PolicySubscription(
            subscription_id="sub-1",
            subscriber_org="org-alpha",
            publisher_org="org-beta",
            action_filter="deploy",
        )
        assert sub.matches_rule(_make_rule(action="deploy")) is True
        assert sub.matches_rule(_make_rule(action="train")) is False

    def test_matches_rule_by_trigram(self) -> None:
        sub = PolicySubscription(
            subscription_id="sub-1",
            subscriber_org="org-alpha",
            publisher_org="org-beta",
            trigram_filter=["dui", "li"],
        )
        rule_dui = _make_rule(conditions={"trigram": "dui"})
        rule_kun = _make_rule(conditions={"trigram": "kun"})
        assert sub.matches_rule(rule_dui) is True
        assert sub.matches_rule(rule_kun) is False

    def test_to_dict(self) -> None:
        sub = PolicySubscription(
            subscription_id="sub-1",
            subscriber_org="org-alpha",
            publisher_org="org-beta",
        )
        d = sub.to_dict()
        assert d["subscription_id"] == "sub-1"


# ------------------------------------------------------------------ #
# FederatedPolicySubscriber — subs management
# ------------------------------------------------------------------ #

class TestSubscriberManagement:
    def test_empty_subscriber(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        assert sub.subscription_count() == 0

    def test_subscribe(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        s = sub.subscribe(publisher_org="org-beta")
        assert s.publisher_org == "org-beta"
        assert sub.subscription_count() == 1

    def test_subscribe_deduplicates(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        s1 = sub.subscribe(publisher_org="org-beta", action_filter="deploy")
        s2 = sub.subscribe(publisher_org="org-beta", action_filter="deploy")
        assert s1.subscription_id == s2.subscription_id

    def test_unsubscribe(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        s = sub.subscribe(publisher_org="org-beta")
        assert sub.unsubscribe(s.subscription_id) is True
        assert sub.unsubscribe("nonexistent") is False

    def test_pause_resume(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        s = sub.subscribe(publisher_org="org-beta")
        assert sub.pause_subscription(s.subscription_id) is True
        assert sub.get_subscription(s.subscription_id).status == SubscriptionStatus.PAUSED
        assert sub.resume_subscription(s.subscription_id) is True
        assert sub.get_subscription(s.subscription_id).status == SubscriptionStatus.ACTIVE

    def test_list_subscriptions_by_status(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        sub.subscribe(publisher_org="org-beta")
        sub.subscribe(publisher_org="org-gamma")
        assert len(sub.list_subscriptions(status=SubscriptionStatus.ACTIVE)) == 2
        assert len(sub.list_subscriptions(status=SubscriptionStatus.PAUSED)) == 0


# ------------------------------------------------------------------ #
# Processing push events
# ------------------------------------------------------------------ #

class TestPushEventProcessing:
    def test_process_rule_added(self) -> None:
        engine = _make_engine()
        sub = FederatedPolicySubscriber(local_engine=engine, local_org="org-alpha")
        sub.subscribe(publisher_org="org-beta", action_filter="deploy")

        rule = _make_rule(rule_id="beta-001", action="deploy", decision=PolicyDecision.DENY)
        event = PolicyPushEvent(
            event_id="evt-001",
            publisher_org="org-beta",
            change_type=PolicyChangeType.RULE_ADDED,
            rule=rule,
        )
        assert sub.process_push_event(event) is True

        # Rule should be imported
        imported_id = "imported:org-beta:beta-001"
        imported = [r for r in engine.list_rules() if r.rule_id == imported_id]
        assert len(imported) == 1
        assert imported[0].decision == PolicyDecision.DENY

    def test_process_rule_added_no_match(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        sub.subscribe(publisher_org="org-beta", action_filter="deploy")

        rule = _make_rule(rule_id="beta-001", action="train")
        event = PolicyPushEvent(
            event_id="evt-002",
            publisher_org="org-beta",
            change_type=PolicyChangeType.RULE_ADDED,
            rule=rule,
        )
        # Action "train" doesn't match subscription filter "deploy"
        assert sub.process_push_event(event) is False

    def test_process_rule_removed(self) -> None:
        engine = _make_engine()
        sub = FederatedPolicySubscriber(local_engine=engine, local_org="org-alpha")
        sub.subscribe(publisher_org="org-beta", action_filter="deploy")

        rule = _make_rule(rule_id="beta-001", action="deploy", decision=PolicyDecision.DENY)
        add_event = PolicyPushEvent(
            event_id="evt-add", publisher_org="org-beta",
            change_type=PolicyChangeType.RULE_ADDED, rule=rule,
        )
        sub.process_push_event(add_event)
        assert engine.rule_count() == 1

        remove_event = PolicyPushEvent(
            event_id="evt-rm", publisher_org="org-beta",
            change_type=PolicyChangeType.RULE_REMOVED, rule=rule,
        )
        sub.process_push_event(remove_event)
        assert engine.rule_count() == 0

    def test_process_rule_updated(self) -> None:
        engine = _make_engine()
        sub = FederatedPolicySubscriber(local_engine=engine, local_org="org-alpha")
        sub.subscribe(publisher_org="org-beta", action_filter="deploy")

        old = _make_rule(rule_id="beta-001", action="deploy", decision=PolicyDecision.DENY)
        new = _make_rule(rule_id="beta-001", action="deploy", decision=PolicyDecision.ALLOW)
        add_event = PolicyPushEvent(
            event_id="evt-add", publisher_org="org-beta",
            change_type=PolicyChangeType.RULE_ADDED, rule=old,
        )
        sub.process_push_event(add_event)

        update_event = PolicyPushEvent(
            event_id="evt-upd", publisher_org="org-beta",
            change_type=PolicyChangeType.RULE_UPDATED, rule=new,
            previous_rule=old,
        )
        sub.process_push_event(update_event)

        imported_id = "imported:org-beta:beta-001"
        imported = [r for r in engine.list_rules() if r.rule_id == imported_id]
        assert len(imported) == 1
        assert imported[0].decision == PolicyDecision.ALLOW

    def test_process_policy_cleared(self) -> None:
        engine = _make_engine()
        sub = FederatedPolicySubscriber(local_engine=engine, local_org="org-alpha")
        sub.subscribe(publisher_org="org-beta", action_filter="deploy")

        for i in range(3):
            rule = _make_rule(rule_id=f"beta-00{i}", action="deploy")
            event = PolicyPushEvent(
                event_id=f"evt-{i}", publisher_org="org-beta",
                change_type=PolicyChangeType.RULE_ADDED, rule=rule,
            )
            sub.process_push_event(event)
        assert engine.rule_count() == 3

        clear_event = PolicyPushEvent(
            event_id="evt-clear", publisher_org="org-beta",
            change_type=PolicyChangeType.POLICY_CLEARED,
        )
        sub.process_push_event(clear_event)
        assert engine.rule_count() == 0

    def test_ignores_event_when_paused(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        s = sub.subscribe(publisher_org="org-beta")
        sub.pause_subscription(s.subscription_id)

        rule = _make_rule(rule_id="beta-001", decision=PolicyDecision.DENY)
        event = PolicyPushEvent(
            event_id="evt-paused", publisher_org="org-beta",
            change_type=PolicyChangeType.RULE_ADDED, rule=rule,
        )
        assert sub.process_push_event(event) is True  # matched sub but paused
        assert s.imported_rule_ids == []  # not imported


# ------------------------------------------------------------------ #
# Publishing
# ------------------------------------------------------------------ #

class TestPublishing:
    def test_publish_rule(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        rule = _make_rule(rule_id="pub-001")
        event = sub.publish_rule(rule)
        assert event.change_type == PolicyChangeType.RULE_ADDED
        assert event.publisher_org == "org-alpha"

        rules = sub.get_published_rules()
        assert "org-alpha" in rules
        assert len(rules["org-alpha"]) == 1

    def test_publish_rule_removal(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        rule = _make_rule(rule_id="pub-001")
        sub.publish_rule(rule)

        removal = sub.publish_rule_removal("pub-001")
        assert removal is not None
        assert removal.change_type == PolicyChangeType.RULE_REMOVED

        # Verify removed from published
        rules = sub.get_published_rules()
        assert len(rules["org-alpha"]) == 0

    def test_publish_rule_removal_nonexistent(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        assert sub.publish_rule_removal("nonexistent") is None


# ------------------------------------------------------------------ #
# Event handlers
# ------------------------------------------------------------------ #

class TestEventHandlers:
    def test_event_handler_called(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        events: list[PolicyPushEvent] = []
        sub.add_event_handler(lambda e: events.append(e))

        rule = _make_rule(rule_id="h-001")
        event = PolicyPushEvent(
            event_id="handler-test", publisher_org="org-beta",
            change_type=PolicyChangeType.RULE_ADDED, rule=rule,
        )
        sub.process_push_event(event)
        assert len(events) == 1


# ------------------------------------------------------------------ #
# Policy drift detection
# ------------------------------------------------------------------ #

class TestPolicyDrift:
    def test_no_drift_when_synced(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        sub.subscribe(publisher_org="org-beta", action_filter="deploy")

        rule = _make_rule(rule_id="beta-001", action="deploy")
        event = PolicyPushEvent(
            event_id="drift-test", publisher_org="org-beta",
            change_type=PolicyChangeType.RULE_ADDED, rule=rule,
        )
        sub.process_push_event(event)
        drift = sub.detect_policy_drift("org-beta")
        assert drift == []

    def test_drift_detected_on_missing_import(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        # Publish but don't subscribe/import
        rule = _make_rule(rule_id="beta-001", action="deploy")
        sub.publish_rule(rule, publisher_org="org-beta")
        drift = sub.detect_policy_drift("org-beta")
        assert len(drift) == 1
        assert drift[0]["issue"] == "missing_import"


# ------------------------------------------------------------------ #
# Summary
# ------------------------------------------------------------------ #

class TestSubscriberSummary:
    def test_summary_empty(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        s = sub.subscriber_summary()
        assert s["local_org"] == "org-alpha"
        assert s["total_subscriptions"] == 0

    def test_summary_with_data(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=_make_engine(),
            local_org="org-alpha",
        )
        sub.subscribe(publisher_org="org-beta")
        sub.subscribe(publisher_org="org-gamma")

        rule = _make_rule(rule_id="r1", action="deploy")
        event = PolicyPushEvent(
            event_id="s-test", publisher_org="org-beta",
            change_type=PolicyChangeType.RULE_ADDED, rule=rule,
        )
        sub.process_push_event(event)

        s = sub.subscriber_summary()
        assert s["total_subscriptions"] == 2
        assert s["active_subscriptions"] == 2
        assert s["total_received_events"] >= 1
