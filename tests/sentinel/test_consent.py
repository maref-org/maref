"""test_consent — JustInTimeConsent 用户即时同意协议测试

覆盖验收标准:
- 1.3-A4: JustInTimeConsent 对未获同意的高权限操作阻断率 100%
- 1.3-A6: 同意决策写入审计日志 (HMAC 签名)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from maref.sentinel.consent import (
    CONSENT_OPERATIONS,
    ConsentDecision,
    ConsentOutcome,
    JustInTimeConsent,
    compute_consent_hash,
)

pytestmark = pytest.mark.asyncio

HMAC_KEY: bytes = b"test-consent-hmac-key"

# 测试用操作名
OP_CA_INSTALL = "sentinel.mitmproxy.ca_install"
OP_PTRACE = "sentinel.process.ptrace"
OP_LD_PRELOAD = "sentinel.process.ld_preload"


class TestConsentDecision:
    """ConsentDecision 数据类 + HMAC 测试"""

    def test_default_values(self) -> None:
        d = ConsentDecision(operation=OP_CA_INSTALL)
        assert d.decision_id  # UUID
        assert d.outcome == ConsentOutcome.DENIED  # 默认拒绝
        assert d.operation == OP_CA_INSTALL
        assert d.hmac_signature == ""

    def test_with_hash_returns_new_instance(self) -> None:
        d = ConsentDecision(operation=OP_CA_INSTALL, outcome=ConsentOutcome.GRANTED)
        signed = d.with_hash(HMAC_KEY)
        assert signed is not d
        assert signed.operation == OP_CA_INSTALL
        assert signed.hmac_signature != ""

    def test_verify_valid_signature(self) -> None:
        d = ConsentDecision(
            operation=OP_CA_INSTALL, outcome=ConsentOutcome.GRANTED
        ).with_hash(HMAC_KEY)
        assert d.verify(HMAC_KEY) is True

    def test_verify_no_signature_returns_false(self) -> None:
        d = ConsentDecision(operation=OP_CA_INSTALL)
        assert d.verify(HMAC_KEY) is False

    def test_verify_tampered_returns_false(self) -> None:
        d = ConsentDecision(
            operation=OP_CA_INSTALL, outcome=ConsentOutcome.GRANTED
        ).with_hash(HMAC_KEY)
        from dataclasses import replace

        tampered = replace(d, outcome=ConsentOutcome.DENIED)
        assert tampered.verify(HMAC_KEY) is False

    def test_is_granted_property(self) -> None:
        assert ConsentDecision(outcome=ConsentOutcome.GRANTED).is_granted is True
        assert ConsentDecision(outcome=ConsentOutcome.DENIED).is_granted is False

    def test_is_active_granted_no_ttl(self) -> None:
        """单次 GRANTED (ttl=0) is_active=True"""
        d = ConsentDecision(
            outcome=ConsentOutcome.GRANTED, ttl=0.0, expires_at=0.0
        )
        assert d.is_active is True

    def test_is_active_granted_with_ttl_not_expired(self) -> None:
        """TTL GRANTED 未过期 is_active=True"""
        d = ConsentDecision(
            outcome=ConsentOutcome.GRANTED,
            ttl=3600.0,
            expires_at=time.time() + 1800,
        )
        assert d.is_active is True

    def test_is_active_granted_expired(self) -> None:
        """TTL GRANTED 已过期 is_active=False"""
        d = ConsentDecision(
            outcome=ConsentOutcome.GRANTED,
            ttl=3600.0,
            expires_at=time.time() - 100,  # 已过期
        )
        assert d.is_active is False

    def test_is_active_denied(self) -> None:
        d = ConsentDecision(outcome=ConsentOutcome.DENIED)
        assert d.is_active is False

    def test_compute_hash_deterministic(self) -> None:
        d1 = ConsentDecision(
            decision_id="d-1", operation=OP_CA_INSTALL,
            outcome=ConsentOutcome.GRANTED, subject="probe",
            decided_at=1000.0,
        )
        d2 = ConsentDecision(
            decision_id="d-1", operation=OP_CA_INSTALL,
            outcome=ConsentOutcome.GRANTED, subject="probe",
            decided_at=1000.0,
        )
        assert compute_consent_hash(d1, HMAC_KEY) == compute_consent_hash(d2, HMAC_KEY)


class TestJustInTimeConsentNoCallback:
    """无 consent_callback — 1.3-A4: 100% 阻断"""

    async def test_no_callback_denies(self) -> None:
        consent = JustInTimeConsent(hmac_key=HMAC_KEY)
        decision = await consent.request(
            operation=OP_CA_INSTALL, subject="network_egress_probe"
        )
        assert decision.outcome == ConsentOutcome.DENIED_NO_CALLBACK
        assert decision.is_granted is False
        assert decision.verify(HMAC_KEY) is True

    async def test_no_callback_records_reason(self) -> None:
        consent = JustInTimeConsent(hmac_key=HMAC_KEY)
        decision = await consent.request(operation=OP_CA_INSTALL)
        assert "no consent_callback" in decision.reason
        assert "deny by default" in decision.reason

    async def test_no_callback_blocks_all_operations(self) -> None:
        """1.3-A4: 无 callback 时所有操作都被阻断"""
        consent = JustInTimeConsent(hmac_key=HMAC_KEY)
        for op in CONSENT_OPERATIONS:
            decision = await consent.request(operation=op)
            assert decision.is_granted is False, f"{op} should be blocked"


class TestJustInTimeConsentGranted:
    """consent_callback 返回 True (同意)"""

    async def test_sync_callback_grants(self) -> None:
        def cb(op: str, ctx: dict) -> bool:
            return True

        consent = JustInTimeConsent(hmac_key=HMAC_KEY, consent_callback=cb)
        decision = await consent.request(operation=OP_CA_INSTALL)
        assert decision.outcome == ConsentOutcome.GRANTED
        assert decision.is_granted is True
        assert decision.verify(HMAC_KEY) is True

    async def test_async_callback_grants(self) -> None:
        async def cb(op: str, ctx: dict) -> bool:
            await asyncio.sleep(0.001)
            return True

        consent = JustInTimeConsent(hmac_key=HMAC_KEY, consent_callback=cb)
        decision = await consent.request(operation=OP_CA_INSTALL)
        assert decision.outcome == ConsentOutcome.GRANTED

    async def test_granted_decision_has_user_granted_reason(self) -> None:
        def cb(op: str, ctx: dict) -> bool:
            return True

        consent = JustInTimeConsent(hmac_key=HMAC_KEY, consent_callback=cb)
        decision = await consent.request(operation=OP_CA_INSTALL)
        assert decision.reason == "user_granted"


class TestJustInTimeConsentDenied:
    """consent_callback 返回 False (拒绝) — 1.3-A4"""

    async def test_sync_callback_denies(self) -> None:
        def cb(op: str, ctx: dict) -> bool:
            return False

        consent = JustInTimeConsent(hmac_key=HMAC_KEY, consent_callback=cb)
        decision = await consent.request(operation=OP_CA_INSTALL)
        assert decision.outcome == ConsentOutcome.DENIED
        assert decision.is_granted is False
        assert decision.reason == "user_denied"

    async def test_async_callback_denies(self) -> None:
        async def cb(op: str, ctx: dict) -> bool:
            return False

        consent = JustInTimeConsent(hmac_key=HMAC_KEY, consent_callback=cb)
        decision = await consent.request(operation=OP_CA_INSTALL)
        assert decision.outcome == ConsentOutcome.DENIED

    async def test_user_denial_blocks_all_high_priv_ops(self) -> None:
        """1.3-A4: 用户拒绝时所有高权限操作被阻断"""
        def cb(op: str, ctx: dict) -> bool:
            return False

        consent = JustInTimeConsent(hmac_key=HMAC_KEY, consent_callback=cb)
        for op in CONSENT_OPERATIONS:
            decision = await consent.request(operation=op)
            assert decision.is_granted is False, f"{op} should be blocked"


class TestJustInTimeConsentError:
    """consent_callback 抛异常 — 1.3-A4: 100% 阻断"""

    async def test_callback_exception_denies(self) -> None:
        def cb(op: str, ctx: dict) -> bool:
            raise RuntimeError("UI crashed")

        consent = JustInTimeConsent(hmac_key=HMAC_KEY, consent_callback=cb)
        decision = await consent.request(operation=OP_CA_INSTALL)
        assert decision.outcome == ConsentOutcome.DENIED_ERROR
        assert decision.is_granted is False
        assert "RuntimeError" in decision.reason
        assert "UI crashed" in decision.reason

    async def test_async_callback_exception_denies(self) -> None:
        async def cb(op: str, ctx: dict) -> bool:
            raise ValueError("async UI error")

        consent = JustInTimeConsent(hmac_key=HMAC_KEY, consent_callback=cb)
        decision = await consent.request(operation=OP_CA_INSTALL)
        assert decision.outcome == ConsentOutcome.DENIED_ERROR
        assert "ValueError" in decision.reason


class TestJustInTimeConsentTTL:
    """TTL 缓存复用测试"""

    async def test_ttl_cached_decision_reused(self) -> None:
        call_count = [0]

        def cb(op: str, ctx: dict) -> bool:
            call_count[0] += 1
            return True

        consent = JustInTimeConsent(
            hmac_key=HMAC_KEY, consent_callback=cb, default_ttl=3600.0
        )
        d1 = await consent.request(operation=OP_CA_INSTALL)
        d2 = await consent.request(operation=OP_CA_INSTALL)

        # callback 只调一次 (第二次复用缓存)
        assert call_count[0] == 1
        assert d1.outcome == ConsentOutcome.GRANTED
        assert d2.outcome == ConsentOutcome.GRANTED
        assert "reused_from" in d2.context
        assert d2.context["reused_from"] == d1.decision_id

    async def test_no_ttl_no_cache(self) -> None:
        """ttl=0 时每次都调 callback"""
        call_count = [0]

        def cb(op: str, ctx: dict) -> bool:
            call_count[0] += 1
            return True

        consent = JustInTimeConsent(
            hmac_key=HMAC_KEY, consent_callback=cb, default_ttl=0.0
        )
        await consent.request(operation=OP_CA_INSTALL)
        await consent.request(operation=OP_CA_INSTALL)
        await consent.request(operation=OP_CA_INSTALL)
        assert call_count[0] == 3

    async def test_is_approved_with_ttl(self) -> None:
        def cb(op: str, ctx: dict) -> bool:
            return True

        consent = JustInTimeConsent(
            hmac_key=HMAC_KEY, consent_callback=cb, default_ttl=3600.0
        )
        assert consent.is_approved(OP_CA_INSTALL) is False
        await consent.request(operation=OP_CA_INSTALL)
        assert consent.is_approved(OP_CA_INSTALL) is True

    async def test_is_approved_no_ttl_always_false(self) -> None:
        def cb(op: str, ctx: dict) -> bool:
            return True

        consent = JustInTimeConsent(
            hmac_key=HMAC_KEY, consent_callback=cb, default_ttl=0.0
        )
        await consent.request(operation=OP_CA_INSTALL)
        # 单次同意不缓存,is_approved 总返回 False
        assert consent.is_approved(OP_CA_INSTALL) is False

    async def test_expired_cache_cleared(self) -> None:
        """TTL 过期后清除缓存,重新询问"""
        call_count = [0]

        def cb(op: str, ctx: dict) -> bool:
            call_count[0] += 1
            return True

        consent = JustInTimeConsent(
            hmac_key=HMAC_KEY, consent_callback=cb
        )
        # 第一次: TTL=0.01 秒,授予
        d1 = await consent.request(operation=OP_CA_INSTALL, ttl=0.01)
        assert d1.outcome == ConsentOutcome.GRANTED

        # 等待过期
        await asyncio.sleep(0.05)

        # 第二次: 缓存过期,重新询问
        d2 = await consent.request(operation=OP_CA_INSTALL, ttl=0.01)
        assert d2.outcome == ConsentOutcome.GRANTED
        assert call_count[0] == 2  # callback 被调两次


class TestJustInTimeConsentRevoke:
    """revoke() 撤销测试"""

    async def test_revoke_granted_consent(self) -> None:
        def cb(op: str, ctx: dict) -> bool:
            return True

        consent = JustInTimeConsent(
            hmac_key=HMAC_KEY, consent_callback=cb, default_ttl=3600.0
        )
        await consent.request(operation=OP_CA_INSTALL)
        assert consent.is_approved(OP_CA_INSTALL) is True

        revoked = consent.revoke(operation=OP_CA_INSTALL)
        assert revoked is not None
        assert revoked.outcome == ConsentOutcome.REVOKED
        assert consent.is_approved(OP_CA_INSTALL) is False

    async def test_revoke_unknown_operation_returns_none(self) -> None:
        consent = JustInTimeConsent(hmac_key=HMAC_KEY)
        result = consent.revoke(operation=OP_CA_INSTALL)
        assert result is None

    async def test_revoked_consent_re_requested_calls_callback(self) -> None:
        """撤销后再次请求会重新调 callback"""
        call_count = [0]

        def cb(op: str, ctx: dict) -> bool:
            call_count[0] += 1
            return True

        consent = JustInTimeConsent(
            hmac_key=HMAC_KEY, consent_callback=cb, default_ttl=3600.0
        )
        await consent.request(operation=OP_CA_INSTALL)  # call 1
        consent.revoke(operation=OP_CA_INSTALL)
        await consent.request(operation=OP_CA_INSTALL)  # call 2
        assert call_count[0] == 2


class TestJustInTimeConsentAudit:
    """audit_callback 测试 — 1.3-A6"""

    async def test_audit_called_on_grant(self) -> None:
        audits: list[Any] = []

        def cb(op: str, ctx: dict) -> bool:
            return True

        def audit_cb(d: Any) -> None:
            audits.append(d)

        consent = JustInTimeConsent(
            hmac_key=HMAC_KEY, consent_callback=cb, audit_callback=audit_cb
        )
        await consent.request(operation=OP_CA_INSTALL)
        assert len(audits) == 1
        assert audits[0].outcome == ConsentOutcome.GRANTED
        assert audits[0].verify(HMAC_KEY) is True

    async def test_audit_called_on_deny(self) -> None:
        audits: list[Any] = []

        def cb(op: str, ctx: dict) -> bool:
            return False

        async def audit_cb(d: Any) -> None:
            audits.append(d)

        consent = JustInTimeConsent(
            hmac_key=HMAC_KEY, consent_callback=cb, audit_callback=audit_cb
        )
        await consent.request(operation=OP_CA_INSTALL)
        assert len(audits) == 1
        assert audits[0].outcome == ConsentOutcome.DENIED

    async def test_audit_called_on_no_callback(self) -> None:
        audits: list[Any] = []

        def audit_cb(d: Any) -> None:
            audits.append(d)

        consent = JustInTimeConsent(
            hmac_key=HMAC_KEY, audit_callback=audit_cb
        )
        await consent.request(operation=OP_CA_INSTALL)
        assert len(audits) == 1
        assert audits[0].outcome == ConsentOutcome.DENIED_NO_CALLBACK

    async def test_audit_called_on_error(self) -> None:
        audits: list[Any] = []

        def cb(op: str, ctx: dict) -> bool:
            raise RuntimeError("fail")

        def audit_cb(d: Any) -> None:
            audits.append(d)

        consent = JustInTimeConsent(
            hmac_key=HMAC_KEY, consent_callback=cb, audit_callback=audit_cb
        )
        await consent.request(operation=OP_CA_INSTALL)
        assert len(audits) == 1
        assert audits[0].outcome == ConsentOutcome.DENIED_ERROR

    async def test_audit_failure_does_not_block_decision(self) -> None:
        """audit_callback 抛异常不影响决策"""

        def cb(op: str, ctx: dict) -> bool:
            return True

        def audit_cb(d: Any) -> None:
            raise RuntimeError("audit log broken")

        consent = JustInTimeConsent(
            hmac_key=HMAC_KEY, consent_callback=cb, audit_callback=audit_cb
        )
        decision = await consent.request(operation=OP_CA_INSTALL)
        assert decision.outcome == ConsentOutcome.GRANTED


class TestJustInTimeConsentContext:
    """请求上下文传递测试"""

    async def test_context_passed_to_callback(self) -> None:
        received_ctx: dict = {}

        def cb(op: str, ctx: dict) -> bool:
            received_ctx.update(ctx)
            return True

        consent = JustInTimeConsent(hmac_key=HMAC_KEY, consent_callback=cb)
        await consent.request(
            operation=OP_PTRACE,
            subject="process_probe",
            context={"target_pid": 1234, "reason": "debug"},
        )
        assert received_ctx.get("target_pid") == 1234
        assert received_ctx.get("reason") == "debug"

    async def test_context_recorded_in_decision(self) -> None:
        def cb(op: str, ctx: dict) -> bool:
            return True

        consent = JustInTimeConsent(hmac_key=HMAC_KEY, consent_callback=cb)
        decision = await consent.request(
            operation=OP_LD_PRELOAD,
            subject="syscall_hook",
            context={"library": "libsentinel.so"},
        )
        assert decision.context.get("library") == "libsentinel.so"
        assert decision.subject == "syscall_hook"

    async def test_none_context_becomes_empty_dict(self) -> None:
        def cb(op: str, ctx: dict) -> bool:
            assert ctx == {}
            return True

        consent = JustInTimeConsent(hmac_key=HMAC_KEY, consent_callback=cb)
        decision = await consent.request(operation=OP_CA_INSTALL, context=None)
        assert decision.context == {}


class TestJustInTimeConsentClearCache:
    """clear_cache() 测试"""

    async def test_clear_cache(self) -> None:
        def cb(op: str, ctx: dict) -> bool:
            return True

        consent = JustInTimeConsent(
            hmac_key=HMAC_KEY, consent_callback=cb, default_ttl=3600.0
        )
        await consent.request(operation=OP_CA_INSTALL)
        assert consent.is_approved(OP_CA_INSTALL) is True
        consent.clear_cache()
        assert consent.is_approved(OP_CA_INSTALL) is False


class TestConsentOperationsRegistry:
    """CONSENT_OPERATIONS 常量测试"""

    def test_all_operations_are_strings(self) -> None:
        for op in CONSENT_OPERATIONS:
            assert isinstance(op, str)
            assert op.startswith("sentinel.")

    def test_operations_include_ca_install(self) -> None:
        """mitmproxy CA 安装必须注册"""
        assert "sentinel.mitmproxy.ca_install" in CONSENT_OPERATIONS

    def test_operations_include_ptrace(self) -> None:
        assert "sentinel.process.ptrace" in CONSENT_OPERATIONS

    def test_operations_include_ld_preload(self) -> None:
        assert "sentinel.process.ld_preload" in CONSENT_OPERATIONS

    def test_at_least_8_operations_registered(self) -> None:
        assert len(CONSENT_OPERATIONS) >= 8
