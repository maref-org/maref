"""test_event — ObservationEvent + HMAC 签名测试

覆盖验收标准:
- 1.1-A7: ObservationEvent.hash = HMAC-SHA256(event_id+ts+subject+evidence)
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from maref.sentinel.event import (
    AttackType,
    ObservationEvent,
    Severity,
    compute_event_hash,
    verify_event_hash,
)

HMAC_KEY: bytes = b"test-hmac-key-for-sentinel-events"


class TestObservationEventSchema:
    """ObservationEvent schema 测试"""

    def test_event_creation_defaults(self) -> None:
        """事件创建 — 默认值"""
        event = ObservationEvent()
        assert event.event_id  # UUID auto-generated
        assert event.ts > 0
        assert event.severity == Severity.LOW
        assert event.attack_type == AttackType.NONE
        assert event.evidence == {}
        assert event.hash == ""

    def test_event_creation_with_values(self) -> None:
        """事件创建 — 指定值"""
        event = ObservationEvent(
            source="process",
            severity=Severity.CRITICAL,
            subject="pid:1234",
            attack_type=AttackType.PRIVILEGE_ABUSE,
            evidence={"detection": "ptrace", "tracer_pid": 999},
        )
        assert event.source == "process"
        assert event.severity == Severity.CRITICAL
        assert event.subject == "pid:1234"
        assert event.attack_type == AttackType.PRIVILEGE_ABUSE
        assert event.evidence["tracer_pid"] == 999

    def test_event_frozen(self) -> None:
        """事件不可变 — frozen=True"""
        event = ObservationEvent(source="test")
        with pytest.raises(AttributeError):
            event.source = "modified"  # type: ignore[misc]

    def test_severity_enum_values(self) -> None:
        """Severity 枚举值"""
        assert Severity.CRITICAL.value == "CRITICAL"
        assert Severity.HIGH.value == "HIGH"
        assert Severity.MEDIUM.value == "MEDIUM"
        assert Severity.LOW.value == "LOW"

    def test_attack_type_enum_values(self) -> None:
        """AttackType 枚举值 — 5 类攻击 + none"""
        assert AttackType.PIXEL_TRACKING.value == "pixel_tracking"
        assert AttackType.SILENT_TIMEZONE.value == "silent_timezone"
        assert AttackType.ENV_EXFIL.value == "env_exfil"
        assert AttackType.STEGANOGRAPHY.value == "steganography"
        assert AttackType.PRIVILEGE_ABUSE.value == "privilege_abuse"
        assert AttackType.NONE.value == "none"


class TestHMACSignature:
    """HMAC-SHA256 签名测试 — 覆盖 1.1-A7"""

    def test_compute_event_hash_format(self) -> None:
        """hash 计算格式: HMAC-SHA256(event_id|ts|subject|evidence_json)"""
        event = ObservationEvent(
            event_id="test-id-123",
            ts=1234567890.123456,
            subject="pid:999",
            evidence={"key": "value", "num": 42},
        )
        h = compute_event_hash(event, HMAC_KEY)
        # HMAC-SHA256 输出 64 字符十六进制
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_compute_event_hash_deterministic(self) -> None:
        """相同输入 → 相同 hash (确定性)"""
        event = ObservationEvent(
            event_id="test-id-123",
            ts=1234567890.123456,
            subject="pid:999",
            evidence={"key": "value"},
        )
        h1 = compute_event_hash(event, HMAC_KEY)
        h2 = compute_event_hash(event, HMAC_KEY)
        assert h1 == h2

    def test_compute_event_hash_manual_verification(self) -> None:
        """手动验证 — 确认 payload 格式正确"""
        event = ObservationEvent(
            event_id="abc",
            ts=100.0,
            subject="pid:1",
            evidence={"x": 1},
        )
        # 手动计算
        payload = f"abc|{100.0:.6f}|pid:1|{json.dumps({'x': 1}, sort_keys=True)}"
        expected = hmac.new(HMAC_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        actual = compute_event_hash(event, HMAC_KEY)
        assert actual == expected

    def test_verify_event_hash_valid(self) -> None:
        """验证签名 — 有效签名返回 True"""
        event = ObservationEvent(
            event_id="test-id",
            ts=123.0,
            subject="pid:1",
            evidence={"detection": "ptrace"},
        )
        signed = event.with_hash(HMAC_KEY)
        assert verify_event_hash(signed, HMAC_KEY) is True

    def test_verify_event_hash_tamper_event_id(self) -> None:
        """篡改 event_id → 验证失败"""
        event = ObservationEvent(
            event_id="original",
            ts=123.0,
            subject="pid:1",
            evidence={"detection": "ptrace"},
        )
        signed = event.with_hash(HMAC_KEY)
        # 创建篡改版本 (event_id 变了但 hash 不变)
        tampered = ObservationEvent(
            event_id="tampered",
            ts=signed.ts,
            source=signed.source,
            severity=signed.severity,
            subject=signed.subject,
            attack_type=signed.attack_type,
            evidence=signed.evidence,
            hash=signed.hash,
        )
        assert verify_event_hash(tampered, HMAC_KEY) is False

    def test_verify_event_hash_tamper_subject(self) -> None:
        """篡改 subject → 验证失败"""
        event = ObservationEvent(
            event_id="test-id",
            ts=123.0,
            subject="pid:1",
            evidence={"detection": "ptrace"},
        )
        signed = event.with_hash(HMAC_KEY)
        tampered = ObservationEvent(
            event_id=signed.event_id,
            ts=signed.ts,
            source=signed.source,
            severity=signed.severity,
            subject="pid:999",  # 篡改
            attack_type=signed.attack_type,
            evidence=signed.evidence,
            hash=signed.hash,
        )
        assert verify_event_hash(tampered, HMAC_KEY) is False

    def test_verify_event_hash_tamper_evidence(self) -> None:
        """篡改 evidence → 验证失败"""
        event = ObservationEvent(
            event_id="test-id",
            ts=123.0,
            subject="pid:1",
            evidence={"detection": "ptrace", "tracer_pid": 0},
        )
        signed = event.with_hash(HMAC_KEY)
        tampered = ObservationEvent(
            event_id=signed.event_id,
            ts=signed.ts,
            source=signed.source,
            severity=signed.severity,
            subject=signed.subject,
            attack_type=signed.attack_type,
            evidence={"detection": "ptrace", "tracer_pid": 999},  # 篡改
            hash=signed.hash,
        )
        assert verify_event_hash(tampered, HMAC_KEY) is False

    def test_verify_event_hash_empty_hash(self) -> None:
        """空 hash → 验证失败"""
        event = ObservationEvent(hash="")
        assert verify_event_hash(event, HMAC_KEY) is False

    def test_with_hash_returns_new_event(self) -> None:
        """with_hash() 返回新事件 (不修改原事件)"""
        event = ObservationEvent(event_id="test", ts=1.0, subject="pid:1")
        signed = event.with_hash(HMAC_KEY)
        assert event.hash == ""  # 原事件不变
        assert signed.hash != ""  # 新事件有 hash
        assert signed.event_id == event.event_id

    def test_different_keys_different_hash(self) -> None:
        """不同 HMAC key → 不同 hash"""
        event = ObservationEvent(event_id="test", ts=1.0, subject="pid:1")
        h1 = compute_event_hash(event, b"key1")
        h2 = compute_event_hash(event, b"key2")
        assert h1 != h2
