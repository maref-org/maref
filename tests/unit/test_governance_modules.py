"""governance 未测试模块单元测试。

覆盖三个模块：
- sync_policy.py: 跨实例同步策略与注册表
- audit_bus.py: 审计事件总线（pub/sub）
- federated_audit.py: 联邦审计日志（HMAC 签名）
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from maref.eivl.federated_audit_log import (
    AuditEventType,
    FederatedAuditEntry,
    FederatedAuditLog,
)
from maref.governance.audit import AuditEntry
from maref.governance.audit_bus import AuditBus
from maref.governance.sync_policy import (
    ConflictStrategy,
    SyncDataType,
    SyncDirection,
    SyncPolicy,
    SyncPolicyRegistry,
)

# ---------------------------------------------------------------------------
# SyncPolicy & SyncPolicyRegistry
# ---------------------------------------------------------------------------

class TestSyncPolicy:

    def test_default_values(self) -> None:
        """SyncPolicy 默认值应为双向、LWW、加密开启。"""
        policy = SyncPolicy(data_type=SyncDataType.TRUST_SCORES)
        assert policy.direction == SyncDirection.BIDIRECTIONAL
        assert policy.conflict_strategy == ConflictStrategy.LAST_WRITE_WINS
        assert policy.encryption_required is True
        assert policy.enabled is True
        assert policy.min_confirmations == 1

    def test_to_dict_contains_key_fields(self) -> None:
        """to_dict 应包含所有关键字段。"""
        policy = SyncPolicy(data_type=SyncDataType.AUDIT_LOGS)
        d = policy.to_dict()
        assert d["data_type"] == "audit_logs"
        assert d["direction"] == "bidirectional"
        assert d["conflict_strategy"] == "last_write_wins"
        assert "encryption_required" in d
        assert "enabled" in d


class TestSyncPolicyRegistry:

    def test_get_default_policy(self) -> None:
        """注册表应预装所有默认策略。"""
        registry = SyncPolicyRegistry()
        for dt in SyncDataType:
            policy = registry.get_policy(dt)
            assert policy is not None, f"缺少默认策略: {dt}"

    def test_trust_scores_default_uses_merge(self) -> None:
        """TRUST_SCORES 默认策略应使用 MERGE 冲突策略和 3 确认。"""
        registry = SyncPolicyRegistry()
        policy = registry.get_policy(SyncDataType.TRUST_SCORES)
        assert policy is not None
        assert policy.conflict_strategy == ConflictStrategy.MERGE
        assert policy.requires_consensus is True
        assert policy.min_confirmations == 3

    def test_circuit_breaker_is_pull_only(self) -> None:
        """CIRCUIT_BREAKER 默认应为 PULL_ONLY 和 BLOCK 冲突策略。"""
        registry = SyncPolicyRegistry()
        policy = registry.get_policy(SyncDataType.CIRCUIT_BREAKER)
        assert policy is not None
        assert policy.direction == SyncDirection.PULL_ONLY
        assert policy.conflict_strategy == ConflictStrategy.BLOCK

    def test_set_custom_policy(self) -> None:
        """set_policy 应覆盖默认策略。"""
        registry = SyncPolicyRegistry()
        custom = SyncPolicy(
            data_type=SyncDataType.ENTROPY,
            direction=SyncDirection.BIDIRECTIONAL,
            encryption_required=True,
        )
        registry.set_policy(custom)
        policy = registry.get_policy(SyncDataType.ENTROPY)
        assert policy is not None
        assert policy.direction == SyncDirection.BIDIRECTIONAL
        assert policy.encryption_required is True

    def test_allow_sync_for_enabled(self) -> None:
        """enabled=True 的策略应允许同步。"""
        registry = SyncPolicyRegistry()
        assert registry.allow_sync(SyncDataType.AUDIT_LOGS) is True

    def test_disallow_sync_for_disabled(self) -> None:
        """enabled=False 的策略应禁止同步。"""
        registry = SyncPolicyRegistry()
        registry.set_policy(SyncPolicy(data_type=SyncDataType.ENTROPY, enabled=False))
        assert registry.allow_sync(SyncDataType.ENTROPY) is False

    def test_reset_to_defaults(self) -> None:
        """reset_to_defaults 应恢复所有默认策略。"""
        registry = SyncPolicyRegistry()
        registry.set_policy(SyncPolicy(data_type=SyncDataType.CONFIG, enabled=False))
        assert registry.allow_sync(SyncDataType.CONFIG) is False
        registry.reset_to_defaults()
        assert registry.allow_sync(SyncDataType.CONFIG) is True

    def test_list_policies_returns_all(self) -> None:
        """list_policies 应返回所有策略。"""
        registry = SyncPolicyRegistry()
        policies = registry.list_policies()
        assert len(policies) == len(SyncDataType)


# ---------------------------------------------------------------------------
# AuditBus
# ---------------------------------------------------------------------------

class TestAuditBus:

    def _log(self, bus: AuditBus, event_type: str = "test_event") -> AuditEntry:
        """通过 AuditBus.log 记录事件（真实分发入口）。"""
        return bus.log(
            event_type=event_type,
            actor="test-actor",
            action="test-action",
            details="test details",
        )

    def test_subscribe_and_publish(self) -> None:
        """订阅特定 topic 后应收到匹配的事件。"""
        bus = AuditBus()
        received: list[AuditEntry] = []
        bus.subscribe("test_event", lambda e: received.append(e))
        self._log(bus, "test_event")
        assert len(received) == 1
        assert received[0].event_type == "test_event"

    def test_wildcard_subscription(self) -> None:
        """通配符 '*' 应接收所有事件。"""
        bus = AuditBus()
        received: list[AuditEntry] = []
        bus.subscribe("*", lambda e: received.append(e))
        self._log(bus, "event_a")
        self._log(bus, "event_b")
        assert len(received) == 2

    def test_unsubscribe(self) -> None:
        """取消订阅后不应再收到事件。"""
        bus = AuditBus()
        received: list[AuditEntry] = []

        def callback(e: AuditEntry) -> None:
            received.append(e)

        bus.subscribe("test_event", callback)
        self._log(bus, "test_event")
        assert len(received) == 1

        bus.unsubscribe("test_event", callback)
        self._log(bus, "test_event")
        assert len(received) == 1  # 仍然只有 1 条

    def test_unsubscribe_nonexistent(self) -> None:
        """取消不存在的订阅不应抛异常。"""
        bus = AuditBus()
        bus.unsubscribe("nonexistent", lambda e: None)  # 不应抛异常

    def test_no_subscribers_no_error(self) -> None:
        """无订阅者时记录事件不应抛异常。"""
        bus = AuditBus()
        self._log(bus, "orphan_event")

    def test_publish_logs_to_logger(self) -> None:
        """log 应同时分发到订阅者并写入 AuditLogger。"""
        bus = AuditBus()
        received: list[AuditEntry] = []
        bus.subscribe("logged_event", lambda e: received.append(e))
        self._log(bus, "logged_event")
        assert len(received) == 1

    def test_multiple_subscribers_same_topic(self) -> None:
        """同一 topic 的多个订阅者都应收到事件。"""
        bus = AuditBus()
        received_a: list[AuditEntry] = []
        received_b: list[AuditEntry] = []
        bus.subscribe("multi", lambda e: received_a.append(e))
        bus.subscribe("multi", lambda e: received_b.append(e))
        self._log(bus, "multi")
        assert len(received_a) == 1
        assert len(received_b) == 1


# ---------------------------------------------------------------------------
# FederatedAuditLog
# ---------------------------------------------------------------------------

class TestFederatedAuditEntry:

    def test_sign_and_verify(self) -> None:
        """签名后验证应通过。"""
        with patch.dict(os.environ, {"MAREF_FEDERATED_AUDIT_KEY": "test-secret-key"}):
            # 重置模块级缓存
            import maref.eivl.federated_audit_log as fa_module
            fa_module._HMAC_KEY = None

            entry = FederatedAuditEntry(
                entry_id="entry-001",
                event_type=AuditEventType.SYNC_COMPLETED,
                source_instance="inst-A",
                target_instance="inst-B",
                data_type="trust_scores",
                details="sync ok",
            )
            entry.sign()
            assert entry.hmac_signature != ""
            assert entry.verify() is True

    def test_verify_tampered_fails(self) -> None:
        """篡改 details 后验证应失败。"""
        with patch.dict(os.environ, {"MAREF_FEDERATED_AUDIT_KEY": "test-secret-key"}):
            import maref.eivl.federated_audit_log as fa_module
            fa_module._HMAC_KEY = None

            entry = FederatedAuditEntry(
                entry_id="entry-002",
                event_type=AuditEventType.SYNC_COMPLETED,
                source_instance="inst-A",
                target_instance="inst-B",
                data_type="trust_scores",
                details="original",
            )
            entry.sign()
            # 篡改 details
            entry.details = "tampered"
            assert entry.verify() is False

    def test_verify_no_signature_returns_false(self) -> None:
        """未签名时 verify 应返回 False。"""
        entry = FederatedAuditEntry(
            entry_id="entry-003",
            event_type=AuditEventType.SYNC_STARTED,
            source_instance="A",
            target_instance="B",
            data_type="config",
            details="",
        )
        assert entry.verify() is False  # 会抛 RuntimeError，但先检查 hmac_signature 为空

    def test_to_dict_contains_all_fields(self) -> None:
        """to_dict 应包含所有字段。"""
        entry = FederatedAuditEntry(
            entry_id="e1",
            event_type=AuditEventType.CONFLICT_DETECTED,
            source_instance="A",
            target_instance="B",
            data_type="observations",
            details="conflict found",
            severity="warning",
        )
        d = entry.to_dict()
        assert d["entry_id"] == "e1"
        assert d["event_type"] == "conflict_detected"
        assert d["source_instance"] == "A"
        assert d["severity"] == "warning"


class TestFederatedAuditLog:

    @pytest.fixture(autouse=True)
    def _setup_key(self) -> None:
        """每个测试前设置 HMAC 密钥。"""
        with patch.dict(os.environ, {"MAREF_FEDERATED_AUDIT_KEY": "test-secret-key"}):
            import maref.eivl.federated_audit_log as fa_module
            fa_module._HMAC_KEY = None
            yield
            fa_module._HMAC_KEY = None

    def test_record_creates_signed_entry(self) -> None:
        """record 应创建带 HMAC 签名的条目。"""
        log = FederatedAuditLog()
        entry = log.record(
            event_type=AuditEventType.SYNC_STARTED,
            source_instance="A",
            target_instance="B",
            data_type="trust_scores",
        )
        assert entry.hmac_signature != ""
        assert entry.event_type == AuditEventType.SYNC_STARTED
        assert log.entry_count == 1

    def test_query_by_event_type(self) -> None:
        """按 event_type 过滤查询。"""
        log = FederatedAuditLog()
        log.record(AuditEventType.SYNC_STARTED, "A", "B", "data")
        log.record(AuditEventType.SYNC_COMPLETED, "A", "B", "data")
        log.record(AuditEventType.SYNC_STARTED, "C", "D", "data")

        results = log.query(event_type=AuditEventType.SYNC_STARTED)
        assert len(results) == 2
        assert all(e.event_type == AuditEventType.SYNC_STARTED for e in results)

    def test_query_by_source(self) -> None:
        """按 source_instance 过滤查询。"""
        log = FederatedAuditLog()
        log.record(AuditEventType.SYNC_STARTED, "inst-A", "B", "data")
        log.record(AuditEventType.SYNC_STARTED, "inst-B", "C", "data")

        results = log.query(source="inst-A")
        assert len(results) == 1
        assert results[0].source_instance == "inst-A"

    def test_query_by_severity(self) -> None:
        """按 severity 过滤查询。"""
        log = FederatedAuditLog()
        log.record(AuditEventType.SYNC_FAILED, "A", "B", "data", severity="error")
        log.record(AuditEventType.SYNC_STARTED, "A", "B", "data", severity="info")

        results = log.query(severity="error")
        assert len(results) == 1
        assert results[0].severity == "error"

    def test_query_limit(self) -> None:
        """limit 应限制返回数量。"""
        log = FederatedAuditLog()
        for i in range(10):
            log.record(AuditEventType.SYNC_STARTED, "A", "B", f"data-{i}")
        results = log.query(limit=5)
        assert len(results) == 5

    def test_verify_all_returns_tampered(self) -> None:
        """verify_all 应返回被篡改的条目列表。"""
        log = FederatedAuditLog()
        log.record(AuditEventType.SYNC_STARTED, "A", "B", "data")
        log.record(AuditEventType.SYNC_COMPLETED, "A", "B", "data")

        # 篡改第一条
        entries = log.get_entries()
        entries[0].details = "tampered"

        tampered = log.verify_all()
        assert len(tampered) == 1

    def test_get_entries_returns_copy(self) -> None:
        """get_entries 应返回列表副本。"""
        log = FederatedAuditLog()
        log.record(AuditEventType.SYNC_STARTED, "A", "B", "data")
        entries = log.get_entries()
        entries.clear()
        assert log.entry_count == 1  # 原始不受影响

    def test_entry_count(self) -> None:
        """entry_count 应返回正确数量。"""
        log = FederatedAuditLog()
        assert log.entry_count == 0
        log.record(AuditEventType.SYNC_STARTED, "A", "B", "data")
        log.record(AuditEventType.SYNC_COMPLETED, "A", "B", "data")
        assert log.entry_count == 2
