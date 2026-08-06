"""Federated Policy Push / Subscribe (F3).

Enables cross-org policy distribution via a publish-subscribe model.
Organizations can:
  - Subscribe to policy rules from remote orgs (by action, trigram, or all).
  - Publish policy rule changes to subscribers.
  - Auto-import pushed rules into the local :class:`FederationPolicyEngine`.
  - Track subscription status and detect policy drift.

The subscriber maintains a local mirror of subscribed remote rules,
allowing offline evaluation and drift detection.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.federation.policy import (
    FederationPolicyEngine,
    PolicyRule,
    PolicyScope,
)


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    TERMINATED = "terminated"
    ERROR = "error"


class PolicyChangeType(str, Enum):
    RULE_ADDED = "rule_added"
    RULE_REMOVED = "rule_removed"
    RULE_UPDATED = "rule_updated"
    POLICY_CLEARED = "policy_cleared"


@dataclass
class PolicyPushEvent:
    """A policy change event pushed from a remote org.

    Attributes:
        event_id: Unique event identifier.
        publisher_org: The org that published this change.
        change_type: The type of policy change.
        rule: The affected policy rule (None for POLICY_CLEARED).
        previous_rule: The previous version of the rule (for RULE_UPDATED).
        timestamp: When the event was generated.
        signature: Optional HMAC/Ed25519 signature for verification.
    """

    event_id: str
    publisher_org: str
    change_type: PolicyChangeType
    rule: PolicyRule | None = None
    previous_rule: PolicyRule | None = None
    timestamp: float = field(default_factory=time.time)
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "publisher_org": self.publisher_org,
            "change_type": self.change_type.value,
            "rule": self.rule.to_dict() if self.rule else None,
            "previous_rule": self.previous_rule.to_dict() if self.previous_rule else None,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }


@dataclass
class PolicySubscription:
    """A subscription to policy changes from a remote org.

    Attributes:
        subscription_id: Unique subscription identifier.
        subscriber_org: The org that owns this subscription.
        publisher_org: The org whose policies are subscribed to.
        action_filter: If set, only subscribe to rules for this action.
            Use ``"*"`` for all actions.
        trigram_filter: If set, only subscribe to rules for these trigrams.
            Empty list means no trigram filter.
        status: Current subscription status.
        imported_rule_ids: IDs of rules imported from this subscription.
        auto_import: Whether to auto-import pushed rules into the local engine.
        created_at: When the subscription was created.
        last_event_at: Timestamp of the last received event.
    """

    subscription_id: str
    subscriber_org: str
    publisher_org: str
    action_filter: str = "*"
    trigram_filter: list[str] = field(default_factory=list)
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    imported_rule_ids: list[str] = field(default_factory=list)
    auto_import: bool = True
    created_at: float = field(default_factory=time.time)
    last_event_at: float = 0.0

    def matches_rule(self, rule: PolicyRule) -> bool:
        """Check whether a rule matches this subscription's filters."""
        if self.action_filter != "*" and rule.action != self.action_filter:
            return False
        if self.trigram_filter:
            rule_trigram = rule.conditions.get("trigram", "")
            if isinstance(rule_trigram, list):
                if not any(t in self.trigram_filter for t in rule_trigram):
                    return False
            elif rule_trigram not in self.trigram_filter:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "subscription_id": self.subscription_id,
            "subscriber_org": self.subscriber_org,
            "publisher_org": self.publisher_org,
            "action_filter": self.action_filter,
            "trigram_filter": list(self.trigram_filter),
            "status": self.status.value,
            "imported_rule_count": len(self.imported_rule_ids),
            "auto_import": self.auto_import,
            "created_at": self.created_at,
            "last_event_at": self.last_event_at,
        }


class FederatedPolicySubscriber:
    """Manages subscriptions to remote policy feeds.

    Each subscription monitors a remote org's policy changes and can
    auto-import matching rules into the local policy engine.

    Usage::

        local_engine = FederationPolicyEngine()
        subscriber = FederatedPolicySubscriber(
            local_engine=local_engine,
            local_org="org-alpha",
        )
        sub = subscriber.subscribe(
            publisher_org="org-beta",
            action_filter="cross_border_transfer",
        )

        # Simulate a push from org-beta
        rule = PolicyRule(
            rule_id="beta-001",
            action="cross_border_transfer",
            scope=PolicyScope.FEDERATION,
            decision=PolicyDecision.DENY,
        )
        event = subscriber.process_push_event(
            PolicyPushEvent(
                event_id="evt-001",
                publisher_org="org-beta",
                change_type=PolicyChangeType.RULE_ADDED,
                rule=rule,
            )
        )
        # The rule is now auto-imported into local_engine
    """

    def __init__(
        self,
        local_engine: FederationPolicyEngine,
        local_org: str,
        publisher_public_keys: dict[str, str] | None = None,
    ) -> None:
        self._local_engine = local_engine
        self._local_org = local_org
        self._subscriptions: dict[str, PolicySubscription] = {}
        self._received_events: list[PolicyPushEvent] = []
        self._event_handlers: list[Callable[[PolicyPushEvent], None]] = []
        self._published_rules: dict[str, list[PolicyRule]] = {}
        self._publisher_public_keys: dict[str, str] = dict(publisher_public_keys or {})
        self.unverified_pushes: list[PolicyPushEvent] = []

    def configure_verification(self, publisher_public_keys: dict[str, str]) -> None:
        """Configure the Ed25519 public-key table used to verify policy pushes.

        Once configured (non-empty), every incoming event must carry a valid
        signature from a known publisher org (fail-closed, v0.50 W6-S1 / F8).
        """
        self._publisher_public_keys = dict(publisher_public_keys)

    @property
    def local_engine(self) -> FederationPolicyEngine:
        """The local policy engine that imported rules are applied to."""
        return self._local_engine

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(
        self,
        publisher_org: str,
        action_filter: str = "*",
        trigram_filter: list[str] | None = None,
        auto_import: bool = True,
    ) -> PolicySubscription:
        """Subscribe to policy changes from a remote org.

        Returns the new subscription.
        """
        sub_id = f"sub-{self._local_org}-{publisher_org}-{int(time.time())}"
        existing = self._find_subscription(publisher_org, action_filter)
        if existing is not None:
            return existing

        sub = PolicySubscription(
            subscription_id=sub_id,
            subscriber_org=self._local_org,
            publisher_org=publisher_org,
            action_filter=action_filter,
            trigram_filter=trigram_filter or [],
            auto_import=auto_import,
        )
        self._subscriptions[sub_id] = sub
        return sub

    def unsubscribe(self, subscription_id: str) -> bool:
        """Terminate a subscription."""
        sub = self._subscriptions.get(subscription_id)
        if sub is None:
            return False
        sub.status = SubscriptionStatus.TERMINATED
        # Remove imported rules from local engine
        for rid in sub.imported_rule_ids:
            self._local_engine.remove_rule(rid)
        return True

    def pause_subscription(self, subscription_id: str) -> bool:
        """Pause a subscription (stop auto-importing)."""
        sub = self._subscriptions.get(subscription_id)
        if sub is None:
            return False
        sub.status = SubscriptionStatus.PAUSED
        return True

    def resume_subscription(self, subscription_id: str) -> bool:
        """Resume a paused subscription."""
        sub = self._subscriptions.get(subscription_id)
        if sub is None or sub.status != SubscriptionStatus.PAUSED:
            return False
        sub.status = SubscriptionStatus.ACTIVE
        return True

    def get_subscription(self, subscription_id: str) -> PolicySubscription | None:
        return self._subscriptions.get(subscription_id)

    def list_subscriptions(
        self,
        status: SubscriptionStatus | None = None,
    ) -> list[PolicySubscription]:
        if status is None:
            return list(self._subscriptions.values())
        return [s for s in self._subscriptions.values() if s.status == status]

    def subscription_count(self) -> int:
        return len(self._subscriptions)

    def _find_subscription(
        self,
        publisher_org: str,
        action_filter: str,
    ) -> PolicySubscription | None:
        """Find an existing subscription matching the given criteria."""
        for sub in self._subscriptions.values():
            if (
                sub.publisher_org == publisher_org
                and sub.action_filter == action_filter
                and sub.status != SubscriptionStatus.TERMINATED
            ):
                return sub
        return None

    # ------------------------------------------------------------------
    # Event processing
    # ------------------------------------------------------------------

    def process_push_event(self, event: PolicyPushEvent) -> bool:
        """Process an incoming policy push event.

        Matches the event against active subscriptions and optionally
        imports the rule into the local engine.

        When a publisher public-key table is configured, the event must
        carry a valid Ed25519 signature from a known publisher; otherwise
        the event is rejected and recorded in ``unverified_pushes``
        (fail-closed, v0.50 W6-S1 / F8).

        Returns True if at least one subscription matched.
        """
        if self._publisher_public_keys:
            if not self._verify_push(event):
                self._received_events.append(event)
                self.unverified_pushes.append(event)
                return False

        self._received_events.append(event)
        self._notify_handlers(event)

        matched = False
        for sub in self._subscriptions.values():
            if sub.publisher_org != event.publisher_org:
                continue

            if event.rule is not None and not sub.matches_rule(event.rule):
                continue

            matched = True

            if sub.status != SubscriptionStatus.ACTIVE:
                continue

            matched = True
            sub.last_event_at = time.time()

            if not sub.auto_import:
                continue

            self._apply_event_to_engine(sub, event)

        return matched

    def _apply_event_to_engine(
        self,
        sub: PolicySubscription,
        event: PolicyPushEvent,
    ) -> None:
        """Apply a push event to the local engine for a subscription."""
        if event.change_type == PolicyChangeType.RULE_ADDED and event.rule:
            local_id = f"imported:{event.publisher_org}:{event.rule.rule_id}"
            imported = PolicyRule(
                rule_id=local_id,
                action=event.rule.action,
                scope=PolicyScope.AD_HOC,
                decision=event.rule.decision,
                priority=event.rule.priority,
                conditions=dict(event.rule.conditions),
                description=f"Imported from {event.publisher_org}: {event.rule.description}",
            )
            self._local_engine.add_rule(imported)
            sub.imported_rule_ids.append(local_id)

        elif event.change_type == PolicyChangeType.RULE_REMOVED and event.rule:
            local_id = f"imported:{event.publisher_org}:{event.rule.rule_id}"
            self._local_engine.remove_rule(local_id)
            if local_id in sub.imported_rule_ids:
                sub.imported_rule_ids.remove(local_id)

        elif event.change_type == PolicyChangeType.RULE_UPDATED and event.rule:
            local_id = f"imported:{event.publisher_org}:{event.rule.rule_id}"
            self._local_engine.remove_rule(local_id)
            updated = PolicyRule(
                rule_id=local_id,
                action=event.rule.action,
                scope=PolicyScope.AD_HOC,
                decision=event.rule.decision,
                priority=event.rule.priority,
                conditions=dict(event.rule.conditions),
                description=f"Imported from {event.publisher_org}: {event.rule.description}",
            )
            self._local_engine.add_rule(updated)
            if local_id not in sub.imported_rule_ids:
                sub.imported_rule_ids.append(local_id)

        elif event.change_type == PolicyChangeType.POLICY_CLEARED:
            for rid in list(sub.imported_rule_ids):
                self._local_engine.remove_rule(rid)
            sub.imported_rule_ids.clear()

    # ------------------------------------------------------------------
    # Event verification (v0.50 W6-S1 / F8)
    # ------------------------------------------------------------------

    def _signing_payload(self, event: PolicyPushEvent) -> bytes:
        rule_part = ""
        if event.rule is not None:
            rule_part = (
                f"{event.rule.rule_id}|{event.rule.action}|"
                f"{event.rule.decision.value}|{event.rule.priority}"
            )
        return (
            f"{event.event_id}|{event.publisher_org}|{event.change_type.value}|{rule_part}"
        ).encode()

    def _verify_push(self, event: PolicyPushEvent) -> bool:
        public_key = self._publisher_public_keys.get(event.publisher_org)
        if public_key is None or not event.signature:
            return False
        from maref.signing.signing_key import ReportSigningKey

        return ReportSigningKey.verify_signature(
            public_key, event.signature, self._signing_payload(event)
        )

    def sign_event(
        self, event: PolicyPushEvent, signing_key: Any, publisher_org: str
    ) -> None:
        """Attach an Ed25519 signature to an event on behalf of an org."""
        event.publisher_org = publisher_org
        event.signature = signing_key.sign_report(self._signing_payload(event))

    # ------------------------------------------------------------------
    # Publishing (simulated — real transport uses sidecar/federation_router)
    # ------------------------------------------------------------------

    def publish_rule(
        self,
        rule: PolicyRule,
        publisher_org: str | None = None,
        signing_key: Any | None = None,
    ) -> PolicyPushEvent:
        """Simulate publishing a rule change to subscribers.

        In production, this event would be dispatched via the sidecar's
        federation router. Here it is recorded locally for testing.

        When ``signing_key`` is provided, the event is signed with it
        (v0.50 W6-S1 / F8).

        Returns the generated event.
        """
        org = publisher_org or self._local_org
        event = PolicyPushEvent(
            event_id=f"evt-{org}-{rule.rule_id}-{int(time.time())}",
            publisher_org=org,
            change_type=PolicyChangeType.RULE_ADDED,
            rule=rule,
        )
        if signing_key is not None:
            self.sign_event(event, signing_key, org)
        if org not in self._published_rules:
            self._published_rules[org] = []
        self._published_rules[org].append(rule)
        self._received_events.append(event)
        return event

    def publish_rule_removal(
        self,
        rule_id: str,
        publisher_org: str | None = None,
    ) -> PolicyPushEvent | None:
        """Simulate publishing a rule removal."""
        org = publisher_org or self._local_org
        rules = self._published_rules.get(org, [])
        rule = next((r for r in rules if r.rule_id == rule_id), None)
        if rule is None:
            return None
        rules.remove(rule)
        event = PolicyPushEvent(
            event_id=f"evt-{org}-del-{rule_id}-{int(time.time())}",
            publisher_org=org,
            change_type=PolicyChangeType.RULE_REMOVED,
            rule=rule,
        )
        self._received_events.append(event)
        return event

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def add_event_handler(
        self, handler: Callable[[PolicyPushEvent], None]
    ) -> None:
        """Register a callback for incoming push events."""
        self._event_handlers.append(handler)

    def _notify_handlers(self, event: PolicyPushEvent) -> None:
        for handler in self._event_handlers:
            handler(event)

    # ------------------------------------------------------------------
    # Drift detection
    # ------------------------------------------------------------------

    def detect_policy_drift(
        self,
        publisher_org: str,
    ) -> list[dict[str, Any]]:
        """Detect differences between published and imported rules.

        Compares the local engine's imported rules against the last
        known published state from a remote org.
        """
        published = self._published_rules.get(publisher_org, [])
        imported = [
            r
            for r in self._local_engine.list_rules()
            if r.rule_id.startswith(f"imported:{publisher_org}:")
        ]
        drift: list[dict[str, Any]] = []
        for pub in published:
            local_id = f"imported:{publisher_org}:{pub.rule_id}"
            imported_rule = next(
                (r for r in imported if r.rule_id == local_id), None
            )
            if imported_rule is None:
                drift.append({
                    "rule_id": pub.rule_id,
                    "issue": "missing_import",
                    "published_decision": pub.decision.value,
                })
            elif imported_rule.decision != pub.decision:
                drift.append({
                    "rule_id": pub.rule_id,
                    "issue": "decision_mismatch",
                    "published_decision": pub.decision.value,
                    "local_decision": imported_rule.decision.value,
                })
        return drift

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_received_events(
        self,
        publisher_org: str | None = None,
        limit: int = 50,
    ) -> list[PolicyPushEvent]:
        """Return received events, optionally filtered by publisher."""
        events = self._received_events
        if publisher_org:
            events = [e for e in events if e.publisher_org == publisher_org]
        return events[-limit:]

    def get_published_rules(
        self,
        org_id: str | None = None,
    ) -> dict[str, list[PolicyRule]]:
        if org_id:
            return {org_id: list(self._published_rules.get(org_id, []))}
        return {k: list(v) for k, v in self._published_rules.items()}

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def subscriber_summary(self) -> dict[str, Any]:
        """Return a summary of the subscriber state."""
        active = sum(
            1 for s in self._subscriptions.values()
            if s.status == SubscriptionStatus.ACTIVE
        )
        imported_count = sum(
            len(s.imported_rule_ids) for s in self._subscriptions.values()
        )
        return {
            "local_org": self._local_org,
            "total_subscriptions": len(self._subscriptions),
            "active_subscriptions": active,
            "total_received_events": len(self._received_events),
            "total_imported_rules": imported_count,
            "published_orgs": list(self._published_rules.keys()),
        }
