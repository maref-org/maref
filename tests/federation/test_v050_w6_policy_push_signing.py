"""
v0.50 W6-S1 — F8 policy push 事件级验签

覆盖：
- 订阅器配置 publisher 公钥表后，未签名事件被拒绝 + 审计 unverified_policy_push
- 签名被篡改 → 拒绝
- 合法签名事件被接受并导入
- publish_rule 带 signing_key 时事件携带签名
- 未配置公钥表时保持旧行为（向后兼容）
"""

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
)
from maref.signing.signing_key import ReportSigningKey


def _make_rule() -> PolicyRule:
    return PolicyRule(
        rule_id="beta-001",
        action="cross_border_transfer",
        scope=PolicyScope.FEDERATION,
        decision=PolicyDecision.DENY,
    )


class TestW6PolicyPushSigning:
    def test_unconfigured_keeps_legacy_behavior(self) -> None:
        sub = FederatedPolicySubscriber(
            local_engine=FederationPolicyEngine(), local_org="org-alpha"
        )
        sub.subscribe(publisher_org="org-beta", action_filter="cross_border_transfer")
        event = PolicyPushEvent(
            event_id="evt-1",
            publisher_org="org-beta",
            change_type=PolicyChangeType.RULE_ADDED,
            rule=_make_rule(),
        )
        assert sub.process_push_event(event) is True

    def test_unsigned_event_rejected_when_key_configured(self) -> None:
        key = ReportSigningKey.generate()
        sub = FederatedPolicySubscriber(
            local_engine=FederationPolicyEngine(), local_org="org-alpha"
        )
        sub.configure_verification({"org-beta": key.public_key_pem})
        sub.subscribe(publisher_org="org-beta", action_filter="cross_border_transfer")
        event = PolicyPushEvent(
            event_id="evt-1",
            publisher_org="org-beta",
            change_type=PolicyChangeType.RULE_ADDED,
            rule=_make_rule(),
        )
        assert sub.process_push_event(event) is False
        assert len(sub.unverified_pushes) == 1
        assert sub.unverified_pushes[0].event_id == "evt-1"

    def test_unknown_publisher_rejected(self) -> None:
        key = ReportSigningKey.generate()
        sub = FederatedPolicySubscriber(
            local_engine=FederationPolicyEngine(), local_org="org-alpha"
        )
        sub.configure_verification({"org-beta": key.public_key_pem})
        sub.subscribe(publisher_org="org-unknown", action_filter="*")
        event = PolicyPushEvent(
            event_id="evt-x",
            publisher_org="org-unknown",
            change_type=PolicyChangeType.RULE_ADDED,
            rule=_make_rule(),
        )
        assert sub.process_push_event(event) is False

    def test_tampered_signature_rejected(self) -> None:
        key = ReportSigningKey.generate()
        sub = FederatedPolicySubscriber(
            local_engine=FederationPolicyEngine(), local_org="org-alpha"
        )
        sub.configure_verification({"org-beta": key.public_key_pem})
        sub.subscribe(publisher_org="org-beta", action_filter="cross_border_transfer")

        publisher = FederatedPolicySubscriber(
            local_engine=FederationPolicyEngine(), local_org="org-beta"
        )
        event = publisher.publish_rule(_make_rule(), publisher_org="org-beta", signing_key=key)
        event.rule = PolicyRule(
            rule_id="beta-999",  # tamper after signing → payload mismatch
            action="cross_border_transfer",
            scope=PolicyScope.FEDERATION,
            decision=PolicyDecision.ALLOW,
        )
        assert sub.process_push_event(event) is False
        assert len(sub.unverified_pushes) == 1

    def test_valid_signed_event_accepted(self) -> None:
        key = ReportSigningKey.generate()
        sub = FederatedPolicySubscriber(
            local_engine=FederationPolicyEngine(), local_org="org-alpha"
        )
        sub.configure_verification({"org-beta": key.public_key_pem})
        sub.subscribe(publisher_org="org-beta", action_filter="cross_border_transfer")

        publisher = FederatedPolicySubscriber(
            local_engine=FederationPolicyEngine(), local_org="org-beta"
        )
        event = publisher.publish_rule(_make_rule(), publisher_org="org-beta", signing_key=key)
        assert event.signature != ""
        assert sub.process_push_event(event) is True
        assert sub.unverified_pushes == []
        imported = sub.local_engine._adhoc_rules.get("imported:org-beta:beta-001")
        assert imported is not None

    def test_publish_without_key_leaves_signature_empty(self) -> None:
        publisher = FederatedPolicySubscriber(
            local_engine=FederationPolicyEngine(), local_org="org-beta"
        )
        event = publisher.publish_rule(_make_rule(), publisher_org="org-beta")
        assert event.signature == ""
